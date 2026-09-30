import argparse
import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path
from .settings import Settings
from .models import ProjectInput
from .workflow import Workflow
from .providers import GFlowProvider, redact, SecretFilter
from .media import probe, run

def parser():
    p=argparse.ArgumentParser(prog="python -m app",description="nextgen-local: reviewed local video production, no automatic posting")
    sub=p.add_subparsers(dest="command",required=True)
    create=sub.add_parser("create-project",help="Create a project")
    for name in ("name","product-name","source-url"):
        create.add_argument("--"+name,required=True)
    for name,default in (("benefits",""),("target-audience",""),("language","th"),("tone","friendly")):
        create.add_argument("--"+name,default=default)
    fact=sub.add_parser("add-fact",help="Add an evidenced fact, or an unsupported claim to review")
    fact.add_argument("--project",required=True)
    fact.add_argument("--fact",required=True)
    fact.add_argument("--source",default="")
    fact.add_argument("--status",choices=["verified","seller_claim","unverified","prohibited"],default="unverified")
    fact.add_argument("--notes",default="")
    for name in ("show","generate-brief","approve-facts","generate-prompts","approve-prompts",
                 "generate-test","approve-test","generate-batch","assemble","qc","export"):
        c=sub.add_parser(name)
        c.add_argument("--project",required=True)
        if name=="assemble":
            c.add_argument("--voiceover",type=Path)
            c.add_argument("--subtitles",type=Path)
    sub.add_parser("list")
    sub.add_parser("doctor",help="Check local executables and provider readiness; no Google access")
    sub.add_parser("gflow-doctor",help="Read local gflow installation metadata; does not access account/session")
    sub.add_parser("demo",help="Complete synthetic mock workflow, including fixture approvals (mock only)")
    serve=sub.add_parser("serve",help="Start loopback-only UI")
    serve.add_argument("--port",type=int,default=8000)
    return p

def emit(value):
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str))

async def demo(wf):
    if wf.settings.video_provider!="mock":
        raise ValueError("demo is allowed only in mock mode; it cannot spend credits")
    p=wf.create(ProjectInput(name="Studio demo",product_name="Demo Blue Cup",source_url="https://example.com/demo-cup",target_audience="Office workers",language="th",tone="friendly"))
    wf.generate_brief(p.id)
    for text in ("color: blue","shape: cylinder","size: 300 ml","accessories: none"):
        wf.add_fact(p.id,text,"Synthetic demo fixture, not a real product","verified","Developer fixture only")
    wf.approve_facts(p.id); wf.generate_prompts(p.id); wf.approve_prompts(p.id)
    await wf.generate(p.id)
    wf.approve_test(p.id)
    await wf.generate(p.id,batch=True)
    final=await asyncio.to_thread(wf.assemble,p.id)
    package=await asyncio.to_thread(wf.export,p.id)
    return dict(project_id=p.id,final=str(final),package=str(package),qc=wf.qc(p.id),
                warning="Synthetic demo: programmatic approvals are restricted to mock mode.")

def main(argv=None):
    args=parser().parse_args(argv)
    settings=Settings()
    handler=logging.StreamHandler()
    handler.addFilter(SecretFilter())
    logging.basicConfig(handlers=[handler],level=logging.WARNING,force=True)
    try:
        if args.command=="serve":
            if not 1024<=args.port<=65535:
                raise ValueError("Choose a port between 1024 and 65535")
            import uvicorn
            from .web import create_app
            uvicorn.run(create_app(settings),host="127.0.0.1",port=args.port,log_level="warning")
            return 0
        wf=Workflow(settings)
        if args.command in {"doctor","gflow-doctor"}:
            result=GFlowProvider(wf.root).readiness()
            result["output_root"]=str(wf.root)
            result["database_url"]=settings.database()
            if args.command=="doctor":
                result["ffmpeg"]=shutil.which(settings.ffmpeg)
                result["ffprobe"]=shutil.which(settings.ffprobe)
                result["active_provider"]=wf.provider_info()
            emit(result)
            return 0 if args.command=="doctor" and wf.provider_info()["ready"] else 2
        if args.command=="create-project":
            p=wf.create(ProjectInput(**{key:getattr(args,key) for key in ProjectInput.model_fields}))
            emit({"project_id":p.id,"output_dir":p.output_dir})
        elif args.command=="list":
            emit([{"id":p.id,"name":p.name,"status":p.status} for p in wf.list()])
        elif args.command=="demo":
            emit(asyncio.run(demo(wf)))
        elif args.command=="add-fact":
            f=wf.add_fact(args.project,args.fact,args.source,args.status,args.notes)
            emit({"fact_id":f.id,"status":f.verification_status})
        elif args.command=="show":
            d=wf.detail(args.project)
            emit({key: [ {c.name:getattr(row,c.name) for c in row.__table__.columns} for row in val] if isinstance(val,list)
                else {c.name:getattr(val,c.name) for c in val.__table__.columns} for key,val in d.items()})
        elif args.command in {"generate-test","generate-batch"}:
            emit(wf.provider_info())
            asyncio.run(wf.generate(args.project,batch=args.command=="generate-batch"))
            emit({"status":wf.detail(args.project)["project"].status})
        elif args.command=="assemble":
            for kind,path in (("voiceover",args.voiceover),("subtitle",args.subtitles)):
                if path:
                    if not path.is_file() or path.stat().st_size>settings.max_upload_mb*1024*1024:
                        raise ValueError("Input file missing or too large")
                    if kind=="voiceover":
                        data=probe(path,settings.ffprobe)
                        if not any(s.get("codec_type")=="audio" for s in data.get("streams",[])):
                            raise ValueError("Voiceover must contain audio")
                    elif path.suffix.lower()!=".srt" or "-->" not in path.read_text(encoding="utf-8-sig"):
                        raise ValueError("Use UTF-8 SRT subtitles")
                    destination=wf.directory(args.project)/"inputs"/(kind+path.suffix.lower())
                    destination.parent.mkdir(exist_ok=True)
                    if path.resolve()!=destination.resolve():
                        shutil.copyfile(path,destination)
                    wf.register_upload(args.project,kind,destination)
            emit({"file":str(wf.assemble(args.project))})
        else:
            fn=getattr(wf,args.command.replace("-","_"))
            emit(fn(args.project))
        return 0
    except (ValueError,OSError,TimeoutError) as exc:
        print(redact(exc),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())

