import json
import logging
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from src.commands import setup_telegram as setup
from src.services.telegram_bot import BotError, TelegramSettings

TOKEN = "123456789:synthetic-private-telegram-token-123456"
USERNAME = "AIScholarLensbot"
OWNER = 987654321
NOW = 1_800_000_000


def proof(state, owner=OWNER):
    return {
        "update_id": 10,
        "message": {
            "date": NOW + 1,
            "from": {"id": owner, "is_bot": False},
            "chat": {"id": owner, "type": "private"},
            "text": f"/start {state['nonce']}",
        },
    }


def test_only_fresh_challenge_selects_owner_not_first_sender():
    state = setup.new_challenge(USERNAME, 123456789, NOW)
    unrelated = proof(state, OWNER + 1)
    unrelated["message"]["text"] = "/start"
    assert setup.verify_owner([unrelated, proof(state)], state, NOW + 2) == OWNER
    assert len(state["nonce"]) <= 64
    assert setup.pairing_link(state).startswith(f"https://t.me/{USERNAME}?start=")


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "/start"),
        ("text", "/start wrong-code"),
        ("date", NOW - 1),
        ("date", True),
        ("date", NOW + 100),
        ("from", {"id": OWNER, "is_bot": True}),
        ("from", {"id": True, "is_bot": False}),
        ("chat", {"id": OWNER, "type": "group"}),
        ("chat", {"id": OWNER + 1, "type": "private"}),
        ("forward_origin", {}),
        ("via_bot", {}),
    ],
)
def test_unproven_or_nonprivate_messages_never_supply_an_owner(field, value):
    state = setup.new_challenge(USERNAME, 123456789, NOW)
    update = proof(state)
    update["message"][field] = value
    assert setup.verify_owner([update], state, NOW + 2) is None


def test_expired_or_ambiguous_proof_fails_closed():
    state = setup.new_challenge(USERNAME, 123456789, NOW)
    with pytest.raises(BotError):
        setup.verify_owner([proof(state)], state, NOW + 3600)
    with pytest.raises(BotError):
        setup.verify_owner([proof(state), proof(state, OWNER + 1)], state, NOW + 2)


def test_same_owner_multiple_proofs_are_safe_but_saturated_queue_requires_review():
    state = setup.new_challenge(USERNAME, 123456789, NOW)
    assert setup.verify_owner([proof(state), proof(state)], state, NOW + 2) == OWNER
    with pytest.raises(BotError):
        setup.verify_owner([proof(state)] * 100, state, NOW + 2)


@pytest.fixture
def sync_http(monkeypatch):
    real_client = httpx.Client

    def install(handler):
        calls = []

        def recording(request):
            calls.append(request)
            return handler(request)

        monkeypatch.setattr(
            setup.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(recording), **kwargs)
        )
        return calls

    return install


def telegram_response(request):
    if request.url.path.endswith("getMe"):
        result = {"id": 123456789, "is_bot": True, "username": USERNAME}
    elif request.url.path.endswith("getWebhookInfo"):
        result = {"url": ""}
    else:
        result = []
    return httpx.Response(200, json={"ok": True, "result": result})


def test_pairing_requests_are_readonly_bounded_and_never_log_token(sync_http, caplog):
    calls = sync_http(telegram_response)
    caplog.set_level(logging.DEBUG, logger="httpx")
    prior_filters = list(logging.getLogger("httpx").filters)
    with setup.PairingAPI(SecretStr(TOKEN)) as api:
        assert api.identity(USERNAME) == 123456789
        assert api.updates() == []
    assert [request.url.path.rsplit("/", 1)[-1] for request in calls] == ["getMe", "getWebhookInfo", "getUpdates"]
    assert json.loads(calls[-1].content) == {"limit": 100, "timeout": 0}
    assert all("X-API-Key" not in request.headers for request in calls)
    assert TOKEN not in caplog.text and "api.telegram.org/bot" not in caplog.text
    assert logging.getLogger("httpx").filters == prior_filters


@pytest.mark.parametrize("failure", ["wrong_bot", "webhook", "timeout", "oversize", "duplicate", "redirect"])
def test_pairing_transport_failures_do_not_expose_provider_data_or_retry(sync_http, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(TOKEN)
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 262145)
        if failure == "duplicate":
            return httpx.Response(200, content=b'{"ok":true,"ok":true,"result":{}}')
        if failure == "redirect":
            return httpx.Response(302, headers={"location": f"https://evil.invalid/{TOKEN}"})
        if failure == "wrong_bot":
            return httpx.Response(200, json={"ok": True, "result": {"id": 123456789, "is_bot": True, "username": "otherbot"}})
        if request.url.path.endswith("getWebhookInfo"):
            return httpx.Response(200, json={"ok": True, "result": {"url": f"https://evil.invalid/{TOKEN}"}})
        return telegram_response(request)

    calls = sync_http(handler)
    with pytest.raises(BotError) as exc, setup.PairingAPI(SecretStr(TOKEN)) as api:
        api.identity(USERNAME)
    assert TOKEN not in str(exc.value) and "evil.invalid" not in str(exc.value)
    assert len(calls) == (2 if failure == "webhook" else 1)


