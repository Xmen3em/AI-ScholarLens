"""The invite-only beta end to end through the study API (docs/specs/multi-user.md, Acceptance)."""

import asyncio

import pytest
from src.services.study import access_text
from src.services.study.store import StudyStore

from tests.unit.test_access_gate import OWNER
from tests.unit.test_study_registry import Harness


async def test_two_invited_students_share_one_slot_and_a_stranger_is_turned_away(tmp_path):
    hold = asyncio.Event()
    h = Harness(tmp_path, hold=hold, parallel_jobs=1)
    try:
        invites = (await h.send(OWNER, "/invite 2"))["reply"]
        codes = [line.strip() for line in invites.splitlines() if len(line.strip()) == 10 and line.strip().isalnum()]
        assert await h.send(111, "/start " + codes[0]) == {"reply": access_text.WELCOME}
        assert await h.send(222, "/start " + codes[1]) == {"reply": access_text.WELCOME}

        first = await h.send(111, "1706.03762")
        second = await h.send(222, "1706.03762")
        await asyncio.sleep(0.05)
        running = {row["user"]: row for row in (await h.client.post("/api/v1/study/pending")).json()["running"]}
        assert running[111]["position"] is None and running[222] == {**running[222], "stage": "queued", "position": 1}

        assert await h.send(333, "1706.03762") == {"reply": access_text.NOT_MEMBER}
        assert await h.send(333, "hello") == {"reply": None}

        hold.set()
        await h.done(111, first["job_id"])
        await h.done(222, second["job_id"])
        for user in (111, 222):
            assert StudyStore(h.path, str(user)).context()["paper_id"] == "1706.03762v1"
            assert await h.send(user, "/usage") == {"reply": access_text.USAGE.format(p=2, P=3, q=30, Q=30)}
        assert StudyStore(h.path, "333").context() is None

        usage = h.gate.owner_usage()
        assert 0 < usage["spent"] <= usage["ceiling"] and usage["reserved"] == 0
        owner = (await h.send(OWNER, "/usage"))["reply"]
        assert "111" in owner and "222" in owner and "333" not in owner
    finally:
        hold.set()
        await asyncio.sleep(0.05)
        await h.aclose()


@pytest.mark.parametrize("enabled", [False])
async def test_the_switch_defaults_to_off(enabled):
    from src.services.study.access_settings import AccessSettings

    assert AccessSettings(_env_file=None).multi_user is enabled
