import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from src.services.study.visual_learning.models import TextRun
from src.services.study.visual_learning.text import plain_text, runs_html

CASES = json.loads((Path(__file__).resolve().parents[2] / "evaluation/visual_learning/arabic-reading.v1.json")
                   .read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_mixed_text_retains_canonical_content_or_rejects_controls(case):
    if case.get("reject"):
        with pytest.raises(ValidationError):
            [TextRun.model_validate(run) for run in case["runs"]]
        return
    runs = [TextRun.model_validate(run) for run in case["runs"]]
    assert plain_text(runs) == "".join(run["text"] for run in case["runs"])
    html = runs_html(runs)
    assert html.count("<bdi ") == len(runs)
    assert "\u2066" not in html and "\u2069" not in html
    for run in runs:
        assert f'dir="{run.direction}"' in html


def test_markup_is_plain_text_and_does_not_create_html_or_script():
    text = '</script><img src=x onerror="alert(1)"> & data'
    runs = [TextRun(text=text, direction="auto")]
    html = runs_html(runs)
    assert "<img" not in html and "</script>" not in html
    assert "&lt;img" in html and "&amp;" in html
    assert plain_text(runs) == text
