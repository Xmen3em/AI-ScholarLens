"""How an OpenSearch response becomes a SearchResponse, including when there isn't one."""

import pytest
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import NotFoundError
from src.exceptions import OllamaConnectionError
from src.services.embeddings.ollama import EMBEDDING_DIMENSIONS
from src.services.search import SearchService


def raw_hit(arxiv_id="2608.26469v1", score=4.2, highlight=None, **overrides):
    source = {
        "arxiv_id": arxiv_id,
        "title": "Retrieval Augmented Generation",
        "authors": "Ada Lovelace, Alan Turing",
        "abstract": "We study retrieval.",
        "categories": ["cs.CL", "cs.AI"],
        "published_date": "2026-08-26T00:00:00",
        "pdf_url": "https://arxiv.org/pdf/2608.26469v1",
    }
    source.update(overrides)
    hit = {"_source": source, "_score": score}
    if highlight is not None:
        hit["highlight"] = highlight
    return hit


def response(hits=(), total=None, took=7):
    return {
        "took": took,
        "hits": {"total": {"value": len(hits) if total is None else total}, "hits": list(hits)},
    }


class FakeSearchClient:
    """Returns a canned response, or raises what OpenSearch would raise."""

    def __init__(self, result=None, raises=None):
        self.result = result if result is not None else response()
        self.raises = raises
        self.requests = []

    def search(self, index, body):
        self.requests.append((index, body))
        if self.raises:
            raise self.raises
        return self.result


class FakeEmbedder:
    """Returns a fixed query vector, or raises what an unreachable Ollama would."""

    def __init__(self, raises=None):
        self.raises = raises
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        if self.raises:
            raise self.raises
        return [0.5] * EMBEDDING_DIMENSIONS


def service(client, embedder=None):
    return SearchService(client, embedder or FakeEmbedder())


# --- shaping the response ---------------------------------------------------


def test_hits_carry_the_paper_and_its_score():
    result = service(FakeSearchClient(response([raw_hit(score=9.5)]))).search_papers("rag")

    assert result.total == 1
    assert result.hits[0].arxiv_id == "2608.26469v1"
    assert result.hits[0].score == 9.5
    assert result.hits[0].categories == ["cs.CL", "cs.AI"]


def test_the_total_is_the_match_count_not_the_page_size():
    result = service(FakeSearchClient(response([raw_hit()], total=347))).search_papers("rag")

    assert (result.total, len(result.hits)) == (347, 1)


def test_the_query_and_the_backend_timing_are_reported_back():
    result = service(FakeSearchClient(response([], took=42))).search_papers("graph neural networks")

    assert result.query == "graph neural networks"
    assert result.took_ms == 42


def test_highlights_are_passed_through():
    highlight = {"title": ["<mark>Retrieval</mark> Augmented Generation"]}
    result = service(FakeSearchClient(response([raw_hit(highlight=highlight)]))).search_papers("retrieval")

    assert result.hits[0].highlights == highlight


def test_a_hit_without_highlights_gets_an_empty_mapping_not_a_null():
    result = service(FakeSearchClient(response([raw_hit()]))).search_papers("rag")

    assert result.hits[0].highlights == {}


@pytest.mark.parametrize("highlight", ["a string", {"title": "not a list"}, {"title": [1, 2]}, 7])
def test_a_malformed_highlight_is_dropped_rather_than_breaking_the_response(highlight):
    result = service(FakeSearchClient(response([raw_hit(highlight=highlight)]))).search_papers("rag")

    assert result.hits[0].highlights == {}


def test_a_date_sorted_hit_has_no_score_but_still_reports_a_number():
    """OpenSearch returns _score: null when a sort replaces relevance ranking."""
    hit = raw_hit()
    hit["_score"] = None
    result = service(FakeSearchClient(response([hit]))).search_papers("", newest_first=True)

    assert result.hits[0].score == 0.0


# --- what reaches OpenSearch ------------------------------------------------


def test_search_arguments_reach_the_query_body():
    client = FakeSearchClient()
    service(client).search_papers("rag", size=25, offset=50, categories=["cs.CL"], newest_first=True)

    _index, body = client.requests[0]
    assert (body["size"], body["from"]) == (25, 50)
    assert body["query"]["bool"]["filter"] == [{"terms": {"categories": ["cs.CL"]}}]
    assert body["sort"][0] == {"published_date": {"order": "desc"}}


