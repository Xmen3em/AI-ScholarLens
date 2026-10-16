"""Isolated PDFium text/render worker; no network, models or settings imports."""

import base64
import io
import json
import re
import sys
from contextlib import closing
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 45
MAX_PAGE_CHARS = 16_000
MAX_TOTAL_CHARS = 250_000
REVISION = "pdfium-5.14.0-v1"


def work(path: Path, action: str, number: int = 1) -> dict:
    import pypdfium2 as pdfium

    if not 0 < path.stat().st_size <= MAX_BYTES or path.read_bytes()[:5] != b"%PDF-":
        raise ValueError("invalid_pdf")
    with pdfium.PdfDocument(path) as document:
        count = len(document)
        if not 1 <= count <= MAX_PAGES:
            raise ValueError("pdf_page_limit")
        if action == "render":
            if not 1 <= number <= count:
                raise ValueError("invalid_pdf_page")
            with closing(document[number - 1]) as page:
                width, height = page.get_size()
                if not 10 <= width <= 20_000 or not 10 <= height <= 20_000:
                    raise ValueError("pdf_dimensions")
                with closing(page.render(scale=min(2.0, 1400 / max(width, height)), may_draw_forms=False)) as bitmap:
                    image = bitmap.to_pil()
                    output = io.BytesIO(); image.save(output, format="PNG"); image.close()
            data = output.getvalue()
            if len(data) > 2_000_000:
                raise ValueError("render_size_limit")
            return {"image": base64.b64encode(data).decode("ascii")}
        blocks, missing, truncated = [], [], []
        total = 0
        for index in range(count):
            with closing(document[index]) as page:
                with closing(page.get_textpage()) as textpage:
                    size = textpage.count_chars()
                    text = textpage.get_text_range(count=min(size, MAX_PAGE_CHARS)) if size else ""
            if size > MAX_PAGE_CHARS:
                truncated.append(index + 1)
            text = "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()
            text = "".join(c for c in text if c.isprintable() or c == "\n")
            if len(re.sub(r"\s", "", text)) < 30:
                missing.append(index + 1)
                continue
            if total + len(text) > MAX_TOTAL_CHARS:
                truncated.extend(range(index + 1, count + 1)); break
            total += len(text)
            heading = text.splitlines()[0]
            section = heading if len(heading) <= 100 else f"Page {index+1}"
            text = " ".join(text.split())
            offset, part = 0, 0
            while offset < len(text):
                end = min(len(text), offset + 1800)
                if end < len(text):
                    end = text.rfind(" ", offset + 1200, end) or end
                    if end <= offset:
                        end = min(len(text), offset + 1800)
                blocks.append({"id": f"p{index+1}b{part}", "page": index + 1, "section": section,
                               "text": text[offset:end].strip(), "origin": "pdf_text"})
                if end == len(text):
                    break
                offset, part = end + 1, part + 1
        coverage = "needs_ocr" if not blocks else "partial_text" if missing or truncated else "full_text"
        return {"page_count": count, "blocks": blocks, "missing_pages": missing,
                "truncated_pages": sorted(set(truncated)), "coverage": coverage, "parser_revision": REVISION}


def main():
    try:
        if len(sys.argv) not in {3, 4} or sys.argv[2] not in {"extract", "render"}:
            raise ValueError
        result = work(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]) if len(sys.argv) == 4 else 1)
        print(json.dumps(result, ensure_ascii=True))
    except Exception:
        print('{"error":"pdf_processing_failed"}')
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
