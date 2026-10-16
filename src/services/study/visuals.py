"""Deterministic study maps; arrows mean reading order, never invented results."""

import io
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features
from src.services.study.tutor import Lesson


def study_map(lesson: Lesson) -> bytes | None:
    # Arabic shaping is required. Do not silently ship disconnected glyphs.
    if not features.check_feature("raqm"):
        return None
    fonts = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf",
             Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    font_path = next((path for path in fonts if path.is_file()), None)
    if font_path is None:
        return None
    font = ImageFont.truetype(str(font_path), 28)
    small = ImageFont.truetype(str(font_path), 18)
    nodes = [section for section in lesson.sections if section.kind == "paper"][:4]
    if not nodes:
        return None
    image = Image.new("RGB", (1000, 170 + 140 * len(nodes)), "#102332")
    draw = ImageDraw.Draw(image)
    draw.text((940, 48), "خريطة مذاكرة الورقة", font=font, fill="#ffffff", direction="rtl", anchor="ra")
    draw.text((940, 94), "الأسهم بترتّب المذاكرة؛ مش نتائج أو علاقات سببية", font=small, fill="#b3c7d4", direction="rtl", anchor="ra")
    for index, node in enumerate(nodes):
        top = 145 + index * 140
        draw.rounded_rectangle((60, top, 940, top + 100), radius=18, fill="#1d4253", outline="#56d4b1", width=2)
        label = node.heading[:44]
        draw.text((910, top + 17), label, font=font, fill="white", direction="rtl", anchor="ra")
        refs = "  ".join(s.block_id for s in node.evidence)
        draw.text((88, top + 62), refs, font=small, fill="#56d4b1")
        if index < len(nodes) - 1:
            draw.line((500, top + 104, 500, top + 130), fill="#56d4b1", width=3)
            draw.polygon([(494, top + 124), (506, top + 124), (500, top + 134)], fill="#56d4b1")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
