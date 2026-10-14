"""Private PC bot launcher; default mode only checks configuration."""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError
from src.config import Settings
from src.services.telegram_bot import BotError, OffsetStore, PrivateTelegramBot, TelegramSettings, single_instance


async def run_bot(config: TelegramSettings, settings: Settings) -> None:
    if settings.api_key is None:
        raise BotError("api_key_required")
    with single_instance(config.offset_path):
        store = OffsetStore(config.offset_path)
        async with PrivateTelegramBot(config, settings.api_key, store) as bot:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        config = TelegramSettings()
    except ValidationError:
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
        asyncio.run(run_bot(config, Settings()))
    except KeyboardInterrupt:
        print(json.dumps({"status": "stopped"}))
    except (BotError, ValidationError, OSError):
        print(json.dumps({"status": "stopped_configuration_or_transport_error"}))


if __name__ == "__main__":
    main()
