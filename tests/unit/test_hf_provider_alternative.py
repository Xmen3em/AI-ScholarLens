import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from src.commands import qualify_hf_schema as command
from src.commands.hf_provider_allowance import AlternativeAllowance, approval_proposal
from src.commands.hf_schema_allowance import SchemaAllowance
from src.commands.hf_schema_execution import load_alternative, load_execution, load_experiment

from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_schema_command import arguments
from tests.unit.test_hf_schema_execution import setup as schema_setup


def setup(tmp_path, *, approved=True):
    old_approval, old = schema_setup(tmp_path / "old")
    grant = SchemaAllowance(old_approval, **old)
    run = tmp_path / "stopped-groq"
    run.mkdir()
    for arm in ["scope", "relevance"]:
        grant.reserve(str(run.resolve()), arm)
        grant.settle(arm, 1)
    metadata = {"kind": load_execution()["kind"], "status": "schema_qualification_completed", "approval_sha256": grant.signature}
    result = {"schema_qualified": False, "app_accepted": False, "outbound_attempts": 2,
              "schema_execution_manifest_sha256": load_execution()["manifest_sha256"],
              "preservation": dict.fromkeys(["source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"], True),
              "qualification": {"fixture_manifest_sha256": load_execution()["qualification_manifest_sha256"], "qualified": False,
                                "checks": [{"id": "scope", "ok": True},
                                           {"id": "relevance", "ok": False, "calls": [{"outbound_attempts": 1, "provider_status": 400,
                                              "provider_error_code": "json_validate_failed", "provider_error_type": "invalid_request_error"}]}]}}
    (run / "metadata.json").write_text(json.dumps(metadata))
    (run / "qualification.json").write_text(json.dumps(result))
    parents = {key: value for key, value in old.items() if key != "path"}
    parents.update(stopped_approval=old_approval, stopped_path=old["path"], stopped_run=run)
    receipt = approval_proposal(**parents)
    if approved:
        receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval = tmp_path / "alternative-approval.json"
    approval.write_text(json.dumps(receipt))
    return approval, {**parents, "path": tmp_path / "alternative.sqlite3"}


def test_provider_candidate_changes_only_model_in_original_five_payloads():
    original, alternative = load_execution(), load_alternative()
    assert alternative["cases"] == original["cases"]
    assert alternative["model"] == "openai/gpt-oss-120b:fireworks-ai"
    assert alternative["maximum_outbound_attempts"] == 5
    for first, second in zip(original["payloads"], alternative["payloads"], strict=True):
        assert {**first, "model": alternative["model"]} == second
    assert load_experiment("provider-alternative-v1") == alternative
    assert load_experiment("schema-execution-v1") == original
    with pytest.raises(ValueError):
        load_experiment("arbitrary-provider")


