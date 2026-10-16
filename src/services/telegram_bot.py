"""Explicit private polling client; no automatic startup or inference retries."""

import asyncio
import json
import logging
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import SettingsConfigDict
from src.config import DefaultSettings
from src.schemas.api.agent import AgentResponse
from src.schemas.api.assistant import LearningResponse
from src.services.rag.service import _unique_object
from src.services.telegram_policy import HELP_TEXT, format_reply, parse_update

API_FAILURE = "The research service is unavailable or could not validate an answer. This question was not retried."
MAX_BODY_BYTES = 262_144
LEARNING_HELP = (
    "Ask me to explain AI/ML concepts or ask about the stored research papers. "
    "Try 'What is RAG?' or 'Explain ML systems.' General explanations use model knowledge; paper answers include citations. "
    "Send a question or /ask followed by your question (up to 500 characters)."
)


class BotError(RuntimeError):
    """Fixed local failure categories; provider text and URLs never become messages."""


class TelegramSettings(DefaultSettings):
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", hide_input_in_errors=True)
    enabled: bool = False
    bot_token: SecretStr | None = None
    owner_id: int | None = Field(default=None, gt=0, le=2**52 - 1)
    api_base_url: str = "http://127.0.0.1:8000/api/v1"
    offset_path: Path = Path("data/telegram/offset.json")

    @field_validator("owner_id", mode="before")
    @classmethod
    def owner_is_an_integer(cls, value):
        if value == "":
            return None
        if value is not None and type(value) is not int and not (type(value) is str and value.isdecimal()):
            raise ValueError("Telegram requires an integer owner ID")
        return value

    @field_validator("bot_token", mode="before")
    @classmethod
    def empty_token(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def private_configuration(self):
        token = self.bot_token.get_secret_value() if self.bot_token else ""
        if token and not re.fullmatch(r"\d{5,20}:[A-Za-z0-9_-]{20,128}", token):
            raise ValueError("Telegram token format is invalid")
        origin = urlsplit(self.api_base_url)
        if (
            origin.scheme != "http"
            or origin.hostname not in {"127.0.0.1", "localhost", "::1"}
            or origin.port not in {8000, 8002}
            or origin.path.rstrip("/") != "/api/v1"
            or origin.username
            or origin.password
            or origin.query
            or origin.fragment
        ):
            raise ValueError("Telegram requires the approved loopback API origin")
        if self.enabled and (not token or self.owner_id is None):
            raise ValueError("Private Telegram token and owner ID are required")
        return self


@contextmanager
def single_instance(offset_path: Path):
    lock = offset_path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as stream:
        try:
            if sys.platform == "win32":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise BotError("bot_already_running") from None
        yield


class OffsetStore:
    def __init__(self, path: Path):
        self.path = path
        self.marker = path.with_suffix(".registered")
        self.offset = 0
        if self.marker.exists() != path.exists():
            raise BotError("offset_recovery_required")
        if path.exists():
            try:
                if self.marker.read_bytes() != b"telegram-offset-v1":
                    raise ValueError
                if path.stat().st_size > 128:
                    raise ValueError
                raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
                if (
                    type(raw) is not dict
                    or set(raw) != {"next_update_id"}
                    or type(raw["next_update_id"]) is not int
                    or not 0 <= raw["next_update_id"] < 2**63
                ):
                    raise ValueError
                self.offset = raw["next_update_id"]
            except (OSError, ValueError):
                raise BotError("offset_recovery_required") from None

    def advance(self, next_update_id: int) -> None:
        if type(next_update_id) is not int or not self.offset < next_update_id < 2**63:
            raise BotError("invalid_update_offset")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            if self.path.exists():
                if not self.marker.is_file() or self.marker.read_bytes() != b"telegram-offset-v1":
                    raise BotError("offset_recovery_required")
            else:
                with self.marker.open("xb") as registration:
                    registration.write(b"telegram-offset-v1")
                    registration.flush()
                    os.fsync(registration.fileno())
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump({"next_update_id": next_update_id}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise BotError("offset_write_failed") from None
        self.offset = next_update_id


class _SuppressHTTPLogs(logging.Filter):
    def filter(self, record):
        return False


def _invalid_constant(value):
    raise ValueError("Invalid JSON constant")


class PrivateTelegramBot:
    def __init__(self, settings: TelegramSettings, api_key: SecretStr, store: OffsetStore, *, development_assistant=False):
        if (
            not settings.enabled
            or settings.owner_id is None
            or settings.bot_token is None
            or len(api_key.get_secret_value()) < 32
        ):
            raise BotError("configuration_required")
        self.settings, self.store = settings, store
        self.development_assistant = development_assistant
        self.owner_id = settings.owner_id
        self._work_lock = asyncio.Lock()
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
        self._api = httpx.AsyncClient(
            headers={"X-API-Key": api_key.get_secret_value()}, timeout=130, trust_env=False, follow_redirects=False, limits=limits
        )
        self._telegram = httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False, limits=limits)
        self._log_filter = _SuppressHTTPLogs()
        self._loggers: list[logging.Logger] = []
        self._active = False

    async def __aenter__(self):
        # Telegram embeds its token in request URLs. HTTP client DEBUG/INFO logs
        # must remain suppressed for this separate bot's lifetime.
        names = {"httpx", "httpcore"} | {name for name in logging.Logger.manager.loggerDict if name.startswith("httpcore.")}
        self._loggers = [logging.getLogger(name) for name in names]
        for logger in self._loggers:
            logger.addFilter(self._log_filter)
        self._active = True
        return self

    async def __aexit__(self, *args):
        try:
            await self._api.aclose()
            await self._telegram.aclose()
        finally:
            self._active = False
            for logger in self._loggers:
                logger.removeFilter(self._log_filter)

    async def _post(self, client: httpx.AsyncClient, url: str, payload: dict) -> dict:
        if not self._active:
            raise BotError("bot_not_started")
        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    raise BotError("request_failed")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        raise BotError("response_size_exceeded")
                    body.extend(chunk)
                raw = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
                if type(raw) is not dict:
                    raise ValueError
                return raw
        except (httpx.HTTPError, ValueError, RecursionError):
            raise BotError("invalid_or_unavailable_response") from None

    async def _call_telegram(self, method: str, payload: dict):
        assert self.settings.bot_token is not None
        raw = await self._post(
            self._telegram, f"https://api.telegram.org/bot{self.settings.bot_token.get_secret_value()}/{method}", payload
        )
        if raw.get("ok") is not True or "result" not in raw:
            raise BotError("telegram_request_failed")
        return raw["result"]

    async def check_webhook(self):
        result = await self._call_telegram("getWebhookInfo", {})
        if type(result) is not dict or result.get("url") != "":
            raise BotError("webhook_configuration_requires_review")

    async def poll(self) -> list[dict]:
        values = await self._call_telegram(
            "getUpdates", {"offset": self.store.offset, "limit": 10, "timeout": 20, "allowed_updates": ["message"]}
        )
        if (
            type(values) is not list
            or len(values) > 10
            or any(
                type(row) is not dict or type(row.get("update_id")) is not int or not 0 <= row["update_id"] < 2**63 - 1
                for row in values
            )
        ):
            raise BotError("invalid_update_batch")
        return sorted(values, key=lambda row: row["update_id"])

    async def handle(self, update: dict) -> str:
        async with self._work_lock:
            update_id = update.get("update_id")
            if type(update_id) is not int or not self.store.offset <= update_id < 2**63 - 1:
                return "ignored"
            # Durable admission precedes all inference and messaging. Interrupted
            # or uncertain work stays consumed instead of being replayed on restart.
            self.store.advance(update_id + 1)
            action = parse_update(update, self.owner_id)
            if action is None:
                return "ignored"
            status = "help"
            replies = [action.reply] if action.reply else []
            if self.development_assistant and action.reply == HELP_TEXT:
                replies = [LEARNING_HELP]
            if action.request is not None:
                try:
                    raw = await self._post(
                        self._api, self.settings.api_base_url.rstrip("/") + "/agent/ask", action.request.model_dump()
                    )
                    if self.development_assistant and raw.get("kind") in {
                        "general_explanation", "clarification", "out_of_scope"
                    }:
                        learning = LearningResponse.model_validate(raw)
                        prefix = "General AI/ML explanation (model knowledge):\n\n" if learning.kind == "general_explanation" else ""
                        text = prefix + learning.answer
                        # Telegram measures UTF-16 units; bound each part without
                        # splitting astral Unicode characters.
                        replies = [text[start:start + 1900] for start in range(0, len(text), 1900)]
                    else:
                        response = AgentResponse.model_validate(raw)
                        replies = format_reply(response)
                    status = "answered"
                except (BotError, ValueError, TypeError):
                    replies, status = [API_FAILURE], "api_failed"
            for reply in replies:
                try:
                    sent = await self._call_telegram("sendMessage", {"chat_id": self.owner_id, "text": reply})
                    if type(sent) is not dict or type(sent.get("message_id")) is not int or sent["message_id"] <= 0:
                        raise BotError("invalid_message_acknowledgement")
                except BotError:
                    return "reply_failed"
            return status
