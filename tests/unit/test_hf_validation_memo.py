import json
import os
from pathlib import Path

import pytest
from src.commands import hf_evaluation, hf_paper_allowance, hf_qualification

from tests.unit.test_hf_paper_allowance import setup


def test_one_paper_validation_does_not_rebuild_the_same_canonical_contracts(tmp_path, monkeypatch):
    metadata, approval, _ = setup(tmp_path, monkeypatch, approved=False)
    original = hf_evaluation.qualification_cases
    builds = []

    def measured():
        builds.append(True)
        return original()

    def history():
        for _ in range(3):
            hf_paper_allowance.load_cerebras()
        return "exhausted-28-history"

    monkeypatch.setattr(hf_evaluation, "qualification_cases", measured)
    monkeypatch.setattr(hf_paper_allowance, "schema_history_binding", history)
    expected = json.loads(approval.read_text(encoding="utf-8"))
    assert hf_paper_allowance.approval_proposal(metadata) == expected
    assert len(builds) == 1
    assert hf_paper_allowance.approval_proposal(metadata) == expected
    assert len(builds) == 2  # Every validation operation checks a fresh contract.


def test_validation_memo_is_local_nested_and_returns_independent_objects():
    from src.commands.hf_validation import memoized_input, validation_scope

    reads = []

    @memoized_input
    def load():
        reads.append(True)
        return {"values": [1]}

    load(); load()
    assert len(reads) == 2
    with validation_scope():
        load()["values"].append(2)
        with validation_scope():
            assert load() == {"values": [1]}
        assert len(reads) == 3
    with validation_scope():
        assert load() == {"values": [1]}
    assert len(reads) == 4


@pytest.mark.parametrize("mutation", ["same_stat_bytes", "deleted", "new_file"])
def test_frozen_input_change_during_validation_rejects_before_scope_returns(tmp_path, monkeypatch, mutation):
    from src.commands import hf_validation as memo

    directory = tmp_path / "inputs"; directory.mkdir()
    path = directory / "manifest.json"; path.write_bytes(b"original")
    monkeypatch.setattr(memo, "FROZEN_ROOT", directory)
    monkeypatch.setattr(memo, "RESEARCH_CATALOG", path)

    @memo.memoized_input
    def load():
        return path.read_bytes()

    with pytest.raises((ValueError, OSError)):
        with memo.validation_scope():
            assert load() == b"original"
            old_stat = path.stat()
            if mutation == "deleted":
                path.unlink()
            elif mutation == "new_file":
                (directory / "extra.json").write_bytes(b"new")
            else:
                path.write_bytes(b"modified")
                os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
            load()  # A memo hit cannot let changed bytes escape the scope.
    if path.exists():
        assert load() == path.read_bytes()  # A failed scope never leaves a cached proof.


def test_explicit_frozen_root_and_between_operation_changes_are_revalidated(tmp_path):
    from src.commands.hf_validation import validation_scope

    for path in Path("evaluation/week7_hf/qualification-v2").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    with validation_scope():
        hf_qualification.load_revision(tmp_path)
        hf_qualification.load_revision(tmp_path)
    victim = tmp_path / "fixtures.json"
    with pytest.raises(ValueError):
        with validation_scope():
            hf_qualification.load_revision(tmp_path)
            victim.write_bytes(victim.read_bytes() + b" ")
            hf_qualification.load_revision(tmp_path)
    with pytest.raises(ValueError):
        with validation_scope():
            hf_qualification.load_revision(tmp_path)


def test_canonical_runtime_contract_is_fresh_between_validation_operations(monkeypatch):
    from src.commands.hf_validation import validation_scope

    with validation_scope():
        hf_qualification.load_revision()
    monkeypatch.setattr(hf_qualification, "CONTROLLER_SYSTEM", "changed runtime contract")
    with pytest.raises(ValueError):
        with validation_scope():
            hf_qualification.load_revision()
