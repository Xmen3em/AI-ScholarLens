"""Offline default; explicitly start a read-only private preview on loopback8002."""

import argparse
import json
import math
from pathlib import Path

import uvicorn
from src.commands.evaluate_agent import free_memory_mib
from src.commands.hf_evaluation import load_protocol
from src.commands.hf_paper_acceptance import validate_acceptance
from src.config import Settings
from src.services.pc_api import create_preview_app
from src.services.pc_configuration import preview_settings
from src.services.qualified_pc_api import accepted_profile, create_qualified_app, validate_policy
from src.services.telegram_bot import single_instance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Offline configuration/resource check (default)")
    mode.add_argument("--execute-preview", action="store_true", help="Serve authenticated read-only preview on127.0.0.1:8002")
    mode.add_argument("--check-app", action="store_true", help="Check accepted Cerebras app without starting services")
    mode.add_argument("--execute-app", action="store_true", help="Serve accepted private app on127.0.0.1:8002")
    parser.add_argument("--acceptance", type=Path, help="Reviewed holdout acceptance lock required for app mode")
    args = parser.parse_args()
    app_mode = args.check_app or args.execute_app
    if app_mode != (args.acceptance is not None):
        parser.error("App mode requires --acceptance; preview does not use an acceptance lock")
    try:
        settings = preview_settings(Settings(), Path.cwd())
        profile = load_protocol()
        if app_mode:
            proof = validate_acceptance(args.acceptance)
            profile = accepted_profile(proof)
            settings = Settings.model_validate(settings.model_copy(update={
                "hf_inference_enabled": True, "agent_enabled": True, "hf_models": [proof["model"]],
                "hf_default_model": proof["model"], "rag_sentence_candidates_per_passage": profile["candidates_per_passage"],
                "rag_max_sentence_candidates": profile.get("max_sentence_candidates"),
            }).model_dump())
            validate_policy(settings, profile_name=profile["version"])
        free_mib = free_memory_mib()
        admitted = math.isfinite(free_mib) and free_mib >= profile["admission_mib"]["hybrid" if app_mode else "bm25"]
        if not args.execute_preview and not args.execute_app:
            print(
                json.dumps(
                    {
                        "status": ("app_prepared" if admitted else "app_prepared_memory_required") if app_mode else (
                            "preview_prepared" if admitted else "preview_prepared_memory_required"),
                        "outbound_calls": 0,
                        "generation_enabled": False,
                        "port": 8002,
                    }
                )
            )
            return
        if not admitted:
            print(json.dumps({"status": "not_started_insufficient_memory", "outbound_calls": 0}))
            return
        with single_instance(Path(settings.api_rate_limit_path)):
            local = create_qualified_app(settings, args.acceptance) if app_mode else create_preview_app(settings)
            uvicorn.run(local, host="127.0.0.1", port=8002, workers=1, access_log=False, ws="none", timeout_graceful_shutdown=3)
    except KeyboardInterrupt:
        print(json.dumps({"status": "stopped"}))
    except Exception:
        print(json.dumps({"status": "app_configuration_or_startup_error" if app_mode else "preview_configuration_or_startup_error"}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
