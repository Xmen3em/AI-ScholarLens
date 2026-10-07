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
    assert len(excerpts) == 2  # Only each passage's best sentence is selectable.
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
