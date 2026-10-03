import asyncio
import pytest
from app.settings import Settings
from app.workflow import Workflow
from app.models import ProjectInput

@pytest.fixture
def wf(tmp_path):
    return Workflow(Settings(output_root=tmp_path, database_url=f"sqlite:///{tmp_path / 'db.sqlite'}"))

def project(wf):
    return wf.create(ProjectInput(name="Demo", product_name="Blue cup", source_url="https://example.com/p?a=1&b=2", benefits="Keeps water cold", target_audience="Office", language="th", tone="friendly"))

def approved(wf):
    p = project(wf)
    for text in ["color: blue", "shape: cylinder", "size: 300 ml", "accessories: none"]:
        wf.add_fact(p.id, text, "User product photograph and label", "verified", "Manually checked")
    wf.approve_facts(p.id)
    wf.generate_prompts(p.id)
    wf.approve_prompts(p.id)
    return p

def test_create_preserves_source_and_classifies_benefits(wf):
    p = project(wf)
    assert p.source_url == "https://example.com/p?a=1&b=2"
    wf.generate_brief(p.id)
    data = wf.detail(p.id)
    assert data["facts"][0].verification_status == "unverified"
    assert data["facts"][0].approved is False

def test_sensitive_claim_needs_evidence(wf):
    p = project(wf)
    with pytest.raises(ValueError):
        wf.add_fact(p.id, "waterproof", "", "verified", "")
    f = wf.add_fact(p.id, "waterproof", "seller listing", "seller_claim", "")
    assert f.verification_status == "unverified"

def test_missing_identity_blocks_prompts(wf):
    p = project(wf)
    with pytest.raises(ValueError):
        wf.approve_facts(p.id)

def test_ugc_prompt_uses_approved_facts_only(wf):
    p = approved(wf)
    shots = wf.detail(p.id)["shots"]
    assert [s.role for s in shots] == ["ugc_showcase"]
    assert len(shots) == 1
    for s in shots:
        assert "Blue cup" in s.prompt and "300 ml" in s.prompt
        assert "9:16" in s.prompt and "8-second" in s.prompt
        assert "Keeps water cold" not in s.prompt
        assert "no fake text" in s.prompt

def test_test_clip_cannot_be_approved_before_it_exists(wf):
    p = approved(wf)
    with pytest.raises(ValueError, match="test"):
        wf.approve_test(p.id)

def test_edits_invalidate_approvals(wf):
    p = approved(wf)
    first = wf.detail(p.id)["shots"][0]
    wf.edit_shot(p.id, first.id, "Changed shot direction", "No artifacts")
    assert not wf.detail(p.id)["project"].prompts_approved
    assert not wf.detail(p.id)["project"].test_approved
    wf.add_fact(p.id, "material: plastic", "label", "verified", "checked")
    assert not wf.detail(p.id)["project"].facts_approved

def test_unknown_ids_and_source_validation(wf):
    with pytest.raises(ValueError):
        wf.detail("..")
    with pytest.raises(ValueError):
        ProjectInput(name="x", product_name="x", source_url="file:///secret")


def test_unknown_submission_not_resubmitted(wf):
    from app.models import Shot
    p = approved(wf)
    with wf.transaction() as s:
        s.get(Shot, wf.detail(p.id)["shots"][0].id).status="indeterminate"
    with pytest.raises(ValueError, match="indeterminate"):
        asyncio.run(wf.generate(p.id))

def test_qc_rejects_stale_assembly(wf):
    p=approved(wf)
    with pytest.raises(ValueError):
        wf.qc(p.id)
