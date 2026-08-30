"""What the indexer writes, and what it refuses to delete when a write fails.

The fake client implements the OpenSearch HTTP contract rather than replacing
``helpers.bulk``, so the real serializer runs and a document the strict mapping
would reject shows up here instead of in the DAG.
"""

import json
from datetime import datetime, timezone

import pytest
from opensearchpy.serializer import JSONSerializer
from src.policies.chunking import MAX_CHUNK_CHARS
from src.repositories.paper import IndexableRow
from src.search.indices import CHUNK_ALIAS, CHUNK_INDEX
from src.services.chunk_indexer import ChunkIndexer


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

    def exists(self, index):
        return index in self.existing

    def create(self, index, body):
        self.created.append((index, body))
        self.existing.add(index)

    def put_alias(self, index, name):
        self.aliases[name] = index

    def refresh(self, index):
        self.refreshed.append(index)


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


class FakeRepository:
    def __init__(self, papers):
        self.papers = papers

    def list_indexable(self):
        return self.papers


def index(papers, client=None):
    client = client or FakeSearchClient()
    return client, ChunkIndexer(client, FakeRepository(papers)).index_corpus()


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
        "section_index", "chunk_index", "content", "char_count", "indexed_at",
    }


def test_documents_are_written_through_the_alias():
    client, _ = index([paper()])
    index_name, _source = next(iter(client.documents.values()))

    assert index_name == CHUNK_ALIAS


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


def test_a_clean_pass_deletes_chunks_older_than_this_run():
    before = datetime.now(timezone.utc)
    client, run = index([paper()])

    assert run.stale_documents_deleted == 7
    target, body = client.delete_queries[0]
    assert target == CHUNK_ALIAS
    cutoff = datetime.fromisoformat(body["query"]["range"]["indexed_at"]["lt"])
    assert cutoff >= before


def test_the_index_is_refreshed_before_stale_chunks_are_matched():
    """Without it the query still sees this run's documents at their old stamp."""
    client, _ = index([paper()])

    assert CHUNK_ALIAS in client.indices.refreshed


# --- index creation ---------------------------------------------------------


def test_a_missing_index_is_created_with_its_alias():
    client = FakeSearchClient(existing_indices=())
    index([paper()], client)

    assert [name for name, _body in client.indices.created] == [CHUNK_INDEX]
    assert client.indices.aliases == {CHUNK_ALIAS: CHUNK_INDEX}


def test_an_existing_index_is_left_alone():
    client = FakeSearchClient()
    index([paper()], client)

    assert client.indices.created == []
