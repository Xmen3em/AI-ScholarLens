"""Bounded provider error labels; messages and generated content are discarded."""

import json

import httpx

ERROR_CODES = frozenset({"json_validate_failed", "context_length_exceeded", "invalid_request_error",
                        "invalid_json_schema", "unsupported_parameter", "model_not_supported"})
ERROR_TYPES = frozenset({"invalid_request_error", "authentication_error", "rate_limit_error", "server_error"})


def allowed_label(value, allowed: frozenset[str]) -> str | None:
    return value if type(value) is str and value in allowed else None


async def error_labels(response: httpx.Response) -> tuple[str | None, str | None]:
    from src.services.hf.client import _unique_object

    body = bytearray()
    try:
        async for chunk in response.aiter_bytes(chunk_size=4096):
            if len(body) + len(chunk) > 8192:
                return None, None
            body.extend(chunk)
        raw = json.loads(body, object_pairs_hook=_unique_object)
        error = raw.get("error") if type(raw) is dict else None
        if type(error) is dict:
            return allowed_label(error.get("code"), ERROR_CODES), allowed_label(error.get("type"), ERROR_TYPES)
    except (ValueError, TypeError, RecursionError, httpx.HTTPError):
        pass
    return None, None
