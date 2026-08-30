"""The scope predicate decides both what gets ingested and what gets deleted."""

import pytest
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST, ai_scope_query, matches_ai_scope


def test_allowlist_is_exactly_the_eight_core_ai_categories():
    assert AI_CATEGORY_ALLOWLIST == frozenset({"cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.RO", "cs.MA", "cs.NE", "stat.ML"})


@pytest.mark.parametrize("category", sorted(AI_CATEGORY_ALLOWLIST))
def test_each_allowed_category_matches_on_its_own(category):
    assert matches_ai_scope([category]) is True


@pytest.mark.parametrize(
    "categories",
    [
        ["quant-ph", "cs.LG"],  # cross-listed on a secondary category
        ["math.CO", "stat.ML"],
        ["cs.IR", "cs.CL", "cs.DL"],
    ],
)
def test_a_secondary_category_is_enough(categories):
    assert matches_ai_scope(categories) is True


@pytest.mark.parametrize(
    "categories",
    [
        ["hep-th", "math.CO"],
        ["cs.IR"],  # adjacent, but not in the allowlist
        ["cs.HC", "eess.AS"],
        ["cs.ai"],  # matching is case-sensitive, as arXiv's own tags are
        ["cs.AI2", "xcs.AI"],  # no substring matching
    ],
)
def test_non_allowlisted_categories_do_not_match(categories):
    assert matches_ai_scope(categories) is False


@pytest.mark.parametrize("categories", [None, [], (), "cs.AI", 42, [123, None], [{"term": "cs.AI"}]])
def test_missing_or_malformed_categories_are_rejected_without_raising(categories):
    """Bad rows are a finding for the audit, so they must not blow it up."""
    assert matches_ai_scope(categories) is False


def test_malformed_entries_do_not_hide_a_valid_one():
    assert matches_ai_scope([None, 42, "cs.CV"]) is True


def test_scope_query_is_the_exact_grouped_disjunction():
    assert ai_scope_query() == (
        "(cat:cs.AI OR cat:cs.CL OR cat:cs.CV OR cat:cs.LG OR cat:cs.MA OR cat:cs.NE OR cat:cs.RO OR cat:stat.ML)"
    )


def test_scope_query_is_stable_across_calls():
    """A frozenset has no iteration order; the query must not vary between processes."""
    assert ai_scope_query() == ai_scope_query()
