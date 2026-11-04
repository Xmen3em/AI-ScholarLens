"""One StudyService per student over the shared store, pool and access gate (docs/specs/multi-user.md §1).

Lesson, evidence and claim-check code is unchanged: each student's service is today's service
bound to that student's owner key. A student holds at most one job, so the job a call belongs
to is that student's current job.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from src.operations import emit_event
from src.services.study.access import WORST_INPUT_TOKENS, AccessGate
from src.services.study.models import DEFAULT_PROFILE, call_cost_usd
from src.services.study.pool import ModelPool
from src.services.study.service import StudyService
from src.services.study.store import StudyStore

# Attempts left in these states may have reached the provider; they are charged their worst case.
UNSETTLED = frozenset({"reserved", "unknown"})


class ServiceRegistry:
    def __init__(self, path: Path, pool: ModelPool, gate: AccessGate, intake, content, *, owner_id: int,
                 research_python: Path | None, token: SecretStr, idle_seconds: float = 1800,
                 now: Callable[[], float] = time.monotonic,
                 model_factory: Callable[[StudyStore, Callable[[dict], None]], Any] | None = None):
        self.path, self.pool, self.gate, self.intake, self.content = path, pool, gate, intake, content
        self.owner_id, self.research_python, self.token = owner_id, research_python, token
        self.idle_seconds, self.now = idle_seconds, now
        self.model_factory = model_factory or self._study_model
        self._services: dict[int, StudyService] = {}
        self._models: dict[int, Any] = {}
        self._used: dict[int, float] = {}
        self._current: dict[int, str] = {}
        self._audited: dict[str, int] = {}

    def _study_model(self, store: StudyStore, audit: Callable[[dict], None]):
        from src.services.study.tutor import StudyModel

        return StudyModel(self.token, store, pool=self.pool, audit=audit)

    def service(self, user: int) -> StudyService:
        self._used[user] = self.now()
        if user not in self._services:
            store = StudyStore(self.path, str(user))
            def audit(record: dict, user: int = user) -> None:
                self._charge(user, record)

            model = self.model_factory(store, audit)
            research = self.research_python if user == self.owner_id else None
            self._models[user] = model
            self._services[user] = StudyService(store, self.intake, self.content, model, research_python=research)
        return self._services[user]

    def _charge(self, user: int, record: dict) -> None:
        job = self._current.get(user)
        usage = record.get("result", {}).get("usage")
        if job is not None:
            self._audited[job] = self._audited.get(job, 0) + 1
            self.gate.charge(job, call_cost_usd(DEFAULT_PROFILE, usage, estimate=WORST_INPUT_TOKENS))

    def track(self, user: int, job_id: str) -> bool:
        """Follow a job the student's service just started; False when no new work began."""
        service = self._services.get(user)
        task = next((task for task in service.tasks if task.get_name() == job_id), None) if service else None
        if task is None or task.done():
            return False
        self._current[user] = job_id
        task.add_done_callback(lambda done: self._finish(user, job_id))
        return True

    def _finish(self, user: int, job_id: str) -> None:
        try:
            store = StudyStore(self.path, str(user))
            attempts = store.attempts(job_id)
            # Unsettled attempts may have reached the provider; succeeded ones the audit hook never saw
            # (the /deep worker runs its own model) are priced at their worst case too.
            unseen = sum(attempt["state"] == "succeeded" for attempt in attempts) - self._audited.get(job_id, 0)
            extra = sum(attempt["state"] in UNSETTLED for attempt in attempts) + max(0, unseen)
            if extra:
                self.gate.charge(job_id, extra * self.gate.worst_call_usd())
            job = store.get_job(job_id)
            kind = (job["result"] or {}).get("kind") if job and job["status"] == "ready" else None
            self.gate.settle(job_id, delivered_kind=kind if kind in ("paper", "question") else None)
        except Exception as exc:  # noqa: BLE001 - startup settlement closes what this could not
            emit_event("study_settle_failed", level=logging.ERROR, error_class=type(exc).__name__,
                       user=StudyStore(self.path, str(user)).fingerprint())
        finally:
            self._audited.pop(job_id, None)
            if self._current.get(user) == job_id:
                del self._current[user]

    def busy(self, user: int) -> bool:
        service = self._services.get(user)
        return bool(service and any(not task.done() for task in service.tasks)) or user in self._current

    def running(self) -> list[dict]:
        rows = []
        for user, service in self._services.items():
            for job_id, stage in list(service.progress.items()):
                position = self.pool.position(job_id)
                rows.append({"user": user, "id": job_id, "stage": "queued" if position else stage, "position": position})
        return rows

    async def forget(self, user: int) -> None:
        service = self._services.pop(user, None)
        model = self._models.pop(user, None)
        self._used.pop(user, None)
        if service is not None:
            await service.aclose()
        if model is not None:
            await model.aclose()
        StudyStore(self.path, str(user)).forget()

    async def close_idle(self) -> None:
        cutoff = self.now() - self.idle_seconds
        for user in [user for user, used in self._used.items() if used < cutoff and not self.busy(user)]:
            service, model = self._services.pop(user, None), self._models.pop(user, None)
            self._used.pop(user, None)
            if service is not None:
                await service.aclose()
            if model is not None:
                await model.aclose()

    def sweep(self, retention_days: int) -> int:
        """Forget every student inactive past the retention window; the owner is never swept."""
        cutoff = self.gate.now() - retention_days * 86400
        swept = 0
        for member in self.gate.members():
            if member["role"] == "student" and member["last_active"] < cutoff and not self.busy(member["user"]):
                StudyStore(self.path, str(member["user"])).forget()
                swept += 1
        return swept

    async def aclose(self) -> None:
        for service in self._services.values():
            await service.aclose()
        for model in self._models.values():
            await model.aclose()
        self._services.clear()
        self._models.clear()
        await asyncio.sleep(0)


def settle_interrupted(gate: AccessGate, path: Path) -> int:
    """At startup: settle reservations a previous run left open, after recover_all_interrupted.

    A bound job's unsettled attempts are charged their worst case and nothing is counted against
    the student; a reservation that never got a job is released. Returns how many were settled.
    """
    settled = 0
    for reservation in gate.open_reservations():
        job = reservation["job"]
        if job:
            attempts = StudyStore(path, str(reservation["user"])).attempts(job)
            unsettled = sum(attempt["state"] in UNSETTLED for attempt in attempts)
            if unsettled:
                gate.charge(job, unsettled * gate.worst_call_usd())
            gate.settle(job, delivered_kind=None)
        else:
            gate.release(reservation["key"])
        settled += 1
    return settled
