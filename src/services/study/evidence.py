"""Stable, exact source snippets: models select IDs; the server copies quotations."""

from src.services.study.content import EvidenceBlock


def evidence_catalog(blocks: list[EvidenceBlock]) -> list[dict]:
    catalog = []
    for block in blocks:
        for part, start in enumerate(range(0, len(block.text), 450)):
            quote = block.text[start:start + 450].strip()
            if len(quote) >= 8:
                catalog.append({"id": f"{block.id}s{part}", "block_id": block.id, "page": block.page,
                                "section": block.section, "quote": quote})
    return catalog


def tool_block(block: EvidenceBlock) -> dict:
    return {"id": block.id, "page": block.page, "section": block.section, "evidence": evidence_catalog([block])}
