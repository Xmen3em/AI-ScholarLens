import httpx
import pytest
from src.services.study.intake import ArxivIntake, StudyInputError, normalize_input, parse_metadata


@pytest.mark.parametrize("value,expected", [
    ("1706.03762", "1706.03762"),
    ("arXiv:1706.03762v7", "1706.03762v7"),
    ("https://arxiv.org/abs/1706.03762v7", "1706.03762v7"),
    ("https://arxiv.org/pdf/1706.03762v7.pdf", "1706.03762v7"),
    ("https://arxiv.org/html/1706.03762v7#intro", "1706.03762v7"),
    ("hep-th/9901001v2", "hep-th/9901001v2"),
])
def test_supported_identifiers_and_links_have_one_canonical_identity(value, expected):
    assert normalize_input(value) == ("id", expected)


@pytest.mark.parametrize("value", [
    "https://arxiv.org.evil.example/abs/1706.03762", "https://arxiv.org@127.0.0.1/abs/1706.03762",
    "https://127.0.0.1/private", "file:///etc/passwd", "https://arxiv.org:8000/abs/1706.03762",
    "https://arxiv.org/abs/../../private", "1700.12345", "1713.12345", "1706.03762v0", "", "x" * 501,
])
def test_untrusted_urls_invalid_ids_and_oversized_inputs_are_rejected(value):
    with pytest.raises(StudyInputError):
        normalize_input(value)


def test_plain_title_is_not_silently_converted_to_an_identifier():
    assert normalize_input("  Attention   Is All You Need  ") == ("title", "Attention Is All You Need")


def test_many_authors_do_not_reject_an_otherwise_valid_ai_paper():
    source = feed()
    extra = "".join(f"<author><name>Additional author {i}</name></author>" for i in range(35))
    papers = parse_metadata(source.replace("</entry>", extra + "</entry>").encode(), "1706.03762v7")
    assert len(papers[0].authors) == 30
    assert papers[0].author_count == 36


def feed(*, identity="1706.03762v7", category="cs.CL", title="Attention Is All You Need"):
    return f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
    <entry><id>http://arxiv.org/abs/{identity}</id><title>{title}</title>
    <summary>A synthetic metadata fixture about attention.</summary><published>2017-06-12T17:57:34Z</published>
    <author><name>Test Author</name></author><category term="{category}"/>
    <link href="http://arxiv.org/pdf/{identity}" title="pdf"/></entry></feed>'''


@pytest.mark.anyio
async def test_metadata_pins_version_and_uses_only_the_fixed_https_api():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=feed())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        papers = await ArxivIntake(client, delay=0).resolve("1706.03762")
    assert len(papers) == 1
    assert papers[0].arxiv_id == "1706.03762v7"
    assert papers[0].source_url == "https://arxiv.org/abs/1706.03762v7"
    assert papers[0].pdf_url == "https://arxiv.org/pdf/1706.03762v7"
    assert str(requests[0].url).startswith("https://export.arxiv.org/api/query?")
    assert requests[0].url.params["id_list"] == "1706.03762"


@pytest.mark.anyio
@pytest.mark.parametrize("body,code", [
    (feed(identity="1706.03762v6"), "version_mismatch"),
    (feed(identity="1706.03763v7"), "version_mismatch"),
    (feed(category="quant-ph"), "outside_ai_scope"),
    ('<!DOCTYPE feed [<!ENTITY attack "unsafe">]>' + feed(), "invalid_metadata"),
    (feed() + "x" * 600_000, "metadata_too_large"),
], ids=["wrong_version", "wrong_paper", "outside_scope", "entity", "size"])
async def test_untrusted_metadata_cannot_change_requested_paper_or_scope(body, code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))) as client:
        with pytest.raises(StudyInputError) as error:
            await ArxivIntake(client, delay=0).resolve("1706.03762v7")
    assert error.value.code == code


@pytest.mark.anyio
async def test_title_query_is_bounded_and_returns_candidates_without_selecting():
    seen = []

    def handler(request):
        seen.append(request.url.params)
        return httpx.Response(200, text=feed())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        papers = await ArxivIntake(client, delay=0).resolve('Attention " OR all:*')
    assert papers[0].title == "Attention Is All You Need"
    assert seen[0]["max_results"] == "3"
    assert '" OR all:*' not in seen[0]["search_query"]


@pytest.mark.anyio
async def test_redirects_and_provider_error_text_are_not_followed_or_exposed():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"}, text="private upstream text")
    )) as client:
        with pytest.raises(StudyInputError) as error:
            await ArxivIntake(client, delay=0).resolve("1706.03762")
    assert error.value.code == "arxiv_unavailable"
    assert "private" not in str(error.value)
