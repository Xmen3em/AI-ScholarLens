import hashlib

import httpx
import pytest
from src.services.study.content import ContentError, PaperContentService, extract_document, render_page
from src.services.study.intake import StudyPaper

from tests.unit.study_helpers import pdf_fixture


def paper():
    return StudyPaper(arxiv_id="1706.03762v7", title="Synthetic attention study", authors=["Test Author"],
                      abstract="This synthetic paper investigates attention in machine learning.",
                      categories=["cs.CL"], published="2017-06-12T17:57:34Z")


def test_real_pdf_extraction_retains_page_provenance_and_content_hash(tmp_path):
    data = pdf_fixture(["Introduction\nThis paper studies attention in machine learning.",
                        "Experiments\nThe method reaches 81 percent accuracy on the synthetic benchmark."])
    path = tmp_path / "source.pdf"; path.write_bytes(data)
    document = extract_document(path, paper())
    assert document.source_sha256 == hashlib.sha256(data).hexdigest()
    assert document.page_count == 2
    assert {block.page for block in document.blocks} == {1, 2}
    assert any("81 percent" in block.text for block in document.blocks)
    assert document.coverage == "full_text"
    assert len({block.id for block in document.blocks}) == len(document.blocks)


def test_scanned_or_empty_pages_are_explicitly_marked_for_ocr(tmp_path):
    path = tmp_path / "scan.pdf"; path.write_bytes(pdf_fixture(["", ""]))
    document = extract_document(path, paper())
    assert document.coverage == "needs_ocr"
    assert document.missing_pages == [1, 2]
    assert document.blocks == []


def test_page_rendering_is_a_bounded_png_from_the_original_document(tmp_path):
    path = tmp_path / "source.pdf"; path.write_bytes(pdf_fixture(["Attention study"]))
    result = render_page(path, 1)
    assert result.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(result) < 2_000_000
    with pytest.raises(ContentError):
        render_page(path, 2)


@pytest.mark.parametrize("payload", [b"not a PDF", pdf_fixture(["page"] * 46)], ids=["invalid", "too_many_pages"])
def test_invalid_and_oversized_page_sets_fail_with_fixed_errors(tmp_path, payload):
    path = tmp_path / "source.pdf"; path.write_bytes(payload)
    with pytest.raises(ContentError):
        extract_document(path, paper())


@pytest.mark.anyio
async def test_download_is_bounded_exact_version_and_reuses_validated_content(tmp_path):
    seen = []
    data = pdf_fixture(["Introduction\nA sufficiently long scientific explanation of a synthetic attention method."])

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=data, headers={"Content-Type": "application/pdf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = PaperContentService(tmp_path / "sources", client)
        first = await service.acquire(paper())
        second = await service.acquire(paper())
    assert first == second
    assert seen == [paper().pdf_url]
    assert len(list((tmp_path / "sources").glob("*.pdf"))) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("status,body,headers", [
    (302, b"", {"Location": "http://127.0.0.1/private"}),
    (200, b"<html>not a PDF</html>", {"Content-Type": "text/html"}),
    (200, b"%PDF-" + b"x" * 101, {"Content-Type": "application/pdf"}),
], ids=["redirect", "html", "size"])
async def test_bad_downloads_do_not_become_cached_sources(tmp_path, status, body, headers):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, content=body, headers=headers)
    )) as client:
        service = PaperContentService(tmp_path / "sources", client, max_bytes=100)
        with pytest.raises(ContentError):
            await service.acquire(paper())
    assert not list((tmp_path / "sources").glob("*.pdf"))
