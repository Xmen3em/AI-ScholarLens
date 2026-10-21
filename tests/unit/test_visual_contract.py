import copy
import json

import pytest
from src.services.study.visual_learning.catalog import load_curated_method
from src.services.study.visual_learning.models import VisualError
from src.services.study.visual_learning.validation import default_spec, validate_spec


def candidate():
    catalog = load_curated_method()
    return catalog, default_spec(catalog).model_dump(mode="json")


def test_checked_method_preserves_training_cycle_and_binds_original_source():
    catalog, raw = candidate()
    spec = validate_spec(json.dumps(raw, ensure_ascii=False), catalog)
    assert spec.source.paper_id == "2005.11401v4"
    updates = {edge.target for edge in spec.edges if edge.relation == "parameter_update"}
    assert updates == {"query_encoder", "generator"}
    assert len(spec.steps) == 8


@pytest.mark.parametrize("field,value", [
    ("paper_id", "2005.11401v3"), ("sha256", "0" * 64), ("parser_revision", "different-parser"),
])
def test_cross_source_specs_are_rejected(field, value):
    catalog, raw = candidate()
    raw["source"][field] = value
    with pytest.raises(VisualError, match="source_mismatch"):
        validate_spec(raw, catalog)


@pytest.mark.parametrize("mutation", ["unknown_fact", "update_fixed_encoder", "unknown_endpoint", "bad_step", "wrong_phase"])
def test_unknown_or_misleading_scientific_bindings_are_rejected(mutation):
    catalog, raw = candidate()
    if mutation == "unknown_fact":
        raw["nodes"][0]["fact_ids"] = ["not-a-fact"]
    elif mutation == "update_fixed_encoder":
        raw["edges"][-1]["target"] = "document_encoder"
    elif mutation == "unknown_endpoint":
        raw["edges"][0]["target"] = "external"
    elif mutation == "bad_step":
        raw["steps"][0]["node_ids"] = ["objective"]
    else:
        raw["nodes"][0]["phase"] = "training"
    with pytest.raises(VisualError):
        validate_spec(raw, catalog)


def test_a_true_fact_id_does_not_authorize_changed_scientific_wording():
    catalog, raw = candidate()
    raw["steps"][3]["body"] = [{"text": "كل فقرة بتعيد البحث من جديد.", "direction": "rtl"}]
    with pytest.raises(VisualError, match="unreviewed_content"):
        validate_spec(raw, catalog)


@pytest.mark.parametrize("mutation", ["extra", "too_many", "duplicate", "control", "unsupported", "oversize", "duplicate_json_key"])
def test_malformed_or_unbounded_specs_fail_at_the_boundary(mutation):
    catalog, raw = candidate()
    if mutation == "extra":
        raw["renderer_code"] = "alert(1)"
    elif mutation == "too_many":
        raw["nodes"] = [copy.deepcopy(raw["nodes"][0])] * 13
    elif mutation == "duplicate":
        raw["nodes"][1]["id"] = raw["nodes"][0]["id"]
    elif mutation == "control":
        raw["title_ar"] += "\u202e"
    elif mutation == "unsupported":
        raw["template"] = "arbitrary_html"
    elif mutation == "oversize":
        raw = " " * 16385
    else:
        raw = '{"schema_version":1,"schema_version":2}'
    with pytest.raises(VisualError):
        validate_spec(raw, catalog)


def test_untrusted_model_instance_is_revalidated_after_nested_mutation():
    catalog, _ = candidate()
    instance = default_spec(catalog)
    instance.edges[0].fact_ids.append("unknown")
    with pytest.raises(VisualError):
        validate_spec(instance, catalog)


def test_excessively_nested_json_has_a_finite_failure():
    catalog = load_curated_method()
    with pytest.raises(VisualError, match="invalid_spec"):
        validate_spec("[" * 1500 + "0" + "]" * 1500, catalog)
