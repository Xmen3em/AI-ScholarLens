"""Read-only study operations shared by research agents and optional MCP."""

import re

from src.services.study.content import PaperContent
from src.services.study.evidence import tool_block
from src.services.study.store import StudyStore


class StudyTools:
    def __init__(self, store: StudyStore, *, max_calls: int = 8):
        context = store.context()
        saved = store.paper(context["paper_id"]) if context else None
        if not saved:
            raise ValueError("active_paper_required")
        self.document = PaperContent.model_validate(saved["content"])
        self.lesson = saved["lesson"]
        self.max_calls, self.calls = max_calls, 0

    def _admit(self):
        if self.calls >= self.max_calls:
            raise ValueError("study_tool_budget_exhausted")
        self.calls += 1

    def overview(self) -> dict:
        self._admit()
        doc = self.document
        return {"paper": doc.paper.model_dump(), "source_url": doc.paper.source_url,
                "coverage": doc.coverage, "page_count": doc.page_count,
                "blocks": [{"id": b.id, "page": b.page, "section": b.section} for b in doc.blocks]}

    def search(self, query: str, limit: int = 6) -> list[dict]:
        self._admit()
        if type(query) is not str or not 1 <= len(query) <= 200 or type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError("invalid_study_search")
        terms = set(re.findall(r"\w{3,}", query.lower()))
        ranked = sorted(self.document.blocks, key=lambda b: sum(term in b.text.lower() for term in terms), reverse=True)
        return [tool_block(b) for b in ranked[:limit]]

    def read(self, ids: list[str]) -> list[dict]:
        self._admit()
        if type(ids) is not list or not 1 <= len(ids) <= 8 or any(type(i) is not str for i in ids):
            raise ValueError("invalid_block_request")
        lookup = {b.id: b for b in self.document.blocks}
        if len(set(ids)) != len(ids) or any(i not in lookup for i in ids):
            raise ValueError("unknown_evidence_block")
        return [tool_block(lookup[i]) for i in ids]

    def notes(self) -> dict:
        self._admit()
        return {"lesson_not_primary_evidence": self.lesson, "source_url": self.document.paper.source_url}
