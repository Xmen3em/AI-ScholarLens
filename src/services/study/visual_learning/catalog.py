"""Load the repository-owned reviewed fixture; never a model-selected path."""

from pathlib import Path

from pydantic import ValidationError
from src.services.study.visual_learning.models import CuratedMethod, VisualError

CATALOG_PATH = Path(__file__).resolve().parents[4] / "evaluation/visual_learning/rag-method.v1.json"


def load_curated_method() -> CuratedMethod:
    try:
        raw = CATALOG_PATH.read_bytes()
        if len(raw) > 128 * 1024:
            raise VisualError("catalog_too_large")
        catalog = CuratedMethod.model_validate_json(raw)
    except (OSError, ValidationError) as exc:
        raise VisualError("catalog_unavailable") from exc
    evidence_ids = {item.id for item in catalog.evidence}
    fact_ids = {fact.id for fact in catalog.facts}
    if len(evidence_ids) != len(catalog.evidence) or len(fact_ids) != len(catalog.facts):
        raise VisualError("catalog_duplicate_id")
    if any(not set(fact.evidence_ids) <= evidence_ids for fact in catalog.facts):
        raise VisualError("catalog_unknown_evidence")
    return catalog
