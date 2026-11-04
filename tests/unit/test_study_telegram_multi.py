import json

import httpx
import pytest
from pydantic import SecretStr
from src.services.study import access_text
from src.services.telegram_bot import OffsetStore, PrivateTelegramBot

from tests.unit.test_study_telegram import telegram_calls
from tests.unit.test_telegram_bot import KEY, settings
from tests.unit.test_telegram_policy import update

STUDENT, OTHER = 555, 666
JOB_A, JOB_B = "a" * 32, "b" * 32


def from_user(text, user, update_id=10):
    value = update(text, **{"from": {"id": user, "is_bot": False}, "chat": {"id": user, "type": "private"}})
    value["update_id"] = update_id
    return value


def bot_for(tmp_path):
    return PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True, multi_user=True)


def api(messages=None, pending=None, claim=None, telegram=None, seen=None):
    def respond(request):
        path = request.url.path
        if request.url.host == "api.telegram.org":
            if telegram is not None:
                return telegram(request)
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
        body = json.loads(request.content) if request.content else {}
        if seen is not None:
            seen.append((path.rsplit("/", 1)[-1], body))
        if path.endswith("/messages"):
            return httpx.Response(200, json=messages or {"reply": "تمام"})
        if path.endswith("/pending"):
            return httpx.Response(200, json=pending.pop(0) if pending else {"jobs": [], "running": []})
        if path.endswith("/claim"):
            return httpx.Response(200, json=claim(body) if claim else {"claimed": False})
        if path.endswith("/undeliverable"):
            return httpx.Response(200, json={"ok": True})
        pytest.fail("unexpected request " + path)
    return respond


@pytest.mark.anyio
async def test_reply_goes_to_the_senders_chat(stub_httpx, tmp_path):
    seen = []
    calls = stub_httpx(api(seen=seen))
    async with bot_for(tmp_path) as bot:
        await bot.handle(from_user("/usage", STUDENT))
    assert seen == [("messages", {"intent": "telegram:10", "text": "/usage", "user_id": STUDENT})]
    assert [call["chat_id"] for call in telegram_calls(calls, "sendMessage")] == [STUDENT]


@pytest.mark.anyio
async def test_a_silent_api_reply_sends_nothing(stub_httpx, tmp_path):
    calls = stub_httpx(api(messages={"reply": None}))
    async with bot_for(tmp_path) as bot:
        assert await bot.handle(from_user("hello", 999)) == "study_silent"
    assert telegram_calls(calls, "sendMessage") == []


@pytest.mark.anyio
async def test_group_chat_gets_one_refusal(stub_httpx, tmp_path):
    seen = []
    calls = stub_httpx(api(seen=seen))
    async with bot_for(tmp_path) as bot:
        group = update("/paper 1706.03762", chat={"id": -100, "type": "group"}, **{"from": {"id": STUDENT, "is_bot": False}})
        assert await bot.handle(group) == "group_refused"
        group["update_id"] = 11
        assert await bot.handle(group) == "ignored"
    assert [(call["chat_id"], call["text"]) for call in telegram_calls(calls, "sendMessage")] == [(-100, access_text.GROUP_CHAT)]
    assert seen == []


@pytest.mark.anyio
async def test_queued_stage_shows_the_place_in_line(stub_httpx, tmp_path):
    running = [{"user": STUDENT, "id": JOB_A, "stage": "queued", "position": 2}]
    calls = stub_httpx(api(messages={"job_id": JOB_A, "reply": "📖 بجهّز الشرح"},
                           pending=[{"jobs": [], "running": running}]))
    async with bot_for(tmp_path) as bot:
        assert await bot.handle(from_user("1706.03762", STUDENT)) == "study_admitted"
        await bot.deliver_study()
    [edit] = telegram_calls(calls, "editMessageText")
    assert edit["chat_id"] == STUDENT and edit["text"] == access_text.QUEUED.format(n=2)


@pytest.mark.anyio
async def test_progress_is_tracked_per_chat(stub_httpx, tmp_path):
    running = [{"user": STUDENT, "id": JOB_A, "stage": "reading", "position": None},
               {"user": OTHER, "id": JOB_B, "stage": "checking", "position": None}]
    replies = iter([{"job_id": JOB_A, "reply": "a"}, {"job_id": JOB_B, "reply": "b"}])

    def messages(request):
        return httpx.Response(200, json=next(replies))
    handler = api(pending=[{"jobs": [], "running": running}])

    def respond(request):
        if request.url.path.endswith("/messages"):
            return messages(request)
        return handler(request)
    calls = stub_httpx(respond)
    async with bot_for(tmp_path) as bot:
        await bot.handle(from_user("1706.03762", STUDENT, 10))
        await bot.handle(from_user("1706.03762", OTHER, 11))
        await bot.deliver_study()
    assert sorted(call["chat_id"] for call in telegram_calls(calls, "editMessageText")) == [STUDENT, OTHER]


@pytest.mark.anyio
async def test_a_403_for_one_student_does_not_block_another(stub_httpx, tmp_path):
    seen = []

    def telegram(request):
        if json.loads(request.content).get("chat_id") == STUDENT:
            return httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})
    jobs = [{"id": JOB_A, "status": "ready", "user": STUDENT}, {"id": JOB_B, "status": "ready", "user": OTHER}]
    calls = stub_httpx(api(pending=[{"jobs": jobs, "running": []}], seen=seen, telegram=telegram,
                           claim=lambda body: {"claimed": True, "result": {"text": "شرح " + str(body["user_id"])}}))
    async with bot_for(tmp_path) as bot:
        await bot.deliver_study()
    assert ("undeliverable", {"user_id": STUDENT}) in seen
    assert ("claim", {"job_id": JOB_B, "user_id": OTHER}) in seen
    assert any(call["chat_id"] == OTHER for call in telegram_calls(calls, "sendMessage"))


@pytest.mark.anyio
async def test_owner_only_bot_ignores_other_users(stub_httpx, tmp_path):
    calls = stub_httpx(lambda _: pytest.fail("a stranger reached the network"))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        assert await bot.handle(from_user("1706.03762", STUDENT)) == "ignored"
    assert not calls


@pytest.mark.anyio
async def test_a_photo_403_for_one_student_does_not_block_another(stub_httpx, tmp_path):
    # Final review, Minor 2 (Review Focus 4): the study-map photo path must handle a blocked student too.
    import base64

    seen = []
    image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"synthetic").decode()

    def telegram(request):
        if request.url.path.endswith("/sendPhoto"):
            return httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})
    jobs = [{"id": JOB_A, "status": "ready", "user": STUDENT}, {"id": JOB_B, "status": "ready", "user": OTHER}]
    calls = stub_httpx(api(pending=[{"jobs": jobs, "running": []}], seen=seen, telegram=telegram,
                           claim=lambda body: {"claimed": True, "result": {"text": "شرح", "image": image}}))
    async with bot_for(tmp_path) as bot:
        await bot.deliver_study()
    assert ("undeliverable", {"user_id": STUDENT}) in seen
    assert any(call["chat_id"] == OTHER for call in telegram_calls(calls, "sendMessage"))
