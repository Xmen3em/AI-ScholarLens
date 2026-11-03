"""Claim-level lesson drafts (docs/specs/claim-check.md). No model call."""

import pytest
from src.services.study.content import EvidenceBlock
from src.services.study.evidence import evidence_catalog
from src.services.study.tutor import TutorError, accept_draft, lesson_schema, validate_draft

BLOCKS = [EvidenceBlock(id="p6b0", page=6, section="Table 1", text="RAG-Token 44.1 55.2/66.1 45.5 50.0"),
          EvidenceBlock(id="p6b1", page=6, section="Table 1", text="RAG-Seq. 44.5 56.8/68.0 45.2 52.2")]


def claim(text, evidence_id):
    return {"text": text, "evidence_id": evidence_id}


def paper(*claims, heading="النتيجة"):
    return {"heading": heading, "kind": "paper", "text": "", "evidence_ids": [], "claims": list(claims)}


def draft(*sections):
    return {"title": "شرح النتايج", "sections": list(sections)}


def test_paper_sections_must_use_claims_and_others_must_use_text():
    with_text = paper(claim("النموذج بيسجّل 66.1 في الجدول ده.", "p6b0s0"))
    with_text["text"] = "نص حر من غير جمل منفصلة."
    empty = paper()
    background = {"heading": "خلفية", "kind": "background", "text": "خلفية عامة عن الموضوع.", "evidence_ids": [],
                  "claims": [claim("جملة مش مكانها هنا خالص.", "p6b0s0")]}
    for bad in (with_text, empty, background):
        with pytest.raises(TutorError) as captured:
            validate_draft(draft(bad), BLOCKS)
        assert captured.value.diagnostic == "shape"


def test_unknown_claim_quote_is_withheld_not_fatal():
    kept = "نموذج RAG-Token سجّل 66.1 في الجدول ده بالظبط."
    result = validate_draft(draft(paper(claim(kept, "p6b0s0"), claim("جملة بمصدر مش موجود في الورقة.", "p9b9s0"))), BLOCKS)
    assert [c.withheld for c in result.sections[0].claims] == [None, "unsupported_quote"]
    lesson, withheld = accept_draft(result)
    assert lesson.sections[0].text == kept
    assert [s.block_id for s in lesson.sections[0].evidence] == ["p6b0"]
    assert withheld == {"النتيجة": 1}


def test_numbers_are_checked_against_each_claims_own_quote():
    wrong = claim("نموذج RAG-Token سجّل 68.0 في الجدول ده.", "p6b0s0")
    right = claim("نموذج RAG-Sequence سجّل 68.0 في الجدول ده.", "p6b1s0")
    result = validate_draft(draft(paper(wrong, right)), BLOCKS)
    assert [c.withheld for c in result.sections[0].claims] == ["unsupported_number", None]


def test_lesson_fails_only_when_no_paper_claim_survives():
    result = validate_draft(draft(paper(claim("جملة بمصدر مش موجود في الورقة خالص.", "p9b9s0"))), BLOCKS)
    with pytest.raises(TutorError) as captured:
        accept_draft(result)
    assert captured.value.diagnostic == "unsupported_quote"


def test_schema_offers_catalog_ids_to_claims():
    schema = lesson_schema(BLOCKS)
    assert schema["$defs"]["DraftClaim"]["properties"]["evidence_id"]["enum"] == [e["id"] for e in evidence_catalog(BLOCKS)] + [""]
