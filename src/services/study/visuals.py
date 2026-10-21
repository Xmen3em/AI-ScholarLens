"""Deterministic study maps; arrows mean reading order, never invented results."""

import base64
import io
import json
import os
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features
from src.services.study.tutor import Lesson


def _map_nodes(lesson: Lesson) -> list[dict]:
    nodes = []
    for section in (s for s in lesson.sections if s.kind == "paper"):
        text = " ".join(section.text.split())
        body = text if len(text) <= 120 else text[:117].rsplit(" ", 1)[0] + "…"
        nodes.append({"label": section.heading[:44], "body": "\n".join(textwrap.wrap(body, width=60)),
                      "refs": "  ".join(dict.fromkeys(s.block_id for s in section.evidence))})
        if len(nodes) == 4:
            break
    return nodes


def study_map(lesson: Lesson) -> bytes | None:
    # Arabic shaping is required. Do not silently ship disconnected glyphs.
    if not features.check_feature("raqm"):
        return _windows_map(lesson) if os.name == "nt" else None
    fonts = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf",
             Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    font_path = next((path for path in fonts if path.is_file()), None)
    if font_path is None:
        return None
    font = ImageFont.truetype(str(font_path), 28)
    small = ImageFont.truetype(str(font_path), 18)
    nodes = _map_nodes(lesson)
    if not nodes:
        return None
    image = Image.new("RGB", (1000, 170 + 190 * len(nodes)), "#102332")
    draw = ImageDraw.Draw(image)
    draw.text((940, 48), "خريطة مذاكرة الورقة", font=font, fill="#ffffff", direction="rtl", anchor="ra")
    draw.text((940, 94), "الأسهم بترتّب المذاكرة؛ مش نتائج أو علاقات سببية", font=small, fill="#b3c7d4", direction="rtl", anchor="ra")
    for index, node in enumerate(nodes):
        top = 145 + index * 190
        draw.rounded_rectangle((60, top, 940, top + 150), radius=18, fill="#1d4253", outline="#56d4b1", width=2)
        draw.text((910, top + 17), node["label"], font=font, fill="white", direction="rtl", anchor="ra")
        for line_number, line in enumerate(node["body"].splitlines()):
            draw.text((910, top + 57 + line_number * 25), line, font=small, fill="#b3c7d4", direction="rtl", anchor="ra")
        draw.text((88, top + 121), node["refs"], font=small, fill="#56d4b1")
        if index < len(nodes) - 1:
            draw.line((500, top + 154, 500, top + 180), fill="#56d4b1", width=3)
            draw.polygon([(494, top + 174), (506, top + 174), (500, top + 184)], fill="#56d4b1")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _windows_map(lesson: Lesson) -> bytes | None:
    nodes = _map_nodes(lesson)
    if not nodes:
        return None
    payload = {"title": "خريطة مذاكرة الورقة", "subtitle": "الأسهم بترتّب المذاكرة؛ مش نتائج أو علاقات سببية",
               "nodes": nodes}
    executable = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-File", str(Path(__file__).with_name("render_map.ps1"))],
            input=json.dumps(payload, ensure_ascii=True).encode("ascii"), capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or len(result.stdout) > 240000:
            return None
        data = base64.b64decode(result.stdout, validate=True)
        return data if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) <= 180000 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