def test_the_alias_is_queried_rather_than_a_versioned_index():
    client = FakeSearchClient()
    service(client).search_papers("rag")

    assert client.requests[0][0] == "arxiv-papers"


# --- failure ----------------------------------------------------------------


def test_a_missing_index_is_an_empty_result_not_an_error():
    """Expected on a stack that has never run the ingestion DAG."""
    client = FakeSearchClient(raises=NotFoundError(404, "index_not_found_exception", {}))

    result = service(client).search_papers("rag")

    assert (result.total, result.hits) == (0, [])


def test_an_unreachable_backend_propagates():
    """Reported as a 503 by the router; swallowing it would look like 'no papers match'."""
    client = FakeSearchClient(raises=OpenSearchConnectionError("N/A", "refused", Exception()))

    with pytest.raises(OpenSearchConnectionError):
        service(client).search_papers("rag")


# --- hybrid search ----------------------------------------------------------


def chunk_hit(doc_id, arxiv_id="2608.26469v1", **overrides):
    source = {
        "arxiv_id": arxiv_id,
        "title": "Active Curriculum Refinement",
        "section_title": "2.1 Reinforcement Learning",
        "section_index": 4,
        "chunk_index": 0,
        "content": "In many reinforcement learning domains...",
        "categories": ["cs.LG"],
        "published_date": "2026-08-26T00:00:00",
    }
    source.update(overrides)
    return {"_id": doc_id, "_source": source, "_score": 3.0}


class TwoResponseClient:
    """Answers the keyword query then the vector query, recording both bodies."""

    def __init__(self, keyword_ids, semantic_ids):
        self.responses = [
            response([chunk_hit(i) for i in keyword_ids]),
            response([chunk_hit(i) for i in semantic_ids]),
        ]
        self.bodies = []

    def search(self, index, body):
        self.bodies.append(body)
        return self.responses[min(len(self.bodies) - 1, len(self.responses) - 1)]


def test_hybrid_ranks_a_passage_both_halves_agree_on_first():
    client = TwoResponseClient(keyword_ids=["a", "b", "c"], semantic_ids=["c", "b", "d"])

    result = service(client).search_hybrid("rag", size=4)

    assert [hit.arxiv_id for hit in result.hits] and result.mode == "hybrid"
    assert result.total == 4  # a, b, c, d


def test_hybrid_scores_are_the_fused_score_not_bm25():
    client = TwoResponseClient(keyword_ids=["a"], semantic_ids=["a"])

    result = service(client).search_hybrid("rag")

    assert result.hits[0].score == pytest.approx(2 / (60 + 1))


def test_both_halves_search_deeper_than_the_page_being_served():
    """Fusion can only reorder what it is given."""
    client = TwoResponseClient(keyword_ids=["a"], semantic_ids=["a"])

    service(client).search_hybrid("rag", size=10)

    keyword_body, vector_body = client.bodies
    assert keyword_body["size"] > 10
    assert vector_body["query"]["knn"]["embedding"]["k"] > 10


def test_the_query_is_embedded_as_a_query_not_as_a_passage():
    embedder = FakeEmbedder()
    service(TwoResponseClient(["a"], ["a"]), embedder).search_hybrid("rag")

    assert embedder.queries == ["rag"]


def test_a_category_filter_reaches_the_vector_half_too():
    client = TwoResponseClient(["a"], ["a"])

    service(client).search_hybrid("rag", categories=["cs.LG"])

    _keyword_body, vector_body = client.bodies
    assert vector_body["query"]["knn"]["embedding"]["filter"] == {"terms": {"categories": ["cs.LG"]}}


def test_an_unreachable_embedding_model_falls_back_to_keyword_results():
    """Worse results beat no results, and the keyword half is complete on its own."""
    client = TwoResponseClient(keyword_ids=["a", "b"], semantic_ids=[])
    embedder = FakeEmbedder(raises=OllamaConnectionError("ollama is down"))

    result = service(client, embedder).search_hybrid("rag")

    assert result.mode == "keyword"
    assert "ollama is down" in result.fallback_reason
    assert len(result.hits) == 2


def test_the_fallback_never_runs_a_vector_query():
    client = TwoResponseClient(keyword_ids=["a"], semantic_ids=[])
    embedder = FakeEmbedder(raises=OllamaConnectionError("down"))

    service(client, embedder).search_hybrid("rag")

    assert len(client.bodies) == 1
    assert "knn" not in str(client.bodies[0])
