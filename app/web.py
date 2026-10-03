import asyncio
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import ValidationError
from PIL import Image
from .settings import Settings, ROOT
from .models import ProjectInput
from .workflow import Workflow, BUSY
from .providers import redact
from .media import CHECKLIST, probe
from . import media
from .prompts import identity

STATUS_LABELS={
    "draft":"ฉบับร่าง", "review":"รอตรวจข้อมูล", "facts_approved":"อนุมัติข้อมูลแล้ว",
    "prompts_approved":"อนุมัติ prompt แล้ว", "generating":"กำลังสร้างคลิป",
    "test_review":"รอตรวจคลิป", "test_approved":"อนุมัติคลิปแล้ว",
    "clips_ready":"คลิปพร้อม", "assembling":"กำลังประกอบวิดีโอ", "assembled":"ประกอบวิดีโอแล้ว",
    "qc_passed":"ตรวจไฟล์ผ่าน", "qc_failed":"ตรวจไฟล์ไม่ผ่าน", "exporting":"กำลังสร้างชุดงาน",
    "exported":"พร้อมดาวน์โหลด", "error":"ต้องตรวจสอบ"
}
NEXT_ACTIONS={
    "draft":"ตรวจข้อมูลสินค้า", "review":"ตรวจหลักฐานสินค้า", "facts_approved":"สร้าง prompt",
    "prompts_approved":"สร้างคลิป", "generating":"กำลังสร้างคลิป", "test_review":"ตรวจและอนุมัติคลิป",
    "test_approved":"ประกอบวิดีโอ", "clips_ready":"ประกอบวิดีโอ", "assembling":"กำลังประกอบวิดีโอ",
    "assembled":"ตรวจคุณภาพวิดีโอ", "qc_passed":"ตรวจรายการแล้วดาวน์โหลด", "qc_failed":"ตรวจรายงาน QC",
    "exporting":"กำลังสร้างชุดงาน", "exported":"พร้อมดาวน์โหลด", "error":"ตรวจข้อความแจ้งปัญหา"
}

