"""Server-owned evidence sentences for constrained extractive answers."""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from src.schemas.api.rag import Citation
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER, validate_answer_length

MAX_EXCERPTS = 3
MAX_CANDIDATES_PER_PASSAGE = 3
MAX_EXCERPT_WORDS = 55
QUESTION_STOPWORDS = frozenset("a an and are as at be by do does for from how in is it of on or papers that the these this to use what which with".split())
MIN_QUERY_COVERAGE = 0.6


def _terms(text: str) -> set[str]:
    """Small English inflection normalization for conservative lexical matching."""
    words = set(re.findall(r"\w+", text.lower())) - QUESTION_STOPWORDS
    return {re.sub(r"(?:ing|ed|s)$", "", word).rstrip("e") if len(word) > 4 else word for word in words if len(word) > 1}


@dataclass(frozen=True)
class EvidenceExcerpt:
    text: str
    marker: str


def build_excerpts(citations: Sequence[Citation], query: str, *, candidates_per_passage: int = 1,
                   max_candidates: int | None = None) -> dict[str, EvidenceExcerpt]:
    """Offer bounded matching whole sentences; expansion is an opt-in experiment.

    Short headings and overlong sentences are omitted, never truncated. Original
    wording is preserved; only PDF whitespace is normalized.
    An optional total cap offers one sentence per passage before extra sentences.
    """
    if not 1 <= candidates_per_passage <= MAX_CANDIDATES_PER_PASSAGE:
        raise ValueError("candidates_per_passage must be between one and three")
    if max_candidates is not None and (type(max_candidates) is not int or not 1 <= max_candidates <= 10):
        raise ValueError("max_candidates must be between one and ten")
    terms = _terms(query)
    # A shared topic mention is insufficient when most requested details are absent.
    # This deliberately abstains on some paraphrases; it is not semantic entailment.
    if not terms:
        return {}
    paper_terms = {
        arxiv_id: _terms(" ".join(c.evidence for c in citations if c.arxiv_id == arxiv_id))
        for arxiv_id in {citation.arxiv_id for citation in citations}
    }
    eligible = {arxiv_id for arxiv_id, available in paper_terms.items() if len(terms & available) / len(terms) >= MIN_QUERY_COVERAGE}
    groups: list[list[EvidenceExcerpt]] = []
    for citation in citations:
        if citation.arxiv_id not in eligible:
            continue
        raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n\s*\n", citation.evidence)
        sentences = [
            " ".join(sentence.split())
            for sentence in raw_sentences
            if 7 <= len(sentence.split()) <= MAX_EXCERPT_WORDS and terms & _terms(sentence)
        ]
        frequency = Counter(term for sentence in raw_sentences for term in _terms(sentence))
        sentences.sort(key=lambda text: -sum(1 / frequency[term] for term in terms & _terms(text)))
        groups.append([EvidenceExcerpt(sentence, citation.marker) for sentence in sentences[:candidates_per_passage]])
    if max_candidates is None:
        offered = [excerpt for group in groups for excerpt in group]
    else:
        # Give every passage a first candidate before offering second/third ones.
        offered = [group[rank] for rank in range(candidates_per_passage) for group in groups if rank < len(group)]
        offered = offered[:max_candidates]
    return {f"E{index}": excerpt for index, excerpt in enumerate(offered, start=1)}


def render_selection(selection: Sequence[str], excerpts: dict[str, EvidenceExcerpt]) -> str:
    """Resolve selected IDs without accepting any model-written factual text."""
    if len(selection) > MAX_EXCERPTS or len(set(selection)) != len(selection):
        raise ValueError("answer selection must contain at most three distinct IDs")
    if any(key not in excerpts for key in selection):
        raise ValueError("answer selection contains an unknown evidence ID")
    if not selection:
        return INSUFFICIENT_EVIDENCE_ANSWER
    answer = "\n".join(f'"{excerpts[key].text}" {excerpts[key].marker}' for key in selection)
    validate_answer_length(answer)
    return answer
