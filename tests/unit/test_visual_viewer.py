import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest
from src.services.study.visual_learning.catalog import load_curated_method
from src.services.study.visual_learning.models import VisualError
from src.services.study.visual_learning.validation import default_spec, validate_spec
from src.services.study.visual_learning.viewer import build_viewer, export_demo


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_viewer_has_isolated_rtl_content_fixed_controls_and_a_restrictive_csp():
    catalog = load_curated_method()
    html = build_viewer(default_spec(catalog), catalog, png_phases=set())
    page = Page(html)
    assert next(attrs for tag, attrs in page.tags if tag == "html") == {"lang": "ar-EG", "dir": "rtl"}
    ids = [attrs["id"] for _, attrs in page.tags if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert {"previous", "next", "component-picker", "evidence-panel", "text-alternative"} <= set(ids)
    csp = next(attrs["content"] for tag, attrs in page.tags if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy")
    assert "connect-src 'none'" in csp and "default-src 'none'" in csp and "'unsafe-inline'" not in csp
    assert not any(attrs.get("src", "").startswith("http") for _, attrs in page.tags)
    assert not any(name.startswith("on") for _, attrs in page.tags for name in attrs)
    assert {"rtl", "ltr", "auto"} <= {attrs["dir"] for _, attrs in page.tags if "dir" in attrs}


def test_source_title_markup_never_escapes_into_the_document():
    catalog = load_curated_method()
    source = catalog.source.model_copy(update={"title": '</script><img src=x onerror="alert(1)">'})
    catalog = catalog.model_copy(update={"source": source})
    html = build_viewer(default_spec(catalog), catalog, png_phases=set())
    assert "&lt;img" in html
    assert not any(tag == "img" for tag, _ in Page(html).tags)


def test_export_is_self_contained_hash_bound_and_refuses_to_overwrite(tmp_path):
    output = tmp_path / "demo"
    manifest = export_demo(output)
    assert (output / "index.html").is_file()
    assert manifest["scope"] == "curated_offline_fixture"
    for name, digest in manifest["assets"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    validate_spec((output / "visual-spec.json").read_bytes(), load_curated_method())
    previous = (output / "manifest.json").read_bytes()
    with pytest.raises(VisualError, match="output_exists"):
        export_demo(output)
    assert (output / "manifest.json").read_bytes() == previous


def test_missing_png_backend_keeps_svg_text_and_sources_usable(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.study.visual_learning.viewer.render_png", lambda *args, **kwargs: None)
    manifest = export_demo(tmp_path / "demo")
    assert manifest["png_phases"] == []
    html = (tmp_path / "demo/index.html").read_text(encoding="utf-8")
    assert "training.svg" in html and "inference.svg" in html
    assert not any(name.endswith(".png") for name in manifest["assets"])
    assert "text-alternative" in html and "evidence-panel" in html


def test_embedded_public_fixture_is_json_and_cannot_close_its_data_block():
    catalog = load_curated_method()
    html = build_viewer(default_spec(catalog), catalog, png_phases=set())
    embedded = html.split('<script id="visual-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    raw = json.loads(embedded)
    assert raw["spec"]["source"]["paper_id"] == "2005.11401v4"
    assert raw["catalog"]["training_policy"]["index"] == "fixed"


def test_concurrent_output_creation_is_preserved_and_reported(tmp_path, monkeypatch):
    output = tmp_path / "demo"
    original = Path.mkdir

    def raced_mkdir(path, *args, **kwargs):
        if path == output:
            original(path)
            (path / "existing.txt").write_text("keep", encoding="utf-8")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", raced_mkdir)
    monkeypatch.setattr("src.services.study.visual_learning.viewer.render_png", lambda *args, **kwargs: None)
    with pytest.raises(VisualError, match="output_exists"):
        export_demo(output)
    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("cleanup_denied", [False, True])
def test_partial_export_failure_is_finite_and_cleans_only_owned_files(tmp_path, monkeypatch, cleanup_denied):
    output = tmp_path / "demo"
    original_open, original_unlink = Path.open, Path.unlink

    def failed_open(path, *args, **kwargs):
        if path == output / "inference.svg":
            raise OSError("simulated disk failure")
        return original_open(path, *args, **kwargs)

    def failed_unlink(path, *args, **kwargs):
        if cleanup_denied and path.parent == output:
            raise PermissionError("simulated cleanup denial")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failed_open)
    monkeypatch.setattr(Path, "unlink", failed_unlink)
    monkeypatch.setattr("src.services.study.visual_learning.viewer.render_png", lambda *args, **kwargs: None)
    with pytest.raises(VisualError, match="export_write_failed"):
        export_demo(output)
    assert output.exists() is cleanup_denied
    assert not (output / "manifest.json").exists()
