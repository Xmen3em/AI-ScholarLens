"""Fixed SVG/PNG primitives from one checked scene, with readable failure fallback."""

import base64
import json
import math
import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from src.resources import free_memory_mib
from src.services.study.visual_learning.models import CuratedMethod, VisualSpec
from src.services.study.visual_learning.scene import COLORS, Scene, build_scene


def _element(parent: ET.Element, tag: str, **attributes: str) -> ET.Element:
    return ET.SubElement(parent, tag, {key.replace("_", "-"): value for key, value in attributes.items()})


def _text(parent: ET.Element, value: str, x: int, y: int, size: int = 18,
          color: str = COLORS["text"], direction: str = "rtl", anchor: str = "start") -> None:
    text = _element(parent, "text", x=str(x), y=str(y), fill=color, font_size=str(size),
                    direction=direction, unicode_bidi="isolate", text_anchor=anchor,
                    font_family="Segoe UI, Arial, sans-serif", lang="en" if direction == "ltr" else "ar-EG")
    text.text = value


def render_svg(spec: VisualSpec, catalog: CuratedMethod, *, phase: str = "inference", interactive: bool = False) -> str:
    scene = build_scene(spec, catalog, phase)
    root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1000 860",
                              "role": "group" if interactive else "img", "aria-labelledby": f"title-{phase} desc-{phase}",
                              "data-source-sha256": scene.source_sha256, "lang": "ar-EG"})
    _element(root, "title", id=f"title-{phase}").text = scene.title
    _element(root, "desc", id=f"desc-{phase}").text = scene.subtitle + ". " + scene.footer
    _element(root, "rect", width="1000", height="860", fill=COLORS["background"])
    definitions = _element(root, "defs")
    for kind in ("data", "update", "preparation"):
        marker = _element(definitions, "marker", id=f"arrow-{phase}-{kind}", markerWidth="10", markerHeight="10",
                          refX="9", refY="4", orient="auto", markerUnits="userSpaceOnUse")
        _element(marker, "path", d="M 0 0 L 9 4 L 0 8 Z", fill=COLORS[kind])
    _text(root, scene.title, 940, 47, 28)
    _text(root, scene.subtitle, 940, 84, 18, COLORS["muted"])
    for edge in scene.edges:
        group = _element(root, "g", data_edge=edge.id, data_relation=edge.relation)
        _element(group, "title").text = edge.label_ar
        kind = {"parameter_update": "update", "preparation": "preparation"}.get(edge.relation, "data")
        coordinates = " L ".join(f"{x} {y}" for x, y in edge.points)
        path = _element(group, "path", d="M " + coordinates, fill="none", stroke=edge.color,
                        stroke_width="2.5", marker_end=f"url(#arrow-{phase}-{kind})")
        if kind != "data":
            path.set("stroke-dasharray", "7 5" if kind == "update" else "3 5")
        if edge.label_position:
            _text(group, edge.label_ar, *edge.label_position, size=15, color=edge.color, anchor="middle")
    for node in scene.nodes:
        group = _element(root, "g", data_node=node.id, id=f"node-{phase}-{node.id}", **{"class": "scene-node"})
        if interactive:
            group.attrib.update({"role": "button", "tabindex": "0", "aria-label": node.label_ar,
                                 "aria-pressed": "false"})
        _element(group, "rect", x=str(node.x), y=str(node.y), width=str(node.width), height=str(node.height),
                 rx="8", fill=COLORS["surface"], stroke=COLORS["border"], stroke_width="2")
        _text(group, node.label_ar, node.x + 230, node.y + 34, 24)
        _text(group, node.term_en, node.x + 20, node.y + 63, 18, COLORS["muted"], direction="ltr")
        if node.status:
            _text(group, node.status, node.x + 230, node.y + 90, 16, node.status_color)
    _text(root, scene.footer, 940, 808, 17, COLORS["muted"])
    _text(root, scene.source_ref, 60, 841, 16, COLORS["muted"], direction="ltr")
    return ET.tostring(root, encoding="unicode")


def _windows_png(scene: Scene) -> bytes | None:
    executable = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    payload = {**asdict(scene), "colors": COLORS}
    worker_env = {key: value for key, value in os.environ.items()
                  if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    try:
        result = subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-File",
                                 str(Path(__file__).with_name("render_scene.ps1"))],
                                input=json.dumps(payload, ensure_ascii=True).encode("ascii"), capture_output=True,
                                timeout=15, creationflags=subprocess.CREATE_NO_WINDOW, env=worker_env)
        if result.returncode or len(result.stdout) > 700000:
            return None
        data = base64.b64decode(result.stdout, validate=True)
        dimensions = (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))
        return data if (data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR"
                        and dimensions == (1000, 860) and len(data) <= 500000) else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def render_png(spec: VisualSpec, catalog: CuratedMethod, *, phase: str = "inference") -> bytes | None:
    scene = build_scene(spec, catalog, phase)
    # No renderer or new dependency is loaded by normal bot startup. A missing
    # backend/resource is an explicit export fallback, never disconnected glyphs.
    try:
        free = free_memory_mib()
    except OSError:
        return None
    if not math.isfinite(free) or free < 600:
        return None
    return _windows_png(scene) if os.name == "nt" else None
