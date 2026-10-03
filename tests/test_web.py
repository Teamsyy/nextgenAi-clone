import re
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.web import create_app, project_ui_state
from app.settings import Settings
from app.models import ProjectInput, Shot

def test_project_ui_state_explains_next_step_and_blocked_provider():
    class Project:
        facts_approved = True
        prompts_approved = False
        test_approved = False
        assembled_current = False
        status = "review"
    detail = {"project": Project(), "shots": [], "facts": []}
    state = project_ui_state(detail, {"ready": False, "reason": "Flow is blocked"}, False)
    assert state["current_step"] == 2
    assert state["next_action"] == "สร้าง prompt จากข้อมูลที่อนุมัติ"
    assert not state["can_approve_facts"]
    assert "Flow is blocked" in state["action_blockers"]["generate-test"]

@pytest.mark.parametrize(("status","facts","prompts","test","assembled","shot_status","step"), [
    ("draft",False,False,False,False,"draft",1),
    ("facts_approved",True,False,False,False,"draft",2),
    ("prompts_approved",True,True,False,False,"approved",3),
    ("test_review",True,True,False,False,"complete",3),
    ("test_approved",True,True,True,False,"complete",4),
    ("assembled",True,True,True,True,"complete",4),
    ("qc_failed",True,True,True,True,"complete",4),
    ("exported",True,True,True,True,"complete",4),
    ("generating",True,True,False,False,"generating",3),
])
def test_project_ui_state_follows_workflow(status,facts,prompts,test,assembled,shot_status,step):
    project=SimpleNamespace(status=status,facts_approved=facts,prompts_approved=prompts,
                            test_approved=test,assembled_current=assembled)
    shot=SimpleNamespace(status=shot_status,prompt="prompt")
    state=project_ui_state({"project":project,"shots":[shot],"facts":[]},
                           {"ready":True,"reason":""},assembled)
    assert state["current_step"]==step
    if status=="generating":
        assert all("กำลังประมวลผล" in reason for reason in state["action_blockers"].values())

