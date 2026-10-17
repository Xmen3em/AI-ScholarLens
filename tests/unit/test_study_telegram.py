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
