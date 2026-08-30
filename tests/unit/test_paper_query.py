"""The query body is where boosting, filtering, and sorting either happen or silently don't."""

import pytest
from src.search.query import DEFAULT_SEARCH_FIELDS, SOURCE_FIELDS, PaperQuery


def multi_match(body):
    return body["query"]["bool"]["must"][0]["multi_match"]


def test_title_outweighs_abstract_which_outweighs_authors():
    assert list(DEFAULT_SEARCH_FIELDS) == ["title^3", "abstract^2", "authors^1"]
    assert multi_match(PaperQuery("rag").build())["fields"] == ["title^3", "abstract^2", "authors^1"]


def test_the_best_single_field_wins_rather_than_the_sum_of_fields():
    """cross_fields would spread the terms and make the title boost meaningless."""
    assert multi_match(PaperQuery("rag").build())["type"] == "best_fields"


def test_typos_are_tolerated_but_not_from_the_first_two_characters():
    match = multi_match(PaperQuery("retreival").build())

    assert match["fuzziness"] == "AUTO"
    assert match["prefix_length"] == 2


def test_the_full_document_text_is_never_returned():
    """The corpus averages 70k characters a paper; nothing in a result list shows them."""
    body = PaperQuery("rag").build()

    assert "raw_text" not in body["_source"]
    assert body["_source"] == list(SOURCE_FIELDS)


# --- filtering --------------------------------------------------------------


def test_categories_filter_rather_than_score():
    """A filter clause must not contribute to relevance, or a category becomes a search term."""
    body = PaperQuery("rag", categories=["cs.CL", "cs.AI"]).build()

    assert body["query"]["bool"]["filter"] == [{"terms": {"categories": ["cs.CL", "cs.AI"]}}]


@pytest.mark.parametrize("categories", [None, []])
def test_no_categories_means_no_filter_clause(categories):
    assert "filter" not in PaperQuery("rag", categories=categories).build()["query"]["bool"]


# --- pagination -------------------------------------------------------------


def test_pagination_passes_through():
    body = PaperQuery("rag", size=25, offset=50).build()

    assert (body["size"], body["from"]) == (25, 50)


def test_the_total_is_counted_past_the_default_ceiling():
    """Without this OpenSearch stops counting at 10,000 and the last page reports a total it cannot reach."""
    assert PaperQuery("rag").build()["track_total_hits"] is True


# --- sorting ----------------------------------------------------------------


def test_a_text_query_is_ranked_by_relevance():
    assert "sort" not in PaperQuery("rag").build()


def test_newest_first_sorts_by_date_and_breaks_ties_on_relevance():
    body = PaperQuery("rag", newest_first=True).build()

    assert body["sort"] == [{"published_date": {"order": "desc"}}, "_score"]


@pytest.mark.parametrize("query", ["", "   ", "\n"])
def test_an_empty_query_browses_the_newest_papers(query):
    body = PaperQuery(query).build()

    assert body["query"]["bool"]["must"] == [{"match_all": {}}]
    assert body["sort"] == [{"published_date": {"order": "desc"}}, "_score"]


def test_browsing_still_honours_the_category_filter():
    body = PaperQuery("", categories=["cs.RO"]).build()

    assert body["query"]["bool"]["filter"] == [{"terms": {"categories": ["cs.RO"]}}]


# --- highlighting -----------------------------------------------------------


def test_every_boosted_field_is_highlighted():
    highlighted = set(PaperQuery("rag").build()["highlight"]["fields"])

    assert highlighted == {field.split("^")[0] for field in DEFAULT_SEARCH_FIELDS}


def test_titles_and_authors_are_highlighted_whole_but_abstracts_in_fragments():
    fields = PaperQuery("rag").build()["highlight"]["fields"]

    assert fields["title"]["number_of_fragments"] == 0
    assert fields["authors"]["number_of_fragments"] == 0
    assert fields["abstract"]["number_of_fragments"] > 0


def test_highlights_survive_a_match_that_came_from_another_field():
    assert PaperQuery("rag").build()["highlight"]["require_field_match"] is False
