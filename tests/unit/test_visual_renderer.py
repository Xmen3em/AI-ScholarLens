import io
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image
from src.services.study.visual_learning.catalog import load_curated_method
from src.services.study.visual_learning.models import VisualError
from src.services.study.visual_learning.renderer import render_png, render_svg
from src.services.study.visual_learning.scene import build_scene
from src.services.study.visual_learning.validation import default_spec


@pytest.mark.parametrize("phase", ["inference", "training"])
def test_svg_has_source_bound_nodes_typed_arrows_and_no_executable_content(phase):
    catalog = load_curated_method()
    spec = default_spec(catalog)
    root = ET.fromstring(render_svg(spec, catalog, phase=phase))
    assert root.get("data-source-sha256") == catalog.source.sha256
    tags = {node.tag.rsplit("}", 1)[-1] for node in root.iter()}
    assert tags <= {"svg", "title", "desc", "defs", "marker", "path", "rect", "g", "text", "circle"}
    assert all(not key.startswith("on") and key not in {"href", "style"} for node in root.iter() for key in node.attrib)
    node_ids = {node.get("data-node") for node in root.iter() if node.get("data-node")}
    assert ("document_encoder" in node_ids) == (phase == "training")
    assert ("answer" in node_ids) == (phase == "inference")
    updates = [node for node in root.iter() if node.get("data-relation") == "parameter_update"]
    assert len(updates) == (2 if phase == "training" else 0)


def test_shared_scene_is_bounded_and_has_fixed_labels_in_training():
    catalog = load_curated_method()
    scene = build_scene(default_spec(catalog), catalog, "training")
    for node in scene.nodes:
        assert 0 <= node.x and node.x + node.width <= scene.width
        assert 0 <= node.y and node.y + node.height <= scene.height
    statuses = {node.id: node.status for node in scene.nodes}
    assert statuses["index"] == statuses["document_encoder"] == "ثابت"
    assert statuses["query_encoder"] == statuses["generator"] == "بيتدرّب"


def test_raster_is_a_real_bounded_image_on_the_pc():
    catalog = load_curated_method()
    data = render_png(default_spec(catalog), catalog, phase="training")
    if data is None:
        assert os.name != "nt"
        return
    assert data.startswith(b"\x89PNG") and len(data) < 500000
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (1000, 860)


def test_worker_failure_leaves_a_text_svg_fallback(monkeypatch):
    catalog = load_curated_method()
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("fixed-renderer", 15)
    monkeypatch.setattr("src.services.study.visual_learning.renderer.subprocess.run", fail)
    assert render_png(default_spec(catalog), catalog) is None
    assert "<svg" in render_svg(default_spec(catalog), catalog)


def test_changed_scientific_plan_cannot_reach_the_renderer(monkeypatch):
    catalog = load_curated_method()
    spec = default_spec(catalog)
    spec.edges[-1].fact_ids.append("not-reviewed")
    with pytest.raises(VisualError):
        render_svg(spec, catalog)


def test_rendering_rejects_an_unknown_phase():
    catalog = load_curated_method()
    with pytest.raises(VisualError, match="unknown_phase"):
        render_svg(default_spec(catalog), catalog, phase="other")


def test_windows_worker_source_is_ascii_and_arabic_enters_only_as_json_data():
    path = Path(__file__).resolve().parents[2] / "src/services/study/visual_learning/render_scene.ps1"
    assert path.read_text(encoding="ascii")


@pytest.mark.parametrize("free", [0, 599, float("nan")])
def test_missing_or_low_memory_uses_the_export_fallback(monkeypatch, free):
    catalog = load_curated_method()
    monkeypatch.setattr("src.services.study.visual_learning.renderer.free_memory_mib", lambda: free)
    assert render_png(default_spec(catalog), catalog) is None


def test_memory_probe_failure_keeps_the_readable_export(monkeypatch):
    catalog = load_curated_method()
    def unavailable():
        raise OSError("probe unavailable")
    monkeypatch.setattr("src.services.study.visual_learning.renderer.free_memory_mib", unavailable)
    assert render_png(default_spec(catalog), catalog) is None
