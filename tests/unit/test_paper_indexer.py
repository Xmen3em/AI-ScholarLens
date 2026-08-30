"""One document per paper, including the papers whose PDF never parsed."""

from datetime import datetime, timezone

import pytest
from src.repositories.paper import SearchableRow
from src.search.indices import PAPER_ALIAS, PAPER_INDEX
from src.services.paper_indexer import PaperIndexer

from tests.unit.test_chunk_indexer import FakeSearchClient

_UNSET = object()


def paper(arxiv_id="2608.26469v1", authors=_UNSET, categories=_UNSET):
    return SearchableRow(
        arxiv_id=arxiv_id,
        title="Retrieval Augmented Generation",
        authors=["Ada Lovelace", "Alan Turing"] if authors is _UNSET else authors,
        abstract="We study retrieval.",
        categories=["cs.CL", "cs.AI"] if categories is _UNSET else categories,
        published_date=datetime(2026, 8, 26, tzinfo=timezone.utc),
        pdf_url="https://arxiv.org/pdf/2608.26469v1",
    )


class FakeRepository:
    def __init__(self, papers):
        self.papers = papers

    def list_searchable(self):
        return self.papers


def index(papers, client=None):
    client = client or FakeSearchClient(existing_indices=(PAPER_INDEX,))
    return client, PaperIndexer(client, FakeRepository(papers)).index_corpus()


def test_each_paper_becomes_one_document_keyed_by_its_arxiv_id():
    client, run = index([paper("2608.00001v1"), paper("2608.00002v1")])

    assert run.documents_indexed == 2
    assert sorted(client.documents) == ["2608.00001v1", "2608.00002v1"]


def test_documents_carry_exactly_the_mapped_fields():
    client, _ = index([paper()])
    _index_name, source = next(iter(client.documents.values()))

    assert set(source) == {
        "arxiv_id", "title", "authors", "abstract", "categories", "published_date", "pdf_url", "indexed_at",
    }


def test_the_full_document_text_is_not_duplicated_into_the_paper_index():
    """raw_text lives in the chunk index, split into passages; a second copy here would double it."""
    client, _ = index([paper()])
    _index_name, source = next(iter(client.documents.values()))

    assert "raw_text" not in source
    assert "sections" not in source


def test_authors_are_joined_so_one_name_can_match_inside_the_list():
    client, _ = index([paper()])
    _index_name, source = next(iter(client.documents.values()))

    assert source["authors"] == "Ada Lovelace, Alan Turing"


@pytest.mark.parametrize("authors", [None, "Ada Lovelace", [{"name": "Ada"}], ["Ada", 7, None]])
def test_malformed_author_columns_do_not_cost_the_paper_its_document(authors):
    client, run = index([paper(authors=authors)])
    _index_name, source = next(iter(client.documents.values()))

    assert run.errors == []
    assert isinstance(source["authors"], str)


def test_an_unparsed_paper_is_still_searchable():
    """Its title and abstract come from arXiv; only its passages are missing."""
    _client, run = index([paper()])

    assert (run.papers_indexed, run.papers_without_documents) == (1, 0)


def test_reindexing_the_same_paper_overwrites_rather_than_duplicates():
    client, _ = index([paper()])
    PaperIndexer(client, FakeRepository([paper()])).index_corpus()

    assert len(client.documents) == 1


def test_a_missing_index_is_created_with_its_alias():
    client = FakeSearchClient(existing_indices=())
    index([paper()], client)

    assert [name for name, _body in client.indices.created] == [PAPER_INDEX]
    assert client.indices.aliases == {PAPER_ALIAS: PAPER_INDEX}


def test_documents_are_written_through_the_alias():
    client, _ = index([paper()])
    index_name, _source = next(iter(client.documents.values()))

    assert index_name == PAPER_ALIAS


def test_stale_cleanup_is_skipped_when_a_paper_failed():
    client = FakeSearchClient(existing_indices=(PAPER_INDEX,), reject_ids={"2608.26469v1"})
    _client, run = index([paper()], client)

    assert client.delete_queries == []
    assert run.errors and run.stale_documents_deleted == 0
