"""Check Markdown repository links, anchors and explicit public claims."""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def slug(text):
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def check(path):
    text = path.read_text(encoding="utf-8")
    anchors = {slug(line) for line in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE)}
    for target in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text):
        target = target.split(maxsplit=1)[0].strip("<>")
        if target.startswith(("https://", "http://", "mailto:")):
            continue
        if target.startswith("#"):
            assert target[1:] in anchors, f"missing anchor: {path}:{target}"
            continue
        relative, _, anchor = target.partition("#")
        resolved = (path.parent / relative).resolve()
        assert resolved.is_relative_to(ROOT), f"outside repository: {path}:{target}"
        assert resolved.exists(), f"missing target: {path}:{target}"
        if anchor and resolved.suffix == ".md":
            subheads = {slug(line) for line in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", resolved.read_text(encoding="utf-8"), re.MULTILINE)}
            assert anchor in subheads, f"missing target anchor: {path}:{target}"
    for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        if not target.startswith("https://"):
            assert (path.parent / target).is_file(), f"missing image: {path}:{target}"
    return len(re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text))


def main():
    results = {}
    for relative in ("README.md", "docs/prototype-notes.md", "site/README.md", "docs/assets/README.md"):
        results[relative] = check(ROOT / relative)
    for relative in ("README.md", "site/index.html", "site/README.md"):
        text = (ROOT / relative).read_text(encoding="utf-8").lower()
        assert "production-ready at scale" not in text
        assert "faithfulness 0%" not in text
        assert "calibrated against human labels" not in text
    assert "2510.26807" not in (ROOT / "site/index.html").read_text(encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
