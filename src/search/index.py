"""The OpenSearch index that holds paper chunks."""

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

CHUNK_INDEX_BODY: Dict[str, Any] = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            # Single-node cluster: an unassignable replica would leave the index
            # yellow forever and make cluster health useless as a signal.
            "number_of_replicas": 0,
        }
    },
    "mappings": {
        # An unmapped field is a defect in the indexer, and a dynamic mapping would
        # guess its type from the first document that carried it.
        "dynamic": "strict",
        "properties": {
            "arxiv_id": {"type": "keyword"},
            "title": {"type": "text"},
            "authors": {"type": "keyword"},
            "categories": {"type": "keyword"},
            "published_date": {"type": "date"},
            "section_title": {"type": "text"},
            "section_index": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "content": {"type": "text"},
            "char_count": {"type": "integer"},
            # Stale chunks are deleted by comparing against the current run's stamp,
            # so this is written on every document, not just for observability.
            "indexed_at": {"type": "date"},
        },
    },
}


def ensure_chunk_index(client: OpenSearch) -> None:
    """Create the chunk index and its alias if they are not already there."""
    if client.indices.exists(index=CHUNK_INDEX):
        return
    client.indices.create(index=CHUNK_INDEX, body=CHUNK_INDEX_BODY)
    client.indices.put_alias(index=CHUNK_INDEX, name=CHUNK_ALIAS)
    logger.info("Created index %s behind alias %s", CHUNK_INDEX, CHUNK_ALIAS)
