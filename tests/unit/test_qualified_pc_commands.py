import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from src.commands import run_pc_api as api
from src.commands import run_telegram as telegram
from src.commands.hf_paper_profile import CEREBRAS_PROFILE, CEREBRAS_TASK_SHA256, EVIDENCE_PROFILE, get_profile
from src.config import Settings
from src.services import qualified_pc_api as runtime
from src.services.telegram_bot import BotError, TelegramSettings

from tests.unit.test_qualified_pc_api import config

PROOF = {"model": "openai/gpt-oss-120b:cerebras", "hosted_manifest_sha256": CEREBRAS_TASK_SHA256, "source_sha256": "source"}


@pytest.mark.parametrize("mode,memory,served", [("--check-app", 4096, False), ("--execute-app", 1024, False),
                                              ("--execute-app", 4096, True)])
@pytest.mark.parametrize("profile_name", [CEREBRAS_PROFILE, EVIDENCE_PROFILE])
def test_app_mode_requires_acceptance_and_hybrid_memory_without_changing_private_configuration(
    tmp_path, monkeypatch, capsys, mode, memory, served, profile_name,
):
    profile, manifest_sha = get_profile(profile_name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(api, "load_protocol", lambda: profile)
    monkeypatch.setattr(api, "accepted_profile", lambda proof: profile)
    monkeypatch.setattr(runtime, "load_profile", lambda: profile)
    monkeypatch.setattr(runtime, "get_profile", lambda name: (profile, manifest_sha))
    original = config(tmp_path)
    before = original.model_dump()
    factory = Mock(return_value=original)
    factory.model_validate = Settings.model_validate
    monkeypatch.setattr(api, "Settings", factory)
    monkeypatch.setattr(api, "validate_acceptance", lambda path: {**PROOF, "hosted_manifest_sha256": manifest_sha})
    monkeypatch.setattr(api, "free_memory_mib", lambda: memory)
    monkeypatch.setattr(api, "single_instance", lambda path: nullcontext())
    built = []
    def create(settings, path):
        assert settings.hf_models == [PROOF["model"]] and settings.agent_enabled
        assert settings.rag_sentence_candidates_per_passage == profile["candidates_per_passage"]
        assert settings.rag_max_sentence_candidates == profile.get("max_sentence_candidates")
        built.append(settings)
        return object()
    monkeypatch.setattr(api, "create_qualified_app", create)
    server = Mock()
    monkeypatch.setattr(api.uvicorn, "run", server)
    monkeypatch.setattr("sys.argv", ["run_pc_api", mode, "--acceptance", "accepted.json"])
    api.main()
    assert bool(built) is served and server.called is served
    if served:
        assert server.call_args.kwargs["port"] == 8002 and server.call_args.kwargs["host"] == "127.0.0.1"
        assert server.call_args.kwargs["workers"] == 1
    else:
        result = json.loads(capsys.readouterr().out)
        assert result["outbound_calls"] == 0
        assert not list(tmp_path.iterdir())
    assert original.model_dump() == before


def test_missing_app_acceptance_never_reads_credentials_or_starts_services(monkeypatch):
    monkeypatch.setattr(api, "Settings", lambda: pytest.fail("Unapproved mode read credentials"))
    monkeypatch.setattr("sys.argv", ["run_pc_api", "--execute-app"])
    with pytest.raises(SystemExit) as exc: api.main()
    assert exc.value.code == 2


@pytest.mark.anyio
@pytest.mark.parametrize("matches", [False, True])
async def test_bot_checks_authenticated_accepted_api_before_telegram_polling(tmp_path, monkeypatch, stub_httpx, matches):
    monkeypatch.setattr(telegram, "validate_acceptance", lambda path: dict(PROOF))
    expected = {"accepted": True, **PROOF}
    calls = stub_httpx(lambda request: httpx.Response(200, json=expected if matches else {"accepted": False}))
    paired = TelegramSettings(_env_file=None, enabled=True, owner_id=123,
        bot_token="12345:synthetic-private-token-1234567890", api_base_url="http://127.0.0.1:8002/api/v1",
        offset_path=tmp_path / "offset.json")
    started = []
    async def start(*args): started.append(args)
    monkeypatch.setattr(telegram, "run_bot", start)
    if matches:
        await telegram.run_qualified_bot(paired, config(tmp_path), Path("acceptance.json"))
    else:
        with pytest.raises(BotError):
            await telegram.run_qualified_bot(paired, config(tmp_path), Path("acceptance.json"))
    assert bool(started) is matches
    assert len(calls) == 1 and str(calls[0].url) == "http://127.0.0.1:8002/api/v1/qualification"
    assert "X-API-Key" in calls[0].headers and not paired.offset_path.exists()


def test_accepted_bot_offline_check_does_not_poll_or_change_global_flags(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    paired = TelegramSettings(_env_file=None, enabled=False, owner_id=123,
        bot_token="12345:synthetic-private-token-1234567890")
    before = paired.model_dump()
    factory = Mock(return_value=paired)
    factory.model_validate = TelegramSettings.model_validate
    monkeypatch.setattr(telegram, "TelegramSettings", factory)
    monkeypatch.setattr(telegram, "validate_acceptance", lambda path: dict(PROOF))
    monkeypatch.setattr(telegram, "PrivateTelegramBot", lambda *args: pytest.fail("Offline check polled Telegram"))
    monkeypatch.setattr("sys.argv", ["run_telegram", "--check", "--acceptance", "accepted.json"])
    telegram.main()
    assert json.loads(capsys.readouterr().out)["status"] == "configured_offline"
    assert paired.model_dump() == before and not list(tmp_path.iterdir())
