"""What the indexer writes, and what it refuses to delete when a write fails.

The fake client implements the OpenSearch HTTP contract rather than replacing
``helpers.bulk``, so the real serializer runs and a document the strict mapping
would reject shows up here instead of in the DAG.
"""

import json
from datetime import datetime, timezone

import pytest
from opensearchpy.exceptions import NotFoundError
from opensearchpy.serializer import JSONSerializer
from src.exceptions import EmbeddingError
from src.policies.chunking import MAX_CHUNK_CHARS
from src.repositories.paper import IndexableRow
from src.search.indices import CHUNK_ALIAS, CHUNK_INDEX
from src.services.chunk_indexer import ChunkIndexer, content_hash
from src.services.embeddings.ollama import EMBEDDING_DIMENSIONS


def prose(chars=400):
    sentences = []
    while sum(len(s) for s in sentences) < chars:
        sentences.append(f"Experiment {len(sentences)} evaluated the model on the benchmark suite. ")
    return "".join(sentences)[:chars]


# None is a value under test for every JSON column here, so it cannot double as
# "argument omitted".
_UNSET = object()


def paper(arxiv_id="2608.26469v1", sections=_UNSET, authors=_UNSET, categories=_UNSET):
    return IndexableRow(
        arxiv_id=arxiv_id,
        title="A Paper",
        authors=["Ada Lovelace"] if authors is _UNSET else authors,
        categories=["cs.AI"] if categories is _UNSET else categories,
        published_date=datetime(2026, 8, 26, tzinfo=timezone.utc),
        sections=[{"title": "Method", "content": prose()}] if sections is _UNSET else sections,
    )


class FakeIndices:
    def __init__(self, existing):
        self.existing = set(existing)
        self.created = []
        self.aliases = {}
        self.refreshed = []
        self.alias_actions = []

    def exists(self, index):
        return index in self.existing

    def create(self, index, body):
        self.created.append((index, body))
        self.existing.add(index)

    def refresh(self, index):
        self.refreshed.append(index)

    def get_alias(self, name):
        if name not in self.aliases:
            raise NotFoundError(404, "alias_not_found_exception", {})
        return {self.aliases[name]: {"aliases": {name: {}}}}

    def exists_alias(self, name, index):
        return self.aliases.get(name) == index

    def update_aliases(self, body):
        self.alias_actions.append(body["actions"])
        for action in body["actions"]:
            if "remove" in action:
                self.aliases.pop(action["remove"]["alias"], None)
            if "add" in action:
                self.aliases[action["add"]["alias"]] = action["add"]["index"]


class FakeEmbedder:
    """Deterministic vectors, and a record of exactly which passages were embedded."""

    def __init__(self, raises=None):
        self.embedded = []
        self.raises = raises

    def embed_documents(self, texts):
        if self.raises:
            raise self.raises
        self.embedded.extend(texts)
        return [[float(len(text) % 7)] * EMBEDDING_DIMENSIONS for text in texts]

    def embed_query(self, text):
        if self.raises:
            raise self.raises
        return [0.5] * EMBEDDING_DIMENSIONS


class FakeTransport:
    """The one attribute opensearchpy's bulk helper reaches through the client for."""

    serializer = JSONSerializer()


class FakeSearchClient:
    """Records documents; rejects any whose ``_id`` is in ``reject_ids``."""

    def __init__(self, existing_indices=(CHUNK_INDEX,), reject_ids=()):
        self.transport = FakeTransport()
        self.indices = FakeIndices(existing_indices)
        self.reject_ids = set(reject_ids)
        self.documents = {}
        self.delete_queries = []

    def bulk(self, body, **kwargs):
        items = []
        lines = body.strip().split("\n")
        for header_line, source_line in zip(lines[::2], lines[1::2]):
            header = json.loads(header_line)["index"]
            if header["_id"] in self.reject_ids:
                items.append({"index": {**header, "status": 400, "error": {"type": "strict_dynamic_mapping_exception"}}})
                continue
            self.documents[header["_id"]] = (header["_index"], json.loads(source_line))
            items.append({"index": {**header, "status": 201}})
        return {"errors": any(i["index"]["status"] >= 400 for i in items), "items": items}

    def delete_by_query(self, index, body, **kwargs):
        self.delete_queries.append((index, body))
        return {"deleted": 7}

    def mget(self, index, body, _source=None):
        docs = []
        for document_id in body["ids"]:
            stored = self.documents.get(document_id)
            if stored is None:
                docs.append({"_id": document_id, "found": False})
                continue
            source = stored[1]
            docs.append({"_id": document_id, "found": True,
                         "_source": {k: source[k] for k in (_source or source) if k in source}})
        return {"docs": docs}


