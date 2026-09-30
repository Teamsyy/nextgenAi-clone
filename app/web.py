import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool
from PIL import Image
from .settings import Settings, ROOT
from .models import ProjectInput
from .workflow import Workflow, BUSY
from .providers import redact
from .media import CHECKLIST, probe

def create_app(settings=None):
    settings=settings or Settings()
    wf=Workflow(settings)
    tasks=set()

    @asynccontextmanager
    async def lifespan(app):
        yield
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks,return_exceptions=True)
        wf.engine.dispose()

    app=FastAPI(title="nextgen-local",lifespan=lifespan,docs_url=None,redoc_url=None)
    app.state.workflow=wf
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["localhost","127.0.0.1","[::1]"])
    app.mount("/static",StaticFiles(directory=ROOT/"app"/"static"),name="static")
    templates=Jinja2Templates(directory=ROOT/"app"/"templates")

    @app.middleware("http")
    async def local_guard(request,call_next):
        if request.method=="POST":
            origin=request.headers.get("origin")
            referer=request.headers.get("referer")
            host=request.headers.get("host","").split(":")[0].lower()
            loopback={"localhost","127.0.0.1","::1","testserver"}
            if origin and origin!="null":
                from urllib.parse import urlsplit
                u=urlsplit(origin)
                orig_host=(u.hostname or "").lower()
                if orig_host not in loopback and orig_host!=host:
                    return HTMLResponse("Origin rejected",status_code=403)
            elif origin=="null" and referer:
                from urllib.parse import urlsplit
                ref_u=urlsplit(referer)
                ref_host=(ref_u.hostname or "").lower()
                if ref_host not in loopback and ref_host!=host:
                    return HTMLResponse("Origin rejected",status_code=403)
            try:
                size=int(request.headers.get("content-length","-1"))
            except ValueError:
                size=-1
            if size<0:
                return HTMLResponse("Content-Length required",status_code=411)
            if size>settings.max_upload_mb*1024*1024+10000:
                return HTMLResponse("Upload too large",status_code=413)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Content-Security-Policy"]="default-src 'self'; img-src 'self'; media-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Cache-Control"]="no-store"
        return response

    def render(request,name,context,status=200):
        token=request.cookies.get("csrf") or secrets.token_urlsafe(32)
        context.update(csrf=token,provider=wf.provider_info(),checklist=CHECKLIST)
        response=templates.TemplateResponse(request=request,name=name,context=context,status_code=status)
        response.set_cookie("csrf",token,httponly=True,samesite="strict")
        return response

    async def form(request):
        f=await request.form(max_files=1,max_fields=80,max_part_size=20000)
        expected=request.cookies.get("csrf","")
        if not expected or not secrets.compare_digest(expected,str(f.get("csrf",""))):
            raise PermissionError("CSRF check failed; reload page")
        return f

    @app.exception_handler(PermissionError)
    async def permission_error(request,exc):
        return HTMLResponse("CSRF check failed; reload page",status_code=403)

    @app.exception_handler(ValueError)
    async def value_error(request,exc):
        # Render through autoescaping, never embed raw exception HTML.
        return render(request,"error.html",dict(error=redact(exc)),400)

    @app.get("/")
    def dashboard(request:Request):
        return render(request,"index.html",dict(projects=wf.list()))

    @app.post("/projects")
    async def create(request:Request):
        f=await form(request)
        fields={k:str(f.get(k,"")) for k in ProjectInput.model_fields}
        p=await run_in_threadpool(wf.create,ProjectInput(**fields))
        return RedirectResponse(f"/projects/{p.id}",303)

    @app.get("/projects/{pid}")
    def project(request:Request,pid:str):
        data=wf.detail(pid)
        data.update(pid=pid,reviewed=json.loads(data["project"].review_checklist),
                    refs=sorted(x.name for x in (wf.directory(pid)/"references").glob("*") if x.is_file()),
                    ready=wf.can_assemble(pid),busy=data["project"].status in BUSY)
        return render(request,"project.html",data)

    async def generate_background(pid,batch):
        try:
            await wf.generate(pid,batch)
        except Exception:
            # Workflow persists a redacted error. Preflight errors are returned before scheduling.
            pass

    @app.post("/projects/{pid}/{action}")
    async def action(request:Request,pid:str,action:str):
        f=await form(request)
        d=wf.detail(pid)
        if d["project"].status in BUSY:
            raise ValueError("Project busy")
        if action=="brief":
            await run_in_threadpool(wf.generate_brief,pid)
        elif action=="fact":
            await run_in_threadpool(wf.add_fact,pid,str(f.get("fact","")),str(f.get("source","")),
                str(f.get("verification_status","unverified")),str(f.get("notes","")),
                int(f["fact_id"]) if f.get("fact_id") else None)
        elif action=="approve-facts":
            await run_in_threadpool(wf.approve_facts,pid)
        elif action=="prompts":
            await run_in_threadpool(wf.generate_prompts,pid)
        elif action=="shot":
            await run_in_threadpool(wf.edit_shot,pid,int(f["shot_id"]),str(f.get("prompt","")),str(f.get("negative_prompt","")))
        elif action=="approve-prompts":
            await run_in_threadpool(wf.approve_prompts,pid)
        elif action=="approve-test":
            await run_in_threadpool(wf.approve_test,pid)
        elif action in ("generate-test","generate-batch"):
            p=d["project"]
            if not p.facts_approved or not p.prompts_approved:
                raise ValueError("Approve facts and prompts first")
            if action=="generate-batch" and not p.test_approved:
                raise ValueError("Approve the test clip first")
            info=wf.provider_info()
            if not info["ready"]:
                raise ValueError(info["reason"])
            task=asyncio.create_task(generate_background(pid,action=="generate-batch"))
            tasks.add(task); task.add_done_callback(tasks.discard)
            await asyncio.sleep(0)  # Let the job acquire its persisted project lock before redirect.
        elif action=="assemble":
            await run_in_threadpool(wf.assemble,pid)
        elif action=="qc":
            await run_in_threadpool(wf.qc,pid)
        elif action=="export":
            await run_in_threadpool(wf.export,pid)
        elif action=="review":
            await run_in_threadpool(wf.save_checklist,pid,f.getlist("items"))
        elif action=="upload":
            upload=f.get("file")
            kind=str(f.get("kind",""))
            if not upload or not hasattr(upload,"read") or kind not in {"reference","voiceover","subtitle"}:
                raise ValueError("Choose an image, audio or SRT file")
            data=await upload.read(settings.max_upload_mb*1024*1024+1)
            await upload.close()
            if not data or len(data)>settings.max_upload_mb*1024*1024:
                raise ValueError("File empty or too large")
            ext=Path(upload.filename or "").suffix.lower()
            allowed={"reference":{".jpg",".jpeg",".png",".webp"},"voiceover":{".wav",".mp3",".m4a"},"subtitle":{".srt"}}
            if ext not in allowed[kind]:
                raise ValueError("Unsupported file extension")
            path=wf.directory(pid)/("references" if kind=="reference" else "inputs")/(uuid4().hex+ext)
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            try:
                if kind=="reference":
                    with Image.open(path) as im:
                        if im.width*im.height>24_000_000:
                            raise ValueError("Image exceeds 24 megapixels")
                        im.verify()
                    with Image.open(path) as im:
                        clean=im.convert("RGB")
                    path.unlink()
                    path=path.with_suffix(".jpg")
                    clean.save(path,"JPEG")
                elif kind=="voiceover":
                    meta=await run_in_threadpool(probe,path,settings.ffprobe)
                    if not any(s.get("codec_type")=="audio" for s in meta.get("streams",[])):
                        raise ValueError("No audio stream found")
                else:
                    content=data.decode("utf-8-sig")
                    if len(data)>1_000_000 or "-->" not in content:
                        raise ValueError("Use a UTF-8 SRT subtitle file")
                await run_in_threadpool(wf.register_upload,pid,kind,path)
            except Exception:
                path.unlink(missing_ok=True)
                raise ValueError("Invalid media or project is busy") from None
        else:
            raise ValueError("Unknown action")
        return RedirectResponse(f"/projects/{pid}",303)

    @app.get("/projects/{pid}/files/{category}/{name}")
    def file(pid:str,category:str,name:str):
        d=wf.detail(pid)
        if category not in {"clips","exports","references"} or Path(name).name!=name:
            raise ValueError("Unknown file")
        path=wf.directory(pid)/category/name
        if not path.resolve().is_relative_to(wf.directory(pid).resolve()) or not path.is_file():
            raise ValueError("Unknown file")
        if category=="clips" and str(path) not in [s.clip_path for s in d["shots"] if s.status=="complete"]:
            raise ValueError("Clip no longer current")
        if category=="exports":
            if not d["project"].assembled_current or name not in {"final-reel.mp4","qc-report.json","project-package.zip"}:
                raise ValueError("Export not current")
            if name=="project-package.zip" and d["project"].status!="exported":
                raise ValueError("Re-export package after changes")
        return FileResponse(path,filename=None if path.suffix in {".mp4",".jpg"} else name)

    return app


