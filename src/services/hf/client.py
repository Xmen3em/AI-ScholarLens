"""Bounded HF chat completions with no retry, redirect, tool or schema fallback."""

import asyncio
import json
from time import perf_counter
from typing import Any, Literal, Mapping

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from src.config import Settings
from src.exceptions import OllamaException, OllamaResponseError, OllamaTimeoutError, UnsupportedModelError
from src.operations import emit_event
from src.schemas.generation import GenerationResult
from src.schemas.ollama import OllamaGenerateResponse
from src.services.hf.errors import ERROR_CODES, ERROR_TYPES, allowed_label, error_labels
from src.services.hf.registry import HF_ROUTER_URL

MAX_RESPONSE_BYTES = 65536


class HFGenerationError(OllamaException):
    """Compatibility with retained API errors; never includes provider text."""

    def __init__(self, message: str = "Hosted generation is unavailable", *, status_code: int | None = None,
                 error_code: str | None = None, error_type: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = allowed_label(error_code, ERROR_CODES)
        self.error_type = allowed_label(error_type, ERROR_TYPES)


class HFResponseError(OllamaResponseError):
    """The hosted response failed the bounded generation contract."""


class HFTimeoutError(OllamaTimeoutError):
    """Local waiting exceeded its deadline; remote billing may continue."""


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, hide_input_in_errors=True)


class _Message(_WireModel):
    role: Literal["assistant"]
    content: str = Field(min_length=1, max_length=8192)
    tool_calls: list | None = None
    function_call: dict | None = None
    refusal: str | None = None


class _Choice(_WireModel):
    index: Literal[0]
    finish_reason: Literal["stop"]
    message: _Message


class _Details(_WireModel):
    reasoning_tokens: int | None = Field(default=None, ge=0)


class _Usage(_WireModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    completion_tokens_details: _Details | None = None


class _Completion(_WireModel):
    choices: list[_Choice] = Field(min_length=1, max_length=1)
    usage: _Usage | None = None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response field")
        result[key] = value
    return result


class HFClient:
    def __init__(self, settings: Settings):
        # Revalidate even if a caller used model_copy/update to bypass validators.
        self.settings = Settings.model_validate(settings.model_dump())
        if not self.settings.hf_inference_enabled:
            raise ValueError("Hosted inference is disabled")
        token = self.settings.hf_token
        if token is None:
            raise ValueError("Hosted inference requires credentials")
        self._client = httpx.AsyncClient(
            base_url=HF_ROUTER_URL, headers={"Authorization": "Bearer " + token.get_secret_value()},
            timeout=httpx.Timeout(self.settings.hf_timeout_seconds, connect=5),
            follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )
        self.attempts = 0
        self._busy = False

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(
        self, model: str, prompt: str, *, system: str | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> OllamaGenerateResponse:
        result = await self.generate_result(model, prompt, system=system, response_format=response_format, options=options)
        return result.as_legacy_response()

    async def generate_result(
        self, model: str, prompt: str, *, system: str | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> GenerationResult:
        payload = self._payload(model, prompt, system, response_format, options)
        if self._busy:
            raise HFGenerationError("Hosted generation capacity is occupied")
        # No await between checking and reserving this single-event-loop client.
        self._busy = True
        self.attempts += 1
        started = perf_counter()
        outcome = "failed"
        status_code = None
        try:
            async with asyncio.timeout(self.settings.hf_timeout_seconds):
                async with self._client.stream("POST", "chat/completions", json=payload) as response:
                    status_code = response.status_code
                    if status_code != 200:
                        code, kind = await error_labels(response)
                        raise HFGenerationError(status_code=status_code, error_code=code, error_type=kind)
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise HFResponseError("Hosted response exceeded the size limit")
                        body.extend(chunk)
            result = self._result(bytes(body), model, payload["max_tokens"], (perf_counter() - started) * 1000)
            outcome = "completed"
            return result
        except (TimeoutError, httpx.TimeoutException):
            raise HFTimeoutError("Hosted generation timed out") from None
        except httpx.HTTPError:
            raise HFGenerationError() from None
        except asyncio.CancelledError:
            outcome = "interrupted"
            raise
        finally:
            self._busy = False
            emit_event("hf_generation_attempt", model=model, provider=model.rsplit(":", 1)[1],
                       outcome=outcome, status_code=status_code, duration_ms=(perf_counter() - started) * 1000)

    def _payload(self, model: str, prompt: str, system: str | None,
                 response_format: Mapping[str, Any] | str | None, options: Mapping[str, Any] | None) -> dict[str, Any]:
        if model not in self.settings.hf_models:
            raise UnsupportedModelError("Requested generation model is not configured")
        controls = dict(options or {"temperature": 0, "num_predict": 512, "num_ctx": 8192})
        if (set(controls) != {"temperature", "num_predict", "num_ctx"} or controls["temperature"] != 0
                or type(controls["num_predict"]) is not int or controls["num_predict"] not in {256, 512}
                or type(controls["num_ctx"]) is not int or controls["num_ctx"] != 8192):
            raise ValueError("Hosted generation requires the fixed bounded controls")
        if not prompt.strip() or len(prompt) > 20000 or (system is not None and len(system) > 20000):
            raise HFGenerationError("Hosted prompt exceeds the bounded profile")
        messages = [] if system is None else [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False,
                                   "max_tokens": controls["num_predict"], "temperature": 0, "reasoning_effort": "low"}
        if response_format is not None:
            if not isinstance(response_format, Mapping):
                raise ValueError("Hosted generation requires the original JSON schema")
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "bounded_generation", "strict": True, "schema": dict(response_format)}}
        # Conservative admission for the registered byte-tokenized model, including
        # schema/message overhead and 512 reserved tokens for provider templates.
        # Provider-reported usage is checked too; absent usage remains unknown.
        wire_bytes = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if wire_bytes > controls["num_ctx"] - controls["num_predict"] - 512:
            raise HFGenerationError("Hosted input exceeds conservative context admission")
        return payload

    @staticmethod
    def _result(body: bytes, model: str, max_tokens: int, elapsed_ms: float) -> GenerationResult:
        try:
            raw = json.loads(body, object_pairs_hook=_unique_object)
            parsed = _Completion.model_validate(raw)
            choice = parsed.choices[0]
            # Literal[0] also admits False in Pydantic; require an actual integer.
            if type(raw["choices"][0]["index"]) is not int:
                raise ValueError("Invalid choice index")
            message = choice.message
            if not message.content.strip() or message.tool_calls or message.function_call or message.refusal:
                raise ValueError("Unexpected completion kind")
            usage = parsed.usage
            input_tokens = usage.prompt_tokens if usage else None
            output_tokens = usage.completion_tokens if usage else None
            reasoning_tokens = (usage.completion_tokens_details.reasoning_tokens
                                if usage and usage.completion_tokens_details else None)
            if (input_tokens is not None and input_tokens > 8192 - max_tokens
                    or output_tokens is not None and output_tokens > max_tokens
                    or reasoning_tokens is not None and output_tokens is not None and reasoning_tokens > output_tokens):
                raise ValueError("Provider usage exceeds the profile")
            return GenerationResult(model=model, content=message.content, elapsed_ms=elapsed_ms,
                                    input_tokens=input_tokens, output_tokens=output_tokens, reasoning_tokens=reasoning_tokens)
        except (ValueError, TypeError, KeyError, RecursionError, ValidationError):
            raise HFResponseError("Hosted generation returned an invalid response") from None
