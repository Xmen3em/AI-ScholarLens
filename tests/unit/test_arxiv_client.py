from urllib.parse import unquote

import httpx
import pytest
from src.config import ArxivSettings
from src.exceptions import ArxivAPIException, ArxivParseError, PDFDownloadException
from src.services.arxiv.client import ArxivClient

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>  A test paper\nwith whitespace  </title>
    <summary>  An abstract\nwith whitespace.  </summary>
    <author><name>Ada Lovelace</name></author>
    <published>2024-01-01T00:00:00Z</published>
    <category term="cs.AI" />
    <link type="application/pdf" href="http://arxiv.org/pdf/2401.00001" />
  </entry>
</feed>"""


def test_feed_entry_maps_to_paper_with_normalized_fields():
    client = ArxivClient(ArxivSettings())

    papers = client._parse_response(ARXIV_FEED)

    assert len(papers) == 1
    assert papers[0].arxiv_id == "2401.00001v1"
    assert papers[0].title == "A test paper with whitespace"
    assert papers[0].authors == ["Ada Lovelace"]
    assert papers[0].categories == ["cs.AI"]
    assert papers[0].pdf_url == "https://arxiv.org/pdf/2401.00001"


def test_malformed_feed_raises_parse_error():
    client = ArxivClient(ArxivSettings())

    with pytest.raises(ArxivParseError):
        client._parse_response("<feed>")


@pytest.mark.anyio
async def test_fetch_papers_queries_configured_category_and_returns_parsed_papers(stub_httpx):
    requests = stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings())

    papers = await client.fetch_papers(max_results=1)

    assert [paper.arxiv_id for paper in papers] == ["2401.00001v1"]
    query = unquote(str(requests[0].url))
    assert f"search_query=cat:{client.search_category}" in query
    assert "max_results=1" in query


@pytest.mark.anyio
async def test_fetch_papers_filters_by_submission_date_window(stub_httpx):
    requests = stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings())

    await client.fetch_papers(max_results=1, from_date="20240101", to_date="20240102")

    assert "submittedDate:[202401010000+TO+202401022359]" in unquote(str(requests[0].url))


@pytest.mark.parametrize("bad_date", ["2024-01-01", "01/01/2024", "20240132", "2024"])
@pytest.mark.anyio
async def test_fetch_papers_rejects_dates_arxiv_cannot_parse(stub_httpx, bad_date):
    requests = stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings())

    with pytest.raises(ArxivAPIException, match="YYYYMMDD"):
        await client.fetch_papers(max_results=1, from_date=bad_date, to_date=bad_date)

    assert requests == [], "a malformed date window must fail before the request is sent"


@pytest.mark.anyio
async def test_fetch_papers_maps_http_error_status_to_arxiv_exception(stub_httpx):
    stub_httpx(lambda request: httpx.Response(503))
    client = ArxivClient(ArxivSettings())

    with pytest.raises(ArxivAPIException):
        await client.fetch_papers(max_results=1)


@pytest.mark.anyio
async def test_download_pdf_returns_cached_file(writable_cache_dir, arxiv_paper):
    client = ArxivClient(ArxivSettings(pdf_cache_dir=str(writable_cache_dir)))
    cached_pdf = writable_cache_dir / "2401.00001.pdf"
    cached_pdf.write_bytes(b"%PDF-cached")

    result = await client.download_pdf(arxiv_paper)

    assert result == cached_pdf


def cache_client(cache_dir) -> ArxivClient:
    """Client with rate limiting disabled so download tests do not sleep."""
    return ArxivClient(ArxivSettings(pdf_cache_dir=str(cache_dir), rate_limit_delay=0.0))


@pytest.mark.anyio
async def test_truncated_cached_pdf_is_discarded_and_redownloaded(stub_httpx, writable_cache_dir, arxiv_paper):
    # A download that died mid-stream used to leave its partial bytes at the cache path,
    # where every later run served them and Docling failed with "PDFium: Data format error".
    cached_pdf = writable_cache_dir / "2401.00001.pdf"
    cached_pdf.write_bytes(b"<!DOCTYPE html><html>gateway timeout")
    requests = stub_httpx(lambda request: httpx.Response(200, content=b"%PDF-1.4 fresh download"))

    result = await cache_client(writable_cache_dir).download_pdf(arxiv_paper)

    assert result == cached_pdf
    assert cached_pdf.read_bytes() == b"%PDF-1.4 fresh download"
    assert len(requests) == 1


@pytest.mark.anyio
async def test_failed_download_leaves_nothing_in_the_cache(stub_httpx, writable_cache_dir, arxiv_paper):
    stub_httpx(lambda request: httpx.Response(200, content=b"<html>not a pdf</html>"))
    client = cache_client(writable_cache_dir)

    with pytest.raises(PDFDownloadException):
        await client.download_pdf(arxiv_paper)

    assert list(writable_cache_dir.iterdir()) == [], "a failed download must not poison the cache"


@pytest.mark.anyio
async def test_completed_download_is_cached_without_leftovers(stub_httpx, writable_cache_dir, arxiv_paper):
    stub_httpx(lambda request: httpx.Response(200, content=b"%PDF-1.4 body"))

    result = await cache_client(writable_cache_dir).download_pdf(arxiv_paper)

    assert result.read_bytes() == b"%PDF-1.4 body"
    assert [path.name for path in writable_cache_dir.iterdir()] == ["2401.00001.pdf"]
