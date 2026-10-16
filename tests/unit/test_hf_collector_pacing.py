import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import src.commands.evaluate_hf_agent as collector
from src.middlewares import RateLimiter

from tests.unit.test_hf_client import settings


@pytest.mark.anyio
@pytest.mark.parametrize("unexpected_rejection", [False, True])
@pytest.mark.parametrize("delayed_qualification", [False, True])
async def test_collector_admits_slow_then_fast_requests_without_batch_window_drift(
    tmp_path, monkeypatch, unexpected_rejection, delayed_qualification,
):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(collector, "time", SimpleNamespace(monotonic=lambda: clock.now))

    async def wait(start, seconds):
        clock.now = max(clock.now, start + seconds)

    monkeypatch.setattr(collector, "wait_window", wait)
    monkeypatch.setattr(collector, "free_memory_mib", lambda: 4096)
    config = settings(api_rate_limit_path=str(tmp_path / "quotas.sqlite3"))
    limiter = RateLimiter(config)
    closed = Mock()

    async def close():
        closed()

    hf = SimpleNamespace(settings=config, attempts=0, stop_on_failed_record=True, aclose=close)
    search = SimpleNamespace(close=Mock())
    monkeypatch.setattr(collector, "OpenSearch", lambda **kwargs: search)
    monkeypatch.setattr(collector, "CountedSearch", lambda *args: None)
    monkeypatch.setattr(collector, "CountedEmbedder", lambda *args: None)
    monkeypatch.setattr(collector, "create_hosted_app", lambda *args: None)
    listener = SimpleNamespace(bind=Mock(), getsockname=lambda: ("127.0.0.1", 12345), close=Mock())
    monkeypatch.setattr(collector, "socket", SimpleNamespace(socket=lambda: listener))

    class Server:
        started = False
        should_exit = False

        async def serve(self, **kwargs):
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(0)

    monkeypatch.setattr(collector.uvicorn, "Server", lambda *args: Server())

    async def qualify(*args, **kwargs):
        if delayed_qualification:
            for _ in range(5):
                assert limiter.reserve(generation=True, now=clock.now) == 0
                clock.now += 20
        return {"qualified": True}

    monkeypatch.setattr(collector, "qualify", qualify)
    arrivals, statuses = [], []
    durations = [1] * 12 if delayed_qualification else [25, 25, 25] + [1] * 9

    async def collect(client, job, *args):
        retry = limiter.reserve(generation=True, now=clock.now)
        if unexpected_rejection and len(arrivals) == 2:
            retry = 7
        arrivals.append(clock.now)
        statuses.append(429 if retry else 200)
        clock.now += durations[len(arrivals) - 1]
        hf.attempts += not retry
        return {**job, "ok": not retry, "error_type": "HTTP429" if retry else None,
                "integrity_breach": False, "resource_passed": True,
                "hosted": {"usage_complete": True, "outbound_attempts": int(not retry), "unknown_usage_attempts": 0},
                "retry_after_seconds": retry}

    monkeypatch.setattr(collector, "collect_hosted_attempt", collect)
    jobs = [{"key": str(i), "case_id": "case", "path": "agent", "mode": "bm25", "transport": "json"} for i in range(12)]
    profile = {"window_seconds": 61, "generations_per_minute": 6, "live_margin_mib": 600}
    completion = await collector.run_collection(config, jobs, [], [], tmp_path, profile, 261,
                                               hf_factory=lambda *args, **kwargs: hf)
    rows = [json.loads(line) for line in (tmp_path / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    if unexpected_rejection:
        assert completion["status"] == "stopped" and completion["stop_reason"] == "failed_paper_request"
        assert len(rows) == len(arrivals) == 3 and statuses == [200, 200, 429]
        assert hf.attempts == 2
    else:
        assert completion["status"] == "collected"
        assert len(rows) == len(arrivals) == 12 and statuses == [200] * 12
        assert all(arrivals[i] - arrivals[i - 6] >= 61 for i in range(6, len(arrivals)))
    search.close.assert_called_once()
    listener.close.assert_called_once()
    closed.assert_called_once()
