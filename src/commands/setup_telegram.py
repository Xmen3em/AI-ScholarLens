"""Explicit one-time private owner pairing; no messages, inference or startup."""

import argparse
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError
from src.services.rag.service import _unique_object
from src.services.telegram_bot import (
    MAX_BODY_BYTES,
    BotError,
    TelegramSettings,
    _invalid_constant,
    _SuppressHTTPLogs,
    single_instance,
)

STATE = Path("data/telegram/pairing.json")
LIFETIME = 3600


def new_challenge(username: str, bot_id: int, now: int) -> dict:
    return {
        "version": 1,
        "username": username,
        "bot_id": bot_id,
        "nonce": f"setup_{secrets.token_urlsafe(24)}",
        "issued_at": now,
        "expires_at": now + LIFETIME,
    }


def validate_state(state: dict, now: int) -> None:
    if (
        type(state) is not dict
        or set(state) != {"version", "username", "bot_id", "nonce", "issued_at", "expires_at"}
        or type(state["version"]) is not int
        or state["version"] != 1
        or type(state["bot_id"]) is not int
        or not 0 < state["bot_id"] < 2**52
        or type(state["username"]) is not str
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", state["username"])
        or type(state["nonce"]) is not str
        or not re.fullmatch(r"setup_[A-Za-z0-9_-]{32}", state["nonce"])
        or type(state["issued_at"]) is not int
        or type(state["expires_at"]) is not int
        or state["expires_at"] != state["issued_at"] + LIFETIME
        or not state["issued_at"] <= now < state["expires_at"]
    ):
        raise BotError("pairing_invalid_or_expired")


def pairing_link(state: dict) -> str:
    # https://core.telegram.org/bots/features#deep-linking
    return f"https://t.me/{state['username']}?start={state['nonce']}"


def verify_owner(updates: list, state: dict, now: int) -> int | None:
    validate_state(state, now)
    if type(updates) is not list or len(updates) >= 100:
        raise BotError("pending_updates_require_review")
    owners = set()
    for update in updates:
        if type(update) is not dict or type(update.get("update_id")) is not int or not 0 <= update["update_id"] < 2**63 - 1:
            raise BotError("invalid_updates")
        message = update.get("message")
        if type(message) is not dict:
            continue
        sender, chat = message.get("from"), message.get("chat")
        if (
            type(sender) is dict
            and type(chat) is dict
            and type(sender.get("id")) is int
            and 0 < sender["id"] < 2**52
            and sender.get("is_bot") is False
            and type(chat.get("id")) is int
            and chat["id"] == sender["id"]
            and chat.get("type") == "private"
            and "forward_origin" not in message
            and "via_bot" not in message
            and type(message.get("date")) is int
            and state["issued_at"] <= message["date"] <= now
            and message.get("text") == f"/start {state['nonce']}"
        ):
            owners.add(sender["id"])
    if len(owners) > 1:
        raise BotError("ambiguous_owner_proof")
    return next(iter(owners), None)


class PairingAPI:
    def __init__(self, token: SecretStr):
        self.token = token
        self.client = httpx.Client(timeout=15, trust_env=False, follow_redirects=False, headers={"Accept-Encoding": "identity"})
        self.log_filter = _SuppressHTTPLogs()
        self.loggers: list[logging.Logger] = []
        self.active = False

    def __enter__(self):
        names = {"httpx", "httpcore"} | {name for name in logging.Logger.manager.loggerDict if name.startswith("httpcore.")}
        self.loggers = [logging.getLogger(name) for name in names]
        for logger in self.loggers:
            logger.addFilter(self.log_filter)
        self.active = True
        return self

    def __exit__(self, *args):
        try:
            self.client.close()
        finally:
            self.active = False
            for logger in self.loggers:
                logger.removeFilter(self.log_filter)

    def call(self, method: str, payload: dict):
        if not self.active or method not in {"getMe", "getWebhookInfo", "getUpdates"}:
            raise BotError("pairing_method_forbidden")
        if payload != ({"limit": 100, "timeout": 0} if method == "getUpdates" else {}):
            raise BotError("pairing_payload_forbidden")
        try:
            url = f"https://api.telegram.org/bot{self.token.get_secret_value()}/{method}"
            with self.client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    raise BotError("pairing_request_failed")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        raise BotError("pairing_response_too_large")
                    body.extend(chunk)
                value = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
                if type(value) is not dict or value.get("ok") is not True or "result" not in value:
                    raise ValueError
                return value["result"]
        except (httpx.HTTPError, ValueError, RecursionError):
            raise BotError("pairing_response_unavailable") from None

    def identity(self, username: str) -> int:
        bot = self.call("getMe", {})
        if (
            type(bot) is not dict
            or type(bot.get("id")) is not int
            or not 0 < bot["id"] < 2**52
            or bot.get("is_bot") is not True
            or type(bot.get("username")) is not str
            or bot["username"].lower() != username.lower()
            or bot["id"] != int(self.token.get_secret_value().split(":", 1)[0])
        ):
            raise BotError("bot_identity_mismatch")
        webhook = self.call("getWebhookInfo", {})
        if type(webhook) is not dict or webhook.get("url") != "":
            raise BotError("webhook_configuration_requires_review")
        return bot["id"]

    def updates(self):
        # No offset: do not confirm/drop any pending update. Do not change the
        # persistent allowed_updates setting. https://core.telegram.org/bots/api#getupdates
        return self.call("getUpdates", {"limit": 100, "timeout": 0})


