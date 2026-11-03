import json

import httpx
import pytest
from pydantic import SecretStr
from src.services.telegram_bot import OffsetStore, PrivateTelegramBot

from tests.unit.test_telegram_bot import KEY, settings
from tests.unit.test_telegram_policy import OWNER, update


@pytest.mark.anyio
@pytest.mark.parametrize("changes", [{"from": {"id": OWNER + 1, "is_bot": False}},
    {"chat": {"id": OWNER, "type": "group"}}, {"forward_origin": {}}, {"via_bot": {}}])
async def test_study_cannot_bypass_owner_gate(stub_httpx, tmp_path, changes):
    calls = stub_httpx(lambda _: pytest.fail("untrusted message triggered network"))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        assert await bot.handle(update("/paper 1706.03762", **changes)) == "ignored"
    assert not calls


@pytest.mark.anyio
async def test_study_intent_uses_durable_update_id_and_does_not_block_on_inference(stub_httpx, tmp_path):
    def respond(request):
        if request.url.host == "api.telegram.org":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        assert json.loads(request.content) == {"intent": "telegram:10", "text": "/paper 1706.03762"}
        assert OffsetStore(tmp_path / "offset.json").offset == 11
        return httpx.Response(200, json={"job_id": "a" * 32, "reply": "بجهّز الشرح"})
    calls = stub_httpx(respond)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        assert await bot.handle(update("/paper 1706.03762")) == "study_admitted"
        assert await bot.handle(update("/paper 1706.03762")) == "ignored"
    assert len(calls) == 2


@pytest.mark.anyio
async def test_uncertain_delivery_is_claimed_first_and_not_replayed(stub_httpx, tmp_path):
    claimed = []
    def respond(request):
        if request.url.path.endswith("/pending"):
            return httpx.Response(200, json={"jobs": [{"id": "a" * 32}]})
        if request.url.path.endswith("/claim"):
            first = not claimed
            claimed.append(True)
            return httpx.Response(200, json={"claimed": first, "result": {"text": "شرح بالمصري"}})
        assert claimed
        raise httpx.ReadTimeout("uncertain Telegram acknowledgement")
    calls = stub_httpx(respond)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        from src.services.telegram_bot import BotError
        with pytest.raises(BotError):
            await bot.deliver_study()
        await bot.deliver_study()
    assert sum(request.url.host == "api.telegram.org" for request in calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("ack", [{}, {"message_id": False}, {"message_id": 0}])
async def test_photo_requires_a_valid_acknowledgement_without_retry(stub_httpx, tmp_path, ack):
    import base64

    from src.services.telegram_bot import BotError
    calls = stub_httpx(lambda _: httpx.Response(200, json={"ok": True, "result": ack}))
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"synthetic-test-image").decode()
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        with pytest.raises(BotError):
            await bot._study_photo(encoded)
    assert len(calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [429, 503, "timeout"])
async def test_study_api_failure_is_explained_once_to_the_owner(stub_httpx, tmp_path, failure):
    def respond(request):
        if request.url.host == "api.telegram.org":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        if failure == "timeout":
            raise httpx.ReadTimeout("uncertain local admission")
        return httpx.Response(failure, json={"detail": "private-diagnostic-must-not-be-forwarded"})
    calls = stub_httpx(respond)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        assert await bot.handle(update("/paper 1706.03762")) == "api_failed"
        assert bot.store.offset == 11
    assert len(calls) == 2
    payload = json.loads(calls[-1].content)
    assert "الخدمة" in payload["text"] and "private-diagnostic" not in payload["text"]


@pytest.mark.anyio
async def test_an_uncertain_admission_reply_does_not_trigger_another_telegram_message(stub_httpx, tmp_path):
    def respond(request):
        if request.url.host == "api.telegram.org":
            raise httpx.ReadTimeout("uncertain message acknowledgement")
        return httpx.Response(200, json={"reply": "بجهّز الشرح", "job_id": "a" * 32})
    calls = stub_httpx(respond)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        assert await bot.handle(update("/paper 1706.03762")) == "reply_failed"
    assert len(calls) == 2


JOB = "a" * 32


