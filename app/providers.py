import asyncio
import logging
import os
import re
import shutil
import json
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from typing import Protocol
from uuid import uuid4
from .media import run

class ProviderError(ValueError):
    pass

class TransientError(ProviderError):
    pass

def redact(value, secrets=()):
    text=str(value)
    for secret in secrets:
        if secret:
            text=text.replace(secret,"[REDACTED]")
    text=re.sub(r"AIza[\w-]{20,}", "[REDACTED]", text)
    text=re.sub(r"(?i)(authorization[:=]\s*bearer\s+)\S+",r"\1[REDACTED]",text)
    text=re.sub(r"(?i)((?:api[_-]?key|token|password|cookie|otp)\s*[:=]\s*)[^\s&,;]+",r"\1[REDACTED]",text)
    return text

class SecretFilter(logging.Filter):
    def __init__(self,secrets=()):
        super().__init__()
        self.secrets=secrets
    def filter(self,record):
        record.msg=redact(record.getMessage(),self.secrets)
        record.args=()
        if record.exc_info:
            record.msg += " [exception details redacted]"
            record.exc_info=None
            record.exc_text=None
        return True

class VideoProvider(Protocol):
    async def generate_video(self,prompt: str,destination: Path) -> str: ...
    async def get_operation_status(self,operation_id: str) -> dict: ...
    async def download_video(self,operation_id: str,destination: Path) -> Path: ...

async def poll_operation(provider,operation_id,timeout,max_retries,initial_delay=.25,on_retry=None):
    loop=asyncio.get_running_loop()
    deadline=loop.time()+timeout
    delay=initial_delay
    retries=0
    while True:
        remaining=deadline-loop.time()
        if remaining<=0:
            raise TimeoutError("Operation timed out; do not resubmit an unknown remote outcome")
        try:
            result=await asyncio.wait_for(provider.get_operation_status(operation_id),remaining)
            if result.get("error"):
                raise ProviderError(str(result["error"]))
            if result.get("done"):
                return result
        except TransientError:
            if retries>=max_retries:
                raise
            retries+=1
            if on_retry:
                on_retry(retries)
        await asyncio.sleep(min(delay,max(0,deadline-loop.time())))
        delay=min(delay*2,15)

class MockVideoProvider:
    capabilities={"supports_reference_images":False,"supports_audio":True,"supports_extension":False}
    model="mock-color-bars"
    def __init__(self,root,ffmpeg="ffmpeg"):
        self.root=Path(root)
        self.ffmpeg=ffmpeg
        self.operations={}
    async def generate_video(self,prompt,destination):
        op="mock-"+uuid4().hex
        self.operations[op]=Path(destination)
        return op
    async def get_operation_status(self,operation_id):
        if operation_id not in self.operations:
            raise ProviderError("Unknown mock operation")
        return {"done":True}
    async def download_video(self,operation_id,destination):
        # Synthetic fixture, not a depiction of the product or a billable generation.
        await asyncio.to_thread(run,[self.ffmpeg,"-y","-f","lavfi","-i",
            "testsrc2=size=720x1280:rate=24","-t","8","-c:v","libx264",
            "-preset","ultrafast","-pix_fmt","yuv420p","-an",str(destination)])
        return Path(destination)

class GFlowProvider:
    capabilities={"supports_reference_images":True,"supports_audio":None,"supports_extension":False}
    model="veo-lite"
    def __init__(self,root,timeout=600):
        self.root=Path(root)
        self.timeout=timeout
        configured=os.getenv("GFLOW_EXECUTABLE")
        self.executable=(shutil.which(configured) if configured else None) or shutil.which("gflow")
        if not self.executable and os.name=="nt":
            candidate=Path.home()/".gflow-venv"/"Scripts"/"gflow.exe"
            if candidate.is_file():
                self.executable=str(candidate)
        self.outputs={}
    def readiness(self):
        try:
            installed=version("gflow-cli")
        except PackageNotFoundError:
            installed=None
        return {
            "provider":"gflow","installed_version":installed,
            "executable_found": bool(self.executable),
            "ready":bool(self.executable), "account_verified":False, "credits":None,
            "estimated_cost":None, "model":self.model if self.executable else None,
            "reason":"สร้างผ่าน gflow-cli · ตรวจสอบเครดิตใน Google Flow ก่อนสร้างคลิป" if self.executable else "ไม่พบ gflow CLI กรุณาติดตั้ง gflow-cli หรือกำหนด GFLOW_EXECUTABLE",
            "documentation":"https://github.com/ffroliva/gflow-cli"
        }
    async def generate_video(self,prompt,destination,reference_images=None,project_name=""):
        if not self.executable:
            raise ProviderError(self.readiness()["reason"])
        images=[Path(x).resolve() for x in (reference_images or [])]
        if not 1<=len(images)<=3 or any(not x.is_file() for x in images):
            raise ProviderError("เลือกภาพอ้างอิงสินค้า 1–3 ภาพก่อนสร้างคลิป")
        destination=Path(destination).resolve()
        if destination.exists():
            raise ProviderError("ไฟล์ปลายทางมีอยู่แล้ว; ป้องกันการใช้คลิปเก่าซ้ำ")
        mode="i2v" if len(images)==1 else "r2v"
        args=[self.executable,"video",mode]
        if mode=="i2v":
            args.extend(["--initial-frame",str(images[0]),prompt])
        else:
            args.append(prompt)
            for image in images:
                args.extend(["--ref",str(image)])
        # Veo Lite defaults to 8 seconds in Flow; omitting duration supports
        # migrated accounts whose composer exposes no duration selector.
        args.extend(["--model","veo-lite","--aspect","9:16",
                     "--count","1","--ui-mode","classic","--project-name",project_name[:120],
                     "--output",str(destination),"--json"])
        proc=None
        try:
            proc=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
            stdout,_=await asyncio.wait_for(proc.communicate(),self.timeout)
        except asyncio.TimeoutError as exc:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            raise TimeoutError("gflow timed out; check Flow before submitting again") from exc
        except OSError as exc:
            raise ProviderError("Could not start gflow video command") from exc
        try:
            result=json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError,ValueError) as exc:
            raise TimeoutError("gflow returned no readable result; check Flow before submitting again") from exc
        detail=result.get("error",{}).get("detail","")
        if (proc.returncode==11 or result.get("exit_code")==11
                or "renders no duration control" in detail):
            raise ProviderError(redact(detail) if detail else "gflow rejected the request before submission")
        if proc.returncode or result.get("status")!="ok":
            message=redact(detail) if detail else "gflow did not confirm a completed video"
            raise TimeoutError(f"{message}; check Flow before submitting again")
        if not destination.is_file() or destination.stat().st_size==0:
            raise ProviderError("gflow generation completed without a local video file")
        operation_id="gflow-"+uuid4().hex
        self.outputs[operation_id]=(destination,destination)
        return operation_id
    async def get_operation_status(self,operation_id):
        if operation_id not in self.outputs:
            raise ProviderError("Unknown gflow MCP operation")
        return {"done":True}
    async def download_video(self,operation_id,destination):
        if operation_id not in self.outputs:
            raise ProviderError("Unknown gflow MCP operation")
        source,_=self.outputs[operation_id]
        destination=Path(destination)
        if source.resolve()!=destination.resolve():
            shutil.copyfile(source,destination)
        return destination

