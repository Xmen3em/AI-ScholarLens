import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from src.commands import qualify_glm_fireworks as command
from src.commands.evaluate_study import SpendLedger
from src.services.study.models import GLM_FIREWORKS_PROFILE
from src.services.study.store import StudyStore

from tests.unit.test_evaluate_study import PAPER, factory_for, honest


@asynccontextmanager
async def observed_factory(store, profile, audit, observer, *, errors, memory):
    async with factory_for(honest)(store, profile, audit, observer) as service:
        yield service



def test_dry_run_uses_the_fixed_paper_shared_ledger_and_no_model_client(monkeypatch, capsys):
    async def refuse(*args, **kwargs):
        raise AssertionError("a dry run must not open a model client")

    monkeypatch.setattr(command, "qualify", refuse)
    assert command.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["paper"] == "2410.13258v4"
    assert plan["profile"] == GLM_FIREWORKS_PROFILE.name
    assert plan["route"] == "zai-org/GLM-5.3:fireworks-ai"
    assert plan["call_ceiling"] == 4
    assert plan["worst_case_usd"] == pytest.approx(0.2556)
    assert plan["ledger"] == str(command.LEDGER)
    assert plan["output_root"] == str(command.OUTPUT_ROOT)
    assert plan["execute"] is False


@pytest.mark.asyncio
async def test_execute_reuses_qualification_with_an_isolated_store_and_shared_ledger(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(command, "PAPER", PAPER)
    monkeypatch.setattr(command, "OUTPUT_ROOT", tmp_path / "run")
    monkeypatch.setattr(command, "ROOT", tmp_path / "frozen")
    (tmp_path / "frozen").mkdir()
    (tmp_path / "frozen" / "papers.v1.json").write_text(
        json.dumps({"papers": [{"id": command.PAPER, "split": "dev", "sha256": "a" * 64}]}), encoding="utf-8")
    monkeypatch.setattr(command, "verify_frozen", lambda root, private: "frozen")
    monkeypatch.setattr(command, "LEDGER", tmp_path / "shared-spend.json")
    monkeypatch.setattr(command, "host_memory_mib", lambda: (_ for _ in ()).throw(AssertionError("host memory used")))
    assert await command.execute(service_factory=observed_factory, memory=lambda: 2000) == 0

    qualification = json.loads((tmp_path / "run" / "qualification.json").read_text(encoding="utf-8"))
    assert qualification["glm-fireworks"]["passed"] is True
    report = json.loads(capsys.readouterr().out)
    assert report["job"]["paper"] == PAPER
    assert report["job"]["status"] == "ready" and report["job"]["kept_claims"] == 1
    assert report["job"]["format"] == {"parseable_calls": 2, "total_calls": 2}
    assert report["job"]["cost_usd"] == pytest.approx(2 * (1000 * 2.10 + 200 * 6.60) / 1e6)
    store = StudyStore(tmp_path / "run" / "qualify-glm-fireworks" / "state.sqlite3", "paper-benchmark")
    assert store.total_attempts() == 2
    assert SpendLedger(tmp_path / "shared-spend.json").spent() == pytest.approx(report["job"]["cost_usd"])
    assert (tmp_path / "run" / "qualification-report.json").exists()


def test_report_counts_format_kept_claims_latency_and_cost(tmp_path):
    row = {"status": "ready", "failure_code": None, "diagnostic": None, "seconds": 42.5,
           "review": {"claims": 12, "kept": 9, "withheld": {"unsupported": 3}},
           "calls": [{"purpose": "lesson", "state": "succeeded", "cost_usd": 0.006,
                      "usage": {"prompt_tokens": 10000, "completion_tokens": 1500}},
                     {"purpose": "grounding_review", "state": "succeeded", "cost_usd": 0.004,
                      "usage": {"prompt_tokens": 5000, "completion_tokens": 800}}]}
    report = command._job_report(paper="2410.13258v4", job_root=tmp_path, rows=[row], errors=[])
    assert report["format"]["parseable_calls"] == 2 and report["format"]["total_calls"] == 2
    assert report["kept_claims"] == 9 and report["latency_seconds"] == 42.5
    assert report["cost_usd"] == pytest.approx(0.01)
    assert report["provider_errors"] == []


def test_provider_errors_are_allowlisted_and_paired_with_their_call():
    assert command._error_rows(
        rows=[{"failure_code": "study_provider_http_400", "calls": [{"purpose": "lesson", "state": "failed"}]}],
        errors=[{"sequence": 1, "code": "unsupported_parameter", "type": "invalid_request_error",
                 "param": "reasoning_effort"}],
    ) == [{"call": 1, "http_status": 400, "sequence": 1, "code": "unsupported_parameter",
           "type": "invalid_request_error", "param": "reasoning_effort"}]
    assert command._error_rows(rows=[{"failure_code": "lesson_validation_failed", "calls": []}], errors=[]) == []


def test_parallel_errors_pair_by_attempt_sequence_not_completion_order():
    first = {"failure_code": "study_provider_http_400", "calls": [{"purpose": "lesson", "state": "failed", "sequence": 1}]}
    retry = {"sequence_base": 1, "failure_code": "study_provider_http_429", "calls": [
        {"purpose": "lesson", "state": "succeeded", "sequence": 1},
        {"purpose": "grounding_review", "state": "failed", "sequence": 2},
        {"purpose": "grounding_review", "state": "failed", "sequence": 3},
    ]}
    errors = [{"sequence": 3, "code": "second_half"}, {"sequence": 4, "code": "first_half"}]
    assert command._error_rows(rows=[first, retry], errors=errors) == [
        {"call": 1, "http_status": 400},
        {"call": 3, "http_status": 429, "sequence": 3, "code": "second_half"},
        {"call": 4, "http_status": 429, "sequence": 4, "code": "first_half"},
    ]
