import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

def create_title_overlay(width=720, height=1280, font_path=None, line1="แก้วเก็บความเย็น 900ml", line2="สไตล์มินิมอล เก๋ๆ", output_png="overlay.png"):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = 42
    font = ImageFont.truetype(font_path, font_size)

    # Calculate positions
    # Top margin ~ 80px
    y1 = 90
    y2 = 155
    cx = width // 2

    # Subtle soft shadow / glow for contrast over light backgrounds
    shadow_color = (255, 255, 255, 180)
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)]:
        draw.text((cx + dx, y1 + dy), line1, font=font, fill=shadow_color, anchor="mm")
        draw.text((cx + dx, y2 + dy), line2, font=font, fill=shadow_color, anchor="mm")

    # Main dark text
    text_color = (35, 35, 35, 255)
    draw.text((cx, y1), line1, font=font, fill=text_color, anchor="mm")
    draw.text((cx, y2), line2, font=font, fill=text_color, anchor="mm")

    img.save(output_png)
    print(f"Overlay created at {output_png}")

if __name__ == "__main__":
    create_title_overlay(
        font_path="projects/b84b143b2aef43f3bb3471895b6d1db4/references/Mali-SemiBold.ttf",
        output_png="projects/b84b143b2aef43f3bb3471895b6d1db4/references/title_overlay.png"
    )
