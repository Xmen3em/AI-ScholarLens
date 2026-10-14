import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from src.services.telegram_bot import BotError, OffsetStore, PrivateTelegramBot, TelegramSettings, single_instance

from tests.unit.test_agent_service import answer, service
from tests.unit.test_telegram_policy import OWNER, update

TOKEN = "123456789:synthetic-private-telegram-token-123456"
KEY = "synthetic-private-api-key-1234567890"


def settings(**values):
    return TelegramSettings(_env_file=None, enabled=True, bot_token=TOKEN, owner_id=OWNER, **values)


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_id": None},
        {"owner_id": True},
        {"bot_token": None},
        {"bot_token": "bad"},
        {"api_base_url": "https://evil.invalid"},
        {"api_base_url": "http://127.0.0.1:8000/api/v1?secret=x"},
    ],
)
def test_required_private_configuration_fails_closed(changes):
    values = {"enabled": True, "bot_token": TOKEN, "owner_id": OWNER, **changes}
    with pytest.raises(ValidationError) as exc:
        TelegramSettings(_env_file=None, **values)
    assert TOKEN not in str(exc.value) and KEY not in str(exc.value)


def test_offset_is_durable_and_missing_or_corrupt_state_cannot_replay_uncertain_work(tmp_path):
    store = OffsetStore(tmp_path / "offset.json")
    assert store.offset == 0
    store.advance(11)
    assert OffsetStore(store.path).offset == 11
    for value in [{"next_update_id": True}, {}, {"next_update_id": 11, "private": "query"}]:
        store.path.write_text(json.dumps(value))
        with pytest.raises(BotError):
            OffsetStore(store.path)


def test_second_instance_cannot_hold_same_owner_offset(tmp_path):
    with single_instance(tmp_path / "offset.json"):
        with pytest.raises(BotError):
            with single_instance(tmp_path / "offset.json"):
                pytest.fail("second bot acquired lock")


@pytest.mark.parametrize("which", ["path", "marker"])
def test_deleted_offset_or_registration_never_reseeds_uncertain_work(tmp_path, which):
    store = OffsetStore(tmp_path / "offset.json")
    store.advance(11)
    getattr(store, which).unlink()
    with pytest.raises(BotError):
        OffsetStore(store.path)


@pytest.mark.anyio
async def test_help_never_calls_api_and_invalid_message_ack_is_not_retried(stub_httpx, tmp_path):
    calls = stub_httpx(lambda request: httpx.Response(200, json={"ok": True, "result": []}))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        assert await bot.handle(update("/help")) == "reply_failed"
    assert len(calls) == 1 and calls[0].url.host == "api.telegram.org"


@pytest.mark.anyio
async def test_owner_ask_uses_authenticated_api_and_never_sends_api_key_to_telegram(stub_httpx, tmp_path, caplog):
    response = await answer(service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}]))

    def handler(request):
        if request.url.host == "127.0.0.1":
            assert request.headers["X-API-Key"] == KEY
            assert OffsetStore(tmp_path / "offset.json").offset == 11
            return httpx.Response(200, json=response.model_dump())
        assert "X-API-Key" not in request.headers
        body = json.loads(request.content)
        assert body["chat_id"] == OWNER and "parse_mode" not in body
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    calls = stub_httpx(handler)
    caplog.set_level(logging.DEBUG, logger="httpx")
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        assert await bot.handle(update()) == "answered"
        assert await bot.handle(update()) == "ignored"
    assert len(calls) == 2 and TOKEN not in caplog.text and KEY not in caplog.text
    saved = (tmp_path / "offset.json").read_text()
    assert set(json.loads(saved)) == {"next_update_id"} and response.answer not in saved


@pytest.mark.anyio
async def test_nonowner_help_and_api_failure_do_not_repeat_inference(stub_httpx, tmp_path):
    calls = stub_httpx(lambda request: httpx.Response(503, json={"detail": "private-error"}))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        assert await bot.handle(update(**{"from": {"id": OWNER + 1, "is_bot": False}})) == "ignored"
        assert not calls
        assert await bot.handle({**update(), "update_id": 11}) == "reply_failed"
        assert await bot.handle({**update(), "update_id": 11}) == "ignored"
    assert len(calls) == 2
    assert "private-error" not in calls[-1].content.decode()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["timeout", "oversize", "malformed", "invalid_answer"])
async def test_uncertain_or_invalid_api_result_consumes_update_and_has_no_inference_retry(stub_httpx, tmp_path, failure):
    response = await answer(service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}]))

    def handler(request):
        if request.url.host != "127.0.0.1":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        if failure == "timeout":
            raise httpx.ReadTimeout("private-token-error")
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 262145)
        if failure == "malformed":
            return httpx.Response(200, json={"answer": "private-provider-output"})
        return httpx.Response(200, json={**response.model_dump(), "answer": "unsupported private answer [1.1]"})

    calls = stub_httpx(handler)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        assert await bot.handle(update()) == "api_failed"
    assert len(calls) == 2 and OffsetStore(tmp_path / "offset.json").offset == 11
    assert "private" not in calls[-1].content.decode()


@pytest.mark.anyio
async def test_startup_refuses_existing_webhook_without_mutating_it(stub_httpx, tmp_path):
    calls = stub_httpx(lambda request: httpx.Response(200, json={"ok": True, "result": {"url": "https://private-hook.invalid"}}))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        with pytest.raises(BotError):
            await bot.check_webhook()
    assert len(calls) == 1 and calls[0].url.path.endswith("/getWebhookInfo")


@pytest.mark.anyio
async def test_polling_is_bounded_and_uses_only_message_updates(stub_httpx, tmp_path):
    calls = stub_httpx(lambda request: httpx.Response(200, json={"ok": True, "result": [update("/help")]}))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        values = await bot.poll()
    assert values == [update("/help")]
    body = json.loads(calls[0].content)
    assert body == {"offset": 0, "limit": 10, "timeout": 20, "allowed_updates": ["message"]}


@pytest.mark.anyio
@pytest.mark.parametrize("result", [None, {}, [{"update_id": True}], [{"update_id": -1}], [{"update_id": 1}] * 11])
async def test_invalid_poll_batch_never_reaches_api_or_replies(stub_httpx, tmp_path, result):
    calls = stub_httpx(lambda request: httpx.Response(200, json={"ok": True, "result": result}))
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        with pytest.raises(BotError):
            await bot.poll()
    assert len(calls) == 1 and not (tmp_path / "offset.json").exists()


@pytest.mark.anyio
async def test_cancellation_consumes_admitted_update_and_closes_api_work_without_reply(stub_httpx, tmp_path):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    calls = stub_httpx(blocked)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), OffsetStore(tmp_path / "offset.json")) as bot:
        task = asyncio.create_task(bot.handle(update()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await bot.handle(update()) == "ignored"
    assert cancelled.is_set() and len(calls) == 1 and OffsetStore(tmp_path / "offset.json").offset == 11


@pytest.mark.anyio
async def test_offset_save_failure_blocks_before_api_or_message(stub_httpx, tmp_path, monkeypatch):
    calls = stub_httpx(lambda request: httpx.Response(200, json={"ok": True, "result": {}}))
    store = OffsetStore(tmp_path / "offset.json")

    def failed(value):
        raise BotError("offset_write_failed")

    monkeypatch.setattr(store, "advance", failed)
    async with PrivateTelegramBot(settings(), SecretStr(KEY), store) as bot:
        with pytest.raises(BotError):
            await bot.handle(update())
    assert not calls
