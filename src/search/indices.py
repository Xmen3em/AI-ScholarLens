"""The OpenSearch indices this corpus writes.

Two, for two different questions. ``arxiv-papers`` answers "which papers are about
X", scoring a whole paper on its title, abstract, and authors. ``paper-chunks``
answers "which passage says X", scoring a few hundred words at a time. One index
cannot do both: BM25 normalizes by field length, so a paper-sized document buries
the passage that actually matched, and a passage-sized document has no title or
abstract to weight.
"""

import logging
from typing import Any, Dict, List

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from src.services.embeddings.ollama import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

# Writes and reads both go through the alias. The concrete index carries a version
# suffix because an OpenSearch mapping cannot be changed in place: a field type
# change means building the next index and repointing the alias. An alias cannot
# share a name with an existing index, so it has to exist from the first write or
# that option is gone for good.
# v2 added the embedding and content_hash fields; a mapping cannot gain a
# knn_vector in place, so the alias moved rather than the index changing.
CHUNK_INDEX = "paper-chunks-v2"
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

# knn has to be switched on at index creation; it cannot be added to a live index.
_VECTOR_SETTINGS: Dict[str, Any] = {
    "index": {"number_of_shards": 1, "number_of_replicas": 0, "knn": True},
    "analysis": _ANALYSIS,
}

CHUNK_INDEX_BODY: Dict[str, Any] = {
    "settings": _VECTOR_SETTINGS,
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
            # Embedding a passage costs about two thirds of a second on CPU, so a full
            # rewrite reuses the stored vector whenever this hash still matches the
            # passage text. Without it every pass would re-embed the whole corpus.
            "content_hash": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIMENSIONS,
                "method": {
                    "name": "hnsw",
                    # Cosine, because nomic-embed-text vectors are not unit length and
                    # a dot product would then rank by magnitude as much as direction.
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                    "parameters": {"ef_construction": 256, "m": 16},
                },
            },
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
    """Create the index if it is absent. The alias is moved separately, once it is full."""
    if client.indices.exists(index=index):
        return
    client.indices.create(index=index, body=body)
    logger.info("Created index %s", index)


def point_alias_at(client: OpenSearch, alias: str, index: str) -> List[str]:
    """Move ``alias`` onto ``index``, and report which indices it left.

    One atomic update_aliases call, so no request ever sees the alias pointing at
    nothing or at two indices at once. Called only after a clean rewrite: until then
    searches keep hitting the previous index, which still holds complete results.
    """
    try:
        current = [name for name in client.indices.get_alias(name=alias) if name != index]
    except NotFoundError:
        current = []

    if current == [] and client.indices.exists_alias(name=alias, index=index):
        return []

    actions: List[Dict[str, Any]] = [{"remove": {"index": name, "alias": alias}} for name in current]
    actions.append({"add": {"index": index, "alias": alias}})
    client.indices.update_aliases(body={"actions": actions})
    logger.info("Alias %s now points at %s (was %s)", alias, index, current or "nothing")
    return current