@pytest.mark.parametrize("name", ["manifest.json", "PROTOCOL.md", "requests.json"])
def test_changed_alternative_freeze_rejected(tmp_path, name):
    for path in Path("evaluation/week7_hf/provider-alternative-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / name).write_bytes(b"{}")
    with pytest.raises(ValueError):
        load_alternative(tmp_path)


@pytest.mark.parametrize("field,value", [("status", "pending_user_approval"), ("model", "openai/gpt-oss-120b:groq"),
    ("maximum_outbound_attempts", 6), ("paper_data_sent", 0), ("stopped_schema_allowance_binding", "0" * 64)])
def test_distinct_exact_alternative_approval_required(tmp_path, field, value):
    approval, paths = setup(tmp_path)
    receipt = json.loads(approval.read_text()); receipt[field] = value
    approval.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        AlternativeAllowance(approval, **paths)
    assert not paths["path"].exists()


def test_new_candidate_uses_no_unspent_groq_arms_and_old_receipt_cannot_fund_it(tmp_path):
    approval, paths = setup(tmp_path)
    protected = {key: paths[key].read_bytes() for key in ["original", "prompt_path", "clarity_path", "stopped_path"]}
    with pytest.raises(ValueError):
        AlternativeAllowance(paths["stopped_approval"], **paths)
    grant = AlternativeAllowance(approval, **paths)
    for arm in load_alternative()["arms"]:
        grant.reserve("alternative", arm); grant.settle(arm, 1)
    assert grant.used == 5
    with pytest.raises(ValueError):
        AlternativeAllowance(approval, **paths).reserve("new-directory", "scope")
    assert all(paths[key].read_bytes() == value for key, value in protected.items())


def test_changed_stopped_groq_proof_blocks_candidate_before_next_reservation(tmp_path):
    approval, paths = setup(tmp_path)
    grant = AlternativeAllowance(approval, **paths)
    proof = paths["stopped_run"] / "qualification.json"
    proof.write_text(proof.read_text() + " ")
    with pytest.raises(ValueError):
        grant.reserve("blocked", "scope")


@pytest.mark.parametrize("alternative", [True, False])
def test_direct_client_cannot_use_other_provider_approval(tmp_path, alternative):
    if alternative:
        approval, paths = schema_setup(tmp_path)
        grant, profile, experiment = SchemaAllowance(approval, **paths), load_alternative(), "provider-alternative-v1"
    else:
        approval, paths = setup(tmp_path)
        grant, profile, experiment = AlternativeAllowance(approval, **paths), load_execution(), "schema-execution-v1"
    config = settings().model_copy(update={"hf_models": [profile["model"]], "hf_default_model": profile["model"]})
    with pytest.raises(ValueError):
        command.SchemaHF(config, grant, tmp_path, {}, experiment=experiment)
    assert grant.used == 0


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "400", "semantic", "timeout"])
async def test_mocked_alternative_keeps_all_qualification_checks_and_failure_stops(tmp_path, stub_httpx, monkeypatch, failure):
    approval, paths = setup(tmp_path)
    grant = AlternativeAllowance(approval, **paths)
    profile = load_alternative()
    config = settings().model_copy(update={"hf_models": [profile["model"]], "hf_default_model": profile["model"],
                                         "api_rate_limit_path": str(tmp_path / "quotas.sqlite3")})
    monkeypatch.setattr(command, "source_hashes", lambda: {})
    bodies = []

    def answer(request):
        ordinal = len(bodies); bodies.append(json.loads(request.content))
        if failure == "timeout":
            raise httpx.ReadTimeout("private timeout", request=request)
        if failure == "400" and ordinal == 1:
            return httpx.Response(400, json={"error": {"code": "json_validate_failed", "type": "invalid_request_error"}})
        expected = profile["cases"][ordinal]["expected"] or {"query": "neural retrieval"}
        if failure == "semantic" and ordinal == 1:
            expected = {"relevant_markers": []}
        response = envelope(json.dumps(expected), usage={"prompt_tokens": 100, "completion_tokens": 20})
        response["choices"][0]["message"]["reasoning"] = "private reasoning"
        return httpx.Response(200, json=response)

    stub_httpx(answer)
    result = await command.collect(config, grant, tmp_path, {}, memory=lambda: 4096, experiment="provider-alternative-v1")
    assert result["qualification"]["qualified"] == (failure is None)
    assert result["app_accepted"] is False and result["qualification"]["large_schema_preflight_rejected"] is True
    assert grant.used == len(bodies) == (5 if failure is None else 1 if failure == "timeout" else 2)
    assert bodies == profile["payloads"][:len(bodies)]
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("proposal", [True, False])
def test_actual_alternative_offline_paths_never_access_credentials_or_funding(tmp_path, monkeypatch, proposal):
    from src.commands.hf_provider_allowance import approval_proposal

    approval, paths = setup(tmp_path, approved=False)
    extra = ["--experiment", "provider-alternative-v1"] + (["--propose-approval"] if proposal else [])
    _, output = arguments(tmp_path, monkeypatch, *extra)
    parents = {key: value for key, value in paths.items() if key != "path"}
    monkeypatch.setattr(command, "alternative_proposal", lambda: approval_proposal(**parents))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Offline credentials read")))
    monkeypatch.setattr(command, "AlternativeAllowance", Mock(side_effect=AssertionError("Offline funding")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["outbound_budget"] == 0 and metadata["configuration"]["model"] == load_alternative()["model"]
    if proposal:
        assert json.loads((output / "proposed-approval.json").read_text()) == json.loads(approval.read_text())


def test_pending_alternative_receipt_stops_before_settings_or_funding(tmp_path, monkeypatch):
    approval, paths = setup(tmp_path, approved=False)
    _, output = arguments(tmp_path, monkeypatch, "--experiment", "provider-alternative-v1", "--execute", "--approval", str(approval))
    monkeypatch.setattr(command, "AlternativeAllowance", lambda receipt: AlternativeAllowance(receipt, **paths))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Unapproved credentials read")))
    command.main()
    assert json.loads((output / "metadata.json").read_text())["reason"] == "approval_required"
    assert not paths["path"].exists()


def test_approved_mocked_alternative_command_uses_exact_model_and_independent_counter(tmp_path, monkeypatch):
    from src.config import Settings as Model

    approval, paths = setup(tmp_path)
    snapshot, output = arguments(tmp_path, monkeypatch, "--experiment", "provider-alternative-v1", "--execute", "--approval", str(approval))
    original = settings()
    factory = Mock(return_value=original)
    factory.model_validate = lambda values: Model(_env_file=None, **values)
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "AlternativeAllowance", lambda receipt: AlternativeAllowance(receipt, **paths))
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)
    state = json.loads((snapshot / "state.json").read_text())
    monkeypatch.setattr(command, "live_snapshot", lambda config: (state, [], []))
    monkeypatch.setattr(command, "provider_available", lambda model: {} if model == load_alternative()["model"] else pytest.fail("Wrong provider"))
    before = paths["stopped_path"].read_bytes()

    async def synthetic(config, grant, directory, source, *, experiment):
        assert experiment == "provider-alternative-v1"
        assert config.hf_models == [load_alternative()["model"]] and config.hf_default_model == load_alternative()["model"]
        for arm in load_alternative()["arms"]:
            grant.reserve(str(directory), arm); grant.settle(arm, 1)
        return {"qualification": {"qualified": True}, "outbound_attempts": 5, "app_accepted": False}

    monkeypatch.setattr(command, "collect", synthetic)
    command.main()
    result = json.loads((output / "qualification.json").read_text())
    assert result["schema_qualified"] is True and result["app_accepted"] is False
    assert result["original_attempts_used"] == 23
    assert paths["stopped_path"].read_bytes() == before
    assert original.hf_default_model == "openai/gpt-oss-120b:groq"
