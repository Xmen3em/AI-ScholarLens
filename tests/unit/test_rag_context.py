import pytest
from pydantic import ValidationError
from src.schemas.api.rag import AskRequest, Citation
from src.schemas.api.search import PaperPassages, PassageHit
from src.services.rag.context import build_context, validate_answer_citations, validate_answer_evidence


def _paper(number: int, passage_lengths: tuple[int, ...] = (20, 20, 20)) -> PaperPassages:
    return PaperPassages(
        arxiv_id=f"2601.0000{number}v2",
        title=f"Paper {number}",
        categories=["cs.AI"],
        score=1 / number,
        passages=[
            PassageHit(
                section_title=f"Section {passage_index}",
                section_index=number,
                chunk_index=passage_index,
                content=str(number) * length,
                score=1 / (number + passage_index),
                highlights={"content": ["must not enter prompt"]},
            )
            for passage_index, length in enumerate(passage_lengths)
        ],
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "x", "top_k": 0},
        {"query": "x", "top_k": 11},
        {"query": "x", "categories": ["hep-th"]},
    ],
)
def test_ask_request_rejects_invalid_controls(payload):
    with pytest.raises(ValidationError):
        AskRequest.model_validate(payload)


def test_context_preserves_leading_passage_from_top_three_then_round_robins():
    context = build_context([_paper(1), _paper(2), _paper(3), _paper(4)], character_budget=500)

    assert [citation.marker for citation in context.citations[:4]] == ["[1.1]", "[2.1]", "[3.1]", "[4.1]"]
    assert context.citations[0].section_index == 1
    assert context.citations[0].chunk_index == 0
    assert context.citations[0].evidence == "1" * 20


def test_context_never_exceeds_evidence_budget_and_does_not_truncate_passages():
    context = build_context([_paper(1, (40, 40)), _paper(2, (40, 40)), _paper(3, (40, 40))], character_budget=125)

    assert sum(len(citation.evidence) for citation in context.citations) == 120
    assert all(len(citation.evidence) == 40 for citation in context.citations)


def test_prompt_contains_only_traceability_fields_and_raw_passages():
    context = build_context([_paper(1, (20,))], character_budget=100)

    assert "[1.1]" in context.prompt_context
    assert "arXiv: 2601.00001v2" in context.prompt_context
    assert "Paper: Paper 1" in context.prompt_context
    assert "Section: Section 0" in context.prompt_context
    assert "Locator: section_index=1, chunk_index=0" in context.prompt_context
    assert "must not enter prompt" not in context.prompt_context
    assert "score" not in context.prompt_context.lower()


def test_sources_are_ordered_deduplicated_pdf_urls():
    context = build_context([_paper(1), _paper(2)], character_budget=500)

    assert context.sources == [
        "https://arxiv.org/pdf/2601.00001.pdf",
        "https://arxiv.org/pdf/2601.00002.pdf",
    ]


def test_grounding_rejects_missing_and_unknown_markers():
    allowed = {"[1.1]", "[2.1]"}

    with pytest.raises(ValueError, match="citation marker"):
        validate_answer_citations("An uncited factual answer.", allowed)
    with pytest.raises(ValueError, match="unknown"):
        validate_answer_citations("Supported [3.1].", allowed)


def test_grounding_accepts_only_known_markers():
    validate_answer_citations("The result follows from both papers [1.1] [2.1].", {"[1.1]", "[2.1]"})


@pytest.fixture
def attribution_evidence():
    # The two methods were conflated in the recorded Week 5 live answers.
    return [
        Citation(marker="[1.1]", arxiv_id="2608.26386v1", title="Co-Evolving Structured Knowledge and Reasoning",
                 section_title="Abstract", section_index=0, chunk_index=0,
                 evidence="We propose KBEVO: a co-evolving framework that jointly learns to construct a structured knowledge base and reason over it."),
        Citation(marker="[3.1]", arxiv_id="2608.00003v1", title="CritICL",
                 section_title="Source-of-Gain Ablation", section_index=1, chunk_index=0,
                 evidence="Generic GPT critique provides critique information without failuremode-specific alignment.\nFinally, shuffled failure labels break the correspondence between failure modes and retrieved critiques."),
    ]


def test_evidence_validation_accepts_exact_excerpts_with_matching_passages(attribution_evidence):
    validate_answer_evidence(
        '"We propose KBEVO: a co-evolving framework that jointly learns to construct a structured knowledge base and reason over it." [1.1]\n\n'
        '- "Generic GPT critique provides critique information without failuremode-specific alignment. Finally, shuffled failure labels break the correspondence between failure modes and retrieved critiques." [3.1]',
        attribution_evidence,
    )


@pytest.mark.parametrize("answer", [
    '"We propose KBEVO: a co-evolving framework that jointly learns to construct a structured knowledge base and reason over it." [3.1]',
    '"KBEVO reduces hallucination by using generic GPT critique." [1.1]',
    '"We propose KBEVO: a co-evolving framework that jointly learns to construct a structured knowledge base and reason over it." [1.1]\nIt reduces hallucinations [3.1].',
    'These papers use dense correct-exemplar retrieval and generic GPT critique [1.1].',
])
def test_evidence_validation_rejects_misattributed_and_unsupported_claims(attribution_evidence, answer):
    with pytest.raises(ValueError):
        validate_answer_evidence(answer, attribution_evidence)


def test_insufficient_evidence_is_allowed_only_as_the_fixed_abstention(attribution_evidence):
    validate_answer_evidence("The retrieved evidence is insufficient to answer this question.", attribution_evidence)
    with pytest.raises(ValueError):
        validate_answer_evidence("The retrieved evidence is insufficient to answer this question. But KBEVO fixes it [1.1].", attribution_evidence)