def progress_api(stages, *, edit=None):
    """A local API that admits one job, then reports it running at each stage in turn; Telegram acknowledges."""
    def respond(request):
        path = request.url.path
        if request.url.host == "api.telegram.org":
            if path.endswith("/editMessageText"):
                if edit is not None:
                    return edit(request)
                return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
        if path.endswith("/messages"):
            return httpx.Response(200, json={"job_id": JOB, "reply": "📖 بجهّز الشرح التمهيدي من الورقة… هبعت النتيجة هنا."})
        if path.endswith("/pending"):
            stage = stages.pop(0)
            return httpx.Response(200, json={"jobs": [], "running": [] if stage is None else [{"id": JOB, "stage": stage}]})
        pytest.fail("unexpected request " + path)
    return respond


def telegram_calls(calls, method):
    return [json.loads(request.content) for request in calls
            if request.url.host == "api.telegram.org" and request.url.path.endswith("/" + method)]


@pytest.mark.anyio
async def test_progress_edits_the_acknowledgement_once_per_stage_without_new_messages(stub_httpx, tmp_path):
    calls = stub_httpx(progress_api(["started", "reading", "reading", "writing_lesson", "checking", "checking"]))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        assert await bot.handle(update("/paper 1706.03762")) == "study_admitted"
        for _ in range(6):
            await bot.deliver_study()
    sent = telegram_calls(calls, "sendMessage")
    # Telegram can edit only messages sent without a reply keyboard.
    assert len(sent) == 1 and "reply_markup" not in sent[0]
    edits = telegram_calls(calls, "editMessageText")
    assert [edit["message_id"] for edit in edits] == [7, 7, 7]
    assert all(edit["chat_id"] == sent[0]["chat_id"] for edit in edits)
    assert ["1 من 3" in edits[0]["text"], "2 من 3" in edits[1]["text"], "3 من 3" in edits[2]["text"]] == [True] * 3
    assert "بقرأ الورقة" in edits[0]["text"] and "بكتب الشرح" in edits[1]["text"] and "نص الورقة" in edits[2]["text"]


@pytest.mark.anyio
async def test_progress_shows_only_known_stages_and_stops_when_the_job_is_no_longer_running(stub_httpx, tmp_path):
    calls = stub_httpx(progress_api(["private provider text", None, "checking"]))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        await bot.handle(update("/paper 1706.03762"))
        for _ in range(3):
            await bot.deliver_study()
    assert telegram_calls(calls, "editMessageText") == []


@pytest.mark.anyio
async def test_a_failed_progress_edit_is_not_retried_and_does_not_stop_delivery(stub_httpx, tmp_path):
    calls = stub_httpx(progress_api(["reading", "writing_lesson"],
                                    edit=lambda _: httpx.Response(400, json={"ok": False, "description": "message can't be edited"})))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        await bot.handle(update("/paper 1706.03762"))
        await bot.deliver_study()
        await bot.deliver_study()
    assert len(telegram_calls(calls, "editMessageText")) == 1


@pytest.mark.anyio
async def test_a_reply_without_a_job_keeps_the_keyboard_and_starts_no_progress(stub_httpx, tmp_path):
    def respond(request):
        if request.url.host == "api.telegram.org":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
        return httpx.Response(200, json={"reply": "تمام، مستوى الشرح اتغيّر"})
    calls = stub_httpx(respond)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        await bot.handle(update("/level researcher"))
        assert bot.progress is None
    assert "reply_markup" in telegram_calls(calls, "sendMessage")[0]


@pytest.mark.anyio
async def test_polling_waits_less_while_a_job_runs_so_progress_and_results_arrive_sooner(stub_httpx, tmp_path):
    api = progress_api(["writing_lesson", None])
    def respond(request):
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": []})
        return api(request)
    calls = stub_httpx(respond)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json"), study=True) as bot:
        await bot.poll()
        await bot.handle(update("/paper 1706.03762"))
        await bot.deliver_study()
        await bot.poll()
        await bot.deliver_study()
        await bot.poll()
    assert [call["timeout"] for call in telegram_calls(calls, "getUpdates")] == [20, 3, 20]
