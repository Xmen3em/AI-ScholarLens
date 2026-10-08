"""Combining two rankings into one."""

from typing import Dict, List, Sequence

# From the paper that introduced RRF (Cormack, Clarke & Buettcher, 2009). It damps the
# contribution of top ranks so that one list cannot dominate the fused order on the
# strength of a single confident hit.
RRF_K = 60


def fused_scores(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> Dict[str, float]:
    """The RRF score of every document, in first-appearance order.

    Each list contributes 1/(k + rank) per document, so a document ranked well by both
    beats one ranked first by a single list. Only positions matter, never scores —
    which is the point: BM25 scores and cosine similarities are on incomparable
    scales, and normalizing them means inventing a conversion nobody can justify.
    """
    scores: Dict[str, float] = {}
    for ranking in rankings:
        for rank, document_id in enumerate(ranking, start=1):
            scores[document_id] = scores.get(document_id, 0.0) + 1.0 / (k + rank)
    return scores


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> List[str]:
    """Merge ranked id lists into one order, best first.

    Ties keep first-appearance order — dicts preserve insertion order and Python's sort
    is stable — so the fused order is deterministic rather than depending on which half
    happened to be iterated first.
    """
    scores = fused_scores(rankings, k)
    return sorted(scores, key=lambda document_id: -scores[document_id])