class FakeRepository:
    def __init__(self, papers):
        self.papers = papers

    def list_indexable(self):
        return self.papers


def index(papers, client=None, embedder=None):
    client = client or FakeSearchClient()
    return client, ChunkIndexer(client, FakeRepository(papers), embedder or FakeEmbedder()).index_corpus()


# --- what gets written ------------------------------------------------------


def test_a_paper_becomes_one_document_per_chunk():
    client, run = index([paper(sections=[{"title": "Method", "content": prose(MAX_CHUNK_CHARS * 2)}])])

    assert run.documents_indexed == len(client.documents) > 1
    assert run.papers_indexed == 1
    assert sorted(client.documents) == ["2608.26469v1:0:0", "2608.26469v1:0:1", "2608.26469v1:0:2"]


def test_documents_carry_exactly_the_mapped_fields():
    client, _ = index([paper()])
    _index_name, source = next(iter(client.documents.values()))

    assert set(source) == {
        "arxiv_id", "title", "authors", "categories", "published_date", "section_title",
        "section_index", "chunk_index", "content", "char_count", "content_hash",
        "embedding", "indexed_at",
    }


def test_documents_are_written_to_the_concrete_index_not_the_alias():
    """The alias must keep serving the previous index until the rewrite is complete."""
    client, _ = index([paper()])
    index_name, _source = next(iter(client.documents.values()))

    assert index_name == CHUNK_INDEX


def test_char_count_matches_the_content_it_describes():
    client, _ = index([paper(sections=[{"title": "Method", "content": prose(MAX_CHUNK_CHARS * 2)}])])

    assert all(source["char_count"] == len(source["content"]) for _, source in client.documents.values())


@pytest.mark.parametrize("authors", [None, "Ada Lovelace", [{"name": "Ada"}], ["Ada", 7, None]])
def test_malformed_json_columns_are_reduced_to_string_lists(authors):
    """A nested object would be rejected by the strict mapping and cost the paper every chunk."""
    client, run = index([paper(authors=authors)])
    _index_name, source = next(iter(client.documents.values()))

    assert run.errors == []
    assert all(isinstance(author, str) for author in source["authors"])


# --- papers with nothing to index -------------------------------------------


@pytest.mark.parametrize("sections", [None, [], [{"title": "References", "content": prose(4000)}]])
def test_a_paper_with_no_indexable_chunks_is_counted_not_indexed(sections):
    client, run = index([paper(sections=sections)])

    assert (run.papers_seen, run.papers_indexed, run.papers_without_documents) == (1, 0, 1)
    assert client.documents == {}


# --- failure handling -------------------------------------------------------


def test_a_rejected_chunk_fails_its_whole_paper_but_not_the_run():
    good, bad = paper("2608.00001v1"), paper("2608.00002v1")
    client = FakeSearchClient(reject_ids={"2608.00002v1:0:0"})
    _client, run = index([good, bad], client)

    assert run.papers_indexed == 1
    assert len(run.errors) == 1
    assert "2608.00002v1" in run.errors[0]
    assert "2608.00001v1:0:0" in client.documents


def test_stale_cleanup_is_skipped_when_any_paper_failed():
    """Otherwise the failed paper's previous, still-good chunks would be deleted."""
    client = FakeSearchClient(reject_ids={"2608.26469v1:0:0"})
    _client, run = index([paper()], client)

    assert client.delete_queries == []
    assert run.stale_documents_deleted == 0
    assert client.indices.alias_actions == [], "a failed rewrite must not become the live index"


def test_a_clean_pass_deletes_chunks_older_than_this_run():
    before = datetime.now(timezone.utc)
    client, run = index([paper()])

    assert run.stale_documents_deleted == 7
    target, body = client.delete_queries[0]
    assert target == CHUNK_INDEX
    cutoff = datetime.fromisoformat(body["query"]["range"]["indexed_at"]["lt"])
    assert cutoff >= before


