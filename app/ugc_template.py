"""
UGC Template Module for Nextgen Video Generator
Provides automated aesthetic UGC video templating:
1. Top background blur (creamy gradient bokeh behind header text)
2. Minimalist Thai typography overlay (Mali font, 2 lines)
3. UGC-style background music (BGM) mixing with smooth fade-in / fade-out
"""

from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).parent.parent / "projects" / "b84b143b2aef43f3bb3471895b6d1db4" / "references"
DEFAULT_FONT = ASSETS_DIR / "Mali-SemiBold.ttf"
DEFAULT_BGM = ASSETS_DIR / "bgm_cute_823.mp3"

def create_title_card(width: int, height: int, line1: str, line2: str, font_path: Path, output_png: Path):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(font_path), 42)
    cx = width // 2
    y1, y2 = 85, 150

    # Soft ambient glow behind text
    glow_color = (255, 255, 255, 230)
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-2, 0), (2, 0)]:
        draw.text((cx + dx, y1 + dy), line1, font=font, fill=glow_color, anchor="mm")
        draw.text((cx + dx, y2 + dy), line2, font=font, fill=glow_color, anchor="mm")

    text_color = (30, 30, 30, 255)
    draw.text((cx, y1), line1, font=font, fill=text_color, anchor="mm")
    draw.text((cx, y2), line2, font=font, fill=text_color, anchor="mm")
    img.save(output_png)

def create_blur_gradient_mask(width: int, height: int, output_png: Path, blur_height: int = 250):
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for y in range(blur_height):
        if y <= 130:
            val = 255
        else:
            val = int(255 * (1.0 - (y - 130) / (blur_height - 130)))
        draw.line([(0, y), (width, y)], fill=val)
    mask.save(output_png)

def apply_ugc_template(
    input_video: str,
    output_video: str,
    line1: str = "แก้วเก็บความเย็น 900ml",
    line2: str = "สไตล์มินิมอล เก๋ๆ",
    bgm_path: str = None,
    trim_seconds: float = None,
    ffmpeg: str = "ffmpeg"
):
    inp = Path(input_video)
    out = Path(output_video)
    temp_dir = out.parent / ".temp_template"
    temp_dir.mkdir(parents=True, exist_ok=True)

    title_png = temp_dir / "title_overlay.png"
    mask_png = temp_dir / "blur_mask.png"

    create_title_card(720, 1280, line1, line2, DEFAULT_FONT, title_png)
    create_blur_gradient_mask(720, 1280, mask_png, 250)

    bgm = Path(bgm_path) if bgm_path else DEFAULT_BGM

    trim_filter = f"trim=0:{trim_seconds},setpts=PTS-STARTPTS," if trim_seconds else ""

    filter_complex = (
        f"[0:v]{trim_filter}split=2[main][for_blur]; "
        f"[for_blur]boxblur=25:5[blurred]; "
        f"[main][blurred][1:v]maskedmerge[with_blur]; "
        f"[with_blur][2:v]overlay=0:0[vfinal]; "
        f"[3:a]volume=0.35,afade=t=in:st=0:d=0.5,afade=t=out:st={trim_seconds - 0.7 if trim_seconds else 6.5}:d=0.7[afinal]"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", str(inp),
        "-i", str(mask_png),
        "-i", str(title_png),
        "-ss", "12", "-i", str(bgm),
        "-filter_complex", filter_complex,
        "-map", "[vfinal]", "-map", "[afinal]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(out)
    ]

    subprocess.run(cmd, check=True)
    print(f"UGC Template successfully applied to {out}")

if __name__ == "__main__":
    import sys
    apply_ugc_template(
        input_video="projects/b84b143b2aef43f3bb3471895b6d1db4/clips/shot-02.mp4",
        output_video="projects/b84b143b2aef43f3bb3471895b6d1db4/exports/final-reel.mp4",
        trim_seconds=7.2
    )
