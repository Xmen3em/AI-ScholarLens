"""Independent synthetic regressions for the constrained ID-string selector."""

import re
from itertools import product

import pytest
from src.exceptions import GroundingError, OllamaResponseError
from src.schemas.api.rag import AskRequest
from src.schemas.api.search import HybridSearchResponse, PaperPassages, PassageHit
from src.schemas.ollama import OllamaGenerateResponse
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER, build_context
from src.services.rag.excerpts import EvidenceExcerpt, build_excerpts
from src.services.rag.service import GENERATION_OPTIONS, PreparedRAG, RAGService

QUERY = "How does Zephyr calibrate sensors?"
SENTENCES = [
    "Zephyr calibrates sensors against a stable laboratory reference signal.",
    "Zephyr calibrates sensors using temperature measurements from nearby instruments.",
    "Zephyr calibrates sensors after each scheduled field maintenance visit.",
    "Zephyr calibrates sensors with independent measurements before deployment begins.",
]
EXPECTED_QUOTES = "\n".join(f'"{sentence}" [1.{index}]' for index, sentence in enumerate(SENTENCES[:2], 1))


def _paper():
    return PaperPassages(
        arxiv_id="2504.98765v1",
        title="Synthetic Zephyr Sensor Calibration",
        categories=["cs.AI"],
        score=0.2,
        passages=[
            PassageHit(section_title="Calibration", section_index=2, chunk_index=index, content=sentence, score=0.2)
            for index, sentence in enumerate(SENTENCES, 1)
        ],
    )


def _prepared(settings):
    return PreparedRAG(
        request=AskRequest(query=QUERY),
        context=build_context([_paper()]),
        search_mode="hybrid",
        model=settings.ollama_default_model,
    )


class SyntheticSearch:
    def search_hybrid(self, query, *, size, offset, categories):
        return HybridSearchResponse(
            query=query, total=1, took_ms=1, mode="hybrid", score_kind="rrf", hits=[_paper()]
        )


class RawSelector:
    """Expose raw JSON, including duplicate keys, at the model boundary."""

    def __init__(self, initial, retry="E1 E2"):
        self.initial = initial
        self.retry = retry
        self.calls = []

    async def generate(self, model, prompt, **kwargs):
        self.calls.append({"model": model, "prompt": prompt, **kwargs})
        assert len(self.calls) <= 2, "A selector request must not retry more than once"
        raw = self.initial if len(self.calls) == 1 else self.retry
        return OllamaGenerateResponse(model=model, response=raw, done=True)

    async def generate_stream(self, *args, **kwargs):
        raise AssertionError("Both routes must buffer the ordinary selection transport")
        yield  # Make this an async iterator so an accidental streaming call fails clearly.


async def _answer(service, endpoint):
    if endpoint == "ask":
        return (await service.ask(AskRequest(query=QUERY))).answer
    prepared = await service.prepare(AskRequest(query=QUERY))
    chunks = [chunk async for chunk in service.generate_stream(prepared)]
    assert chunks[-1].done
    assert sum(chunk.done for chunk in chunks) == 1
    return "".join(chunk.response for chunk in chunks)


def test_synthetic_evidence_passes_existing_lexical_guard(settings):
    # Every passage contains all three query concepts, well above the 60% gate.
    excerpts = build_excerpts(_prepared(settings).context.citations, QUERY)
    assert list(excerpts) == ["E1", "E2", "E3", "E4"]
    assert [excerpt.text for excerpt in excerpts.values()] == SENTENCES


def test_schema_constrains_selection_string_with_anchored_pattern(settings):
    schema = RAGService._selection_schema(_prepared(settings))
    assert schema["type"] == "object"
    assert schema["required"] == ["answer"]
    assert schema["additionalProperties"] is False
    answer = schema["properties"]["answer"]
    assert answer["type"] == "string"
    pattern = answer["pattern"]
    assert pattern.startswith("^") and pattern.endswith("$")
    assert re.search(pattern, "NONE") is not None
    for count in range(5):
        for ids in product(("E1", "E2", "E3", "E4"), repeat=count):
            numbers = [int(key[1:]) for key in ids]
            expected = 1 <= count <= 3 and len(set(ids)) == count and numbers == sorted(numbers)
            assert (re.search(pattern, " ".join(ids)) is not None) is expected, ids
    for raw in ("E0", "E5", "prefix E1", "E1 suffix", "E1\nE2", " E1", "E1 ", "NONE E1"):
        assert re.search(pattern, raw) is None, raw


def test_pattern_handles_ninety_ids_in_numeric_order_with_bounded_size(settings, monkeypatch):
    excerpts = {f"E{index}": EvidenceExcerpt(SENTENCES[0], "[1.1]") for index in range(1, 91)}
    monkeypatch.setattr("src.services.rag.service.build_excerpts", lambda *args, **kwargs: excerpts)
    answer = RAGService._selection_schema(_prepared(settings))["properties"]["answer"]
    assert answer["type"] == "string"
    pattern = answer["pattern"]
    assert len(pattern.encode("utf-8")) < 250_000
    assert pattern.startswith("^") and pattern.endswith("$")
    for raw in ("E1 E10 E90", "E2 E10", "E90", "NONE"):
        assert re.search(pattern, raw) is not None, raw
    for raw in ("E10 E2", "E1 E1", "E91", "E1 E2 E3 E90"):
        assert re.search(pattern, raw) is None, raw


