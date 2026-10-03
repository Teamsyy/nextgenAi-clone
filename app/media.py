import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from PIL import Image, ImageDraw, ImageFont, ImageOps

CHECKLIST=["Product shape/color correct","Logo spelling correct","No extra parts","Hands/faces acceptable","No fake text","No unsupported claims","Continuity acceptable","CTA readable"]

def run(args,timeout=180):
    try:
        p=subprocess.run([str(a) for a in args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,check=False)
    except FileNotFoundError:
        raise ValueError(f"Required executable not found: {args[0]}") from None
    if p.returncode:
        # Media diagnostics contain local file names, never provider credentials.
        raise ValueError(f"{Path(str(args[0])).name} failed: {p.stderr[-1200:]}")
    return p.stdout

def probe(path,ffprobe="ffprobe"):
    return json.loads(run([ffprobe,"-v","error","-show_streams","-show_format","-of","json",str(path)],60))

def parse_probe(data,file_path,audio_required=False):
    streams=data.get("streams",[])
    videos=[s for s in streams if s.get("codec_type")=="video"]
    v=videos[0] if videos else {}
    audio=any(s.get("codec_type")=="audio" for s in streams)
    width=int(v.get("width",0)); height=int(v.get("height",0))
    try:
        duration=float(data.get("format",{}).get("duration",0))
    except (TypeError,ValueError):
        duration=0
    duration=duration if math.isfinite(duration) else 0
    readable=bool(v.get("codec_name") and v.get("codec_name")!="unknown")
    passed=bool(videos and readable and duration>0 and height>width>0 and (audio or not audio_required))
    return dict(file_path=str(file_path),has_video=bool(videos),has_audio=audio,width=width,height=height,duration=duration,
                portrait=height>width>0,codec=v.get("codec_name",""),ffprobe_ok=bool(streams),
                visual_review_required=True,passed=passed,notes=[],manual_checklist=CHECKLIST)

def normalize_command(ffmpeg,source,target,has_audio,start_seconds=0):
    args=[ffmpeg,"-y"]
    if start_seconds:
        args += ["-ss",str(start_seconds)]
    args += ["-i",str(source)]
    if not has_audio:
        args+=["-f","lavfi","-i","anullsrc=channel_layout=stereo:sample_rate=48000"]
    args+=["-map","0:v:0","-map","0:a:0" if has_audio else "1:a:0",
           "-vf","scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1",
           "-r","24","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p",
           "-c:a","aac","-ar","48000","-ac","2","-shortest","-movflags","+faststart",str(target)]
    return args

def _title_font(size,font_path=None):
    bundled=Path(__file__).parent/"static"/"fonts"/"Mali-SemiBold.ttf"
    if bundled.is_file():
        return ImageFont.truetype(str(bundled),size)
    root=Path(os.getenv("WINDIR",r"C:\Windows"))
    for path in (root/"Fonts"/"tahoma.ttf",root/"Fonts"/"LeelawUI.ttf",root/"Fonts"/"angsana.ttc",root/"Fonts"/"cordia.ttc",
                 Path("/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf"),Path("/usr/share/fonts/truetype/tlwg/TlwgTypo.ttf")):
        if path.is_file():
            return ImageFont.truetype(str(path),size)
    if font_path and Path(font_path).is_file():
        return ImageFont.truetype(str(font_path),size)
    return ImageFont.load_default(size=size)

def short_product_title(title):
    words=title.strip().split()
    if len(words)<=3:
        return " ".join(words)
    model=next((word for word in reversed(words) if re.fullmatch(r"[A-Z]{1,8}-?\d[A-Z0-9-]*",word.upper())),None)
    return " ".join(words[:2]+([model] if model and model not in words[:2] else []))

def _title_assets(title,directory,font_path=None):
    width,height=720,1280
    overlay=Image.new("RGBA",(width,height),(0,0,0,0))
    draw=ImageDraw.Draw(overlay)
    text=title.strip()
    max_width=width-72
    font=_title_font(62,font_path)
    def wrap(value,current_font):
        lines=[]
        for word in value.split():
            if draw.textlength(word,font=current_font)>max_width:
                parts=[]
                for char in word:
                    if parts and draw.textlength(parts[-1]+char,font=current_font)>max_width:
                        parts.append(char)
                    elif parts:
                        parts[-1]+=char
                    else:
                        parts.append(char)
                words=parts
            else:
                words=[word]
            for part in words:
                candidate=f"{lines[-1]} {part}" if lines else part
                if lines and draw.textlength(candidate,font=current_font)<=max_width:
                    lines[-1]=candidate
                else:
                    lines.append(part)
        return lines or [value]
    lines=wrap(text,font)
    while len(lines)>3 and font.size>38:
        font=_title_font(font.size-2,font_path)
        lines=wrap(text,font)
    top=30
    line_height=round(font.size*1.08)
    for index,line in enumerate(lines):
        y=top+index*line_height
        draw.text((width//2+2,y+3),line,font=font,fill=(0,0,0,150),anchor="mt",stroke_width=3,stroke_fill=(0,0,0,100))
        draw.text((width//2,y),line,font=font,fill=(255,255,255,255),anchor="mt",stroke_width=2,stroke_fill=(39,34,28,220))
    overlay_path=Path(directory)/"title.png"
    overlay.save(overlay_path)
    mask=Image.new("L",(width,height),0)
    mask_draw=ImageDraw.Draw(mask)
    for y in range(230):
        strength=128 if y<100 else round(128*(230-y)/130)
        mask_draw.line((0,y,width,y),fill=strength)
    mask_path=Path(directory)/"blur-mask.png"
    mask.save(mask_path)
    return overlay_path,mask_path

def add_title_and_soft_blur(input_video,output_video,title,ffmpeg="ffmpeg",font_path=None):
    if not title or not title.strip():
        raise ValueError("Product title is required")
    output=Path(output_video)
    # Veo sometimes embeds the actual portrait shot between black mattes.
    # Detect those borders, then fill the 9:16 canvas by scaling/cropping the
    # shot itself. This avoids a second blurred/dark band at the bottom.
    detected=subprocess.run(
        [ffmpeg,"-ss","0.2","-i",str(input_video),"-frames:v","12","-vf",
         "cropdetect=limit=0.30:round=2:reset=0","-f","null","-"],
        capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30,check=False)
    crop_matches=re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)",detected.stderr)
    crop=""
    if crop_matches:
        crop_width,crop_height,crop_x,crop_y=map(int,crop_matches[-1])
        source_info=probe(input_video)
        source_video=next((stream for stream in source_info.get("streams",[]) if stream.get("codec_type")=="video"),{})
        source_width=int(source_video.get("width",0)); source_height=int(source_video.get("height",0))
        if (crop_width==source_width and source_height*0.60<=crop_height<source_height*0.92 and crop_y>0):
            crop=f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
    with tempfile.TemporaryDirectory(prefix=".title-overlay-",dir=output.parent) as temporary:
        title_png,mask_png=_title_assets(title,temporary,font_path)
        run([ffmpeg,"-y","-i",input_video,"-i",mask_png,"-i",title_png,
             "-filter_complex",f"[0:v]{crop}scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,split=2[sharp-src][blur-src];"
             "[sharp-src]format=yuv444p[sharp];[blur-src]boxblur=20:2,format=yuv444p[blurred];"
             "[1:v]format=yuv444p[mask];[sharp][blurred][mask]maskedmerge[soft];[soft][2:v]overlay=0:0:format=auto[v]",
             "-map","[v]","-map","0:a?","-map","0:s?","-c:v","libx264","-preset","ultrafast",
             "-pix_fmt","yuv420p","-c:a","copy","-c:s","copy","-movflags","+faststart",output])
    return output

def create_thumbnail(video,output,ffmpeg="ffmpeg"):
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".thumbnail-",dir=output.parent) as temporary:
        frame=Path(temporary)/"frame.png"
        run([ffmpeg,"-y","-ss","1","-i",video,"-frames:v","1",str(frame)])
        image=ImageOps.fit(Image.open(frame).convert("RGB"),(720,1280))
        image.convert("RGB").save(output,"JPEG",quality=90,optimize=True)
    return output

def assemble(clips,output,ffmpeg,ffprobe,voiceover=None,subtitle=None,title=None,font_path=None):
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    working=output.parent / "normalized"
    working.mkdir(exist_ok=True)
    for i,clip in enumerate(clips,1):
        info=probe(clip,ffprobe)
        has_audio=any(s.get("codec_type")=="audio" for s in info.get("streams",[]))
        # Veo can retain the Shopee listing image as its opening transition.
        # Skip that short reference-frame lead-in on the first shot only.
        run(normalize_command(ffmpeg,clip,working/f"{i:02}.mp4",has_audio,start_seconds=0.8 if i==1 else 0))
    concat=working/"concat.txt"
    concat.write_text("".join(f"file '{i:02}.mp4'\n" for i in range(1,len(clips)+1)),encoding="utf-8")
    joined=output.parent/"joined.mp4"
    run([ffmpeg,"-y","-f","concat","-safe","1","-i",str(concat),"-c","copy",str(joined)])
    args=[ffmpeg,"-y","-i",str(joined)]
    if voiceover:
        args+=["-i",str(voiceover)]
    if subtitle:
        args+=["-i",str(subtitle)]
    args+=["-map","0:v:0"]
    if voiceover:
        duration=probe(joined,ffprobe)["format"]["duration"]
        args+=["-map","1:a:0","-af","apad","-t",str(duration),"-c:a","aac"]
    else:
        args+=["-map","0:a:0?","-c:a","copy"]
    if subtitle:
        args+=["-map",f"{2 if voiceover else 1}:s:0","-c:s","mov_text","-metadata:s:s:0","language=tha"]
    temp=output.with_name("final-reel.pending.mp4")
    args+=["-c:v","copy","-movflags","+faststart",str(temp)]
    run(args)
    if title:
        rendered=output.with_name("final-reel.titled.pending.mp4")
        add_title_and_soft_blur(temp,rendered,title,ffmpeg,font_path)
        rendered.replace(output)
        temp.unlink(missing_ok=True)
    else:
        temp.replace(output)
    create_thumbnail(output,output.parent/"thumbnail.jpg",ffmpeg)
    return output

def quality_check(path,ffprobe,ffmpeg,audio_required=False):
    path=Path(path)
    if not path.is_file() or not path.stat().st_size:
        result=parse_probe({},path,audio_required)
        result["notes"].append("Missing or empty output")
        return result
    try:
        result=parse_probe(probe(path,ffprobe),path,audio_required)
        run([ffmpeg,"-v","error","-xerror","-i",str(path),"-map","0:v:0","-map","0:a:0?","-f","null","-"],180)
        result["decode_ok"]=True
    except (ValueError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        result=parse_probe({},path,audio_required)
        result["decode_ok"]=False
        result["notes"].append(str(exc))
    result["passed"]=result["passed"] and result.get("decode_ok",False)
    return result

class ManifestShot(BaseModel):
    shot_number: int = Field(ge=1,le=7)
    role: Literal["ugc_showcase","hook","product_demo","lifestyle","detail","benefit","proof","cta"]
    prompt: str = Field(min_length=1)
    clip: str
    duration_seconds: float = Field(gt=0)

class Manifest(BaseModel):
    project_id: str
    source_url: str
    shots: list[ManifestShot] = Field(min_length=1,max_length=7)
    @model_validator(mode="after")
    def order(self):
        roles=[s.role for s in self.shots]
        legacy=["hook","product_demo","lifestyle","detail","benefit","proof","cta"]
        if len(self.shots)==1 and roles==["ugc_showcase"]:
            return self
        if roles!=legacy or [s.shot_number for s in self.shots]!=list(range(1,8)):
            raise ValueError("Manifest requires one UGC shot or seven ordered legacy shots")
        return self

