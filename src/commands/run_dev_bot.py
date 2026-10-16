"""Run the paired private bot and BM25/HF development API in one process."""

import argparse
import asyncio
import json
import math
from contextlib import suppress
from pathlib import Path

import uvicorn
from src.commands.evaluate_agent import free_memory_mib
from src.commands.run_telegram import run_bot
from src.config import Settings
from src.services.development_pc_api import ADMISSION_MIB, MODEL, create_development_app, development_settings
from src.services.hf.tokenizer import verify_vocabulary
from src.services.telegram_bot import TelegramSettings, single_instance

STOP_PATH = Path("data/pc-app/development.stop")


async def run(settings: Settings, bot: TelegramSettings) -> None:
    local = create_development_app(settings, study_owner=bot.owner_id)
    server = uvicorn.Server(uvicorn.Config(local, host="127.0.0.1", port=8002, workers=1,
        access_log=False, ws="none", lifespan="on", timeout_graceful_shutdown=3))
    server_task = asyncio.create_task(server.serve())
    bot_task = stop_task = None
    try:
        async with asyncio.timeout(20):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("Development API startup failed")
                await asyncio.sleep(0.05)
        print(json.dumps({"status": "development_api_ready", "port": 8002, "model": MODEL,
                          "search_mode": "bm25", "accepted": False}), flush=True)
        bot_task = asyncio.create_task(run_bot(bot, settings, development_assistant=True, study=True))

        async def wait_stop():
            while not STOP_PATH.exists():
                await asyncio.sleep(1)

        stop_task = asyncio.create_task(wait_stop())
        done, _ = await asyncio.wait({server_task, bot_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    finally:
        for cleanup_task in (bot_task, stop_task):
            if cleanup_task is not None:
                cleanup_task.cancel()
                # Preserve the original task failure while still closing the API.
                with suppress(asyncio.CancelledError, Exception):
                    await cleanup_task
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=8)
        except TimeoutError:
            server_task.cancel()
            with suppress(asyncio.CancelledError):
                await server_task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Offline check; no network or state writes (default)")
    mode.add_argument("--execute", action="store_true", help="Start private development testing, including user-triggered HF calls")
    mode.add_argument("--stop", action="store_true", help="Stop this development API and bot gracefully")
    args = parser.parse_args()
    workspace = Path.cwd().resolve()
    if not STOP_PATH.resolve().is_relative_to(workspace / "data/pc-app"):
        parser.error("Development state must stay in its workspace directory")
    if args.stop:
        STOP_PATH.parent.mkdir(parents=True, exist_ok=True)
        STOP_PATH.write_text("stop\n", encoding="utf-8")
        print(json.dumps({"status": "stop_requested"}))
        return
    try:
        settings = development_settings(Settings(), workspace)
        paired = TelegramSettings()
        bot = type(paired).model_validate(paired.model_copy(update={
            "enabled": True, "api_base_url": "http://127.0.0.1:8002/api/v1",
        }).model_dump())
        state = bot.offset_path.resolve()
        if state.suffix != ".json" or not state.is_relative_to(workspace / "data/telegram"):
            raise ValueError("Private bot offset must remain in its workspace directory")
        verify_vocabulary()
        free = free_memory_mib()
        admitted = math.isfinite(free) and free >= ADMISSION_MIB
        if not args.execute or not admitted:
            print(json.dumps({"status": "development_ready" if admitted else "insufficient_memory",
                              "free_mib": round(free, 1) if math.isfinite(free) else None,
                              "required_mib": ADMISSION_MIB, "outbound_calls": 0, "accepted": False}))
            return
        with single_instance(Path(settings.api_rate_limit_path)):
            STOP_PATH.unlink(missing_ok=True)
            asyncio.run(run(settings, bot))
    except KeyboardInterrupt:
        print(json.dumps({"status": "stopped"}))
    except Exception as exc:
        print(json.dumps({"status": "development_startup_or_transport_error", "error_class": type(exc).__name__}), flush=True)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
