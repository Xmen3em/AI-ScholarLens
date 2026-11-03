"""Frozen scientific regression cases for paper lessons. No model call."""

import json
from pathlib import Path

import pytest
from src.services.study.content import EvidenceBlock
from src.services.study.tutor import (
    ClaimVerdict,
    TutorError,
    accept_draft,
    check_claims,
    screen_claims,
    validate_draft,
)

from tests.unit.test_study_service import honest_spans

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "evaluation/paper_learning/science-cases.v1.json").read_text(encoding="utf-8"))
TRUTH = json.loads((ROOT / CASES["truth_source"]["fixture"]).read_text(encoding="utf-8"))
CRITICAL_CLASSES = {"best_result", "units_splits", "training_updates", "equation_signs", "token_paragraph_mechanism"}
REVIEW_ISSUES = set(ClaimVerdict.model_json_schema()["properties"]["issue"]["enum"]) - {"none"}


def locator_blocks() -> list[EvidenceBlock]:
    # Locators are rebuilt from the reviewed fixture, never stored as free text here.
    evidence = {item["id"]: item for item in TRUTH["evidence"]}
    blocks = []
    for locator in CASES["locators"]:
        if locator["construction"] == "reviewed_excerpts":
            text = " … ".join(evidence[i]["quote"] for i in locator["evidence_ids"])
        else:
            text = locator["text"]
        blocks.append(EvidenceBlock(id=locator["block_id"], page=locator["page"], section=locator["section"], text=text))
    return blocks


def draft(case: dict) -> dict:
    return {"title": "شرح RAG", "sections": [case["section"]]}


def test_cases_are_bound_to_the_reviewed_rag_source():
    assert CASES["truth_source"]["revision"] == TRUTH["revision"]
    assert CASES["source"] == {key: TRUTH["source"][key] for key in ("paper_id", "sha256", "parser_revision")}


def test_locators_use_only_reviewed_excerpts_or_a_verified_native_extract():
    evidence = {item["id"]: item for item in TRUTH["evidence"]}
    comparison = TRUTH["reviewed_comparison"]
    for locator in CASES["locators"]:
        if locator["construction"] == "reviewed_excerpts":
            assert locator["evidence_ids"]
            for identity in locator["evidence_ids"]:
                assert (evidence[identity]["block_id"], evidence[identity]["page"]) == (locator["block_id"], locator["page"])
        else:
            assert locator["construction"] == "native_extract_excerpt"
            assert (comparison["block_id"], comparison["page"]) == (locator["block_id"], locator["page"])
            # The reviewed comparison must be readable in the excerpt itself.
            for value in comparison["values"].values():
                assert str(value) in locator["text"]
            assert comparison["split"] in locator["text"] and len(locator["text"]) <= 450


LOCAL_PDF = ROOT / "data/study/sources/b4a081248864de48638444aec3a678250d63e10d77b0d824160c77017bccdf39.pdf"


@pytest.mark.skipif(not LOCAL_PDF.is_file(), reason="optional ignored source PDF; CI uses the stored excerpt")
def test_native_excerpts_are_exact_substrings_of_the_reviewed_pdf_extraction():
    import hashlib

    from src.services.study.content import _worker

    assert hashlib.sha256(LOCAL_PDF.read_bytes()).hexdigest() == CASES["source"]["sha256"]
    raw = _worker(LOCAL_PDF, "extract")
    assert raw["parser_revision"] == CASES["source"]["parser_revision"]
    blocks = {block["id"]: block["text"] for block in raw["blocks"]}
    for locator in CASES["locators"]:
        if locator["construction"] == "native_extract_excerpt":
            assert locator["text"] in blocks[locator["block_id"]]


def test_case_records_are_unique_and_inspectable():
    ids = [case["id"] for case in CASES["cases"]]
    assert len(ids) == len(set(ids))
    for case in CASES["cases"]:
        assert case["polarity"] in {"supported", "critical_error"}
        assert case["class"] in CRITICAL_CLASSES
        expected = case["expected"]
        if case["polarity"] == "supported":
            assert expected == {"deterministic": "kept", "review": "accept"}
        elif expected["deterministic"] == "kept":
            # A critical error the offline gate admits must name what the review has to catch.
            assert expected["review"] == "reject" and set(expected["issues"]) <= REVIEW_ISSUES and expected["issues"]
        else:
            assert expected["deterministic"].startswith("withheld:") and "review" not in expected


def test_every_reviewed_rejected_claim_has_a_critical_case():
    reviewed = {claim["id"] for claim in TRUTH["rejected_claims"]}
    used = {case["rejected_claim"] for case in CASES["cases"] if "rejected_claim" in case}
    assert used == reviewed