def test_owner_write_preserves_every_other_private_setting_and_does_not_enable_bot(tmp_path):
    path = tmp_path / ".env"
    original = f"# private settings\r\nTELEGRAM_BOT_TOKEN={TOKEN}\r\nTELEGRAM_ENABLED=false\r\nTELEGRAM_OWNER_ID=\r\nAPI_KEY=keep-this-value\r\nHF_INFERENCE_ENABLED=false\r\n".encode()
    path.write_bytes(original)
    setup.write_owner(path, tmp_path / "private.tmp", SecretStr(TOKEN), OWNER)
    expected = original.replace(b"TELEGRAM_OWNER_ID=\r\n", f"TELEGRAM_OWNER_ID={OWNER}\r\n".encode())
    assert path.read_bytes() == expected
    setup.write_owner(path, tmp_path / "private.tmp", SecretStr(TOKEN), OWNER)
    assert path.read_bytes() == expected and not (tmp_path / "private.tmp").exists()


@pytest.mark.parametrize(
    "extra",
    ["TELEGRAM_ENABLED=true\n", "TELEGRAM_OWNER_ID=456\n", "TELEGRAM_OWNER_ID=\nTELEGRAM_OWNER_ID=\n"],
)
def test_owner_setup_refuses_runtime_activation_or_existing_owner_replacement(tmp_path, extra):
    path = tmp_path / ".env"
    original = f"TELEGRAM_BOT_TOKEN={TOKEN}\n{extra}".encode()
    path.write_bytes(original)
    with pytest.raises(BotError):
        setup.write_owner(path, tmp_path / "private.tmp", SecretStr(TOKEN), OWNER)
    assert path.read_bytes() == original


def test_offline_check_never_opens_network_or_creates_private_state(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup, "TelegramSettings", lambda: TelegramSettings(_env_file=None, bot_token=TOKEN))
    monkeypatch.setattr(setup, "PairingAPI", lambda *args: pytest.fail("Offline check used network"))
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--check"])
    setup.main()
    assert json.loads(capsys.readouterr().out) == {"status": "owner_required", "outbound_calls": 0}
    assert not list(tmp_path.iterdir())


def test_prepare_then_verify_saves_only_proven_owner_without_confirming_updates(monkeypatch, tmp_path, sync_http, capsys):
    monkeypatch.chdir(tmp_path)
    original = f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_ENABLED=false\nTELEGRAM_OWNER_ID=\n".encode()
    (tmp_path / ".env").write_bytes(original)
    monkeypatch.setattr(setup, "TelegramSettings", lambda: TelegramSettings(_env_file=None, bot_token=TOKEN))
    monkeypatch.setattr(setup.time, "time", lambda: NOW)
    calls = sync_http(telegram_response)
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--prepare", "--username", f"@{USERNAME}"])
    setup.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "awaiting_private_start" and result["pairing_url"].startswith("https://t.me/")
    assert (tmp_path / ".env").read_bytes() == original
    state_path = tmp_path / "data/telegram/pairing.json"
    state = json.loads(state_path.read_text())
    calls = sync_http(
        lambda request: httpx.Response(200, json={"ok": True, "result": [proof(state)]})
        if request.url.path.endswith("getUpdates")
        else telegram_response(request)
    )
    monkeypatch.setattr(setup.time, "time", lambda: NOW + 2)
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--verify"])
    setup.main()
    assert json.loads(capsys.readouterr().out)["status"] == "owner_configured_bot_disabled"
    assert (tmp_path / ".env").read_bytes() == original.replace(b"TELEGRAM_OWNER_ID=\n", f"TELEGRAM_OWNER_ID={OWNER}\n".encode())
    assert json.loads(state_path.read_text()) == {"version": 1, "status": "paired", "username": USERNAME, "bot_id": 123456789}
    assert json.loads(calls[-1].content) == {"limit": 100, "timeout": 0}


