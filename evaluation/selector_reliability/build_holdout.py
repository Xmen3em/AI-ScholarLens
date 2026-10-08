"""Materialize predeclared labels with exact locators from the saved source snapshot."""

import json
from pathlib import Path

ROOT = Path("evaluation/selector_reliability")
data = json.loads(Path("test_output/selector_reliability/corpus.json").read_text())


def support(aid, section, chunk=0):
    item = next(c for c in data["chunks"] if (c["arxiv_id"], c["section_index"], c["chunk_index"]) == (aid, section, chunk))
    return {"locators": [{"arxiv_id": aid, "section_index": section, "chunk_index": chunk,
                          "section_title": item["section_title"], "source_excerpt": item["content"]}]}


fast = "2608.27763v1"
load = "2608.27756v1"
cg = "2608.26375v1"
definitions = [
    ("fast-family", "literal", "In Fast Weight Attention, what updates do Falcon-1, Falcon-2 and Falcon-3 use?",
     ["Falcon-1 is a scalar NLMS update.", "Falcon-2 is the per-column extension.", "Falcon-3 is a sliding-window minibatch update."], [support(fast, 2)]),
    ("fast-forms", "paraphrase", "Which computational forms of the fast-weight updates are provided in Fast Weight Attention?",
     ["The updates have recurrent, masked-parallel and chunk-parallel forms."], [support(fast, 2)]),
    ("load-size", "literal", "How many UKLO puzzles does Load-Bearing Context start from and what two deletion variants does it generate?",
     ["It starts from 53 UKLO puzzles.", "Uniform random deletion removes one context example.", "ECC-inspired targeted deletion removes one structurally load-bearing context example."], [support(load, 2), support(load, 3, 1)]),
    ("load-score", "paraphrase", "In Load-Bearing Context, what does the Question Damage Score count after a context example is removed?",
     ["It counts the questions that become unanswerable after deleting that context example."], [support(load, 3, 1)]),
    ("cg-weights", "literal", "In CG4AI, what determines the mixture weights and what guides the pricing subproblem?",
     ["A master linear program determines the optimal mixture weights.", "LP dual variables guide new-model generation in the pricing subproblem toward violated constraints."], [support(cg, 2)]),
    ("multi-forms-weights", "multi", "What update forms does Fast Weight Attention provide, and what determines mixture weights in CG4AI?",
     ["Fast Weight Attention provides recurrent, masked-parallel and chunk-parallel forms.", "In CG4AI a master linear program determines the optimal mixture weights."], [support(fast, 2), support(cg, 2)]),
    ("unsupported-load-energy", "unsupported_related", "How many kilowatt-hours did Load-Bearing Context use to evaluate its 53 UKLO puzzles?", [], []),
    ("unsupported-fast-price", "unsupported_related", "What monthly subscription price is charged for Falcon-3 in Fast Weight Attention?", [], []),
    ("unsupported-space", "unsupported_unrelated", "What is the surface temperature on Neptune today?", [], []),
]
cases = [dict(id=key, kind=kind, answerable=bool(facts), query=query,
              facts=[dict(id=f"{key}-f{i}", text=text) for i, text in enumerate(facts, 1)], support=units)
         for key, kind, query, facts, units in definitions]
result = dict(version="selector-reliability-fresh-v1", reviewed_on="2026-10-08", reviewer="Codex stored-source review",
              split="Fresh convenience holdout; labels fixed before model collection; separate synthetic development.",
              corpus=dict(papers=58, chunks=2775, alias_target="paper-chunks-v2", preserved_v1_chunks=1221), cases=cases)
target = ROOT / "holdout.json"
if target.exists():
    raise SystemExit("Refusing to overwrite frozen labels")
target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print("Fixed", len(cases), "cases before collection")