def test_status_endpoint_only_exposes_safe_job_fields(tmp_path):
    app = create_app(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'status.db'}"))
    p = app.state.workflow.create(ProjectInput(name="UI", product_name="Cup", source_url="https://example.com"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(f"/projects/{p.id}/status")
    assert response.status_code == 200
    assert set(response.json()) == {"project_status", "busy", "completed_count", "shot_count", "jobs"}
    assert "prompt" not in response.text and "clip_path" not in response.text

def test_dashboard_uses_studio_shell_and_project_thumbnail(tmp_path):
    from PIL import Image
    app=create_app(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'cards.db'}"))
    project=app.state.workflow.create(ProjectInput(name="Poster",product_name="Cup",source_url="https://example.com"))
    ref=app.state.workflow.directory(project.id)/"references"/"cover.jpg"
    Image.new("RGB",(20,30),"pink").save(ref)
    with TestClient(app,base_url="http://127.0.0.1") as client:
        page=client.get("/")
    assert page.status_code==200
    assert 'class="studio-rail"' in page.text
    assert 'class="project-grid"' in page.text
    assert f'/projects/{project.id}/files/references/cover.jpg' in page.text

def test_gflow_reference_picker_shows_images_and_selects_clean_default(tmp_path):
    from PIL import Image
    app=create_app(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'refs.db'}",video_provider="gflow"))
    p=app.state.workflow.create(ProjectInput(name="Clean",product_name="Cup",source_url="https://example.com"))
    refs=app.state.workflow.directory(p.id)/"references"
    Image.new("RGB",(20,20),"white").save(refs/"clean_initial_frame_916.png")
    Image.new("RGB",(20,20),"pink").save(refs/"detail.jpg")
    with TestClient(app,base_url="http://127.0.0.1") as c:
        page=c.get(f"/projects/{p.id}")
    assert page.status_code==200
    assert 'type="checkbox" name="reference_images" value="clean_initial_frame_916.png" checked' in page.text
    assert 'type="checkbox" name="reference_images" value="detail.jpg"' in page.text
    assert f"/projects/{p.id}/files/references/clean_initial_frame_916.png" in page.text

def test_saved_fact_redirects_back_to_the_fact_being_edited(tmp_path):
    app = create_app(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'scroll.db'}"))
    p = app.state.workflow.create(ProjectInput(name="Scroll", product_name="Cup", source_url="https://example.com"))
    fact = app.state.workflow.add_fact(p.id, "color: blue", "label", "verified", "checked")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        page = client.get(f"/projects/{p.id}")
        token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        response = client.post(f"/projects/{p.id}/fact", data={"csrf":token,"fact_id":fact.id,
            "fact":"color: navy", "source":"label", "verification_status":"verified", "notes":"checked"},
            follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{p.id}#fact-{fact.id}"

def test_invalid_project_form_keeps_values_and_names_field_error(tmp_path):
    app = create_app(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'form.db'}"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        home = client.get("/")
        token = re.search(r'name="csrf" value="([^"]+)"', home.text).group(1)
        response = client.post("/projects", data={"csrf":token,"name":"Keep this name","product_name":"Cup",
                              "source_url":"file:///bad","language":"th","tone":"friendly"})
    assert response.status_code == 422
    assert 'value="Keep this name"' in response.text
    assert 'id="source-error"' in response.text
    assert 'name="language"' in response.text

def test_csrf_failure_keeps_safe_create_values_without_creating_project(tmp_path):
    app = create_app(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'csrf-form.db'}"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        home = client.get("/")
        token = re.search(r'name="csrf" value="([^"]+)"', home.text).group(1)
        response = client.post("/projects", data={"csrf":"expired", "name":"Keep this draft",
            "product_name":"Cup", "source_url":"https://example.com/item", "benefits":"fragile claim",
            "target_audience":"Office", "language":"th", "tone":"calm"})
        refreshed = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert response.status_code == 403
    assert 'value="Keep this draft"' in response.text
    assert 'value="https://example.com/item"' in response.text
    assert refreshed and refreshed.group(1) != token
    assert app.state.workflow.list() == []

def test_studio_page_names_the_next_step_and_blocked_reason(tmp_path):
    app = create_app(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'studio.db'}"))
    from test_workflow import approved
    project = approved(app.state.workflow)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        page = client.get(f"/projects/{project.id}")
    assert page.status_code == 200
    assert "ตรวจ prompt" in page.text and "สร้างและตรวจคลิป" in page.text
    assert "สร้างและตรวจคลิป UGC" in page.text
    assert "ตอนประกอบวิดีโอจะใส่ชื่อสินค้าและเบลอพื้นหลังด้านบนเล็กน้อย" in page.text
    assert "คลิปสังเคราะห์" in page.text
    assert 'disabled aria-describedby="why-approve-facts"' in page.text

def test_completed_clip_is_previewed_in_generation_step(tmp_path):
    app=create_app(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'preview.db'}"))
    from test_workflow import approved
    project=approved(app.state.workflow)
    clip=app.state.workflow.directory(project.id)/"clips"/"clip.mp4"
    clip.parent.mkdir(parents=True,exist_ok=True)
    clip.write_bytes(b"video")
    with app.state.workflow.transaction() as session:
        shot=session.query(Shot).filter_by(project_id=project.id).one()
        shot.status="complete"
        shot.clip_path=str(clip)
    with TestClient(app,base_url="http://127.0.0.1") as client:
        page=client.get(f"/projects/{project.id}")
    generate=page.text.index('id="generate"')
    preview=page.text.index('aria-label="ตัวอย่างคลิป UGC"')
    assert preview>generate
    assert f'href="/projects/{project.id}/files/clips/clip.mp4" download' in page.text

def test_draft_assembly_preview_can_be_generated_before_approval(tmp_path,monkeypatch):
    from app import web
    app=create_app(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'draft-preview.db'}"))
    from test_workflow import approved
    project=approved(app.state.workflow)
    clip=app.state.workflow.directory(project.id)/"clips"/"clip.mp4"
    clip.parent.mkdir(parents=True,exist_ok=True)
    clip.write_bytes(b"source")
    with app.state.workflow.transaction() as session:
        stored_project=session.get(type(project),project.id)
        stored_project.status="test_review"
        shot=session.query(Shot).filter_by(project_id=project.id).one()
        shot.status="complete"
        shot.clip_path=str(clip)
    def render_preview(clips,output,*args,**kwargs):
        output.write_bytes(b"draft preview")
        return output
    monkeypatch.setattr(web.media,"assemble",render_preview)
    with TestClient(app,base_url="http://127.0.0.1") as client:
        page=client.get(f"/projects/{project.id}")
        token=re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
        response=client.post(f"/projects/{project.id}/preview-assembly",data={"csrf":token},follow_redirects=False)
        page=client.get(f"/projects/{project.id}")
        video=client.get(f"/projects/{project.id}/files/exports/assembly-preview.mp4")
    assert response.status_code==303
    assert 'aria-label="ตัวอย่างวิดีโอฉบับร่างพร้อมชื่อสินค้าและพื้นหลังเบลอ"' in page.text
    assert "ตัวอย่างฉบับร่าง · ยังไม่ได้อนุมัติคลิป" in page.text
    assert video.status_code==200 and video.content==b"draft preview"
    assert app.state.workflow.detail(project.id)["project"].test_approved is False

def test_dashboard_search_filters_projects(tmp_path):
    app=create_app(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'search.db'}"))
    app.state.workflow.create(ProjectInput(name="Blue cup story",product_name="Blue cup",source_url="https://example.com/cup"))
    app.state.workflow.create(ProjectInput(name="Desk fan story",product_name="Desk fan",source_url="https://example.com/fan"))
    with TestClient(app,base_url="http://127.0.0.1") as client:
        page=client.get("/?q=cup")
    assert page.status_code==200
    assert "Blue cup story" in page.text
    assert "Desk fan story" not in page.text

def test_ui_creation_and_csrf(tmp_path):
    app = create_app(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path/'web.db'}"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        home = client.get("/")
        assert home.status_code == 200
        token = re.search(r'name="csrf" value="([^"]+)"', home.text).group(1)
        blocked = client.post("/projects", data={"name":"bad"})
        assert blocked.status_code == 403
        token = re.search(r'name="csrf" value="([^"]+)"', blocked.text).group(1)
        r = client.post("/projects",data={"csrf":token,"name":"UI","product_name":"Cup","source_url":"https://example.com","benefits":"","target_audience":"Adults","language":"th","tone":"friendly"})
        assert r.status_code == 200 and "Cup" in r.text
        assert "Manual review" in r.text
        assert client.get("/",headers={"host":"evil.example"}).status_code == 400
        assert client.post("/projects",headers={"origin":"https://evil.example"},data={"csrf":token}).status_code == 403
        r_origin = client.post("/projects",headers={"origin":"http://localhost"},data={"csrf":token,"name":"Loopback UI","product_name":"Cup","source_url":"https://example.com","benefits":"","target_audience":"Adults","language":"th","tone":"friendly"})
        assert r_origin.status_code == 200

