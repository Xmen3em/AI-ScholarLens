"""Allowlisted operational events; never serialize requests or provider output."""

import json
import logging
from contextvars import ContextVar

request_context: ContextVar[dict | None] = ContextVar("request_context", default=None)
logger = logging.getLogger(__name__)


def emit_event(event: str, *, level: int = logging.INFO, **fields) -> None:
    context = request_context.get() or {}
    logger.log(level, json.dumps({"event": event, "entry_point": "api", "request_id": context.get("request_id"), **fields}))