def project_ui_state(detail, provider, can_assemble):
    project=detail["project"]
    shots=detail["shots"]
    busy=project.status in BUSY
    first_complete=bool(shots and shots[0].status=="complete")
    if not project.facts_approved:
        step=1
        next_action="อนุมัติข้อมูลที่มีหลักฐาน"
    elif not project.prompts_approved:
        step=2
        next_action="สร้าง prompt จากข้อมูลที่อนุมัติ"
    elif first_complete and not project.test_approved:
        step=3
        next_action="ตรวจและอนุมัติคลิป UGC"
    elif not project.test_approved or not first_complete:
        step=3
        next_action="สร้างและตรวจคลิป UGC"
    elif not project.assembled_current:
        step=4
        next_action="ประกอบ ตรวจ QC และดาวน์โหลด"
    else:
        step=4
        next_action="ตรวจ QC และดาวน์โหลด"
    legacy_project=len(shots)>1
    if legacy_project:
        next_action="ดูหรือดาวน์โหลดงานเดิม หรือสร้างโปรเจกต์ใหม่"

    blockers={}
    eligible_facts=[f for f in detail["facts"] if f.verification_status=="verified" and f.source.strip() and f.notes.strip()]
    try:
        identity(eligible_facts)
        can_approve_facts=True
    except ValueError:
        can_approve_facts=False
    can_approve_prompts=bool(shots and all(s.prompt.strip() for s in shots))
    if busy:
        blockers={key:"โปรเจกต์กำลังประมวลผล รอให้งานปัจจุบันเสร็จก่อน" for key in
                  ("approve-facts","prompts","approve-prompts","generate-test","approve-test","assemble","qc","export")}
    else:
        if project.facts_approved:
            blockers["approve-facts"]="ข้อมูลสินค้านี้อนุมัติแล้ว"
        elif not can_approve_facts:
            blockers["approve-facts"]="ตรวจหลักฐานสี รูปร่าง ขนาด และอุปกรณ์ให้ครบก่อนอนุมัติ"
        if project.prompts_approved:
            blockers["prompts"]="prompt อนุมัติแล้ว หากต้องการเปลี่ยนให้แก้ prompt ในขั้นที่ 2"
        elif not project.facts_approved:
            blockers["prompts"]="อนุมัติข้อเท็จจริงที่มีหลักฐานก่อน"
        if project.prompts_approved:
            blockers["approve-prompts"]="prompt ชุดปัจจุบันอนุมัติแล้ว"
        elif not shots or not can_approve_prompts:
            blockers["approve-prompts"]="สร้าง creative prompt ก่อน"
        if not project.prompts_approved:
            blockers["generate-test"]="อนุมัติ creative prompt ก่อน"
        if not provider.get("ready"):
            blockers["generate-test"]=provider.get("reason") or "ผู้ให้บริการยังไม่พร้อม"
        elif first_complete and not project.test_approved:
            blockers["generate-test"]="คลิปสร้างแล้ว โปรดตรวจคลิปและกดอนุมัติ"
        elif first_complete and project.test_approved:
            blockers["generate-test"]="คลิปปัจจุบันอนุมัติแล้ว; แก้ prompt หากต้องการสร้างคลิปใหม่"
        if project.test_approved:
            blockers["approve-test"]="คลิปนี้อนุมัติแล้ว"
        elif not first_complete:
            blockers["approve-test"]="สร้างคลิปให้เสร็จและตรวจดูก่อน"
        if project.assembled_current:
            blockers["assemble"]="วิดีโอปัจจุบันประกอบแล้ว; แก้ไฟล์ต้นทางก่อนประกอบใหม่"
        elif not can_assemble:
            blockers["assemble"]="อนุมัติคลิปและสร้างคลิปปัจจุบันให้ครบก่อน"
        if not project.assembled_current:
            blockers["qc"]="ประกอบวิดีโอปัจจุบันก่อนตรวจคุณภาพ"
            blockers["export"]="ประกอบวิดีโอปัจจุบันก่อนดาวน์โหลด"
    return dict(current_step=step,next_action=next_action,action_blockers=blockers,
                shot_count=len(shots),completed_count=sum(s.status=="complete" for s in shots),
                can_approve_facts=can_approve_facts,can_approve_prompts=can_approve_prompts,
                status_label=STATUS_LABELS.get(project.status,"สถานะโปรเจกต์"))

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

    def render(request,name,context,status=200,rotate_csrf=False):
        token=secrets.token_urlsafe(32) if rotate_csrf else (request.cookies.get("csrf") or secrets.token_urlsafe(32))
        context.setdefault("form_values",{})
        context.setdefault("form_errors",{})
        context.setdefault("form_error","")
        context.setdefault("inline_error","")
        context.update(csrf=token,provider=wf.provider_info(),checklist=CHECKLIST,
                       max_upload_mb=settings.max_upload_mb)
        response=templates.TemplateResponse(request=request,name=name,context=context,status_code=status)
        response.set_cookie("csrf",token,httponly=True,samesite="strict")
        return response

    async def form(request):
        f=await request.form(max_files=7,max_fields=80,max_part_size=20000)
        allowed=ProjectInput.model_fields if request.url.path=="/projects" else {
            "fact", "source", "verification_status", "notes", "prompt", "negative_prompt", "fact_id"}
        request.state.form_values={k:f.get(k,"") for k in allowed if isinstance(f.get(k,""),str)}
        expected=request.cookies.get("csrf","")
        if not expected or not secrets.compare_digest(expected,str(f.get("csrf",""))):
            raise PermissionError("CSRF check failed; reload page")
        return f

    def project_context(pid):
        data=wf.detail(pid)
        provider=wf.provider_info()
        can_assemble=wf.can_assemble(pid)
        preview=data["project"].status=="test_review" and data["project"].prompts_approved and len(data["shots"])==1 and data["shots"][0].status=="complete" and (wf.directory(pid)/"exports"/"assembly-preview.mp4").is_file()
        can_preview=data["project"].status=="test_review" and data["project"].prompts_approved and len(data["shots"])==1 and data["shots"][0].status=="complete"
        data.update(pid=pid,reviewed=json.loads(data["project"].review_checklist),
                    refs=sorted(x.name for x in (wf.directory(pid)/"references").glob("*") if x.is_file() and x.suffix.lower() in {".jpg",".jpeg",".png",".webp"}),
                    default_ref="clean_initial_frame_916.png" if "clean_initial_frame_916.png" in [x.name for x in (wf.directory(pid)/"references").glob("*")] else "",
                    ready=can_assemble,busy=data["project"].status in BUSY,
                    assembly_preview_ready=preview,can_preview_assembly=can_preview,
                    legacy_project=len(data["shots"])>1,
                    ui=project_ui_state(data,provider,can_assemble),
                    status_labels=STATUS_LABELS)
        return data

    def dashboard_context(q="",status=""):
        all_projects=wf.list()
        q=q.strip()[:120]
        status=status if status in STATUS_LABELS else ""
        if q:
            needle=q.casefold()
            all_projects=[p for p in all_projects if needle in p.name.casefold() or needle in p.product_name.casefold()]
        if status in STATUS_LABELS:
            all_projects=[p for p in all_projects if p.status==status]
        bangkok=timezone(timedelta(hours=7))
        cards=[]
        for p in all_projects:
            directory=wf.directory(p.id)
            poster=directory/"exports"/"thumbnail.jpg"
            references=directory/"references"
            fallback=next(iter(sorted(x for x in references.iterdir() if x.suffix.lower() in {".jpg",".jpeg",".png",".webp"})),None)
            thumbnail=(f"/projects/{p.id}/files/exports/thumbnail.jpg" if p.assembled_current and poster.is_file()
                       else f"/projects/{p.id}/files/references/{fallback.name}" if fallback else None)
            cards.append({"project":p,"updated":p.updated_at.astimezone(bangkok).strftime("%d/%m/%Y %H:%M"),
                          "next":NEXT_ACTIONS.get(p.status,"ตรวจสถานะโปรเจกต์"),"thumbnail":thumbnail})
        return dict(projects=cards,project_count=len(cards),status_labels=STATUS_LABELS,
                    next_actions=NEXT_ACTIONS,query=q,selected_status=status)

    @app.exception_handler(ValueError)
    async def value_error(request,exc):
        path=request.url.path.split("/")
        if len(path)>2 and path[1]=="projects":
            try:
                data=project_context(path[2])
                data.update(inline_error=redact(exc),form_values=getattr(request.state,"form_values",{}))
                return render(request,"project.html",data,400)
            except ValueError:
                pass
        return render(request,"error.html",dict(error=redact(exc)),400)

    @app.exception_handler(PermissionError)
    async def permission_error(request,exc):
        path=request.url.path
        values=getattr(request.state,"form_values",{})
        message="เซสชันหมดอายุ กรุณาตรวจข้อมูลแล้วส่งอีกครั้ง"
        if path=="/projects":
            context=dashboard_context()
            context.update(form_values=values,form_errors={},form_error=message)
            return render(request,"index.html",context,403,rotate_csrf=True)
        match=re.fullmatch(r"/projects/([a-f0-9]{32})/[^/]+",path)
        if match:
            try:
                data=project_context(match.group(1))
                data.update(inline_error=message,form_values=values)
                return render(request,"project.html",data,403,rotate_csrf=True)
            except ValueError:
                pass
        back=path if re.fullmatch(r"/projects/[a-f0-9]{32}",path) else "/"
        return render(request,"error.html",dict(error="เซสชันหมดอายุ กรุณาโหลดหน้านี้ใหม่แล้วลองอีกครั้ง",back_url=back),403,rotate_csrf=True)

    @app.get("/")
    def dashboard(request:Request,q:str="",status:str=""):
        context=dashboard_context(q,status)
        context.update(form_values={},form_errors={},form_error="")
        return render(request,"index.html",context)

    @app.post("/projects")
    async def create(request:Request):
        f=await form(request)
        request.state.form_values={k:str(f.get(k,"")) for k in ProjectInput.model_fields}
        fields={k:str(f.get(k,"")) for k in ProjectInput.model_fields}
        try:
            data=ProjectInput(**fields)
        except ValidationError as exc:
            errors={str(e["loc"][0]):e["msg"] for e in exc.errors() if e.get("loc")}
            context=dashboard_context()
            context.update(form_values=request.state.form_values,form_errors=errors,
                           form_error="ตรวจช่องที่มีข้อความแจ้งเตือน แล้วลองอีกครั้ง")
            return render(request,"index.html",context,422)
        p=await run_in_threadpool(wf.create,data)
        return RedirectResponse(f"/projects/{p.id}",303)

    @app.get("/projects/{pid}")
    def project(request:Request,pid:str):
        return render(request,"project.html",project_context(pid))

    @app.get("/projects/{pid}/status")
    def project_status(pid:str):
        data=wf.detail(pid)
        shots=data["shots"]
        jobs=data["jobs"]
        return {"project_status":data["project"].status,
                "busy":data["project"].status in BUSY,
                "completed_count":sum(s.status=="complete" for s in shots),
                "shot_count":len(shots),
                "jobs":[{"id":j.id[:8],"status":j.status,"retry_count":j.retry_count} for j in jobs[:8]]}

    async def generate_background(pid,reference_images=None):
        try:
            await wf.generate(pid,reference_images)
        except Exception:
            # Workflow persists a redacted error. Preflight errors are returned before scheduling.
            pass

    @app.post("/projects/{pid}/{action}")
    async def action(request:Request,pid:str,action:str):
        f=await form(request)
        request.state.form_values={k:str(f.get(k,"")) for k in ("fact","source","verification_status","notes","prompt","negative_prompt","fact_id") if f.get(k) is not None}
        d=wf.detail(pid)
        if d["project"].status in BUSY:
            raise ValueError("Project busy")
        if len(d["shots"])>1:
            raise ValueError("โปรเจกต์นี้ใช้รูปแบบ 7 ช็อตรุ่นเดิมและเปิดดู/ดาวน์โหลดได้เท่านั้น กรุณาสร้างโปรเจกต์ใหม่เพื่อทำงานต่อ")
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
        elif action=="preview-assembly":
            p=d["project"]
            shots=d["shots"]
            if not p.prompts_approved or len(shots)!=1 or shots[0].status!="complete" or not Path(shots[0].clip_path).is_file():
                raise ValueError("สร้างตัวอย่างได้หลังมีคลิปเสร็จและอนุมัติ prompt แล้ว")
            output=wf.directory(pid)/"exports"/"assembly-preview.mp4"
            font=wf.directory(pid)/"references"/"Mali-SemiBold.ttf"
            await run_in_threadpool(media.assemble,[Path(shots[0].clip_path)],output,settings.ffmpeg,settings.ffprobe,
                p.voiceover_path or None,p.subtitle_path or None,media.short_product_title(p.product_name),font if font.is_file() else None)
        elif action=="generate-test":
            p=d["project"]
            if not p.facts_approved or not p.prompts_approved:
                raise ValueError("Approve facts and prompts first")
            info=wf.provider_info()
            if not info["ready"]:
                raise ValueError(info["reason"])
            reference_images=list(dict.fromkeys(str(x) for x in f.getlist("reference_images") if x))
            if settings.video_provider=="gflow":
                refs=wf.directory(pid)/"references"
                if not 1<=len(reference_images)<=3 or any(Path(name).name!=name or Path(name).suffix.lower() not in {".jpg",".jpeg",".png",".webp"} or not (refs/name).is_file() for name in reference_images):
                    raise ValueError("เลือกรูปอ้างอิงที่อัปโหลดไว้ 1–3 รูปสำหรับ Veo Lite โดยระบบจะแสดงภาพให้ตรวจก่อนเลือก")
            task=asyncio.create_task(generate_background(pid,reference_images or None))
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
            uploads=f.getlist("file")
            kind=str(f.get("kind",""))
            if not uploads or any(not hasattr(upload,"read") for upload in uploads) or kind not in {"reference","voiceover","subtitle"}:
                raise ValueError("Choose an image, audio or SRT file")
            if len(uploads)>7 or (kind!="reference" and len(uploads)>1):
                raise ValueError("อัปโหลดรูปได้ครั้งละไม่เกิน 7 รูป; ไฟล์เสียงและซับให้อัปโหลดทีละไฟล์")
            allowed={"reference":{".jpg",".jpeg",".png",".webp"},"voiceover":{".wav",".mp3",".m4a"},"subtitle":{".srt"}}
            saved=[]
            try:
                for upload in uploads:
                    data=await upload.read(settings.max_upload_mb*1024*1024+1)
                    await upload.close()
                    if not data or len(data)>settings.max_upload_mb*1024*1024:
                        raise ValueError("File empty or too large")
                    ext=Path(upload.filename or "").suffix.lower()
                    if ext not in allowed[kind]:
                        raise ValueError("Unsupported file extension")
                    path=wf.directory(pid)/("references" if kind=="reference" else "inputs")/(uuid4().hex+ext)
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(data)
                    saved.append(path)
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
                        saved[-1]=path
                    elif kind=="voiceover":
                        meta=await run_in_threadpool(probe,path,settings.ffprobe)
                        if not any(s.get("codec_type")=="audio" for s in meta.get("streams",[])):
                            raise ValueError("No audio stream found")
                    else:
                        content=data.decode("utf-8-sig")
                        if len(data)>1_000_000 or "-->" not in content:
                            raise ValueError("Use a UTF-8 SRT subtitle file")
                for path in saved:
                    await run_in_threadpool(wf.register_upload,pid,kind,path)
            except Exception:
                for path in saved:
                    path.unlink(missing_ok=True)
                raise ValueError("Invalid media or project is busy") from None
        else:
            raise ValueError("Unknown action")
        anchors={"brief":"facts","fact":"add-fact","approve-facts":"facts",
                 "prompts":"shots","shot":"shots","approve-prompts":"shots",
                 "approve-test":"generate","generate-test":"generate","preview-assembly":"export","assemble":"export",
                 "qc":"export","export":"export","review":"review-checklist","upload":"references"}
        anchor=anchors[action]
        if action=="fact" and f.get("fact_id"):
            fact_id=str(f.get("fact_id"))
            if any(str(item.id)==fact_id for item in d["facts"]):
                anchor=f"fact-{fact_id}"
        return RedirectResponse(f"/projects/{pid}#{anchor}",303)

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
            draft_preview=(name=="assembly-preview.mp4" and d["project"].status=="test_review"
                           and d["project"].prompts_approved and len(d["shots"])==1
                           and d["shots"][0].status=="complete")
            if not draft_preview and (not d["project"].assembled_current or name not in {"final-reel.mp4","thumbnail.jpg","qc-report.json","project-package.zip"}):
                raise ValueError("Export not current")
            if name=="project-package.zip" and d["project"].status!="exported":
                raise ValueError("Re-export package after changes")
        return FileResponse(path,filename=None if path.suffix in {".mp4",".jpg"} else name)

    return app


