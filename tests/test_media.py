import asyncio
import json
import pytest
from app.media import normalize_command, parse_probe, Manifest, probe, run, short_product_title, _title_font
from app.settings import Settings
from app.workflow import Workflow
from test_workflow import approved

def test_normalization_arguments():
    cmd = normalize_command("ffmpeg","in.mp4","out.mp4",True)
    assert "libx264" in cmd and "aac" in cmd
    assert any("720:1280" in a for a in cmd)
    assert cmd[-1] == "out.mp4"

def test_normalization_can_skip_opening_reference_frame():
    cmd=normalize_command("ffmpeg","in.mp4","out.mp4",True,start_seconds=0.8)
    assert cmd[cmd.index("-ss") + 1] == "0.8"
    assert cmd.index("-ss") < cmd.index("-i")

def test_qc_parsing_checks_audio_and_dimensions():
    payload = {"streams":[{"codec_type":"video","codec_name":"h264","width":720,"height":1280}],"format":{"duration":"56"}}
    report = parse_probe(payload, "final.mp4", True)
    assert report["portrait"]
    assert not report["passed"]
    assert report["visual_review_required"]
    assert not parse_probe({}, "bad", False)["passed"]

def test_manifest_rejects_empty_shots():
    with pytest.raises(ValueError):
        Manifest(project_id="abc", source_url="https://example.com", shots=[])

def test_manifest_accepts_single_ugc_shot():
    manifest = Manifest(project_id="abc", source_url="https://example.com", shots=[
        dict(shot_number=1, role="ugc_showcase", prompt="Show the product", clip="clip-01.mp4", duration_seconds=8)
    ])
    assert len(manifest.shots) == 1

def test_long_thumbnail_title_uses_multiple_lines(tmp_path):
    from PIL import Image
    from app.media import _title_assets
    title,_=_title_assets("แก้วพลาสติกขนาดใหญ่ 900 มล. พร้อมหลอดดูด สีโตปามีน",tmp_path)
    alpha=Image.open(title).getchannel("A")
    assert alpha.getbbox()[3]-alpha.getbbox()[1] > 70

def test_short_product_title_keeps_product_and_model_without_listing_specs():
    assert short_product_title("JAMAY พัดลมพกพา แบตเตอรี่ 6000mAh Bladeless Pocket Fan ABS พร้อมจอ LED รุ่น FS930")=="JAMAY พัดลมพกพา FS930"

def test_title_font_prefers_a_thai_capable_system_font(tmp_path):
    from pathlib import Path
    font=_title_font(48,Path("missing-project-font.ttf"))
    assert Path(font.path).name=="Mali-SemiBold.ttf"

def test_title_blur_crops_mattes_and_only_blurs_title_area(tmp_path):
    from PIL import Image, ImageDraw
    from app.media import add_title_and_soft_blur
    source=tmp_path/"letterboxed.mp4"
    image=Image.new("RGB",(720,1280),"black")
    ImageDraw.Draw(image).rectangle((0,220,719,1050),fill=(170,190,150))
    ImageDraw.Draw(image).rectangle((0,990,719,1100),fill=(20,20,20))
    frame=tmp_path/"letterbox.png"; image.save(frame)
    run(["ffmpeg","-y","-loop","1","-i",str(frame),"-t","1","-r","24","-c:v","libx264","-pix_fmt","yuv420p",str(source)])
    output=tmp_path/"titled.mp4"
    add_title_and_soft_blur(source,output,"JAMAY FS930")
    result=tmp_path/"output.png"
    run(["ffmpeg","-y","-i",str(output),"-frames:v","1",str(result)])
    from PIL import ImageStat
    output_image=Image.open(result).convert("RGB")
    top=ImageStat.Stat(output_image.crop((0,120,120,200))).mean
    seam=ImageStat.Stat(output_image.crop((0,1000,120,1030))).mean
    bottom=ImageStat.Stat(output_image.crop((0,1120,120,1200))).mean
    content=output_image.getpixel((360,800))
    assert sum(top)>100
    assert sum(seam)>100
    assert sum(bottom)>100
    assert content[1]>content[0]  # preserve the clip's color after matte removal

def test_end_to_end_mock_and_export(tmp_path):
    wf = Workflow(Settings(output_root=tmp_path,database_url=f"sqlite:///{tmp_path/'test.db'}"))
    p = approved(wf)
    asyncio.run(wf.generate(p.id))
    wf.approve_test(p.id)
    final = wf.assemble(p.id)
    raw_duration=float(probe(wf.detail(p.id)["shots"][0].clip_path,wf.settings.ffprobe)["format"]["duration"])
    from PIL import Image, ImageChops, ImageStat
    source_frame=tmp_path/"source-frame.png"
    final_frame=tmp_path/"final-frame.png"
    run(["ffmpeg","-y","-ss","1","-i",str(final.parent/"joined.mp4"),"-frames:v","1",str(source_frame)])
    run(["ffmpeg","-y","-ss","1","-i",str(final),"-frames:v","1",str(final_frame)])
    difference=ImageChops.difference(Image.open(source_frame).convert("RGB"),Image.open(final_frame).convert("RGB"))
    top=ImageStat.Stat(difference.crop((0,0,720,250))).mean[0]
    body=ImageStat.Stat(difference.crop((0,300,720,1280))).mean[0]
    assert top>body, "final video should add more title/blur changes near the top than the unadorned body"
    poster_path=final.parent/"thumbnail.jpg"
    assert poster_path.is_file()
    poster=Image.open(poster_path).convert("RGB")
    assert poster.size==(720,1280)
    poster_diff=ImageChops.difference(poster.crop((626,1160,694,1228)),Image.open(final_frame).convert("RGB").crop((626,1160,694,1228)))
    assert ImageStat.Stat(poster_diff).mean[0] < 10, "thumbnail should not draw a play button over the video"
    qc = wf.qc(p.id)
    assert final.exists() and final.stat().st_size > 0
    assert qc["passed"] and qc["width"] == 720 and qc["height"] == 1280
    assert 7 < qc["duration"] < 9
    assert qc["duration"] < raw_duration-0.6, "assembly should remove the opening product-reference transition"
    package = wf.export(p.id)
    assert package.exists()
    assert json.loads((final.parent / "qc-report.json").read_text())["passed"]
    import zipfile
    with zipfile.ZipFile(package) as z:
        assert "final-reel.mp4" in z.namelist()
        assert "thumbnail.jpg" in z.namelist()
        assert "manifest.json" in z.namelist()

