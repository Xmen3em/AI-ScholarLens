"""Presentation isolation without rewriting canonical Arabic/English content."""

from collections.abc import Sequence
from html import escape

from src.services.study.visual_learning.models import TextRun


def plain_text(runs: Sequence[TextRun]) -> str:
    return "".join(run.text for run in runs)


def runs_html(runs: Sequence[TextRun]) -> str:
    result = []
    for run in runs:
        language = {"rtl": ' lang="ar-EG"', "ltr": ' lang="en"', "auto": ""}[run.direction]
        result.append(f'<bdi dir="{run.direction}"{language}>{escape(run.text)}</bdi>')
    return "".join(result)
