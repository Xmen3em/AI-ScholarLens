import hashlib
import json

import pytest
from src.commands.backup import Recovery


class FakeRecovery(Recovery):
    def __init__(self):
        super().__init__()
        self.calls = []

    def run(self, args, *, output=None, input_stream=None):
        self.calls.append(args)
        if output:
            output.write(b"PGDMP\x00\xff\r\n")
        if "psql" in args and "SELECT" in args[-1]:
            return b'{"papers":58,"content_md5":"abc","schema_revision":"0001"}'
        return b""


def test_binary_backup_and_restore_to_generated_empty_target(tmp_path):
    recovery = FakeRecovery()
    directory = tmp_path / "backup"
    manifest = recovery.create(directory)
    assert (directory / "database.dump").read_bytes() == b"PGDMP\x00\xff\r\n"
    assert manifest["sha256"] == hashlib.sha256(b"PGDMP\x00\xff\r\n").hexdigest()
    report = recovery.drill(directory)
    assert report["matched"] is True
    assert report["target"].startswith("scholarlens_restore_")
    commands = " ".join(" ".join(c) for c in recovery.calls)
    assert "--single-transaction" in commands
    assert "--clean" not in commands
    assert "DROP DATABASE" in commands
    assert 'DROP DATABASE "rag_db"' not in commands


def test_modified_archive_is_rejected_before_any_database_work(tmp_path):
    recovery = FakeRecovery()
    directory = tmp_path / "backup"
    recovery.create(directory)
    (directory / "database.dump").write_bytes(b"corrupt")
    recovery.calls.clear()
    with pytest.raises(ValueError, match="checksum"):
        recovery.drill(directory)
    assert recovery.calls == []


def test_backup_never_overwrites_previous_artifacts(tmp_path):
    recovery = FakeRecovery()
    with pytest.raises(FileExistsError):
        recovery.create(tmp_path)
    assert recovery.calls == []


def test_restore_mismatch_is_reported_and_only_scratch_is_removed(tmp_path):
    recovery = FakeRecovery()
    directory = tmp_path / "backup"
    recovery.create(directory)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source"]["papers"] = 59
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="fingerprint"):
        recovery.drill(directory)
    assert "DROP DATABASE" in " ".join(recovery.calls[-1])
    assert json.loads((directory / "restore-drill.json").read_text())["matched"] is False
