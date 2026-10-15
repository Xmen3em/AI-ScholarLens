import copy
import json
import sys

import pytest
from src.commands import evaluate_hf_papers as command
from src.commands import hf_paper_allowance as funding

from tests.unit.test_hf_client import settings
from tests.unit.test_hf_paper_allowance import setup


def prepare(tmp_path, monkeypatch, *, approved=False):
    metadata, approval, path = setup(tmp_path, monkeypatch, approved=approved)
    monkeypatch.setattr(command, "plan_collection", lambda *args, **kwargs: copy.deepcopy(metadata))
    monkeypatch.setattr(funding, "DEVELOPMENT_ALLOWANCE", path)
    output = tmp_path / "output"
    args = ["evaluate_hf_papers", "--snapshot", str(tmp_path), "--output", str(output)]
    return metadata, approval, path, output, args


@pytest.mark.parametrize("mode", ["default", "proposal", "pending"])
def test_offline_and_unapproved_modes_never_load_credentials_or_create_funding(tmp_path, monkeypatch, mode):
    _, approval, path, output, args = prepare(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs): raise AssertionError("No credentials or services are allowed")

    monkeypatch.setattr(command, "Settings", forbidden)
    monkeypatch.setattr(command, "live_snapshot", forbidden)
    monkeypatch.setattr(command, "provider_available", forbidden)
    if mode == "proposal": args += ["--propose-approval"]
    if mode == "pending": args += ["--execute", "--approval", str(approval)]
    monkeypatch.setattr(sys, "argv", args)
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["outbound_budget"] == metadata["approved_outbound_budget"] == 0
    assert metadata["app_accepted"] is False
    assert not path.exists() and not path.with_suffix(".registered").exists()
    if mode == "proposal":
        receipt = json.loads((output / "proposed-approval.json").read_text())
        assert receipt["status"] == "pending_user_approval" and receipt["maximum_outbound_attempts"] == 261
        assert receipt["paper_data_planned"] is True
    if mode == "pending": assert metadata["reason"] == "approval_required"


def test_approved_admission_failure_preserves_empty_fixed_grant_and_makes_no_service_calls(tmp_path, monkeypatch):
    _, approval, path, output, args = prepare(tmp_path, monkeypatch, approved=True)
    monkeypatch.setattr(command, "Settings", lambda: settings(rag_sentence_candidates_per_passage=1))
    monkeypatch.setattr(command, "free_memory_mib", lambda: 599)

    def forbidden(*args, **kwargs): raise AssertionError("Admission must precede all service calls")

    monkeypatch.setattr(command, "live_snapshot", forbidden)
    monkeypatch.setattr(command, "provider_available", forbidden)
    monkeypatch.setattr(sys, "argv", args + ["--execute", "--approval", str(approval)])
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["status"] == "not_started" and metadata["reason"] == "insufficient_memory"
    assert path.is_file() and path.with_suffix(".registered").is_file()
    with funding.closing(funding.sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
