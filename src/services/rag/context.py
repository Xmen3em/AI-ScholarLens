"""Deterministic evidence selection and citation validation."""

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from src.schemas.api.rag import Citation
from src.schemas.api.search import PaperPassages

CITATION_PATTERN = re.compile(r"\[(\d+)\.(\d+)\]")


@dataclass(frozen=True)
class RAGContext:
    citations: list[Citation]
    sources: list[str]
    prompt_context: str


def build_context(papers: Sequence[PaperPassages], *, character_budget: int = 12_000) -> RAGContext:
    """Select whole passages under budget, prioritizing three-source diversity."""
    selected: list[tuple[int, int]] = []
    used = 0

    def include(paper_index: int, passage_index: int) -> bool:
        nonlocal used
        passage = papers[paper_index].passages[passage_index]
        length = len(passage.content)
        if not passage.content or used + length > character_budget:
            return False
        selected.append((paper_index, passage_index))
        used += length
        return True

    for paper_index in range(min(3, len(papers))):
        if papers[paper_index].passages:
            include(paper_index, 0)

    max_passages = max((len(paper.passages) for paper in papers), default=0)
    for passage_index in range(max_passages):
        for paper_index, paper in enumerate(papers):
            coordinate = (paper_index, passage_index)
            if coordinate in selected or passage_index >= len(paper.passages):
                continue
            include(paper_index, passage_index)

    citations = [_citation(papers, paper_index, passage_index) for paper_index, passage_index in selected]
    sources = list(dict.fromkeys(_pdf_url(citation.arxiv_id) for citation in citations))
    blocks = [
        "\n".join(
            [
                citation.marker,
                f"arXiv: {citation.arxiv_id}",
                f"Paper: {citation.title}",
                f"Section: {citation.section_title}",
                f"Locator: section_index={citation.section_index}, chunk_index={citation.chunk_index}",
                "Evidence:",
                citation.evidence,
            ]
        )
        for citation in citations
    ]
    return RAGContext(citations=citations, sources=sources, prompt_context="\n\n".join(blocks))


def validate_answer_citations(answer: str, allowed_markers: Iterable[str]) -> None:
    """Reject output with no traceability or markers outside the supplied catalog."""
    found = {f"[{paper}.{passage}]" for paper, passage in CITATION_PATTERN.findall(answer)}
    if not found:
        raise ValueError("answer is missing a citation marker")
    unknown = sorted(found - set(allowed_markers))
    if unknown:
        raise ValueError(f"answer contains unknown citation markers: {', '.join(unknown)}")


def _citation(papers: Sequence[PaperPassages], paper_index: int, passage_index: int) -> Citation:
    paper = papers[paper_index]
    passage = paper.passages[passage_index]
    return Citation(
        marker=f"[{paper_index + 1}.{passage_index + 1}]",
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        section_title=passage.section_title,
        section_index=passage.section_index,
        chunk_index=passage.chunk_index,
        evidence=passage.content,
    )


def _pdf_url(arxiv_id: str) -> str:
    versionless_id = re.sub(r"v\d+$", "", arxiv_id)
    return f"https://arxiv.org/pdf/{versionless_id}.pdf"
