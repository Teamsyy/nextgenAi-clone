import asyncio
import json
import re
import zipfile
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, select, delete, text
from sqlalchemy.orm import Session
from .settings import Settings
from uuid import uuid4
from .models import Base, Project, ProductFact, Shot, GenerationJob, QCReport, ProjectInput, now
from .prompts import ROLES, NEGATIVE, SENSITIVE, classify, identity, prompt_for, check_sensitive_claims
from .providers import MockVideoProvider, GFlowProvider, poll_operation, redact
from . import media

BUSY={"generating","assembling","exporting"}

class Workflow:
    def __init__(self, settings=None):
        self.settings=settings or Settings()
        self.root=self.settings.output_root.resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.engine=create_engine(self.settings.database(),connect_args={"check_same_thread":False,"timeout":30})
        Base.metadata.create_all(self.engine)

    @contextmanager
    def transaction(self):
        with Session(self.engine,expire_on_commit=False) as s:
            s.execute(text("BEGIN IMMEDIATE"))
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    def _project(self,s,pid,editable=False):
        if not re.fullmatch(r"[a-f0-9]{32}",pid):
            raise ValueError("Unknown project")
        p=s.get(Project,pid)
        if not p:
            raise ValueError("Unknown project")
        if editable and p.status in BUSY:
            raise ValueError("Project is busy; wait for the current job")
        return p

    def directory(self,pid):
        if not re.fullmatch(r"[a-f0-9]{32}",pid):
            raise ValueError("Invalid project identifier")
        return self.root / pid

    def list(self):
        with Session(self.engine) as s:
            return list(s.scalars(select(Project).order_by(Project.created_at.desc())))

    def detail(self,pid):
        with Session(self.engine,expire_on_commit=False) as s:
            p=self._project(s,pid)
            return dict(project=p,
                facts=list(s.scalars(select(ProductFact).where(ProductFact.project_id==pid).order_by(ProductFact.id))),
                shots=list(s.scalars(select(Shot).where(Shot.project_id==pid).order_by(Shot.shot_number))),
                jobs=list(s.scalars(select(GenerationJob).where(GenerationJob.project_id==pid).order_by(GenerationJob.created_at.desc()))),
                qc=list(s.scalars(select(QCReport).where(QCReport.project_id==pid).order_by(QCReport.id.desc()))))

    def create(self,data):
        with self.transaction() as s:
            p=Project(**data.model_dump())
            s.add(p); s.flush()
            p.output_dir=str(self.directory(p.id))
            (self.directory(p.id)/"clips").mkdir(parents=True)
            (self.directory(p.id)/"references").mkdir()
            (self.directory(p.id)/"exports").mkdir()
            return p

    def _invalidate(self,s,p,facts=False):
        if facts:
            p.facts_approved=False
            for f in s.scalars(select(ProductFact).where(ProductFact.project_id==p.id)):
                f.approved=False
            for shot in s.scalars(select(Shot).where(Shot.project_id==p.id)):
                shot.prompt=""
                shot.negative_prompt=""
        p.assembled_current=False
        p.prompts_approved=False
        p.test_approved=False
        p.status="review"
        p.review_checklist="[]"
        p.updated_at=now()
        for shot in s.scalars(select(Shot).where(Shot.project_id==p.id)):
            shot.status="draft"
            shot.clip_path=""
            shot.operation_id=""
        s.execute(delete(QCReport).where(QCReport.project_id==p.id))

    def add_fact(self,pid,fact,source,status="unverified",notes="",fact_id=None):
        if not fact.strip() or len(fact)>2000 or len(source)>2000 or len(notes)>4000:
            raise ValueError("Fact, evidence or notes are empty/too long")
        status=classify(fact,source,status,notes)
        with self.transaction() as s:
            p=self._project(s,pid,True)
            f=s.get(ProductFact,fact_id) if fact_id else ProductFact(project_id=pid)
            if f is None or f.project_id!=pid:
                raise ValueError("Unknown fact")
            f.fact=fact; f.source=source; f.verification_status=status; f.notes=notes
            s.add(f)
            self._invalidate(s,p,True)
            s.flush()
            return f

    def generate_brief(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            for line in p.benefits.splitlines():
                line=line.strip()
                if line and not s.scalar(select(ProductFact.id).where(ProductFact.project_id==pid,ProductFact.fact==line)):
                    s.add(ProductFact(project_id=pid,fact=line,source=p.source_url,
                        verification_status=classify(line,p.source_url,"seller_claim",""),
                        notes="User supplied benefit; not independently verified."))
            p.brief=(f"Product: {p.product_name}\nAudience: {p.target_audience}\nLanguage: {p.language}\nTone: {p.tone}\n"
                     "7 shots x 8 seconds; portrait 9:16. Use only facts manually verified with evidence. "
                     "Unsupported claims must not appear. Thai narration/subtitles remain editable drafts.")
            self._invalidate(s,p,True)
            return p.brief

    def approve_facts(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            facts=list(s.scalars(select(ProductFact).where(ProductFact.project_id==pid)))
            allowed=[f for f in facts if f.verification_status=="verified" and f.source.strip() and f.notes.strip()]
            identity(allowed)
            if not allowed:
                raise ValueError("No verified facts")
            for f in facts:
                f.approved=f in allowed
            p.facts_approved=True
            p.status="facts_approved"

    def generate_prompts(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            if not p.facts_approved:
                raise ValueError("Approve facts first")
            facts=list(s.scalars(select(ProductFact).where(ProductFact.project_id==pid,ProductFact.approved==True)))
            identity(facts)
            if s.scalar(select(GenerationJob.id).where(GenerationJob.project_id==pid).limit(1)):
                # Keep audit rows; reuse shot IDs rather than deleting referenced records.
                shots=list(s.scalars(select(Shot).where(Shot.project_id==pid).order_by(Shot.shot_number)))
            else:
                s.execute(delete(Shot).where(Shot.project_id==pid))
                shots=[]
            for n,role in enumerate(ROLES,1):
                shot=shots[n-1] if shots else Shot(project_id=pid,shot_number=n,role=role)
                shot.prompt=prompt_for(p.product_name,facts,role,p.target_audience,p.tone)
                shot.negative_prompt=NEGATIVE
                s.add(shot)
            self._invalidate(s,p)
            return 7

    def edit_shot(self,pid,shot_id,prompt,negative):
        if not prompt.strip() or len(prompt)>12000 or len(negative)>3000:
            raise ValueError("Prompt empty or too long")
        with self.transaction() as s:
            p=self._project(s,pid,True)
            shot=s.get(Shot,shot_id)
            if shot is None or shot.project_id!=pid:
                raise ValueError("Unknown shot")
            facts=list(s.scalars(select(ProductFact).where(ProductFact.project_id==pid,ProductFact.approved==True)))
            check_sensitive_claims(prompt, facts, shot.role)
            shot.prompt=prompt
            shot.negative_prompt=negative
            self._invalidate(s,p)

    def approve_prompts(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            if not p.facts_approved:
                raise ValueError("Approve facts first")
            shots=list(s.scalars(select(Shot).where(Shot.project_id==pid).order_by(Shot.shot_number)))
            if len(shots)!=7 or any(not shot.prompt.strip() for shot in shots):
                raise ValueError("Generate all seven prompts first")
            facts=list(s.scalars(select(ProductFact).where(ProductFact.project_id==pid,ProductFact.approved==True)))
            for shot in shots:
                check_sensitive_claims(shot.prompt, facts, shot.role)
                if not shot.negative_prompt.startswith(NEGATIVE):
                    shot.negative_prompt=NEGATIVE+("; "+shot.negative_prompt if shot.negative_prompt else "")
                if shot.status=="draft":
                    shot.status="approved"
            p.prompts_approved=True
            if p.status in ("draft","review","facts_approved"):
                p.status="prompts_approved"

    def provider_info(self):
        if self.settings.video_provider=="gflow":
            return GFlowProvider(self.root).readiness()
        return dict(provider="mock",model="mock-color-bars",ready=True,credits=None,estimated_cost=0,
                    reason="Synthetic test clips. No AI depiction, no external API, no credits spent.")

    def approve_test(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            shot=s.scalar(select(Shot).where(Shot.project_id==pid,Shot.shot_number==1))
            if not p.prompts_approved or shot is None or shot.status!="complete" or not Path(shot.clip_path).is_file():
                raise ValueError("Generate and inspect the current test clip first")
            p.test_approved=True
            p.status="test_approved"

    def can_assemble(self,pid):
        d=self.detail(pid)
        return (d["project"].facts_approved and d["project"].prompts_approved and d["project"].test_approved
                and len(d["shots"])==7 and all(s.status=="complete" and Path(s.clip_path).is_file() for s in d["shots"]))

    async def generate(self,pid,batch=False):
        provider=MockVideoProvider(self.root,self.settings.ffmpeg) if self.settings.video_provider=="mock" else GFlowProvider(self.root)
        with self.transaction() as s:
            p=self._project(s,pid,True)
            if not p.facts_approved or not p.prompts_approved:
                raise ValueError("Approve facts and prompts first")
            if batch and not p.test_approved:
                raise ValueError("Approve the current test clip before batch generation")
            if self.settings.video_provider=="gflow":
                raise ValueError(provider.readiness()["reason"])
            shots=list(s.scalars(select(Shot).where(Shot.project_id==pid).order_by(Shot.shot_number)))
            selected=shots[1:] if batch else shots[:1]
            selected=[x for x in selected if x.status!="complete"]
            if any(x.status=="indeterminate" for x in selected):
                raise ValueError("An indeterminate submission requires reconciliation; automatic resubmission blocked")
            if not selected:
                raise ValueError("Selected clips already complete; edit prompts to invalidate and regenerate")
            p.status="generating"
            p.error_message=""
            shot_ids=[x.id for x in selected]
        current_job=None
        try:
            for sid in shot_ids:
                with self.transaction() as s:
                    shot=s.get(Shot,sid)
                    job=GenerationJob(project_id=pid,shot_id=sid,provider=self.settings.video_provider,
                        model=provider.model,status="submitting",estimated_cost=0)
                    s.add(job); s.flush()
                    current_job=job.id
                    shot.status="generating"
                    prompt=shot.prompt
                    path=self.directory(pid)/"clips"/f"clip-{shot.shot_number:02}-{shot.role.replace('_','-')}.mp4"
                op=await asyncio.wait_for(provider.generate_video(prompt,path),self.settings.operation_timeout)
                with self.transaction() as s:
                    s.get(GenerationJob,current_job).operation_id=op
                    s.get(GenerationJob,current_job).status="polling"
                    s.get(Shot,sid).operation_id=op
                def retry(count):
                    with self.transaction() as s:
                        s.get(GenerationJob,current_job).retry_count=count
                await poll_operation(provider,op,self.settings.operation_timeout,self.settings.max_retries,
                                     self.settings.poll_initial_delay,retry)
                await asyncio.wait_for(provider.download_video(op,path),self.settings.operation_timeout)
                info=media.probe(path,self.settings.ffprobe)
                if not any(x.get("codec_type")=="video" for x in info.get("streams",[])):
                    raise ValueError("Downloaded clip has no readable video")
                with self.transaction() as s:
                    shot=s.get(Shot,sid); shot.status="complete"; shot.clip_path=str(path)
                    shot.duration_seconds=float(info["format"]["duration"])
                    job=s.get(GenerationJob,current_job); job.status="complete"; job.completed_at=now(); job.actual_cost_if_available=0
            with self.transaction() as s:
                p=self._project(s,pid)
                p.status="clips_ready" if batch else "test_review"
        except BaseException as exc:
            message=redact(exc)
            with self.transaction() as s:
                p=self._project(s,pid); p.status="error"; p.error_message=message
                if current_job:
                    job=s.get(GenerationJob,current_job)
                    job.status="indeterminate" if isinstance(exc,(TimeoutError,asyncio.CancelledError)) else "failed"
                    job.error_message=message; job.completed_at=now()
                    shot=s.get(Shot,job.shot_id); shot.status=job.status; shot.error_message=message
            raise

    def assemble(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            shots=list(s.scalars(select(Shot).where(Shot.project_id==pid).order_by(Shot.shot_number)))
            if not (p.facts_approved and p.prompts_approved and p.test_approved
                    and len(shots)==7 and all(sh.status=="complete" and Path(sh.clip_path).is_file() for sh in shots)):
                raise ValueError("Seven current clips and test approval required")
            p.status="assembling"
            voice=p.voiceover_path; subtitle=p.subtitle_path
        try:
            clips=[Path(x.clip_path) for x in self.detail(pid)["shots"]]
            out=media.assemble(clips,self.directory(pid)/"exports"/"final-reel.mp4",
                               self.settings.ffmpeg,self.settings.ffprobe,voice or None,subtitle or None)
            with self.transaction() as s:
                p=self._project(s,pid)
                p.status="assembled"
                p.assembled_current=True
            return out
        except BaseException as exc:
            with self.transaction() as s:
                p=self._project(s,pid); p.status="error"; p.error_message=redact(exc)
            raise

    def qc(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            shots=list(s.scalars(select(Shot).where(Shot.project_id==pid).order_by(Shot.shot_number)))
            if not p.assembled_current or not (p.facts_approved and p.prompts_approved and p.test_approved
                    and len(shots)==7 and all(sh.status=="complete" and Path(sh.clip_path).is_file() for sh in shots)):
                raise ValueError("Assemble current approved clips before QC")
            voice_required=bool(p.voiceover_path)
        path=self.directory(pid)/"exports"/"final-reel.mp4"
        result=media.quality_check(path,self.settings.ffprobe,self.settings.ffmpeg,voice_required)
        (path.parent/"qc-report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        with self.transaction() as s:
            p=self._project(s,pid,True)
            s.add(QCReport(project_id=pid,**{k:result[k] for k in ("file_path","has_video","has_audio","width","height","duration","portrait","ffprobe_ok","visual_review_required")},notes=json.dumps(result["notes"])))
            p.status="qc_passed" if result["passed"] else "qc_failed"
        return result

    def save_checklist(self,pid,items):
        if not set(items)<=set(media.CHECKLIST):
            raise ValueError("Unknown review item")
        with self.transaction() as s:
            p=self._project(s,pid,True)
            p.review_checklist=json.dumps(items)
            if p.status=="exported":
                p.status="qc_passed"
        (self.directory(pid)/"exports"/"project-package.zip").unlink(missing_ok=True)

    def register_upload(self,pid,kind,path):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            if kind=="reference":
                self._invalidate(s,p)
            elif kind in {"voiceover","subtitle"}:
                setattr(p,kind+"_path",str(path))
                p.assembled_current=False
                p.status="clips_ready" if p.test_approved else "review"
                p.review_checklist="[]"
                s.execute(delete(QCReport).where(QCReport.project_id==pid))
            else:
                raise ValueError("Unsupported upload type")

    def export(self,pid):
        with self.transaction() as s:
            p=self._project(s,pid,True)
            shots=list(s.scalars(select(Shot).where(Shot.project_id==pid).order_by(Shot.shot_number)))
            if not p.assembled_current or not (p.facts_approved and p.prompts_approved and p.test_approved
                    and len(shots)==7 and all(sh.status=="complete" and Path(sh.clip_path).is_file() for sh in shots)):
                raise ValueError("Assemble current approved clips before export")
            prev_status=p.status
            p.status="exporting"
        try:
            path=self.directory(pid)/"exports"/"final-reel.mp4"
            d=self.detail(pid); p_info=d["project"]
            result=media.quality_check(path,self.settings.ffprobe,self.settings.ffmpeg,bool(p_info.voiceover_path))
            (path.parent/"qc-report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            with self.transaction() as s:
                s.add(QCReport(project_id=pid,**{k:result[k] for k in ("file_path","has_video","has_audio","width","height","duration","portrait","ffprobe_ok","visual_review_required")},notes=json.dumps(result["notes"])))
            if not result["passed"]:
                with self.transaction() as s:
                    self._project(s,pid).status="qc_failed"
                raise ValueError("Technical QC failed; see qc-report.json")
            out=self.directory(pid)/"exports"
            manifest=media.Manifest(project_id=pid,source_url=p_info.source_url,shots=[
                dict(shot_number=s.shot_number,role=s.role,prompt=s.prompt,
                     clip=Path(s.clip_path).name,duration_seconds=s.duration_seconds) for s in d["shots"]])
            (out/"manifest.json").write_text(manifest.model_dump_json(indent=2),encoding="utf-8")
            (out/"facts.json").write_text(json.dumps([dict(fact=f.fact,source=f.source,status=f.verification_status,notes=f.notes,approved=f.approved) for f in d["facts"]],ensure_ascii=False,indent=2),encoding="utf-8")
            (out/"prompts.txt").write_text("\n\n".join(f"{s.shot_number}. {s.role}\n{s.prompt}\nNegative: {s.negative_prompt}" for s in d["shots"]),encoding="utf-8")
            (out/"caption-th.txt").write_text(f"{p_info.product_name}\nดูรายละเอียดสินค้าจากแหล่งข้อมูล: {p_info.source_url}\nเนื้อหาสร้างด้วย AI โปรดตรวจสอบก่อนเผยแพร่\n",encoding="utf-8")
            (out/"narration-th.txt").write_text(f"นี่คือ {p_info.product_name}\n[เติมบทพูดภาษาไทยจากข้อเท็จจริงที่อนุมัติแล้ว และตรวจความถูกต้องก่อนบันทึกเสียง]\n",encoding="utf-8")
            (out/"review.json").write_text(json.dumps(dict(checked=json.loads(p_info.review_checklist),
                remaining=[x for x in media.CHECKLIST if x not in json.loads(p_info.review_checklist)],
                publication_approved=False,warning="Manual review required. Technical QC does not verify product identity or claims."),indent=2),encoding="utf-8")
            package=out/"project-package.zip"
            tmp_package=out/f"project-package.{uuid4().hex}.tmp"
            with zipfile.ZipFile(tmp_package,"w",zipfile.ZIP_DEFLATED) as z:
                for name in ("final-reel.mp4","qc-report.json","manifest.json","facts.json","prompts.txt","caption-th.txt","narration-th.txt","review.json"):
                    z.write(out/name,name)
                for shot in d["shots"]:
                    z.write(shot.clip_path,"clips/"+Path(shot.clip_path).name)
                if p_info.subtitle_path:
                    sub_text = Path(p_info.subtitle_path).read_text(encoding="utf-8").replace("\r\n", "\n")
                    z.writestr("subtitles.srt", sub_text.encode("utf-8"))
            tmp_package.replace(package)
            with self.transaction() as s:
                self._project(s,pid).status="exported"
            return package
        except BaseException as exc:
            with self.transaction() as s:
                proj=s.get(Project,pid)
                if proj and proj.status=="exporting":
                    proj.status=prev_status if not isinstance(exc, ValueError) or "QC failed" not in str(exc) else "qc_failed"
            raise

