import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from src.commands.hf_clarity_allowance import ClarityAllowance
from src.commands.hf_clarity_execution import load_execution as clarity_execution
from src.commands.hf_schema_allowance import SchemaAllowance, approval_proposal
from src.commands.hf_schema_execution import load_execution
from src.commands.qualify_hf_schema import SchemaHF, collect
from src.services.hf.client import HFGenerationError

from tests.unit.test_hf_clarity_execution import setup as clarity_setup
from tests.unit.test_hf_client import envelope, settings


def setup(tmp_path, *, approved=True):
    approval, old = clarity_setup(tmp_path / "old")
    grant = ClarityAllowance(approval, **old)
    for arm in clarity_execution()["arms"]:
        grant.reserve("clarity-run", arm)
        grant.settle(arm, 1)
    run = tmp_path / "completed-clarity"
    run.mkdir()
    profile = clarity_execution()
    metadata = {"kind": profile["kind"], "status": "diagnostic_completed", "approval_sha256": grant.signature,
                "reproduction_manifest_sha256": profile["manifest_sha256"], "outbound_budget": 2,
                "paper_collection_planned": False}
    result = {"qualification_accepted": False, "pair_passed": True, "outbound_attempts": 2,
              "extension_attempts_used": 2, "original_attempts_used": 19,
              "reproduction_manifest_sha256": profile["manifest_sha256"],
              "preservation": dict.fromkeys(["source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"], True),
              "records": [{"arm": arm, "category": "passed", "outbound_attempts": 1, "schema_valid": True,
                           "expected_match": True, "work": {"usage_complete": True, "schema_violations": 0}}
                          for arm in profile["arms"]]}
    (run / "metadata.json").write_text(json.dumps(metadata))
    (run / "comparison.json").write_text(json.dumps(result))
    parents = {key: value for key, value in old.items() if key != "path"}
    parents.update(clarity_path=old["path"], clarity_approval=approval, clarity_run=run)
    receipt = approval_proposal(**parents)
    if approved:
        receipt.update(status="approved", authorization_source="explicit_user_approval")
    new = tmp_path / "schema-approval.json"
    new.write_text(json.dumps(receipt))
    return new, {**parents, "path": tmp_path / "schema.sqlite3"}


def test_five_case_execution_preserves_original_fixtures_and_payloads():
    from src.commands.hf_qualification import load_revision

    profile = load_execution()
    revision = load_revision()
    assert profile["cases"] == revision["cases"]
    assert profile["arms"] == ["scope", "relevance", "rewrite", "selector-1", "selector-10"]
    assert profile["maximum_outbound_attempts"] == 5
    assert all(payload["temperature"] == 0 and payload["reasoning_effort"] == "low" for payload in profile["payloads"])
    assert [payload["max_tokens"] for payload in profile["payloads"]] == [256, 256, 256, 512, 512]


@pytest.mark.parametrize("name", ["manifest.json", "requests.json", "PROTOCOL.md"])
def test_changed_schema_execution_freeze_rejected(tmp_path, name):
    for path in Path("evaluation/week7_hf/schema-execution-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / name).write_bytes(b"{}")
    with pytest.raises(ValueError):
        load_execution(tmp_path)


@pytest.mark.parametrize("field,value", [
    ("status", "pending_user_approval"), ("maximum_outbound_attempts", 6), ("maximum_outbound_attempts", True),
    ("paper_data_sent", 0), ("model", "other:provider"), ("endpoint", "https://evil.invalid"),
    ("clarity_allowance_binding", "0" * 64), ("arms", ["scope"]),
])
def test_schema_approval_must_match_exact_five_attempt_scope(tmp_path, field, value):
    approval, paths = setup(tmp_path)
    receipt = json.loads(approval.read_text())
    receipt[field] = value
    approval.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        SchemaAllowance(approval, **paths)
    assert not paths["path"].exists()


def test_new_five_case_allowance_is_persistent_and_old_ledgers_remain_unchanged(tmp_path):
    approval, paths = setup(tmp_path)
    protected = {key: paths[key].read_bytes() for key in ("original", "prompt_path", "clarity_path", "clarity_approval")}
    grant = SchemaAllowance(approval, **paths)
    for arm in load_execution()["arms"]:
        grant.reserve("run", arm)
        grant.settle(arm, 1)
    fresh = SchemaAllowance(approval, **paths)
    assert fresh.used == 5
    for arm in load_execution()["arms"]:
        with pytest.raises(ValueError):
            fresh.reserve("new-output", arm)
    assert all(paths[key].read_bytes() == value for key, value in protected.items())


@pytest.mark.parametrize("which", ["clarity_path", "clarity_approval", "clarity_run"])
def test_changed_completed_clarity_proof_blocks_next_attempt(tmp_path, which):
    approval, paths = setup(tmp_path)
    grant = SchemaAllowance(approval, **paths)
    if which == "clarity_run":
        proof = paths[which] / "comparison.json"
        proof.write_text(proof.read_text() + " ")
    elif which == "clarity_approval":
        paths[which].write_text("{}")
    else:
        with sqlite3.connect(paths[which]) as db:
            db.execute("UPDATE arms SET run='tampered'")
    with pytest.raises(ValueError):
        grant.reserve("blocked", "scope")


def test_unknown_and_zero_attempts_never_allow_repeat_and_missing_ledger_never_reseeds(tmp_path):
    approval, paths = setup(tmp_path)
    grant = SchemaAllowance(approval, **paths)
    grant.reserve("unknown", "scope")
    assert grant.used == 1
    grant.settle("scope", None)
    grant.reserve("preflight", "relevance")
    grant.settle("relevance", 0)
    with pytest.raises(ValueError):
        grant.reserve("retry", "relevance")
    grant.path.unlink()
    with pytest.raises(ValueError):
        SchemaAllowance(approval, **paths)
    assert not grant.path.exists()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "400", "timeout", "schema", "missing_usage", "source", "memory"])
