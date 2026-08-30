"""Reciprocal rank fusion, which is the only thing reconciling BM25 with cosine similarity."""

import pytest
from src.search.fusion import RRF_K, fused_scores, reciprocal_rank_fusion


def test_a_document_ranked_well_by_both_beats_one_ranked_first_by_only_one():
    """The whole reason to fuse: agreement across rankings is evidence, a single
    confident hit is not."""
    keyword = ["a", "b"]
    semantic = ["c", "b"]

    assert reciprocal_rank_fusion([keyword, semantic]) == ["b", "a", "c"]


def test_a_first_place_and_a_third_still_outrank_two_seconds():
    """RRF is not linear in rank: 1/61 + 1/63 edges past 1/62 + 1/62. Pinned because it
    is the behaviour that makes a single strong signal count for something."""
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "d"]])

    assert fused[:2] == ["c", "b"]


def test_a_document_in_one_ranking_only_still_appears():
    fused = reciprocal_rank_fusion([["a"], ["b"]])

    assert set(fused) == {"a", "b"}


def test_scores_never_leak_in_only_positions_do():
    """BM25 scores and cosine similarities are on incomparable scales; RRF sees neither."""
    order = ["a", "b", "c"]

    assert reciprocal_rank_fusion([order, order]) == order


def test_the_top_of_one_list_is_damped_rather_than_dominant():
    """Without the k constant a rank-1 hit would outweigh every other signal."""
    scores = fused_scores([["a"], ["b"]])

    assert scores["a"] == pytest.approx(1 / (RRF_K + 1))
    assert scores["a"] < 2 / RRF_K


def test_fusing_one_ranking_preserves_it():
    assert reciprocal_rank_fusion([["a", "b", "c"]]) == ["a", "b", "c"]


def test_no_rankings_fuse_to_nothing():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_ties_break_on_first_appearance_so_the_order_is_deterministic():
    first = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
    second = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])

    assert first == second == ["a", "b"]


def test_every_document_is_scored_exactly_once_per_ranking_it_appears_in():
    scores = fused_scores([["a", "b"], ["a", "c"]])

    assert scores["a"] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 1))
    assert scores["b"] == pytest.approx(1 / (RRF_K + 2))
