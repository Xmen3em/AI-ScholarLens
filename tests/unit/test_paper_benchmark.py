import json
from pathlib import Path

import pytest
from src.commands import build_benchmark
from src.commands.build_benchmark import ALLOWED_LICENSES, FIELDS, admit, check_manifest, parse_license
from src.services.study.content import EvidenceBlock, PaperContent
from src.services.study.intake import StudyPaper

ROOT = Path("evaluation/paper_benchmark")
CC_BY = "http://creativecommons.org/licenses/by/4.0/"
ARXIV_ONLY = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


def oai(license_url: str | None) -> bytes:
    element = f"<license>{license_url}</license>" if license_url else ""
    return (f'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><GetRecord><record><metadata>'
            f'<arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>2510.26807</id>{element}</arXiv>'
            f'</metadata></record></GetRecord></OAI-PMH>').encode()


def content(*, pages=10, blocks=True, categories=("stat.AP", "cs.LG"), coverage="full_text"):
    paper = StudyPaper(arxiv_id="2510.26807v1", title="Diabetes", authors=["A"], abstract="RL for diabetes.",
                       categories=list(categories), published="2025-10-19T00:00:00Z")
    rows = [EvidenceBlock(id="p1b0", page=1, section="Intro", text="We use reinforcement learning.")] if blocks else []
    return PaperContent(paper=paper, source_sha256="b" * 64, parser_revision="pdfium-5.14.0-v1", page_count=pages,
                        blocks=rows, missing_pages=[], coverage=coverage)


CANDIDATE = {"id": "2510.26807v1", "field": "medicine", "features": ["table_result"], "reason": "RL in medicine"}


def test_license_is_read_from_oai_record():
    assert parse_license(oai(CC_BY)) == CC_BY
    assert parse_license(oai(None)) is None
    with pytest.raises(ValueError):
        parse_license(b'<!DOCTYPE x [<!ENTITY a "b">]><x/>')


def test_admit_writes_a_manifest_row():
    row = admit(CANDIDATE, content(), CC_BY)
    assert row == {"id": "2510.26807v1", "field": "medicine", "split": None, "license": CC_BY, "publish": True,
                   "categories": ["stat.AP", "cs.LG"], "pages": 10, "blocks": 1, "sha256": "b" * 64,
                   "parser_revision": "pdfium-5.14.0-v1", "features": ["table_result"]}


@pytest.mark.parametrize(("change", "reason"), [
    ({"license": ARXIV_ONLY}, "license"), ({"pages": 41}, "pages"), ({"blocks": False}, "no_text"),
    ({"coverage": "abstract_only"}, "no_text"), ({"categories": ("stat.AP",)}, "outside_ai_scope")])
def test_admit_rejects_unlicensed_long_textless_and_out_of_scope(change, reason):
    license_url = change.pop("license", CC_BY)
    with pytest.raises(ValueError, match=reason):
        admit(CANDIDATE, content(**change), license_url)


def test_only_an_allowed_private_candidate_keeps_a_restrictive_license():
    row = admit({**CANDIDATE, "allow_private": True}, content(), ARXIV_ONLY)
    assert row["publish"] is False and row["license"] == ARXIV_ONLY


def manifest_rows():
    rows = []
    for field in FIELDS:
        for index in range(5):
            rows.append({"id": f"25{FIELDS.index(field):02}.0000{index}v1", "field": field,
                         "split": "dev" if index < 2 else "holdout", "license": CC_BY, "publish": True,
                         "categories": ["cs.LG"], "pages": 10, "blocks": 50, "sha256": "c" * 64,
                         "parser_revision": "pdfium-5.14.0-v1",
                         "features": ["table_result"] if index == 0 else ["equation_method"] if index == 1 else []})
    rows[5] = {**rows[5], "id": "2510.26807v1", "license": ARXIV_ONLY, "publish": False}
    return {"version": "paper-benchmark-papers-v1", "papers": rows, "rejected": []}


