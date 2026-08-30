from urllib.parse import unquote

import httpx
import pytest
from src.config import ArxivSettings
from src.exceptions import ArxivAPIException, ArxivParseError, PDFDownloadException
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST, ai_scope_query
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
async def test_fetch_papers_queries_the_whole_ai_allowlist_and_returns_parsed_papers(stub_httpx):
    requests = stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings())

    papers = await client.fetch_papers(max_results=1)

    assert [paper.arxiv_id for paper in papers] == ["2401.00001v1"]
    query = unquote(str(requests[0].url))
    assert (
        "search_query=(cat:cs.AI OR cat:cs.CL OR cat:cs.CV OR cat:cs.LG "
        "OR cat:cs.MA OR cat:cs.NE OR cat:cs.RO OR cat:stat.ML)" in query
    )
    assert "max_results=1" in query


@pytest.mark.anyio
async def test_fetch_papers_asks_for_every_allowlisted_category(stub_httpx):
    """A category silently dropped from the query is a silently shrunken corpus."""
    requests = stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings())

    await client.fetch_papers(max_results=1)

    query = unquote(str(requests[0].url))
    assert all(f"cat:{category}" in query for category in AI_CATEGORY_ALLOWLIST)


@pytest.mark.anyio
async def test_fetch_papers_filters_by_submission_date_window(stub_httpx):
    requests = stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings())

    await client.fetch_papers(max_results=1, from_date="20240101", to_date="20240102")

    assert "submittedDate:[202401010000+TO+202401022359]" in unquote(str(requests[0].url))


@pytest.mark.anyio
async def test_date_window_is_ANDed_against_the_grouped_category_clause(stub_httpx):
    """The group must stay parenthesised, or AND would bind to the last category only."""
    requests = stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings())

    await client.fetch_papers(max_results=1, from_date="20240101", to_date="20240102")

    query = unquote(str(requests[0].url))
    assert f"search_query={ai_scope_query()} AND submittedDate:[202401010000+TO+202401022359]" in query


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


def recording_async_client(monkeypatch, handler):
    """Patch httpx.AsyncClient and capture the keyword arguments it was built with."""
    real_client_cls = httpx.AsyncClient
    captured: dict = {}

    def factory(*args, **kwargs):
        captured.update(kwargs)
        kwargs.pop("transport", None)
        return real_client_cls(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return captured


@pytest.mark.parametrize(
    "call",
    [
        lambda client: client.fetch_papers(max_results=1),
        lambda client: client.fetch_papers_with_query("cat:cs.AI", max_results=1),
        lambda client: client.fetch_paper_by_id("2401.00001"),
    ],
    ids=["fetch_papers", "fetch_papers_with_query", "fetch_paper_by_id"],
)
@pytest.mark.anyio
async def test_every_arxiv_request_carries_the_configured_timeout(monkeypatch, call):
    """fetch_paper_by_id used a bare client, so a stalled connection never timed out."""
    captured = recording_async_client(monkeypatch, lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings(rate_limit_delay=0.0, timeout_seconds=7))

    await call(client)

    assert captured["timeout"] == 7


@pytest.mark.parametrize(
    "call",
    [
        lambda client: client.fetch_papers(max_results=1),
        lambda client: client.fetch_papers_with_query("cat:cs.AI", max_results=1),
        lambda client: client.fetch_paper_by_id("2401.00001"),
    ],
    ids=["fetch_papers", "fetch_papers_with_query", "fetch_paper_by_id"],
)
@pytest.mark.anyio
async def test_every_arxiv_request_waits_out_the_rate_limit(stub_httpx, monkeypatch, call):
    """arXiv asks for 3 seconds between requests; fetch_paper_by_id never waited."""
    slept: list[float] = []

    async def record_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("src.services.arxiv.client.asyncio.sleep", record_sleep)
    stub_httpx(lambda request: httpx.Response(200, text=ARXIV_FEED))
    client = ArxivClient(ArxivSettings(rate_limit_delay=3.0))

    await call(client)  # first request has nothing to wait for
    assert slept == []

    await call(client)  # second request must be spaced out
    assert len(slept) == 1 and 0 < slept[0] <= 3.0