@pytest.mark.parametrize("change", [{"nonce": "bad"}, {"bot_id": True}, {"expires_at": NOW + 999999}, {"extra": TOKEN}])
def test_corrupt_pairing_state_is_rejected_before_network_or_env_changes(monkeypatch, tmp_path, change, capsys):
    monkeypatch.chdir(tmp_path)
    state_path = tmp_path / "data/telegram/pairing.json"
    state_path.parent.mkdir(parents=True)
    state = deepcopy(setup.new_challenge(USERNAME, 123456789, NOW))
    state.update(change)
    state_path.write_text(json.dumps(state))
    monkeypatch.setattr(setup, "TelegramSettings", lambda: TelegramSettings(_env_file=None, bot_token=TOKEN))
    monkeypatch.setattr(setup.time, "time", lambda: NOW + 2)
    monkeypatch.setattr(setup, "PairingAPI", lambda *args: pytest.fail("Corrupt state used network"))
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--verify"])
    with pytest.raises(SystemExit) as exc:
        setup.main()
    assert exc.value.code == 2 and TOKEN not in capsys.readouterr().out


def test_state_path_escape_is_rejected_before_network(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "data").mkdir()
    try:
        (tmp_path / "data/telegram").symlink_to(outside, target_is_directory=True)
    except OSError:
        # Windows without symlink privileges: a substituted resolver exercises
        # the same path boundary without skipping the security assertion.
        real_resolve = Path.resolve
        monkeypatch.setattr(
            Path, "resolve", lambda self: outside / "pairing.json" if self.name == "pairing.json" else real_resolve(self)
        )
    monkeypatch.setattr(setup, "TelegramSettings", lambda: TelegramSettings(_env_file=None, bot_token=TOKEN))
    monkeypatch.setattr(setup, "PairingAPI", lambda *args: pytest.fail("Escaped path used network"))
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--prepare", "--username", USERNAME])
    with pytest.raises(SystemExit) as exc:
        setup.main()
    assert exc.value.code == 2


def test_setup_cannot_send_messages_or_confirm_pending_updates(sync_http):
    calls = sync_http(telegram_response)
    with setup.PairingAPI(SecretStr(TOKEN)) as api:
        for method, payload in [("sendMessage", {"chat_id": OWNER}), ("getUpdates", {"offset": 11}), ("deleteWebhook", {})]:
            with pytest.raises(BotError):
                api.call(method, payload)
    assert not calls
    with pytest.raises(BotError):
        api.call("getMe", {})


def test_null_state_cannot_be_replaced_implicitly_during_prepare(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    state_path = tmp_path / "data/telegram/pairing.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("null")
    monkeypatch.setattr(setup, "TelegramSettings", lambda: TelegramSettings(_env_file=None, bot_token=TOKEN))
    monkeypatch.setattr(setup, "PairingAPI", lambda *args: pytest.fail("Null state used network"))
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--prepare", "--username", USERNAME])
    with pytest.raises(SystemExit) as exc:
        setup.main()
    assert exc.value.code == 2 and state_path.read_text() == "null"


def test_owner_write_refuses_changed_token_or_invalid_owner(tmp_path):
    path = tmp_path / ".env"
    original = f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_OWNER_ID=\n".encode()
    path.write_bytes(original)
    for owner in [True, 0, -1, 2**52]:
        with pytest.raises(BotError):
            setup.write_owner(path, tmp_path / "private.tmp", SecretStr(TOKEN), owner)
    with pytest.raises(BotError):
        setup.write_owner(path, tmp_path / "private.tmp", SecretStr(TOKEN + "changed"), OWNER)
    assert path.read_bytes() == original and not (tmp_path / "private.tmp").exists()


def test_expired_pairing_requires_explicit_renewal(monkeypatch, tmp_path, sync_http, capsys):
    monkeypatch.chdir(tmp_path)
    state_path = tmp_path / "data/telegram/pairing.json"
    state_path.parent.mkdir(parents=True)
    state = setup.new_challenge(USERNAME, 123456789, NOW)
    state_path.write_text(json.dumps(state))
    monkeypatch.setattr(setup, "TelegramSettings", lambda: TelegramSettings(_env_file=None, bot_token=TOKEN))
    monkeypatch.setattr(setup.time, "time", lambda: NOW + 3601)
    calls = sync_http(telegram_response)
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--prepare", "--username", USERNAME])
    with pytest.raises(SystemExit):
        setup.main()
    assert not calls
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["setup_telegram", "--prepare", "--username", USERNAME, "--renew"])
    setup.main()
    assert json.loads(capsys.readouterr().out)["status"] == "awaiting_private_start"
    renewed = json.loads(state_path.read_text())
    assert renewed["nonce"] != state["nonce"] and renewed["issued_at"] == NOW + 3601
    assert len(calls) == 2
