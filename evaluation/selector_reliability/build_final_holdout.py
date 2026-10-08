"""Save a second fresh source-reviewed holdout, without overwriting prior labels."""

import json
from pathlib import Path

data = json.loads(Path("test_output/selector_reliability/corpus.json").read_text(encoding="utf-8"))
diff = "2608.26462v1"
sf = "2608.26437v1"


def support(aid, section, index=0):
    chunk = next(c for c in data["chunks"] if (c["arxiv_id"], c["section_index"], c["chunk_index"]) == (aid, section, index))
    return {"locators": [{"arxiv_id": aid, "section_index": section, "chunk_index": index,
                          "section_title": chunk["section_title"], "source_excerpt": chunk["content"]}]}


definitions = [
    ("diff-access", "literal", "What model access does Diff Mining need?",
     ["Diff Mining needs only output logits, without access to model internals."], [support(diff, 2)]),
    ("diff-stages", "paraphrase", "How does Diff Mining turn base and finetuned model outputs into interpretable tokens?",
     ["It extracts per-context logit differences between finetuned and base models on a reference corpus.", "It aggregates the signals into an interpretable token set representing the finetune."], [support(diff, 2)]),
    ("sf-edges", "literal", "Which signals identify bias-prone edges in SF-GNN, and how are those edges filtered during message passing?",
     ["It combines sensitive homophily with hub participation and triadic closure.", "Stochastic filtering at each message-passing step downweights or removes those edges while preserving the remaining graph structure."], [support(sf, 1)]),
    ("sf-penalty", "paraphrase", "What penalty and warm-up schedule stabilize training in SF-GNN?",
     ["Training uses a statistical-parity regularizer with a linear warm-up schedule."], [support(sf, 2, 1)]),
    ("multi-access-edges", "multi", "What model access is needed by Diff Mining, and which bias-prone edge signals are used in SF-GNN?",
     ["Diff Mining needs only output logits without model internals.", "SF-GNN combines sensitive homophily with hub participation and triadic closure."], [support(diff, 2), support(sf, 1)]),
    ("unsupported-diff-price", "unsupported_related", "What monthly subscription price is charged for Diff Mining?", [], []),
    ("unsupported-sf-energy", "unsupported_related", "What kilowatt-hour energy cost does SF-GNN report for its five benchmark datasets?", [], []),
]
cases = [dict(id=key, kind=kind, answerable=bool(facts), query=query,
              facts=[dict(id=f"{key}-f{i}", text=text) for i, text in enumerate(facts, 1)], support=units)
         for key, kind, query, facts, units in definitions]
result = dict(version="selector-reliability-final-fresh-v1", reviewed_on="2026-10-08", reviewer="Codex stored-source review",
              split="Second fresh convenience holdout; fixed after map rejection and before final collection. No paired quality-improvement estimate.",
              corpus=dict(papers=58, chunks=2775, alias_target="paper-chunks-v2", preserved_v1_chunks=1221), cases=cases)
target = Path("evaluation/selector_reliability/final_holdout.json")
if target.exists():
    raise ValueError("Refusing to overwrite frozen final labels")
target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print("Fixed", len(cases), "fresh questions before final collection")