def write_owner(env_path: Path, temporary: Path, token: SecretStr, owner: int) -> None:
    if type(owner) is not int or not 0 < owner < 2**52 or env_path.is_symlink() or env_path.stat().st_size > 1_048_576:
        raise BotError("private_configuration_requires_review")
    original = env_path.read_bytes()
    values = dotenv_values(env_path)
    owner_line = re.compile(rb"(?m)^(?:export[ \t]+)?TELEGRAM_OWNER_ID[ \t]*=[^\r\n]*")
    if (
        values.get("TELEGRAM_BOT_TOKEN") != token.get_secret_value()
        or (values.get("TELEGRAM_ENABLED") or "false").lower() not in {"false", "0", "no", "off"}
        or values.get("TELEGRAM_OWNER_ID") not in {None, "", str(owner)}
        or len(owner_line.findall(original)) > 1
    ):
        raise BotError("private_configuration_requires_review")
    replacement = f"TELEGRAM_OWNER_ID={owner}".encode("ascii")
    if owner_line.search(original):
        updated = owner_line.sub(replacement, original)
    else:
        newline = b"\r\n" if b"\r\n" in original else b"\n"
        updated = original + (newline if original and not original.endswith(b"\n") else b"") + replacement + newline
    if updated == original:
        return
    # The temporary file is inside the ignored pairing directory, never tracked.
    # Exclusive creation preserves any interrupted write for explicit recovery.
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(updated)
        stream.flush()
        os.fsync(stream.fileno())
    if env_path.read_bytes() != original:
        temporary.unlink()
        raise BotError("private_configuration_changed")
    os.replace(temporary, env_path)


def read_state(path: Path) -> dict:
    if path.stat().st_size > 1024:
        raise BotError("pairing_state_invalid")
    state = json.loads(path.read_bytes(), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if type(state) is not dict:
        raise BotError("pairing_state_invalid")
    return state


def save_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pair the private Telegram owner without starting the bot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Offline configuration check (default)")
    mode.add_argument("--prepare", action="store_true", help="Read bot identity and create a one-hour private start link")
    mode.add_argument("--verify", action="store_true", help="Read pending updates once and save the proven owner ID")
    parser.add_argument("--username", help="Bot username only, required for preparation")
    parser.add_argument("--renew", action="store_true", help="Explicitly replace a pending challenge during preparation")
    args = parser.parse_args()
    try:
        config = TelegramSettings()
        if not args.prepare and not args.verify:
            status = "token_required" if config.bot_token is None else "owner_configured" if config.owner_id else "owner_required"
            print(json.dumps({"status": status, "outbound_calls": 0}))
            return
        if config.bot_token is None or config.enabled or (args.renew and not args.prepare):
            raise BotError("disabled_private_configuration_required")
        workspace = Path.cwd().resolve()
        state_path = (workspace / STATE).resolve()
        if not state_path.is_relative_to(workspace / "data" / "telegram"):
            raise BotError("pairing_state_path_requires_review")
        now = int(time.time())
        if args.prepare:
            username = (args.username or "").lstrip("@")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", username) or config.owner_id is not None:
                raise BotError("unpaired_bot_username_required")
            state = read_state(state_path) if state_path.exists() else None
            if state is not None:
                # Renewal may replace only a structurally valid pending challenge.
                issued_at = state.get("issued_at")
                if type(issued_at) is not int:
                    raise BotError("pairing_state_invalid")
                validate_state(state, issued_at if args.renew else now)
                if state["username"].lower() != username.lower():
                    raise BotError("bot_identity_mismatch")
        else:
            state = read_state(state_path)
            validate_state(state, now)
            username = state["username"]
        with single_instance(state_path), PairingAPI(config.bot_token) as api:
            # State was validated before opening the client; recheck after the
            # lock so a simultaneous prepare/renew cannot replace this proof.
            latest = read_state(state_path) if state_path.exists() else None
            if latest != state:
                raise BotError("pairing_state_changed")
            bot_id = api.identity(username)
            if state is not None and state["bot_id"] != bot_id:
                raise BotError("bot_identity_mismatch")
            if args.prepare:
                if state is None or args.renew:
                    state = new_challenge(username, bot_id, now)
                    save_state(state_path, state)
                print(
                    json.dumps(
                        {
                            "status": "awaiting_private_start",
                            "pairing_url": pairing_link(state),
                            "expires_in_seconds": state["expires_at"] - now,
                        }
                    )
                )
                return
            if state is None:
                raise BotError("pairing_state_required")
            owner = verify_owner(api.updates(), state, int(time.time()))
            if owner is None:
                print(json.dumps({"status": "awaiting_private_start"}))
                return
            if config.owner_id not in {None, owner}:
                raise BotError("existing_owner_requires_review")
            if read_state(state_path) != state:
                raise BotError("pairing_state_changed")
            write_owner(workspace / ".env", state_path.with_suffix(".env.tmp"), config.bot_token, owner)
            save_state(state_path, {"version": 1, "status": "paired", "username": username, "bot_id": bot_id})
            print(json.dumps({"status": "owner_configured_bot_disabled"}))
    except (BotError, ValidationError, OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({"status": "pairing_configuration_or_transport_error"}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
