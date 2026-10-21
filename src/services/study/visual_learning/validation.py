"""Review binding, not a claim that arbitrary generated prose is scientifically verified."""

import json
from typing import Any

from pydantic import ValidationError
from src.services.study.visual_learning.models import (
    MAX_SPEC_BYTES,
    CuratedMethod,
    VisualEdge,
    VisualError,
    VisualNode,
    VisualSpec,
    VisualStep,
)


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VisualError("duplicate_json_key")
        result[key] = value
    return result


def default_spec(catalog: CuratedMethod) -> VisualSpec:
    raw = catalog.model_dump(mode="json", include={"source", "title_ar", "nodes", "edges", "steps"})
    raw["catalog_revision"] = catalog.revision
    return validate_spec(raw, catalog)


def validate_spec(candidate: str | bytes | dict | VisualSpec, catalog: CuratedMethod) -> VisualSpec:
    if isinstance(candidate, VisualSpec):
        candidate = candidate.model_dump(mode="json")
    try:
        if isinstance(candidate, dict):
            candidate = json.dumps(candidate, ensure_ascii=False, allow_nan=False)
        encoded = candidate.encode("utf-8") if isinstance(candidate, str) else candidate
        if not isinstance(encoded, bytes) or len(encoded) > MAX_SPEC_BYTES:
            raise VisualError("spec_too_large")
        raw = json.loads(encoded, object_pairs_hook=_unique)
        spec = VisualSpec.model_validate(raw)
    except (ValidationError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, VisualError):
            raise
        raise VisualError("invalid_spec") from None
    if spec.source != catalog.source or spec.catalog_revision != catalog.revision:
        raise VisualError("source_mismatch")
    facts = {fact.id for fact in catalog.facts}
    nodes = {node.id: node for node in spec.nodes}
    edges = {edge.id: edge for edge in spec.edges}
    if any(len({item.id for item in items}) != len(items) for items in (spec.nodes, spec.edges, spec.steps)):
        raise VisualError("duplicate_id")
    bound_items: list[VisualNode | VisualEdge | VisualStep] = [*spec.nodes, *spec.edges, *spec.steps]
    for item in bound_items:
        if not set(item.fact_ids) <= facts:
            raise VisualError("unknown_fact")
    for edge in spec.edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise VisualError("unknown_endpoint")
        if edge.relation == "parameter_update" and catalog.training_policy.get(edge.target) != "updated":
            raise VisualError("fixed_component_update")
    for step in spec.steps:
        if not set(step.node_ids) <= nodes.keys() or not set(step.edge_ids) <= edges.keys():
            raise VisualError("unknown_step_reference")
        if any(nodes[key].phase not in {"both", step.phase} for key in step.node_ids):
            raise VisualError("wrong_step_phase")
    # V1 only accepts the reviewed mechanism/text. A valid fact ID alone is not
    # semantic review of new wording. Later planning requires a reviewed catalog.
    if (spec.title_ar, spec.nodes, spec.edges, spec.steps) != (
        catalog.title_ar, catalog.nodes, catalog.edges, catalog.steps,
    ):
        raise VisualError("unreviewed_content")
    return spec