def test_check_manifest_accepts_the_rules_and_names_each_violation():
    check_manifest(manifest_rows())
    broken = {
        "count": lambda m: m["papers"].pop(),
        "rag_paper": lambda m: m["papers"][0].update(id="2005.11401v4"),
        "split": lambda m: m["papers"][2].update(split="dev"),
        "features": lambda m: [row.update(features=[]) for row in m["papers"] if row["field"] == "physics"],
        "publish": lambda m: m["papers"][0].update(license=ARXIV_ONLY),
        "scope": lambda m: m["papers"][0].update(categories=["stat.AP"]),
        "diabetes": lambda m: m["papers"][5].update(field="biology"),
        "duplicate": lambda m: m["papers"][1].update(id=m["papers"][0]["id"]),
    }
    for name, mutate in broken.items():
        manifest = manifest_rows()
        mutate(manifest)
        with pytest.raises(ValueError):
            check_manifest(manifest)
        assert name


def test_committed_manifest_follows_the_rules():
    manifest = json.loads((ROOT / "papers.v1.json").read_text(encoding="utf-8"))
    check_manifest(manifest)
    assert {row["license"] for row in manifest["papers"] if row["publish"]} <= ALLOWED_LICENSES


def test_cli_without_execute_makes_no_request(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise AssertionError("network used without --execute")

    monkeypatch.setattr(build_benchmark.httpx, "AsyncClient", refuse)
    assert build_benchmark.main(["papers"]) == 0
    assert "--execute" in capsys.readouterr().out


def question_set(q1="ورقة 2510.26807 بتقول إيه عن الدقة؟"):
    return {"version": "paper-benchmark-questions-v1", "papers": {"2510.26807v1": {
        "Q1": {"text": q1, "facts": [{"fact": "The paper uses RL.", "block": "p1b0", "quote": "We use   reinforcement learning."}]},
        "Q2": {"text": "إزاي النموذج بيتعلم من المريض؟", "facts": [
            {"fact": "RL is used.", "block": "p1b0", "quote": "reinforcement learning"}]},
        "Q3": {"text": "الورقة جربت النموذج على القطط؟", "absent_terms": ["cat"], "hits": 0}}}}


def one_paper():
    return {"papers": [{"id": "2510.26807v1", "field": "medicine", "split": "dev", "publish": False}]}


def test_every_quote_is_in_its_block_after_whitespace_normalization():
    from src.commands.build_benchmark import check_questions

    good = question_set("الدقة كانت كام في التجربة الأساسية؟")
    check_questions(good, one_paper(), {"2510.26807v1": content()})
    good["papers"]["2510.26807v1"]["Q2"]["facts"][0]["quote"] = "supervised learning"
    with pytest.raises(ValueError, match="quote_missing"):
        check_questions(good, one_paper(), {"2510.26807v1": content()})


def test_q3_absent_terms_have_zero_hits():
    from src.commands.build_benchmark import check_questions

    bad = question_set("الدقة كانت كام في التجربة الأساسية؟")
    bad["papers"]["2510.26807v1"]["Q3"]["absent_terms"] = ["reinforcement"]
    with pytest.raises(ValueError, match="q3_terms_present"):
        check_questions(bad, one_paper(), {"2510.26807v1": content()})


@pytest.mark.parametrize("text", ["2005.11401 ده بيقول إيه", "https://arxiv.org/abs/1", "/paper x", "2005.11401"])
def test_question_text_cannot_open_a_new_paper(text):
    from src.commands.build_benchmark import check_questions

    with pytest.raises(ValueError, match="question_opens_paper"):
        check_questions(question_set(text), one_paper(), None)


def test_every_paper_needs_all_three_questions():
    from src.commands.build_benchmark import check_questions

    bad = question_set("الدقة كانت كام في التجربة الأساسية؟")
    del bad["papers"]["2510.26807v1"]["Q2"]
    with pytest.raises(ValueError, match="shape"):
        check_questions(bad, one_paper(), None)


def test_spot_check_sheet_covers_every_field():
    from src.commands.build_benchmark import spot_check_sheet

    manifest = manifest_rows()
    questions = {"papers": {row["id"]: {kind: {"text": f"سؤال {kind} {row['id']}", "facts": [
        {"fact": "f", "block": "p1b0", "quote": "q"}]} for kind in ("Q1", "Q2")} for row in manifest["papers"]}}
    for row in manifest["papers"]:
        questions["papers"][row["id"]]["Q3"] = {"text": "سؤال Q3 " + row["id"], "absent_terms": ["x"], "hits": 0}
    sheet = spot_check_sheet(questions, manifest)
    assert sheet.count("\n## ") == 20
    for field in FIELDS:
        assert sheet.count(f"({field})") >= 3


def test_committed_questions_cover_every_paper():
    from src.commands.build_benchmark import check_questions, load_contents, load_questions

    papers = json.loads((ROOT / "papers.v1.json").read_text(encoding="utf-8"))
    contents = load_contents(papers)
    check_questions(load_questions(), papers, contents if len(contents) == 30 else None)


def test_freeze_detects_any_changed_file(tmp_path):
    from src.commands.build_benchmark import FROZEN_FILES, freeze, verify_frozen

    for name in FROZEN_FILES:
        (tmp_path / name).write_text(name, encoding="utf-8")
    digest = freeze(tmp_path)["sha256"]
    assert verify_frozen(tmp_path) == json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["manifest_sha256"]
    assert set(digest) == set(FROZEN_FILES)
    for name in FROZEN_FILES:
        original = (tmp_path / name).read_text(encoding="utf-8")
        (tmp_path / name).write_text(original + " ", encoding="utf-8")
        with pytest.raises(ValueError, match="manifest_changed"):
            verify_frozen(tmp_path)
        (tmp_path / name).write_text(original, encoding="utf-8")
    (tmp_path / "manifest.json").unlink()
    with pytest.raises(ValueError, match="manifest_missing"):
        verify_frozen(tmp_path)


def test_models_file_loads_and_matches_spec_routes():
    from src.services.study.models import DEFAULT_PROFILE, GPT_OSS_PROFILE, load_profiles

    profiles = load_profiles(ROOT / "models.v1.json")
    assert {name: profile.route for name, profile in profiles.items()} == {
        "baseline": "openai/gpt-oss-120b:cerebras", "qwen-27b": "Qwen/Qwen3.8-27B:deepinfra",
        "qwen-397b": "Qwen/Qwen3.5-397B-A17B:deepinfra", "control": "zai-org/GLM-5.3:deepinfra",
        "judge": "deepseek-ai/DeepSeek-V4-Pro:deepinfra"}
    # Production runs exactly the profile the benchmark measured.
    assert profiles["control"] == DEFAULT_PROFILE and profiles["baseline"] == GPT_OSS_PROFILE
    assert profiles["control"].input_estimate == "glm_tokenizer"
    assert all(profile.input_estimate == "utf8_bytes_div_3" for name, profile in profiles.items()
               if name not in {"baseline", "control"})


RAW = ('<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><GetRecord><record><metadata>'
       '<arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/"><id>2502.03275</id>'
       '<version version="v1"><date>Wed, 05 Feb 2025 15:33:00 GMT</date></version>'
       '<version version="v2"><date>Mon, 01 Sep 2025 18:25:38 GMT</date></version>'
       '<title>Token   Assorted</title><authors>DiJia Su, Hanlin Zhu and Qinqing Zheng</authors>'
       '<categories>cs.CL cs.AI</categories><license>' + CC_BY + '</license>'
       '<abstract> Mixing latent and text tokens. </abstract></arXivRaw></metadata></record></GetRecord></OAI-PMH>').encode()


def test_raw_record_gives_the_latest_version_and_its_license():
    from src.commands.build_benchmark import parse_raw

    paper, license_url = parse_raw(RAW)
    assert paper.arxiv_id == "2502.03275v2" and paper.title == "Token Assorted"
    assert paper.authors == ["DiJia Su", "Hanlin Zhu", "Qinqing Zheng"] and paper.categories == ["cs.CL", "cs.AI"]
    assert paper.published.startswith("2025-02-05") and paper.abstract == "Mixing latent and text tokens."
    assert license_url == CC_BY