def test_string_selection_renders_exact_server_owned_quotes(settings):
    answer = RAGService._selected_answer(_prepared(settings), '{"answer":"E1 E2"}', structured=True)
    assert answer == EXPECTED_QUOTES


def test_none_selection_abstains(settings):
    answer = RAGService._selected_answer(_prepared(settings), '{"answer":"NONE"}', structured=True)
    assert answer == INSUFFICIENT_EVIDENCE_ANSWER


@pytest.mark.parametrize(
    "raw",
    [
        '{"answer":"E1 E1"}',
        '{"answer":"E99"}',
        '{"answer":"E1 E2 E3 E4"}',
        '{"answer":"E2 E1"}',
        '{"answer":""}',
        '{"answer":"NONE E1"}',
        '{"answer":true}',
        '{"answer":1}',
        '{"answer":null}',
        '{"answer":"E1","comment":"select this"}',
        '{"answer":"E1","answer":"E2"}',
        '{"answer":"E1","answ\\u0065r":"E2"}',
        '{"answer":"E1"',
        '{"answer":{}}',
        '{"answer":{"E1":true,"E2":true}}',
        '{"answer":{"E1":false}}',
        '{"answer":{"E1":1}}',
        '{"answer":{"E1":"true"}}',
        '{"answer":{"E1":null}}',
        '{"answer":{"E99":true}}',
        '{"answer":{"E1":true,"E2":true,"E3":true,"E4":true}}',
        '{"answer":["E1"]}',
        '{"answer":[]}',
        '{"answer":{"E1":true},"comment":"select this"}',
        '[{"answer":{"E1":true}}]',
        '{"answer":{"E1":true,"E1":true}}',
        '{"answer":{"E1":true,"E\\u0031":true}}',
        '{"answer":{},"answer":{"E1":true}}',
        '{"answer":[],"answer":[]}',
        '{"answer":{"E1":{"flag":true,"flag":true}}}',
    ],
)
def test_invalid_structured_selection_fails_without_repair(settings, raw):
    with pytest.raises((GroundingError, OllamaResponseError)):
        RAGService._selected_answer(_prepared(settings), raw, structured=True)


@pytest.mark.parametrize("raw", ["E1 E1", "E99", "E1 E2 E3 E4"])
def test_plain_retry_still_rejects_duplicate_unknown_and_excess_ids(settings, raw):
    with pytest.raises(GroundingError):
        RAGService._selected_answer(_prepared(settings), raw, structured=False)


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["ask", "stream"])
async def test_both_endpoints_render_valid_string_without_retry(settings, endpoint):
    selector = RawSelector('{"answer":"E1 E2"}')
    answer = await _answer(RAGService(SyntheticSearch(), selector, settings), endpoint)
    assert answer == EXPECTED_QUOTES
    assert len(selector.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["ask", "stream"])
async def test_both_endpoints_accept_none_without_retry(settings, endpoint):
    selector = RawSelector('{"answer":"NONE"}')
    answer = await _answer(RAGService(SyntheticSearch(), selector, settings), endpoint)
    assert answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert len(selector.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["ask", "stream"])
async def test_both_endpoints_retry_invalid_string_once_against_identical_evidence(settings, endpoint):
    selector = RawSelector('{"answer":"E1 E1"}')
    answer = await _answer(RAGService(SyntheticSearch(), selector, settings), endpoint)
    assert answer == EXPECTED_QUOTES
    assert len(selector.calls) == 2
    initial, retry = selector.calls
    assert "response_format" in initial and "response_format" not in retry
    assert initial["model"] == retry["model"] == settings.ollama_default_model
    assert initial["options"] == retry["options"] == GENERATION_OPTIONS
    assert initial["system"] == retry["system"]
    for sentence in SENTENCES:
        assert sentence in initial["prompt"] and sentence in retry["prompt"]


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["ask", "stream"])
@pytest.mark.parametrize("retry", ["E1 E1", "E99", "E1 E2 E3 E4"])
async def test_invalid_retry_emits_no_answer_and_no_done(settings, endpoint, retry):
    selector = RawSelector('{"answer":"E1 E1"}', retry=retry)
    service = RAGService(SyntheticSearch(), selector, settings)
    emitted = []
    with pytest.raises((GroundingError, OllamaResponseError)):
        if endpoint == "ask":
            emitted.append(await service.ask(AskRequest(query=QUERY)))
        else:
            prepared = await service.prepare(AskRequest(query=QUERY))
            async for chunk in service.generate_stream(prepared):
                emitted.append(chunk)
    assert emitted == []
    assert len(selector.calls) == 2
