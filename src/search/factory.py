"""Construction of the OpenSearch client, mirroring src/db/factory.py."""

from opensearchpy import OpenSearch
from src.config import get_settings


def make_search_client() -> OpenSearch:
    settings = get_settings()
    return OpenSearch(
        hosts=[settings.opensearch_host],
        # The cluster is reached over the internal Docker network with no auth; a
        # retry on timeout is what stands between a slow bulk write and a failed DAG run.
        retry_on_timeout=True,
        max_retries=3,
        timeout=30,
    )