def test_the_index_is_refreshed_before_stale_chunks_are_matched():
    """Without it the query still sees this run's documents at their old stamp."""
    client, _ = index([paper()])

    assert CHUNK_INDEX in client.indices.refreshed


# --- index creation ---------------------------------------------------------


def test_a_missing_index_is_created_and_the_alias_points_at_it():
    client = FakeSearchClient(existing_indices=())
    index([paper()], client)

    assert [name for name, _body in client.indices.created] == [CHUNK_INDEX]
    assert client.indices.aliases == {CHUNK_ALIAS: CHUNK_INDEX}


def test_an_existing_index_is_left_alone():
    client = FakeSearchClient()
    index([paper()], client)

    assert client.indices.created == []


# --- embeddings -------------------------------------------------------------


def test_every_passage_is_embedded_on_a_first_pass():
    embedder = FakeEmbedder()
    _client, run = index([paper(sections=[{"title": "Method", "content": prose(MAX_CHUNK_CHARS * 2)}])], embedder=embedder)

    assert run.embeddings_computed == 3
    assert run.embeddings_reused == 0
    assert len(embedder.embedded) == 3


def test_an_unchanged_passage_is_never_embedded_twice():
    """Embedding costs about two thirds of a second a passage; a full rewrite would
    otherwise cost a quarter of an hour every run."""
    client = FakeSearchClient()
    index([paper()], client)

    second = FakeEmbedder()
    _client, run = index([paper()], client, embedder=second)

    assert second.embedded == []
    assert (run.embeddings_computed, run.embeddings_reused) == (0, 1)


def test_edited_text_is_re_embedded_but_its_neighbours_are_not():
    client = FakeSearchClient()
    sections = [{"title": "Method", "content": prose(400)}, {"title": "Results", "content": prose(500)}]
    index([paper(sections=sections)], client)

    edited = [{"title": "Method", "content": prose(400)}, {"title": "Results", "content": prose(500) + " One more sentence."}]
    embedder = FakeEmbedder()
    _client, run = index([paper(sections=edited)], client, embedder=embedder)

    assert (run.embeddings_computed, run.embeddings_reused) == (1, 1)
    assert len(embedder.embedded) == 1


def test_the_stored_hash_identifies_the_text_the_vector_came_from():
    client, _ = index([paper()])
    _index_name, source = next(iter(client.documents.values()))

    assert source["content_hash"] == content_hash(source["content"])
    assert len(source["embedding"]) == EMBEDDING_DIMENSIONS


def test_an_embedding_failure_fails_the_run_rather_than_indexing_a_vectorless_passage():
    """A document with no embedding is invisible to vector search but looks indexed."""
    with pytest.raises(EmbeddingError):
        index([paper()], embedder=FakeEmbedder(raises=EmbeddingError("model missing")))


# --- the alias swap ---------------------------------------------------------


def test_the_alias_moves_off_the_previous_index_in_one_action():
    client = FakeSearchClient(existing_indices=())
    client.indices.aliases[CHUNK_ALIAS] = "paper-chunks-v1"
    index([paper()], client)

    assert client.indices.aliases == {CHUNK_ALIAS: CHUNK_INDEX}
    remove, add = client.indices.alias_actions[0]
    assert remove == {"remove": {"index": "paper-chunks-v1", "alias": CHUNK_ALIAS}}
    assert add == {"add": {"index": CHUNK_INDEX, "alias": CHUNK_ALIAS}}


def test_the_previous_index_is_left_in_place_to_roll_back_to():
    client = FakeSearchClient(existing_indices=())
    client.indices.aliases[CHUNK_ALIAS] = "paper-chunks-v1"
    index([paper()], client)

    assert "paper-chunks-v1" not in [name for name, _body in client.indices.created]
    assert client.delete_queries[0][0] == CHUNK_INDEX, "cleanup must not touch the old index"


def test_an_alias_already_in_place_is_not_rewritten():
    client = FakeSearchClient()
    client.indices.aliases[CHUNK_ALIAS] = CHUNK_INDEX
    index([paper()], client)

    assert client.indices.alias_actions == []
