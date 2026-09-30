import asyncio
import logging
import os
import re
import shutil
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
    capabilities={"supports_reference_images":None,"supports_audio":None,"supports_extension":None}
    model="unverified"
    def __init__(self,root):
        self.root=Path(root)
    def readiness(self):
        try:
            installed=version("gflow-cli")
        except PackageNotFoundError:
            installed=None
        return {
            "provider":"gflow","installed_version":installed,
            "executable_found": bool(shutil.which("gflow")),
            "ready":False, "account_verified":False, "credits":None,
            "estimated_cost":None, "model":None,
            "reason":"Live generation blocked: audited non-bypass browser path and live account, Pro/Ultra subscription, model and credit-cost verification are not implemented. Upstream credit lookup reports limitations for flow.google.com.",
            "documentation":"https://github.com/ffroliva/gflow-cli/blob/develop/KNOWN_ISSUES.md"
        }
    async def generate_video(self,prompt,destination):
        raise ProviderError(self.readiness()["reason"])
    async def get_operation_status(self,operation_id):
        raise ProviderError(self.readiness()["reason"])
    async def download_video(self,operation_id,destination):
        raise ProviderError(self.readiness()["reason"])

