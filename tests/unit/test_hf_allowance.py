import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from src.commands.agent_collection import build_jobs
from src.commands.hf_allowance import PilotAllowance, validate_pilot_scope
from src.commands.hf_evaluation import HF_MANIFEST_SHA256, hosted_work, load_protocol

from tests.unit.test_hf_configuration import MODEL
from tests.unit.test_hf_scoring import call


def seed(tmp_path):
    prior = tmp_path / "prior"
    prior.mkdir()
    values = {"metadata.json": {**pilot(), "created_unix": 1, "hosted_manifest_sha256": HF_MANIFEST_SHA256},
              "completion.json": {"outbound_attempts": 2},
              "qualification.json": {"checks": [{"calls": [call()], "work": hosted_work([call()], load_protocol(), MODEL)} for _ in range(2)]}}
    for name, value in values.items():
        (prior / name).write_text(json.dumps(value))
    (prior / "records.jsonl").write_text("")
    return PilotAllowance(tmp_path / "allowance.sqlite3", prior=prior), prior


def test_fresh_output_cannot_reset_paid_allowance(tmp_path):
    grant, _ = seed(tmp_path)
    assert grant.reserve("first", 13) == 11
    with pytest.raises(ValueError):
        grant.reserve("second", 13)
    grant.settle("first", 7)
    assert grant.reserve("second", 13) == 4
    with pytest.raises(ValueError):
        grant.settle("first", 0)


def test_uncertain_interrupted_run_retains_its_entire_reservation(tmp_path):
    grant, _ = seed(tmp_path)
    grant.reserve("interrupted", 13)
    grant.settle("interrupted", None)
    with pytest.raises(ValueError):
        grant.reserve("fresh", 13)


def test_simultaneous_reservations_cannot_both_spend_remaining_budget(tmp_path):
    grant, _ = seed(tmp_path)

    def reserve(run):
        try:
            return grant.reserve(run, 13)
        except ValueError:
            return 0

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(reserve, ("one", "two")))
    assert sorted(values) == [0, 11]


def test_prior_evidence_change_cannot_reinitialize_allowance(tmp_path):
    grant, prior = seed(tmp_path)
    grant.reserve("one", 13)
    path = prior / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["created_unix"] += 1
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        PilotAllowance(grant.path, prior=prior)


@pytest.mark.parametrize("used", [-1, 12, True])
def test_settlement_cannot_exceed_or_fabricate_reserved_attempts(tmp_path, used):
    grant, _ = seed(tmp_path)
    grant.reserve("one", 13)
    with pytest.raises(ValueError):
        grant.settle("one", used)


def test_allowance_scope_cannot_expand_to_other_questions_or_transports():
    metadata = pilot()
    validate_pilot_scope(metadata)
    metadata["jobs"][0]["case_id"] = "another"
    with pytest.raises(ValueError):
        validate_pilot_scope(metadata)


def pilot():
    return {"split": "development", "configuration": {"model": MODEL},
            "jobs": build_jobs([{"id": "week7-development-narrative-rubrics-literal", "query": "public synthetic"}],
                               modes=("bm25",), transports=("json",))}
