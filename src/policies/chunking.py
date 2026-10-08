"""How a stored paper is split into retrievable chunks.

Chunk identity is derived from the split, so two code paths that chunked
differently would write colliding or orphaned documents into the search index.
One implementation, imported everywhere — the same reason ai_scope.py exists.

Dependency-free (stdlib only) so the API image, the Airflow image, and the CLI
can all import it.
"""

import re
from typing import Any, List, NamedTuple, Tuple

# Sized for the retrieval side rather than for storage: ~2000 characters is roughly
# 500 tokens, which fits the context window of the sentence-embedding models this
# corpus will be encoded with, with room for the section title.
MAX_CHUNK_CHARS = 2000

# Carried from the tail of the previous chunk so a passage split mid-argument is
# still recoverable from either side of the cut.
CHUNK_OVERLAP_CHARS = 200

# Below this a "section" is a parser artifact, not prose. Measured on the live
# corpus: all 48 sections under 100 characters were arXiv stamp lines, author
# affiliation blocks, or bare link captions — 2791 characters in total.
MIN_CHUNK_CHARS = 100

# Cut points, coarsest first: paragraph, line, sentence, word.
_CUT_SEPARATORS: Tuple[str, ...] = ("\n\n", "\n", ". ", " ")

# A bibliography is a list of other people's titles. Indexed as body text it matches
# almost any query and grounds nothing, and it is the largest section in the corpus
# (26 of 26 parsed papers, 234k of 1.8M characters). Excluded from retrieval; the
# text stays in papers.sections for whoever extracts citations later.
_BIBLIOGRAPHY_TITLES = frozenset({"references", "reference", "bibliography", "works cited"})

_LEADING_SECTION_NUMBER = re.compile(r"^[\d.\s]+")


class Chunk(NamedTuple):
    """One retrievable passage, positioned within its source paper."""

    section_index: int
    chunk_index: int
    section_title: str
    content: str


def is_bibliography(title: str) -> bool:
    """Whether a section title names a reference list rather than prose.

    Matches the normalized title exactly, so "F.1 FineWeb Reference Text" and
    "ACMReference Format:" — both real section titles in this corpus — are kept.
    """
    return _LEADING_SECTION_NUMBER.sub("", title).strip().strip(".:").lower() in _BIBLIOGRAPHY_TITLES


def chunk_sections(sections: Any) -> List[Chunk]:
    """Split a paper's stored sections into indexable chunks.

    ``section_index`` is the position in the stored array, not in the kept subset, so
    a chunk keeps its identity when the skip rules here change. Malformed entries are
    skipped rather than raising: papers.sections is parser output, and one bad section
    must not cost the paper its other thirty.
    """
    if not isinstance(sections, (list, tuple)):
        return []

    chunks: List[Chunk] = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        title = section.get("title")
        content = section.get("content")
        if not isinstance(title, str) or not isinstance(content, str):
            continue
        if is_bibliography(title):
            continue
        content = content.strip()
        if len(content) < MIN_CHUNK_CHARS:
            continue
        for chunk_index, piece in enumerate(split_text(content)):
            chunks.append(Chunk(section_index, chunk_index, title, piece))
    return chunks


def split_text(text: str, limit: int = MAX_CHUNK_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """Slice text into overlapping windows of at most ``limit`` characters.

    Raises ValueError when the overlap is at least half the limit. _cut_point
    guarantees each window advances by more than ``limit // 2``, so a wider overlap
    would claw back the whole advance and shred the text into single characters —
    a silently useless index rather than a crash, which is worse.
    """
    if overlap >= limit // 2:
        raise ValueError(f"overlap {overlap} must be under half of limit {limit}")

    pieces: List[str] = []
    start = 0
    while start < len(text):
        if len(text) - start <= limit:
            pieces.append(text[start:])
            break
        cut = start + _cut_point(text[start:], limit)
        pieces.append(text[start:cut])
        start = cut - overlap
    return pieces


def _cut_point(text: str, limit: int) -> int:
    """Where to end a chunk: the last natural boundary at or before ``limit``.

    A boundary in the first half of the window is worse than a clean character cut —
    it would leave most of the budget unused and inflate the chunk count — so the
    search stops at the halfway mark and falls back to ``limit``.
    """
    window = text[:limit]
    for separator in _CUT_SEPARATORS:
        boundary = window.rfind(separator)
        if boundary > limit // 2:
            return boundary + len(separator)
    return limit


def chunk_document_id(arxiv_id: str, section_index: int, chunk_index: int) -> str:
    """The search-index document id for a chunk.

    Deterministic so that re-indexing a paper overwrites its chunks instead of
    duplicating them — the ingestion DAG re-runs over the same papers routinely.
    """
    return f"{arxiv_id}:{section_index}:{chunk_index}"