async def test_guarded_five_case_collection_stops_safely_and_never_accepts_app(stub_httpx, tmp_path, monkeypatch, failure):
    from src.commands import qualify_hf_schema as command

    approval, paths = setup(tmp_path)
    grant = SchemaAllowance(approval, **paths)
    profile = load_execution()
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quotas.sqlite3")})
    monkeypatch.setattr(command, "source_hashes", lambda: {"file": "changed" if failure == "source" else "original"})

    def answer(request):
        ordinal = len(sent)
        sent.append(json.loads(request.content))
        if failure == "400":
            return httpx.Response(400, json={"error": {"code": "json_validate_failed", "type": "invalid_request_error",
                                                       "message": "private provider error"}})
        if failure == "timeout":
            raise httpx.ReadTimeout("private timeout", request=request)
        expected = profile["cases"][ordinal]["expected"] or {"query": "neural retrieval"}
        if failure == "schema":
            expected = {"in_scope": "true"}
        response = envelope(json.dumps(expected), usage=None if failure == "missing_usage" else {"prompt_tokens": 100, "completion_tokens": 20})
        if failure == "missing_usage":
            response.pop("usage", None)
        response["choices"][0]["message"]["reasoning"] = "private reasoning"
        return httpx.Response(200, json=response)

    sent = []
    stub_httpx(answer)
    result = await collect(config, grant, tmp_path, {"file": "original"}, memory=lambda: 599 if failure == "memory" else 4096)
    assert result["app_accepted"] is False
    assert result["qualification"]["large_schema_preflight_rejected"] is True
    assert result["qualification"]["qualified"] == (failure is None)
    assert result["outbound_attempts"] == len(sent) == (5 if failure is None else 0 if failure in {"source", "memory"} else 1)
    assert grant.used == len(sent)
    assert sent == profile["payloads"][:len(sent)]
    assert not any(label in json.dumps(result) for label in ("private provider error", "private timeout", "private reasoning"))


@pytest.mark.anyio
async def test_changed_valid_payload_is_rejected_before_reservation_or_request(stub_httpx, tmp_path, monkeypatch):
    from src.commands import qualify_hf_schema as command

    approval, paths = setup(tmp_path)
    grant = SchemaAllowance(approval, **paths)
    monkeypatch.setattr(command, "source_hashes", lambda: {})
    sent = stub_httpx(lambda request: httpx.Response(500))
    client = SchemaHF(settings(), grant, tmp_path, {}, memory=lambda: 4096)
    case = load_execution()["cases"][0]
    try:
        with pytest.raises(ValueError):
            await client.generate(client.settings.hf_default_model, case["prompt"] + " altered", system=case["system"],
                                  response_format=case["schema"], options={"temperature": 0, "num_predict": 256, "num_ctx": 8192})
    finally:
        await client.aclose()
    assert not sent and grant.used == 0


@pytest.mark.anyio
async def test_direct_result_api_cannot_bypass_approval_counter(stub_httpx, tmp_path, monkeypatch):
    from src.commands import qualify_hf_schema as command

    approval, paths = setup(tmp_path)
    grant = SchemaAllowance(approval, **paths)
    monkeypatch.setattr(command, "source_hashes", lambda: {})
    sent = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"in_scope":true}',
                         usage={"prompt_tokens": 100, "completion_tokens": 20})))
    client = SchemaHF(settings(), grant, tmp_path, {}, memory=lambda: 4096)
    case = load_execution()["cases"][0]
    kwargs = {"system": case["system"], "response_format": case["schema"],
              "options": {"temperature": 0, "num_predict": 256, "num_ctx": 8192}}
    try:
        await client.generate_result(client.settings.hf_default_model, case["prompt"], **kwargs)
        with pytest.raises(ValueError):
            await client.generate_result(client.settings.hf_default_model, case["prompt"], **kwargs)
    finally:
        await client.aclose()
    assert len(sent) == grant.used == 1


@pytest.mark.anyio
async def test_direct_result_api_has_no_sixth_outbound_attempt(stub_httpx, tmp_path, monkeypatch):
    from src.commands import qualify_hf_schema as command

    approval, paths = setup(tmp_path)
    grant = SchemaAllowance(approval, **paths)
    monkeypatch.setattr(command, "source_hashes", lambda: {})
    cases = load_execution()["cases"]
    replies = iter(case["expected"] or {"query": "neural retrieval"} for case in cases)
    sent = stub_httpx(lambda request: httpx.Response(200, json=envelope(json.dumps(next(replies)),
                         usage={"prompt_tokens": 100, "completion_tokens": 20})))
    client = SchemaHF(settings(), grant, tmp_path, {}, memory=lambda: 4096)
    try:
        for case in [*cases, cases[0]]:
            kwargs = {"system": case["system"], "response_format": case["schema"],
                      "options": {"temperature": 0, "num_predict": 512 if case["id"].startswith("selector") else 256,
                                  "num_ctx": 8192}}
            if client.attempts < 5:
                await client.generate_result(client.settings.hf_default_model, case["prompt"], **kwargs)
            else:
                with pytest.raises(HFGenerationError):
                    await client.generate_result(client.settings.hf_default_model, case["prompt"], **kwargs)
    finally:
        await client.aclose()
    assert len(sent) == grant.used == 5
