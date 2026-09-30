import asyncio
import json
import pytest
from app.media import normalize_command, parse_probe, Manifest, run
from app.settings import Settings
from app.workflow import Workflow
from test_workflow import approved

def test_normalization_arguments():
    cmd = normalize_command("ffmpeg","in.mp4","out.mp4",True)
    assert "libx264" in cmd and "aac" in cmd
    assert any("720:1280" in a for a in cmd)
    assert cmd[-1] == "out.mp4"

def test_qc_parsing_checks_audio_and_dimensions():
    payload = {"streams":[{"codec_type":"video","codec_name":"h264","width":720,"height":1280}],"format":{"duration":"56"}}
    report = parse_probe(payload, "final.mp4", True)
    assert report["portrait"]
    assert not report["passed"]
    assert report["visual_review_required"]
    assert not parse_probe({}, "bad", False)["passed"]

def test_manifest_rejects_bad_shots():
    with pytest.raises(ValueError):
        Manifest(project_id="abc", source_url="https://example.com", shots=[])

def test_end_to_end_mock_and_export(tmp_path):
    wf = Workflow(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'test.db'}"))
    p = approved(wf)
    asyncio.run(wf.generate(p.id))
    wf.approve_test(p.id)
    asyncio.run(wf.generate(p.id, batch=True))
    final = wf.assemble(p.id)
    qc = wf.qc(p.id)
    assert final.exists() and final.stat().st_size > 0
    assert qc["passed"] and qc["width"] == 720 and qc["height"] == 1280
    assert 55 < qc["duration"] < 58
    package = wf.export(p.id)
    assert package.exists()
    assert json.loads((final.parent / "qc-report.json").read_text())["passed"]
    import zipfile
    with zipfile.ZipFile(package) as z:
        assert "final-reel.mp4" in z.namelist()
        assert "manifest.json" in z.namelist()

