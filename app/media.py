import json
import math
import subprocess
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, model_validator

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

def normalize_command(ffmpeg,source,target,has_audio):
    args=[ffmpeg,"-y","-i",str(source)]
    if not has_audio:
        args+=["-f","lavfi","-i","anullsrc=channel_layout=stereo:sample_rate=48000"]
    args+=["-map","0:v:0","-map","0:a:0" if has_audio else "1:a:0",
           "-vf","scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1",
           "-r","24","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p",
           "-c:a","aac","-ar","48000","-ac","2","-shortest","-movflags","+faststart",str(target)]
    return args

def assemble(clips,output,ffmpeg,ffprobe,voiceover=None,subtitle=None):
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    working=output.parent / "normalized"
    working.mkdir(exist_ok=True)
    for i,clip in enumerate(clips,1):
        info=probe(clip,ffprobe)
        has_audio=any(s.get("codec_type")=="audio" for s in info.get("streams",[]))
        run(normalize_command(ffmpeg,clip,working/f"{i:02}.mp4",has_audio))
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
    temp.replace(output)
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
    role: Literal["hook","product_demo","lifestyle","detail","benefit","proof","cta"]
    prompt: str = Field(min_length=1)
    clip: str
    duration_seconds: float = Field(gt=0)

class Manifest(BaseModel):
    project_id: str
    source_url: str
    shots: list[ManifestShot] = Field(min_length=7,max_length=7)
    @model_validator(mode="after")
    def order(self):
        roles=["hook","product_demo","lifestyle","detail","benefit","proof","cta"]
        if [s.shot_number for s in self.shots]!=list(range(1,8)) or [s.role for s in self.shots]!=roles:
            raise ValueError("Manifest requires exactly seven ordered roles")
        return self

