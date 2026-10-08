"""Chunk boundaries decide document identity, so the split has to be reproducible."""

import pytest
from src.policies.chunking import (
    CHUNK_OVERLAP_CHARS,
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    Chunk,
    chunk_document_id,
    chunk_sections,
    is_bibliography,
    split_text,
)


def section(title, content):
    return {"title": title, "content": content}


def prose(chars):
    """Text of exactly the requested length, with sentence boundaries to cut on.

    Every sentence is distinct so that a reassembly test cannot be fooled by
    repeated text matching in the wrong place.
    """
    sentences = []
    length = 0
    while length < chars:
        sentence = f"Experiment {len(sentences)} evaluated the model on the benchmark suite. "
        sentences.append(sentence)
        length += len(sentence)
    return "".join(sentences)[:chars]


# --- bibliography detection -------------------------------------------------


@pytest.mark.parametrize(
    "title",
    ["References", "REFERENCES", "references", "Bibliography", "7 References", "7. REFERENCES", "References:"],
)
def test_bibliography_headings_are_recognized(title):
    assert is_bibliography(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "ACMReference Format:",  # a real section title in this corpus
        "F.1 FineWeb Reference Text",  # appendix content, not a reference list
        "Related Work",
        "",
    ],
)
def test_titles_that_merely_contain_the_word_are_kept(title):
    assert is_bibliography(title) is False


def test_bibliography_sections_are_not_indexed():
    chunks = chunk_sections([section("Introduction", prose(400)), section("References", prose(4000))])

    assert [chunk.section_title for chunk in chunks] == ["Introduction"]


def test_skipped_sections_do_not_shift_the_indices_of_later_ones():
    chunks = chunk_sections([section("References", prose(400)), section("Method", prose(400))])

    assert [chunk.section_index for chunk in chunks] == [1]


# --- splitting --------------------------------------------------------------


def test_a_section_under_the_limit_stays_one_chunk():
    chunks = chunk_sections([section("Method", prose(MAX_CHUNK_CHARS))])

    assert len(chunks) == 1
    assert chunks[0] == Chunk(0, 0, "Method", prose(MAX_CHUNK_CHARS))


def test_every_piece_of_a_long_section_respects_the_limit():
    pieces = split_text(prose(9000))

    assert len(pieces) > 1
    assert all(len(piece) <= MAX_CHUNK_CHARS for piece in pieces)


def test_consecutive_pieces_overlap():
    pieces = split_text(prose(9000))

    for earlier, later in zip(pieces, pieces[1:]):
        assert earlier.endswith(later[:CHUNK_OVERLAP_CHARS])


def test_the_split_covers_the_whole_text():
    text = prose(9000)
    pieces = split_text(text)

    # Each piece after the first repeats the previous piece's last CHUNK_OVERLAP_CHARS,
    # so reassembly drops that prefix.
    rebuilt = pieces[0] + "".join(piece[CHUNK_OVERLAP_CHARS:] for piece in pieces[1:])
    assert rebuilt == text


def test_a_paragraph_boundary_is_preferred_over_a_sentence_boundary():
    first = prose(1600) + "\n\n"
    pieces = split_text(first + prose(3000))

    assert pieces[0] == first


def test_text_with_no_boundary_at_all_is_cut_at_the_limit():
    pieces = split_text("x" * 5000)

    assert len(pieces[0]) == MAX_CHUNK_CHARS
    assert all(len(piece) <= MAX_CHUNK_CHARS for piece in pieces)


def test_the_default_constants_satisfy_the_overlap_constraint():
    split_text(prose(6000))  # would raise if MAX_CHUNK_CHARS and CHUNK_OVERLAP_CHARS drifted


def test_an_overlap_too_wide_to_make_progress_is_rejected():
    with pytest.raises(ValueError, match="under half"):
        split_text(prose(6000), limit=1000, overlap=500)


# --- malformed input --------------------------------------------------------


@pytest.mark.parametrize("sections", [None, "References", 42, {"title": "Method"}])
def test_sections_that_are_not_a_list_yield_nothing(sections):
    assert chunk_sections(sections) == []


@pytest.mark.parametrize(
    "entry",
    [
        None,
        "Introduction",
        {"title": "Method"},  # no content
        {"content": prose(400)},  # no title
        {"title": 7, "content": prose(400)},
        {"title": "Method", "content": None},
    ],
)
def test_a_malformed_section_is_skipped_without_raising(entry):
    chunks = chunk_sections([entry, section("Method", prose(400))])

    assert [chunk.section_title for chunk in chunks] == ["Method"]


def test_parser_artifacts_below_the_minimum_are_dropped():
    stamp = "arXiv:2608.26423v1  [cs.LG]  26 Aug 2026"
    assert len(stamp) < MIN_CHUNK_CHARS

    assert chunk_sections([section("Content", stamp)]) == []


def test_whitespace_only_content_is_dropped():
    assert chunk_sections([section("Method", "   \n\n  \t ")]) == []


# --- identity ---------------------------------------------------------------


def test_document_id_is_stable_for_the_same_position():
    assert chunk_document_id("2608.26423", 3, 1) == "2608.26423:3:1"


def test_chunking_the_same_sections_twice_gives_the_same_ids():
    sections = [section("Method", prose(9000)), section("Results", prose(400))]

    first = [chunk_document_id("2608.26423", c.section_index, c.chunk_index) for c in chunk_sections(sections)]
    second = [chunk_document_id("2608.26423", c.section_index, c.chunk_index) for c in chunk_sections(sections)]

    assert first == second
    assert len(set(first)) == len(first)
