"""Worker-shared local budgets and stream-aware request logging."""

import hmac
import logging
import math
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import anyio
from fastapi.responses import JSONResponse
from src.config import Settings, get_settings
from src.operations import emit_event, request_context
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RateLimiter:
    """Two global fixed-window budgets shared by workers using the same SQLite file.

    Rejected calls spend neither budget. A local instance has one key/principal;
    per-user and multi-replica quotas require a different shared store.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def reserve(self, *, generation: bool, now: float | None = None) -> int:
        now = time.time() if now is None else now
        path = Path(self.settings.api_rate_limit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=2)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS budgets (name TEXT PRIMARY KEY, starts REAL, used INTEGER)")
            connection.execute("BEGIN IMMEDIATE")
            budgets = [("requests", self.settings.api_requests_per_minute)]
            if generation:
                budgets.append(("generation", self.settings.api_generations_per_minute))
            updates = []
            retry_after = 0
            for name, limit in budgets:
                row = connection.execute("SELECT starts, used FROM budgets WHERE name = ?", (name,)).fetchone()
                starts, used = row if row and now < row[0] + 60 else (now, 0)
                if used >= limit:
                    retry_after = max(retry_after, math.ceil(starts + 60 - now))
                updates.append((name, starts, used + 1))
            if not retry_after:
                connection.executemany("INSERT OR REPLACE INTO budgets VALUES (?, ?, ?)", updates)
            connection.commit()
            return retry_after
        finally:
            connection.close()


class OperationalMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings | None = None):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = self.settings or getattr(scope["app"].state, "settings", None) or get_settings()
        context = {"request_id": uuid4().hex}
        token = request_context.set(context)
        started = time.perf_counter()
        status, completed, response_started = 500, False, False

        async def observe(message: Message) -> None:
            nonlocal status, completed, response_started
            if message["type"] == "http.response.start":
                status, response_started = message["status"], True
                MutableHeaders(scope=message)["X-Request-ID"] = context["request_id"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            if scope["path"] != "/api/v1/ping":
                provided = Headers(scope=scope).get("x-api-key", "")
                if settings.api_key and not hmac.compare_digest(provided.encode(), settings.api_key.get_secret_value().encode()):
                    await JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)(scope, receive, observe)
                    return
                # Readiness retains authentication but must not consume or be
                # blocked by user traffic budgets (including a broken store).
                if scope["path"] == "/api/v1/health":
                    await self.app(scope, receive, observe)
                    return
                try:
                    retry = await anyio.to_thread.run_sync(
                        lambda: RateLimiter(settings).reserve(generation=scope["path"] in {"/api/v1/ask", "/api/v1/stream"})
                    )
                except (OSError, sqlite3.Error):
                    emit_event("rate_limit_store_unavailable", level=logging.ERROR)
                    await JSONResponse({"detail": "Access controls unavailable"}, status_code=503)(scope, receive, observe)
                    return
                if retry:
                    await JSONResponse({"detail": "Rate limit exceeded"}, status_code=429,
                                       headers={"Retry-After": str(retry)})(scope, receive, observe)
                    return
            await self.app(scope, receive, observe)
        except Exception:
            if response_started:
                raise
            await JSONResponse({"detail": "Internal server error"}, status_code=500)(scope, receive, observe)
        finally:
            route = scope.get("route")
            outcome = "stream_error" if context.get("stream_failed") else "completed" if completed and status < 500 else "failed"
            emit_event("http_request_completed", method=scope["method"], route=getattr(route, "path", "unmatched"),
                       status=status, duration_ms=round((time.perf_counter() - started) * 1000, 2), outcome=outcome)
            request_context.reset(token)
