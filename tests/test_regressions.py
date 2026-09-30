
import asyncio
import re
import zipfile
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.models import Project, Shot
from app.media import run, probe
from app.web import create_app
from app.settings import Settings
from app.workflow import Workflow
from test_workflow import approved

def test_busy_project_blocks_mutations(tmp_path):
    wf=Workflow(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'busy.db'}"))
    p=approved(wf)
    with wf.transaction() as s:
        s.get(Project,p.id).status="generating"
    with pytest.raises(ValueError,match="busy"):
        wf.add_fact(p.id,"material: steel","label","verified","checked")
    with pytest.raises(ValueError,match="busy"):
        wf.edit_shot(p.id,wf.detail(p.id)["shots"][0].id,"new","none")

def test_checklist_change_invalidates_zip(tmp_path):
    wf=Workflow(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'review.db'}"))
    p=approved(wf)
    with wf.transaction() as s:
        obj=s.get(Project,p.id)
        obj.status="exported"
        obj.assembled_current=True
    wf.save_checklist(p.id,["No fake text"])
    assert wf.detail(p.id)["project"].status!="exported"

def test_voiceover_reassembly_and_subtitle_track(tmp_path):
    wf=Workflow(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'media.db'}"))
    p=approved(wf)
    asyncio.run(wf.generate(p.id))
    wf.approve_test(p.id)
    asyncio.run(wf.generate(p.id,batch=True))
    wf.assemble(p.id)
    voice=tmp_path/"voice.wav"
    run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=440:duration=2",str(voice)])
    sub=tmp_path/"captions.srt"
    sub.write_text("1\n00:00:00,000 --> 00:00:02,000\nสวัสดี\n",encoding="utf-8")
    wf.register_upload(p.id,"voiceover",voice)
    wf.register_upload(p.id,"subtitle",sub)
    with pytest.raises(ValueError):
        wf.qc(p.id)
    wf.assemble(p.id)
    report=wf.qc(p.id)
    assert report["passed"] and report["has_audio"]
    assert 55<report["duration"]<58
    meta=probe(wf.directory(p.id)/"exports"/"final-reel.mp4")
    assert any(s["codec_type"]=="subtitle" for s in meta["streams"])
    package=wf.export(p.id)
    with zipfile.ZipFile(package) as z:
        assert z.read("subtitles.srt").decode("utf-8").endswith("สวัสดี\n")

def test_web_fact_edit_xss_upload_and_social_actions(tmp_path):
    app=create_app(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'guard.db'}"))
    wf=app.state.workflow
    p=approved(wf)
    with TestClient(app,base_url="http://127.0.0.1") as c:
        page=c.get(f"/projects/{p.id}")
        csrf=re.search('name="csrf" value="([^"]+)"',page.text).group(1)
        for action in ["tiktok-login","shopee-post","publish","attach-cart"]:
            assert c.post(f"/projects/{p.id}/{action}",data={"csrf":csrf}).status_code==400
        r=c.post(f"/projects/{p.id}/fact",data={"csrf":csrf,"fact":"<script>alert(1)</script>","source":"manual","verification_status":"unverified","notes":""})
        assert "<script>alert(1)</script>" not in r.text
        assert "&lt;script&gt;" in r.text
        assert c.post(f"/projects/{p.id}/upload",data={"csrf":csrf,"kind":"reference"},files={"file":("bad.jpg",b"not image","image/jpeg")}).status_code==400
        assert not list((wf.directory(p.id)/"references").iterdir())

def test_gflow_rejection_is_exposed_without_job_submission(tmp_path):
    app=create_app(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'flow.db'}",video_provider="gflow"))
    p=approved(app.state.workflow)
    with TestClient(app,base_url="http://127.0.0.1") as c:
        page=c.get(f"/projects/{p.id}")
        csrf=re.search('name="csrf" value="([^"]+)"',page.text).group(1)
        r=c.post(f"/projects/{p.id}/generate-test",data={"csrf":csrf})
        assert r.status_code==400 and "blocked" in r.text
        assert app.state.workflow.detail(p.id)["jobs"]==[]

def test_withdrawn_facts_invalidates_prompts_and_cannot_survive(tmp_path):
    wf = Workflow(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'withdrawn.db'}"))
    p = approved(wf)
    fact = wf.add_fact(p.id, "waterproof", "official spec sheet", "verified", "lab tested")
    wf.approve_facts(p.id)
    wf.generate_prompts(p.id)
    wf.approve_prompts(p.id)
    assert any("waterproof" in s.prompt for s in wf.detail(p.id)["shots"])

    wf.add_fact(p.id, "waterproof", "seller claim", "unverified", "withdrawn", fact_id=fact.id)
    assert not wf.detail(p.id)["project"].prompts_approved
    assert all(not s.prompt for s in wf.detail(p.id)["shots"])

    wf.approve_facts(p.id)
    with pytest.raises(ValueError, match="seven prompts"):
        wf.approve_prompts(p.id)

    wf.generate_prompts(p.id)
    wf.approve_prompts(p.id)
    assert not any("waterproof" in s.prompt for s in wf.detail(p.id)["shots"])

def test_reapproving_prompts_preserves_completed_and_indeterminate_shots(tmp_path):
    wf = Workflow(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'preserve.db'}"))
    p = approved(wf)
    asyncio.run(wf.generate(p.id))
    wf.approve_test(p.id)
    detail = wf.detail(p.id)
    shot1 = detail["shots"][0]
    assert shot1.status == "complete"
    assert detail["project"].test_approved

    wf.approve_prompts(p.id)
    detail2 = wf.detail(p.id)
    assert detail2["shots"][0].status == "complete"

    with wf.transaction() as s:
        s.get(Shot, detail2["shots"][1].id).status = "indeterminate"
    wf.approve_prompts(p.id)
    assert wf.detail(p.id)["shots"][1].status == "indeterminate"

def test_export_reserves_project_and_blocks_mutations(tmp_path):
    wf = Workflow(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'export_busy.db'}"))
    p = approved(wf)
    with wf.transaction() as s:
        s.get(Project, p.id).status = "exporting"
    with pytest.raises(ValueError, match="busy"):
        wf.add_fact(p.id, "color: red", "label", "verified", "checked")
    with pytest.raises(ValueError, match="busy"):
        wf.assemble(p.id)
    with pytest.raises(ValueError, match="busy"):
        wf.export(p.id)

def test_save_all_seven_default_prompts(tmp_path):
    wf = Workflow(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'default_prompts.db'}"))
    p = approved(wf)
    shots = wf.detail(p.id)["shots"]
    assert len(shots) == 7
    for shot in shots:
        wf.edit_shot(p.id, shot.id, shot.prompt, shot.negative_prompt)
    proof_shot = [s for s in shots if s.role == "proof"][0]
    assert "certifications" in proof_shot.prompt


