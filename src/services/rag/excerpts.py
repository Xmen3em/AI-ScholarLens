"""Server-owned evidence sentences for constrained extractive answers."""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from src.schemas.api.rag import Citation
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER, validate_answer_length

MAX_EXCERPTS = 3
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


def build_excerpts(citations: Sequence[Citation], query: str) -> dict[str, EvidenceExcerpt]:
    """Offer the best matching whole sentence from each retrieved passage.

    Short headings and overlong sentences are omitted, never truncated. Original
    wording is preserved; only PDF whitespace is normalized.
    """
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
    excerpts: dict[str, EvidenceExcerpt] = {}
    for citation in citations:
        if citation.arxiv_id not in eligible:
            continue
        raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n\s*\n", citation.evidence)
        sentences = [
            " ".join(sentence.split())
            for sentence in raw_sentences
            if 7 <= len(sentence.split()) <= MAX_EXCERPT_WORDS
        ]
        frequency = Counter(term for sentence in raw_sentences for term in _terms(sentence))
        sentences.sort(key=lambda text: -sum(1 / frequency[term] for term in terms & _terms(text)))
        if sentences:
            excerpts[f"E{len(excerpts) + 1}"] = EvidenceExcerpt(sentences[0], citation.marker)
    return excerpts


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
