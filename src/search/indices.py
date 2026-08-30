"""The OpenSearch indices this corpus writes.

Two, for two different questions. ``arxiv-papers`` answers "which papers are about
X", scoring a whole paper on its title, abstract, and authors. ``paper-chunks``
answers "which passage says X", scoring a few hundred words at a time. One index
cannot do both: BM25 normalizes by field length, so a paper-sized document buries
the passage that actually matched, and a passage-sized document has no title or
abstract to weight.
"""

import logging
from typing import Any, Dict

from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)

# Writes and reads both go through the alias. The concrete index carries a version
# suffix because an OpenSearch mapping cannot be changed in place: a field type
# change means building the next index and repointing the alias. An alias cannot
# share a name with an existing index, so it has to exist from the first write or
# that option is gone for good.
CHUNK_INDEX = "paper-chunks-v1"
CHUNK_ALIAS = "paper-chunks"
PAPER_INDEX = "arxiv-papers-v1"
PAPER_ALIAS = "arxiv-papers"

# `text_analyzer` stems with snowball, so a query for "learning" also matches
# "learned". `name_analyzer` only lowercases: stemming a surname turns "Hastie"
# into something no query spells.
_ANALYSIS: Dict[str, Any] = {
    "analyzer": {
        "text_analyzer": {"type": "custom", "tokenizer": "standard", "filter": ["lowercase", "stop", "snowball"]},
        "name_analyzer": {"type": "custom", "tokenizer": "standard", "filter": ["lowercase"]},
    }
}

# Single-node cluster: an unassignable replica would leave every index yellow
# forever and make cluster health useless as a signal.
_SETTINGS: Dict[str, Any] = {"index": {"number_of_shards": 1, "number_of_replicas": 0}, "analysis": _ANALYSIS}

CHUNK_INDEX_BODY: Dict[str, Any] = {
    "settings": _SETTINGS,
    "mappings": {
        # An unmapped field is a defect in the indexer, and a dynamic mapping would
        # guess its type from the first document that carried it.
        "dynamic": "strict",
        "properties": {
            "arxiv_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "text_analyzer"},
            "authors": {"type": "keyword"},
            "categories": {"type": "keyword"},
            "published_date": {"type": "date"},
            "section_title": {"type": "text", "analyzer": "text_analyzer"},
            "section_index": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "content": {"type": "text", "analyzer": "text_analyzer"},
            "char_count": {"type": "integer"},
            # Stale documents are deleted by comparing against the current run's stamp,
            # so this is written on every document, not just for observability.
            "indexed_at": {"type": "date"},
        },
    },
}

PAPER_INDEX_BODY: Dict[str, Any] = {
    "settings": _SETTINGS,
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "arxiv_id": {"type": "keyword"},
            # The keyword sub-field is for exact title lookup and sorting; the analyzed
            # field is what BM25 scores.
            "title": {
                "type": "text",
                "analyzer": "text_analyzer",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            # Text, not keyword: a search for "Lovelace" has to match one name inside
            # a list of thirty.
            "authors": {"type": "text", "analyzer": "name_analyzer"},
            "abstract": {"type": "text", "analyzer": "text_analyzer"},
            "categories": {"type": "keyword"},
            "published_date": {"type": "date"},
            "pdf_url": {"type": "keyword"},
            "indexed_at": {"type": "date"},
        },
    },
}


def ensure_chunk_index(client: OpenSearch) -> None:
    """Create the chunk index and its alias if they are not already there."""
    _ensure_index(client, CHUNK_INDEX, CHUNK_ALIAS, CHUNK_INDEX_BODY)


def ensure_paper_index(client: OpenSearch) -> None:
    """Create the paper index and its alias if they are not already there."""
    _ensure_index(client, PAPER_INDEX, PAPER_ALIAS, PAPER_INDEX_BODY)


def _ensure_index(client: OpenSearch, index: str, alias: str, body: Dict[str, Any]) -> None:
    if client.indices.exists(index=index):
        return
    client.indices.create(index=index, body=body)
    client.indices.put_alias(index=index, name=alias)
    logger.info("Created index %s behind alias %s", index, alias)
