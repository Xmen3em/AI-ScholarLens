"""A fair, bounded pool of model-call slots shared by every student (docs/specs/multi-user.md §1, §4).

Slots are granted in arrival order; a waiting job can report its place in line. One HTTP client
serves every student's StudyModel.
"""

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

import httpx
from pydantic import SecretStr

# The running job's deadline (set by StudyService._run); waiting for a slot extends it by the wait.
JOB_DEADLINE: ContextVar[asyncio.Timeout | None] = ContextVar("study_job_deadline", default=None)


class ModelPool:
    def __init__(self, token: SecretStr, slots: int):
        if type(slots) is not int or not 1 <= slots <= 4:
            raise ValueError("invalid_pool_slots")
        self.slots = slots
        self.client = httpx.AsyncClient(headers={"Authorization": "Bearer " + token.get_secret_value()},
            timeout=httpx.Timeout(80, connect=5), follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=slots, max_keepalive_connections=slots))
        self._running = 0
        self._waiting: deque[tuple[str, asyncio.Future]] = deque()
        # Jobs that have held a slot: their next call (the claim check) goes ahead of new jobs.
        self._started: set[str] = set()

    def position(self, job: str) -> int | None:
        """1-based place among waiting jobs, or None when the job is running or unknown."""
        for index, (waiting, _) in enumerate(self._waiting, 1):
            if waiting == job:
                return index
        return None

    def _grant(self) -> None:
        while self._waiting and self._running < self.slots:
            _, future = self._waiting.popleft()
            if not future.done():
                self._running += 1
                future.set_result(None)

    @asynccontextmanager
    async def slot(self, job: str) -> AsyncIterator[None]:
        if self._running < self.slots and not self._waiting:
            self._running += 1
        else:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            entry = (job, future)
            if job in self._started:
                # Behind other continuations, ahead of every job that has not started yet.
                index = next((i for i, (waiting, _) in enumerate(self._waiting) if waiting not in self._started),
                             len(self._waiting))
                self._waiting.insert(index, entry)
            else:
                self._waiting.append(entry)
            # The job's deadline pauses while it waits and resumes with the time it had left.
            deadline = JOB_DEADLINE.get()
            when = deadline.when() if deadline is not None else None
            remaining = when - loop.time() if when is not None else None
            if deadline is not None and remaining is not None:
                deadline.reschedule(None)
            try:
                await future
            except asyncio.CancelledError:
                if entry in self._waiting:
                    self._waiting.remove(entry)
                elif future.done() and not future.cancelled():
                    # Granted just as it was cancelled: hand the slot on.
                    self._running -= 1
                    self._grant()
                raise
            finally:
                if deadline is not None and remaining is not None:
                    deadline.reschedule(loop.time() + remaining)
        self._started.add(job)
        try:
            yield
        finally:
            self._running -= 1
            self._grant()

    async def aclose(self) -> None:
        await self.client.aclose()
