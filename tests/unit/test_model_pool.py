import asyncio

import httpx
import pytest
from pydantic import SecretStr
from src.services.study.pool import ModelPool
from src.services.study.store import StudyStore
from src.services.study.tutor import StudyModel, TutorError

TOKEN = SecretStr("x" * 40)


async def test_at_most_n_calls_run_at_once():
    pool, running, peak = ModelPool(TOKEN, 3), 0, 0

    async def call(job):
        nonlocal running, peak
        async with pool.slot(job):
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    await asyncio.gather(*(call(f"j{i}") for i in range(5)))
    assert peak == 3
    await pool.aclose()


async def test_waiters_are_served_in_arrival_order():
    pool, order, release = ModelPool(TOKEN, 1), [], asyncio.Event()

    async def call(job, hold=False):
        async with pool.slot(job):
            order.append(job)
            if hold:
                await release.wait()

    first = asyncio.create_task(call("j1", hold=True))
    await asyncio.sleep(0)
    waiters = []
    for job in ("j2", "j3", "j4"):
        waiters.append(asyncio.create_task(call(job)))
        await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, *waiters)
    assert order == ["j1", "j2", "j3", "j4"]
    await pool.aclose()


async def test_position_counts_waiters_ahead():
    pool, release = ModelPool(TOKEN, 3), asyncio.Event()

    async def call(job):
        async with pool.slot(job):
            await release.wait()

    tasks = []
    for i in range(1, 6):
        tasks.append(asyncio.create_task(call(f"j{i}")))
        await asyncio.sleep(0)
    assert pool.position("j1") is None and pool.position("j3") is None
    assert pool.position("j4") == 1 and pool.position("j5") == 2 and pool.position("unknown") is None
    release.set()
    await asyncio.gather(*tasks)
    await pool.aclose()


async def test_a_cancelled_waiter_leaves_the_queue():
    pool, release = ModelPool(TOKEN, 1), asyncio.Event()

    async def call(job):
        async with pool.slot(job):
            await release.wait()

    holder = asyncio.create_task(call("j1"))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(call("j2"))
    later = asyncio.create_task(call("j3"))
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.sleep(0)
    assert pool.position("j2") is None and pool.position("j3") == 1
    release.set()
    await asyncio.gather(holder, later)
    await pool.aclose()


def test_slots_are_bounded():
    with pytest.raises(ValueError):
        ModelPool(TOKEN, 0)
    with pytest.raises(ValueError):
        ModelPool(TOKEN, 5)


async def test_a_model_with_a_pool_shares_its_client(tmp_path):
    pool = ModelPool(TOKEN, 3)
    a, b = (StudyModel(TOKEN, StudyStore(tmp_path / "s.sqlite3", owner), pool=pool) for owner in ("1", "2"))
    assert a.client is b.client is pool.client
    await a.aclose()
    assert not pool.client.is_closed
    await pool.aclose()


async def test_a_pooled_call_waits_for_a_slot(tmp_path):
    pool, entered = ModelPool(TOKEN, 1), asyncio.Event()
    store = StudyStore(tmp_path / "s.sqlite3", "1")
    job = store.create_job("t", {}, max_calls=1)
    model = StudyModel(TOKEN, store, pool=pool, memory=lambda: 2000, counter=lambda _: 100)
    model.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))

    async def hold():
        async with pool.slot("other"):
            entered.set()
            await asyncio.sleep(0.05)

    holder = asyncio.create_task(hold())
    await entered.wait()
    call = asyncio.create_task(model.complete(job["id"], "lesson", [{"role": "user", "content": "q"}],
                                              schema={"type": "object"}))
    await asyncio.sleep(0.01)
    assert pool.position(job["id"]) == 1 and store.attempts(job["id"]) == []
    with pytest.raises(TutorError):
        await call
    await holder
    await model.client.aclose()
    await pool.aclose()


async def test_a_started_jobs_next_call_goes_ahead_of_new_jobs():
    # Final review, Important 4: a lesson's check call must not queue behind newer lessons' writer calls.
    from src.services.study.pool import ModelPool

    pool, order, release = ModelPool(TOKEN, 1), [], asyncio.Event()

    async def call(job, hold=False):
        async with pool.slot(job):
            order.append(job)
            if hold:
                await release.wait()

    await call("a")                       # job a has had a slot (its writer call)
    holder = asyncio.create_task(call("x", hold=True))
    await asyncio.sleep(0)
    newcomer = asyncio.create_task(call("b"))
    await asyncio.sleep(0)
    continuation = asyncio.create_task(call("a"))
    await asyncio.sleep(0)
    assert pool.position("a") == 1 and pool.position("b") == 2
    release.set()
    await asyncio.gather(holder, newcomer, continuation)
    assert order == ["a", "x", "a", "b"]
    await pool.aclose()


async def test_time_spent_waiting_extends_the_jobs_deadline():
    # Final review, Important 4: queue time must not count toward the job's 160 s limit.
    from src.services.study.pool import JOB_DEADLINE, ModelPool

    pool, release = ModelPool(TOKEN, 1), asyncio.Event()

    async def hold():
        async with pool.slot("other"):
            await release.wait()

    holder = asyncio.create_task(hold())
    await asyncio.sleep(0)

    async def job():
        async with asyncio.timeout(0.1) as deadline:
            JOB_DEADLINE.set(deadline)
            async with pool.slot("mine"):
                await asyncio.sleep(0.05)
        return "done"

    task = asyncio.create_task(job())
    await asyncio.sleep(0.15)
    release.set()
    assert await task == "done"
    await holder
    await pool.aclose()
