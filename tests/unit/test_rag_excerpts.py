import pytest
from src.schemas.api.rag import Citation
from src.services.rag.excerpts import build_excerpts, render_selection


def _citation(marker, text):
    return Citation(marker=marker, arxiv_id="2601.00001v1", title="Paper", section_title="Methods",
                    section_index=0, chunk_index=0, evidence=text)


def test_excerpts_prioritize_question_terms_and_keep_passage_diversity():
    citations = [
        _citation("[1.1]", "Introduction. We discuss background information about language models. Retrieval augmented generation conditions answers on retrieved passages."),
        _citation("[2.1]", "We evaluate retrieval augmented generation with knowledge-gap canaries."),
    ]
    excerpts = build_excerpts(citations, "How do papers use retrieval augmented generation?")
    assert excerpts["E1"].text == "Retrieval augmented generation conditions answers on retrieved passages."
    assert excerpts["E1"].marker == "[1.1]"
    assert excerpts["E2"].marker == "[2.1]"
    assert len(excerpts) == 2  # The default offers each passage's best sentence.
    assert render_selection(["E1", "E2"], excerpts) == (
        '"Retrieval augmented generation conditions answers on retrieved passages." [1.1]\n'
        '"We evaluate retrieval augmented generation with knowledge-gap canaries." [2.1]'
    )


@pytest.mark.parametrize("selection", [["E99"], ["E1", "E1"], ["E1"] * 4])
def test_selection_rejects_unknown_repeated_and_excess_ids(selection):
    excerpts = build_excerpts([_citation("[1.1]", "The method binds claims to retrieved evidence.")], "claims")
    with pytest.raises(ValueError):
        render_selection(selection, excerpts)


def test_selection_can_abstain_without_attaching_irrelevant_citations():
    assert render_selection([], {}) == "The retrieved evidence is insufficient to answer this question."


def test_excerpts_do_not_cut_long_sentences_or_change_source_words():
    excerpts = build_excerpts([_citation("[1.1]", "long " * 60 + "sentence.\nThe method binds claims to\nretrieved evidence.")], "claims")
    assert len(excerpts) == 1
    assert excerpts["E1"].text == "The method binds claims to retrieved evidence."


def test_topic_mentions_do_not_satisfy_missing_question_details():
    citations = [_citation("[1.1]", "Orion is a vision model that recognizes nearby objects.")]
    assert build_excerpts(citations, "How does Orion fix memory leaks?") == {}


def test_excerpt_ranking_prefers_specific_answer_terms_over_repeated_topic_terms():
    citations = [_citation("[1.1]", "Penalty-aware scoring evaluates RAG answers and their ranking. Penalty-aware evaluation studies RAG products. Scoring: correct +1, wrong -4, abstain 0.")]
    excerpts = build_excerpts(citations, "How does penalty-aware evaluation score correct, wrong, and abstained RAG answers?")
    assert excerpts["E1"].text == "Scoring: correct +1, wrong -4, abstain 0."


def test_relevance_shortlist_excludes_other_papers_with_only_generic_overlap():
    primary = _citation("[1.1]", "Orion builds knowledge graphs from a set of structured documents.")
    unrelated = _citation("[2.1]", "Language models acquire knowledge from their earlier training examples.")
    unrelated.arxiv_id = "2601.00002v1"
    excerpts = build_excerpts([primary, unrelated], "What are Orion knowledge graphs?")
    assert [excerpt.marker for excerpt in excerpts.values()] == ["[1.1]"]


def test_candidates_keep_separate_requested_facts_from_one_passage():
    method = "Aster uses a linear classifier to select visual facts."
    result = "Aster reports an accuracy of 0.812 on the evaluation set."
    excerpts = build_excerpts([_citation("[1.1]", method + "\n" + result)],
                              "What classifier and accuracy does Aster report?", candidates_per_passage=3)
    assert {e.text for e in excerpts.values()} == {method, result}
    answer = render_selection(list(excerpts), excerpts)
    assert method in answer and result in answer
    assert answer.count("[1.1]") == 2


def test_candidate_expansion_is_bounded_and_omits_zero_overlap_background():
    facts = [
        "Brio supports audio durations of up to 18 seconds.",
        "Brio generates audio at a sample rate of 32 kHz.",
        "Brio offers models with 2 billion and 8 billion parameters.",
        "Brio includes another audio model for additional experiments.",
    ]
    background = "Earlier research provides general background about the field."
    excerpts = build_excerpts([_citation("[1.1]", " ".join([*facts, background]))],
                              "What audio duration, sample rate and parameters does Brio support?", candidates_per_passage=3)
    assert len(excerpts) == 3
    assert {e.text for e in excerpts.values()} == set(facts[:3])


def test_candidate_expansion_keeps_other_passages_and_source_markers():
    citations = [
        _citation("[1.1]", "Aster uses a linear classifier to select visual facts. Aster reports an accuracy of 0.812 on its evaluation set."),
        _citation("[2.1]", "Brio uses a neural classifier to select visual facts. Brio reports an accuracy of 0.734 on its evaluation set."),
    ]
    citations[1].arxiv_id = "2601.00002v1"
    excerpts = build_excerpts(citations, "What classifier and accuracy do Aster and Brio report?", candidates_per_passage=3)
    assert len(excerpts) == 4
    assert {e.marker for e in excerpts.values()} == {"[1.1]", "[2.1]"}
    for excerpt in excerpts.values():
        citation = next(c for c in citations if c.marker == excerpt.marker)
        assert excerpt.text in citation.evidence


def test_expansion_does_not_change_default_candidate_count():
    citation = _citation("[1.1]", "Aster uses a linear classifier to select visual facts. Aster reports an accuracy of 0.812 on its evaluation set.")
    assert len(build_excerpts([citation], "What classifier and accuracy does Aster report?")) == 1


@pytest.mark.parametrize("limit", [0, 4])
def test_candidate_expansion_rejects_limits_outside_the_measured_bound(limit):
    with pytest.raises(ValueError):
        build_excerpts([], "classifier", candidates_per_passage=limit)
