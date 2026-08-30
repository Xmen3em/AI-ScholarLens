"""The query body is where boosting, filtering, and sorting either happen or silently don't."""

import pytest
from src.search.query import CHUNK_PROFILE, PAPER_PROFILE, SearchQuery


def multi_match(body):
    return body["query"]["bool"]["must"][0]["multi_match"]


def test_title_outweighs_abstract_which_outweighs_authors():
    assert list(PAPER_PROFILE.fields) == ["title^3", "abstract^2", "authors^1"]
    assert multi_match(SearchQuery(PAPER_PROFILE, "rag").build())["fields"] == ["title^3", "abstract^2", "authors^1"]


def test_the_best_single_field_wins_rather_than_the_sum_of_fields():
    """cross_fields would spread the terms and make the title boost meaningless."""
    assert multi_match(SearchQuery(PAPER_PROFILE, "rag").build())["type"] == "best_fields"


def test_typos_are_tolerated_but_not_from_the_first_two_characters():
    match = multi_match(SearchQuery(PAPER_PROFILE, "retreival").build())

    assert match["fuzziness"] == "AUTO"
    assert match["prefix_length"] == 2


def test_the_full_document_text_is_never_returned():
    """The corpus averages 70k characters a paper; nothing in a result list shows them."""
    body = SearchQuery(PAPER_PROFILE, "rag").build()

    assert "raw_text" not in body["_source"]
    assert body["_source"] == list(PAPER_PROFILE.source)


# --- filtering --------------------------------------------------------------


def test_categories_filter_rather_than_score():
    """A filter clause must not contribute to relevance, or a category becomes a search term."""
    body = SearchQuery(PAPER_PROFILE, "rag", categories=["cs.CL", "cs.AI"]).build()

    assert body["query"]["bool"]["filter"] == [{"terms": {"categories": ["cs.CL", "cs.AI"]}}]


@pytest.mark.parametrize("categories", [None, []])
def test_no_categories_means_no_filter_clause(categories):
    assert "filter" not in SearchQuery(PAPER_PROFILE, "rag", categories=categories).build()["query"]["bool"]


# --- pagination -------------------------------------------------------------


def test_pagination_passes_through():
    body = SearchQuery(PAPER_PROFILE, "rag", size=25, offset=50).build()

    assert (body["size"], body["from"]) == (25, 50)


def test_the_total_is_counted_past_the_default_ceiling():
    """Without this OpenSearch stops counting at 10,000 and the last page reports a total it cannot reach."""
    assert SearchQuery(PAPER_PROFILE, "rag").build()["track_total_hits"] is True


# --- sorting ----------------------------------------------------------------


def test_a_text_query_is_ranked_by_relevance():
    assert "sort" not in SearchQuery(PAPER_PROFILE, "rag").build()


def test_newest_first_sorts_by_date_and_breaks_ties_on_relevance():
    body = SearchQuery(PAPER_PROFILE, "rag", newest_first=True).build()

    assert body["sort"] == [{"published_date": {"order": "desc"}}, "_score"]


@pytest.mark.parametrize("query", ["", "   ", "\n"])
def test_an_empty_query_browses_the_newest_papers(query):
    body = SearchQuery(PAPER_PROFILE, query).build()

    assert body["query"]["bool"]["must"] == [{"match_all": {}}]
    assert body["sort"] == [{"published_date": {"order": "desc"}}, "_score"]


def test_browsing_still_honours_the_category_filter():
    body = SearchQuery(PAPER_PROFILE, "", categories=["cs.RO"]).build()

    assert body["query"]["bool"]["filter"] == [{"terms": {"categories": ["cs.RO"]}}]


# --- highlighting -----------------------------------------------------------


def test_every_boosted_field_is_highlighted():
    highlighted = set(SearchQuery(PAPER_PROFILE, "rag").build()["highlight"]["fields"])

    assert highlighted == {field.split("^")[0] for field in PAPER_PROFILE.fields}


def test_titles_and_authors_are_highlighted_whole_but_abstracts_in_fragments():
    fields = SearchQuery(PAPER_PROFILE, "rag").build()["highlight"]["fields"]

    assert fields["title"]["number_of_fragments"] == 0
    assert fields["authors"]["number_of_fragments"] == 0
    assert fields["abstract"]["number_of_fragments"] > 0


def test_highlights_survive_a_match_that_came_from_another_field():
    assert SearchQuery(PAPER_PROFILE, "rag").build()["highlight"]["require_field_match"] is False


# --- the passage profile ----------------------------------------------------


def chunk_multi_match(**kwargs):
    return SearchQuery(CHUNK_PROFILE, "ablation", **kwargs).build()["query"]["bool"]["must"][0]["multi_match"]


def test_passage_text_outweighs_its_section_heading():
    assert list(CHUNK_PROFILE.fields) == ["content^3", "section_title^2"]


def test_the_paper_title_is_not_scored_when_searching_passages():
    """Measured on this corpus, boosting it collapsed six hits to one distinct paper:
    every passage of a paper carries the same title."""
    assert not any(field.startswith("title") for field in CHUNK_PROFILE.fields)


def test_passages_are_searched_in_the_chunk_index():
    assert SearchQuery(CHUNK_PROFILE, "ablation").build() and CHUNK_PROFILE.alias == "paper-chunks"


def test_passage_results_carry_their_position_in_the_paper():
    """Without these a caller cannot say where a quoted passage came from."""
    assert {"section_index", "chunk_index", "section_title"} <= set(CHUNK_PROFILE.source)


def test_both_profiles_share_the_same_matching_rules():
    """The profile changes which fields are searched, never how."""
    paper = SearchQuery(PAPER_PROFILE, "ablation").build()["query"]["bool"]["must"][0]["multi_match"]
    chunk = chunk_multi_match()

    assert {k: v for k, v in paper.items() if k != "fields"} == {k: v for k, v in chunk.items() if k != "fields"}


def test_the_category_filter_applies_to_passages_too():
    body = SearchQuery(CHUNK_PROFILE, "ablation", categories=["cs.LG"]).build()

    assert body["query"]["bool"]["filter"] == [{"terms": {"categories": ["cs.LG"]}}]
