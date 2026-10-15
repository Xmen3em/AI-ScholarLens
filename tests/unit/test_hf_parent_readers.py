import sqlite3

from src.commands import hf_prompt_allowance as module

from tests.unit.test_hf_prompt_allowance import setup


def test_parent_validation_and_usage_close_readonly_handles_without_gc(tmp_path, monkeypatch):
    original, prior, approval, ledger = setup(tmp_path)
    grant = module.PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    before = original.path.read_bytes(), ledger.read_bytes()
    real_connect = sqlite3.connect
    connections = []

    class Tracked(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def connect(*args, **kwargs):
        kwargs["factory"] = Tracked
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(module.sqlite3, "connect", connect)
    assert module.original_binding(original.path, prior=prior)
    assert grant.used == 0
    assert connections and all(connection.closed for connection in connections)
    assert (original.path.read_bytes(), ledger.read_bytes()) == before
