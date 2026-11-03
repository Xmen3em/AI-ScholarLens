"""Claim-level lesson drafts (docs/specs/claim-check.md). No model call."""

import json

import pytest
from src.services.study.content import EvidenceBlock
from src.services.study.evidence import evidence_catalog
from src.services.study.tutor import TutorError, accept_draft, check_claims, lesson_schema, validate_draft

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


class Checker:
    """A scripted checker: returns fixed verdicts and records what it was sent."""

    def __init__(self, output):
        self.output, self.calls = output, []

    async def complete(self, job, purpose, messages, **kwargs):
        self.calls.append({"purpose": purpose, "payload": json.loads(messages[-1]["content"]), "schema": kwargs["schema"]})
        return {"output": self.output}


SEQ = "نموذج RAG-Sequence سجّل 68.0 في الجدول ده."


def verdict(identity, supported=True, spans=("RAG-Seq. 44.5 56.8/68.0",), issue="none"):
    return {"id": identity, "supported": supported, "support_spans": list(spans), "issue": issue}


async def checked(claims, verdicts, blocks=BLOCKS, extra=()):
    draft = validate_draft(draft_of(paper(*claims), *extra), blocks)
    checker = Checker({"verdicts": verdicts})
    report = {}
    result = await check_claims(checker, "job", draft, blocks=blocks, report=report)
    return result, checker, report


def draft_of(*sections):
    return {"title": "شرح النتايج", "sections": list(sections)}


@pytest.mark.anyio
async def test_honest_spans_keep_the_claim():
    result, checker, report = await checked([claim(SEQ, "p6b1s0")], [verdict("c0")])
    assert result.sections[0].claims[0].withheld is None
    assert checker.calls[0]["purpose"] == "grounding_review"
    assert report["checked"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize("spans", [("RAG-Seq. 99.9 nothing like it",), ("56.8/68.0",), ("RAG-Seq. 44.5 56.8",)],
                         ids=["span-outside-quote", "fewer-than-three-words", "number-outside-spans"])
async def test_supported_without_valid_proof_is_unverified(spans):
    result, _, _ = await checked([claim(SEQ, "p6b1s0")], [verdict("c0", spans=spans)])
    assert result.sections[0].claims[0].withheld == "unverified_support"


@pytest.mark.anyio
async def test_unsupported_verdict_withholds_and_records_its_issue():
    result, _, report = await checked([claim(SEQ, "p6b1s0")], [verdict("c0", supported=False, spans=(), issue="contradiction")])
    assert result.sections[0].claims[0].withheld == "unsupported"
    assert report["issues"] == ["contradiction"]


@pytest.mark.anyio
async def test_duplicate_unknown_or_missing_verdicts_withhold_only_those_claims():
    claims = [claim(SEQ, "p6b1s0"), claim(SEQ.replace("نموذج", "المودل"), "p6b1s0"), claim(SEQ.replace("الجدول", "الصف"), "p6b1s0")]
    result, _, _ = await checked(claims, [verdict("c0"), verdict("c1"), verdict("c1"), verdict("c9")])
    assert [c.withheld for c in result.sections[0].claims] == [None, "missing_verdict", "missing_verdict"]


@pytest.mark.anyio
async def test_unparsable_response_fails_the_review():
    draft = validate_draft(draft_of(paper(claim(SEQ, "p6b1s0"))), BLOCKS)
    with pytest.raises(TutorError, match="review_validation_failed"):
        await check_claims(Checker({"verdicts": "not a list"}), "job", draft, blocks=BLOCKS)


@pytest.mark.anyio
async def test_no_items_means_no_call():
    class Refuse:
        async def complete(self, *args, **kwargs):
            raise AssertionError("no check call expected")

    question = {"heading": "سؤال", "kind": "question", "text": "إيه اللي فهمته من الجدول ده؟", "evidence_ids": [], "claims": []}
    draft = validate_draft(draft_of(paper(claim("جملة بمصدر مش موجود في الورقة خالص.", "p9b9s0")), question), BLOCKS)
    assert await check_claims(Refuse(), "job", draft, blocks=BLOCKS) is draft


@pytest.mark.anyio
async def test_false_analogy_is_dropped_and_counted():
    analogy = {"heading": "تشبيه", "kind": "analogy", "text": "كل token فقرة كاملة بتدوّر عليها من جديد.", "evidence_ids": [], "claims": []}
    result, _, _ = await checked([claim(SEQ, "p6b1s0")], [verdict("c0"), verdict("a0", supported=False, spans=(),
                                 issue="analogy_mismatch")], extra=(analogy,))
    lesson, withheld = accept_draft(result)
    assert [s.kind for s in lesson.sections] == ["paper"] and withheld == {"تشبيه": 1}


@pytest.mark.anyio
async def test_hyphen_and_quote_variants_still_verify():
    result, _, _ = await checked([claim(SEQ.replace("RAG-", "RAG‑"), "p6b1s0")],
                                 [verdict("c0", spans=("RAG‑Seq. 44.5 56.8/68.0",))])
    assert result.sections[0].claims[0].withheld is None


@pytest.mark.anyio
async def test_arabic_indic_digits_count_as_present():
    result, _, _ = await checked([claim("نموذج RAG-Sequence سجّل ٦٨٫٠ في الجدول ده.", "p6b1s0")], [verdict("c0")])
    assert result.sections[0].claims[0].withheld is None


@pytest.mark.anyio
async def test_whitespace_differences_still_verify():
    spaced = [EvidenceBlock(id="p6b1", page=6, section="Table 1", text="RAG-Seq.\n44.5   56.8/68.0 45.2 52.2")]
    result, _, _ = await checked([claim(SEQ, "p6b1s0")], [verdict("c0")], blocks=spaced)
    assert result.sections[0].claims[0].withheld is None


@pytest.mark.anyio
async def test_repeated_block_is_sent_once():
    sections = [paper(*[claim(SEQ, "p6b1s0")] * 5, heading=f"جزء {i}") for i in range(3)]
    draft = validate_draft(draft_of(*sections), BLOCKS)
    checker = Checker({"verdicts": [verdict(f"c{i}") for i in range(15)]})
    await check_claims(checker, "job", draft, blocks=BLOCKS)
    assert [block["id"] for block in checker.calls[0]["payload"]["source_context"]] == ["p6b1"]
    assert len(checker.calls[0]["payload"]["items"]) == 15
