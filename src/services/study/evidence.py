"""Stable, exact source snippets: models select IDs; the server copies quotations."""

from src.services.study.content import EvidenceBlock

SNIPPET_CHARS = 450


def _spans(text: str) -> list[tuple[int, int]]:
    # Cut at whitespace so a quotation never starts or ends inside a word; a run
    # with no space in the last third (a URL, a long token) is still cut at the limit.
    spans, start = [], 0
    while start < len(text):
        end = min(start + SNIPPET_CHARS, len(text))
        if end < len(text) and not text[end].isspace():
            space = text.rfind(" ", start + SNIPPET_CHARS * 2 // 3, end)
            if space > start:
                end = space
        spans.append((start, end))
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return spans


def evidence_catalog(blocks: list[EvidenceBlock]) -> list[dict]:
    catalog = []
    for block in blocks:
        for part, (start, end) in enumerate(_spans(block.text)):
            quote = block.text[start:end].strip()
            if len(quote) >= 8:
                catalog.append({"id": f"{block.id}s{part}", "block_id": block.id, "page": block.page,
                                "section": block.section, "quote": quote})
    return catalog


def tool_block(block: EvidenceBlock) -> dict:
    return {"id": block.id, "page": block.page, "section": block.section, "evidence": evidence_catalog([block])}
