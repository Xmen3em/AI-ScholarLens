"""Private PC bot launcher; default mode only checks configuration."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from pydantic import ValidationError
from src.commands.hf_paper_acceptance import validate_acceptance
from src.config import Settings
from src.services.telegram_bot import BotError, OffsetStore, PrivateTelegramBot, TelegramSettings, single_instance


async def run_bot(config: TelegramSettings, settings: Settings, *, development_assistant=False) -> None:
    if settings.api_key is None:
        raise BotError("api_key_required")
    with single_instance(config.offset_path):
        store = OffsetStore(config.offset_path)
        extra = {"development_assistant": True} if development_assistant else {}
        async with PrivateTelegramBot(config, settings.api_key, store, **extra) as bot:
            await bot.check_webhook()
            print(json.dumps({"status": "polling_private_bot"}), flush=True)
            delay = 1
            while True:
                try:
                    updates = await bot.poll()
                except BotError:
                    print(json.dumps({"status": "poll_unavailable", "retry_seconds": delay}), flush=True)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                delay = 1
                for update in updates:
                    status = await bot.handle(update)
                    print(json.dumps({"status": status}), flush=True)


async def run_qualified_bot(config: TelegramSettings, settings: Settings, acceptance: Path) -> None:
    proof = validate_acceptance(acceptance)
    if config.api_base_url != "http://127.0.0.1:8002/api/v1" or settings.api_key is None:
        raise BotError("accepted_api_required")
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = await client.get(config.api_base_url + "/qualification",
                                    headers={"X-API-Key": settings.api_key.get_secret_value()})
        expected = {"accepted": True, **{key: proof[key] for key in ("model", "hosted_manifest_sha256", "source_sha256")}}
        if response.status_code != 200 or response.json() != expected:
            raise BotError("accepted_api_required")
    await run_bot(config, settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--acceptance", type=Path, help="Use the accepted private PC API8002 with paired owner configuration")
    args = parser.parse_args()
    try:
        config = TelegramSettings()
        if args.acceptance is not None:
            validate_acceptance(args.acceptance)
            config = TelegramSettings.model_validate(config.model_copy(update={
                "enabled": True, "api_base_url": "http://127.0.0.1:8002/api/v1",
            }).model_dump())
    except (ValidationError, ValueError, OSError, KeyError):
        print(json.dumps({"status": "configuration_required", "outbound_calls": 0}))
        return
    workspace = Path.cwd().resolve()
    state = config.offset_path.resolve()
    roots = [workspace / name for name in ("data/telegram", "tests/test_output", "test_output")]
    if (
        not state.is_relative_to(workspace)
        or state.suffix != ".json"
        or not any(state.is_relative_to(root.resolve()) and state != root.resolve() for root in roots)
    ):
        parser.error("Telegram offset must stay in a local ignored state directory")
    if not config.enabled:
        print(json.dumps({"status": "disabled", "outbound_calls": 0}))
        return
    if not args.execute:
        print(json.dumps({"status": "configured_offline", "outbound_calls": 0}))
        return
    try:
        settings = Settings()
        asyncio.run(run_qualified_bot(config, settings, args.acceptance) if args.acceptance else run_bot(config, settings))
    except KeyboardInterrupt:
        print(json.dumps({"status": "stopped"}))
    except (BotError, ValidationError, OSError, ValueError, httpx.HTTPError):
        print(json.dumps({"status": "stopped_configuration_or_transport_error"}))


if __name__ == "__main__":
    main()
