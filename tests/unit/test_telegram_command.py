import asyncio
import json
from contextlib import nullcontext
from pathlib import Path

import pytest
from pydantic import SecretStr
from src.commands import run_telegram as command
from src.config import Settings
from src.services.telegram_bot import BotError, TelegramSettings


def test_check_mode_never_constructs_bot_or_changes_offset(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("Check mode started bot")

    monkeypatch.setattr(command, "PrivateTelegramBot", forbidden)
    monkeypatch.setattr(command, "TelegramSettings", lambda: TelegramSettings(_env_file=None))
    monkeypatch.setattr("sys.argv", ["run_telegram", "--check"])
    command.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "disabled" and result["outbound_calls"] == 0


def test_missing_private_configuration_cannot_execute(monkeypatch, capsys):
    monkeypatch.setattr(command, "TelegramSettings", lambda: TelegramSettings(_env_file=None))
    monkeypatch.setattr("sys.argv", ["run_telegram", "--execute"])
    command.main()
    assert json.loads(capsys.readouterr().out)["status"] == "disabled"


def test_state_must_stay_in_workspace_ignored_directory(monkeypatch, tmp_path):
    config = TelegramSettings(
        _env_file=None,
        enabled=True,
        owner_id=123,
        bot_token="12345:synthetic-private-token-1234567890",
        offset_path=Path("docs/private-offset.json"),
    )
    monkeypatch.setattr(command, "TelegramSettings", lambda: config)
    monkeypatch.setattr("sys.argv", ["run_telegram", "--check"])
    with pytest.raises(SystemExit) as exc:
        command.main()
    assert exc.value.code == 2 and not config.offset_path.exists()


@pytest.mark.anyio
async def test_poll_reconnect_does_not_repeat_question_or_log_sensitive_content(monkeypatch, tmp_path, capsys):
    config = TelegramSettings(
        _env_file=None,
        enabled=True,
        owner_id=123,
        bot_token="12345:synthetic-private-token-1234567890",
        offset_path=tmp_path / "offset.json",
    )
    sleeps = []

    class FakeBot:
        polls = 0
        handled = 0

        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def check_webhook(self):
            pass

        async def poll(self):
            self.polls += 1
            if self.polls == 1:
                raise BotError("private-provider-error")
            if self.polls == 2:
                return [{"update_id": 10}]
            raise asyncio.CancelledError

        async def handle(self, update):
            self.handled += 1
            assert self.handled == 1
            return "help"

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(command, "PrivateTelegramBot", FakeBot)
    monkeypatch.setattr(command, "single_instance", lambda path: nullcontext())
    monkeypatch.setattr(command.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await command.run_bot(config, Settings(_env_file=None, api_key=SecretStr("synthetic-private-api-key-1234567890")))
    output = capsys.readouterr().out
    assert sleeps == [1] and "private-provider-error" not in output and config.bot_token.get_secret_value() not in output


@pytest.mark.anyio
@pytest.mark.parametrize("enabled", [True, False])
async def test_study_bot_follows_the_multi_user_setting(tmp_path, monkeypatch, enabled):
    from contextlib import nullcontext

    from pydantic import SecretStr
    from src.config import Settings
    from src.services.telegram_bot import TelegramSettings

    seen = {}

    class FakeBot:
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)

        async def __aenter__(self):
            raise asyncio.CancelledError

        async def __aexit__(self, *args):
            pass

    monkeypatch.setenv("STUDY_MULTI_USER", "true" if enabled else "false")
    monkeypatch.setattr(command, "PrivateTelegramBot", FakeBot)
    monkeypatch.setattr(command, "single_instance", lambda path: nullcontext())
    config = TelegramSettings(_env_file=None, enabled=True, bot_token="12345:synthetic-private-token-1234567890", owner_id=5,
                              offset_path=tmp_path / "offset.json")
    with pytest.raises(asyncio.CancelledError):
        await command.run_bot(config, Settings(_env_file=None, api_key=SecretStr("synthetic-private-api-key-1234567890")),
                              study=True)
    assert seen == {"study": True, "multi_user": enabled}