def test_every_critical_class_is_covered_or_explicitly_open():
    assert set(CASES["critical_classes"]) == CRITICAL_CLASSES
    for name, status in CASES["critical_classes"].items():
        errors = [c for c in CASES["cases"] if c["class"] == name and c["polarity"] == "critical_error"]
        if status == "covered":
            assert errors, name
        else:
            assert status.startswith("open: ") and len(status) > 20 and not errors, name


def test_development_cases_do_not_claim_a_holdout():
    holdout = CASES["holdout"]
    if holdout["status"] == "not_reserved":
        assert len(holdout["reason"]) > 20
    else:
        assert CASES["source"]["paper_id"] not in {paper["paper_id"] for paper in holdout["papers"]}


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda case: case["id"])
def test_offline_validation_matches_the_frozen_outcome(case):
    expected = case["expected"]["deterministic"]
    checked = validate_draft(draft(case), locator_blocks())
    claims = checked.sections[0].claims
    if expected == "kept":
        lesson, withheld = accept_draft(checked)
        written = case["section"]["claims"][0]["text"] if claims else case["section"]["text"]
        assert lesson.sections[0].text == written and withheld == {}
    else:
        reason = expected.removeprefix("withheld:")
        assert [claim.withheld for claim in claims] == [reason]
        with pytest.raises(TutorError, match="lesson_validation_failed") as captured:
            accept_draft(checked)
        assert captured.value.diagnostic == reason


SEMANTIC_ONLY = [case for case in CASES["cases"] if case["expected"].get("review") == "reject"]


class Checker:
    """Scripted claim checker: records the payload and answers every item the same way."""

    def __init__(self, supported, issue="none"):
        self.supported, self.issue, self.payload = supported, issue, None

    async def complete(self, job, purpose, messages, **kwargs):
        self.payload = json.loads(messages[-1]["content"])
        return {"output": {"verdicts": [
            {"id": item["id"], "supported": self.supported, "issue": self.issue,
             "support_spans": honest_spans(item["quote"]) if self.supported and "quote" in item else []}
            for item in self.payload["items"]]}}


@pytest.mark.anyio
@pytest.mark.parametrize("case", SEMANTIC_ONLY, ids=lambda case: case["id"])
async def test_errors_the_offline_gate_admits_reach_the_check_with_their_exact_quote(case):
    blocks = locator_blocks()
    checked = validate_draft(draft(case), blocks)
    checker = Checker(False, case["expected"]["issues"][0])
    result = await check_claims(checker, "science-case", checked, blocks=blocks)
    item = checker.payload["items"][0]
    if case["section"]["kind"] == "paper":
        claim = result.sections[0].claims[0]
        assert item["quote"] == claim.support.quote and claim.withheld == "unsupported"
        assert [block["id"] for block in checker.payload["source_context"]] == [claim.support.block_id]
        with pytest.raises(TutorError, match="lesson_validation_failed"):
            accept_draft(result)
    else:
        assert "analogy" in item and result.sections[0].dropped == "unsupported"


SUPPORTED = [case for case in CASES["cases"] if case["polarity"] == "supported"]


@pytest.mark.anyio
@pytest.mark.parametrize("case", SUPPORTED, ids=lambda case: case["id"])
async def test_verified_correct_sections_survive_an_honest_checker(case):
    blocks = locator_blocks()
    result = await check_claims(Checker(True), "science-case", validate_draft(draft(case), blocks), blocks=blocks)
    lesson, withheld = accept_draft(result)
    assert withheld == {} and lesson.sections[0].text == case["section"]["claims"][0]["text"]


ADMITTED = [case for case in CASES["cases"] if case["expected"]["deterministic"] == "kept"]


@pytest.mark.parametrize("case", ADMITTED, ids=lambda case: case["id"])
def test_first_lesson_screen_matches_the_frozen_outcome(case):
    def screened(question):
        result = screen_claims(validate_draft(draft(case), locator_blocks()), question=question)
        return [claim.withheld for claim in result.sections[0].claims]

    expected = case["expected"].get("screen")
    if case["section"]["kind"] != "paper":
        assert screened("ابدأ درس تمهيدي متكامل عن الورقة.") == [] and not expected
    else:
        assert screened("ابدأ درس تمهيدي متكامل عن الورقة.") == [expected]
        # The same claim is allowed through to the check when the learner asked who is better.
        assert screened("مين الأحسن في TQA-Wiki؟") == [None]
