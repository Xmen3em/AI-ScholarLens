"""Async Ollama client with validated normal and streaming responses."""

import json
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any, Literal

import httpx
from pydantic import ValidationError
from src.config import Settings
from src.exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from src.schemas.ollama import OllamaGenerateResponse, OllamaModel, OllamaReadiness, OllamaTagsResponse

logger = logging.getLogger(__name__)

CONTROL_TIMEOUT_SECONDS = 10.0


def normalize_model_name(name: str) -> str:
    """Match Ollama's implicit `:latest` tag without changing explicit tags."""
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


class OllamaClient:
    """One reusable async client for an API worker's Ollama connection pool."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.generation_timeout = httpx.Timeout(float(settings.ollama_timeout), connect=10.0)
        self.control_timeout = httpx.Timeout(CONTROL_TIMEOUT_SECONDS)
        self._client = httpx.AsyncClient(base_url=settings.ollama_host, timeout=self.generation_timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_models(self) -> list[OllamaModel]:
        try:
            response = await self._client.get("/api/tags", timeout=self.control_timeout)
            response.raise_for_status()
            return OllamaTagsResponse.model_validate(response.json()).models
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            raise OllamaException("Ollama returned an invalid model list") from exc
        except httpx.HTTPError as exc:
            raise self._domain_error(exc, "listing models") from exc

    async def readiness(self) -> OllamaReadiness:
        models = await self.list_models()
        installed = sorted(
            {
                normalize_model_name(name)
                for entry in models
                if (name := entry.model or entry.name)
            }
        )
        installed_set = set(installed)
        required = normalize_model_name(self.settings.ollama_default_model)
        optional = [
            normalize_model_name(model)
            for model in [*self.settings.ollama_models, self.settings.ollama_embedding_model]
            if normalize_model_name(model) != required
        ]
        missing_required = [] if required in installed_set else [required]
        missing_optional = list(dict.fromkeys(model for model in optional if model not in installed_set))
        status: Literal["healthy", "degraded", "unhealthy"]
        status = "unhealthy" if missing_required else "degraded" if missing_optional else "healthy"
        return OllamaReadiness(
            status=status,
            installed=installed,
            missing_required=missing_required,
            missing_optional=missing_optional,
        )

    async def health_check(self) -> dict[str, Any]:
        """Compatibility wrapper for callers that still expect a mapping."""
        readiness = await self.readiness()
        return {
            "status": readiness.status,
            "message": self._readiness_message(readiness),
        }

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> OllamaGenerateResponse:
        payload = self._generation_payload(
            model,
            prompt,
            stream=False,
            system=system,
            response_format=response_format,
            options=options,
        )
        try:
            response = await self._client.post("/api/generate", json=payload, timeout=self.generation_timeout)
            response.raise_for_status()
            generated = OllamaGenerateResponse.model_validate(response.json())
            if not generated.done:
                raise OllamaException("Ollama returned a nonterminal normal response")
            return generated
        except OllamaException:
            raise
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            raise OllamaException("Ollama returned an invalid generation response") from exc
        except httpx.HTTPError as exc:
            raise self._domain_error(exc, "generating") from exc

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[OllamaGenerateResponse]:
        payload = self._generation_payload(model, prompt, stream=True, system=system, options=options)
        terminal_seen = False
        try:
            async with self._client.stream(
                "POST", "/api/generate", json=payload, timeout=self.generation_timeout
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                        if isinstance(raw, dict) and raw.get("error"):
                            raise OllamaException("Ollama generation stream failed")
                        chunk = OllamaGenerateResponse.model_validate(raw)
                    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
                        raise OllamaException("Ollama returned invalid streamed data") from exc
                    yield chunk
                    if chunk.done:
                        terminal_seen = True
                        break
        except OllamaException:
            raise
        except httpx.HTTPError as exc:
            raise self._domain_error(exc, "streaming generation") from exc
        if not terminal_seen:
            raise OllamaException("Ollama stream ended without a terminal response")

    @staticmethod
    def _generation_payload(
        model: str,
        prompt: str,
        *,
        stream: bool,
        system: str | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": stream}
        if system is not None:
            payload["system"] = system
        if response_format is not None:
            payload["format"] = response_format
        if options is not None:
            payload["options"] = dict(options)
        return payload

    @staticmethod
    def _domain_error(exc: httpx.HTTPError, operation: str) -> OllamaException:
        if isinstance(exc, httpx.TimeoutException):
            return OllamaTimeoutError(f"Ollama timed out while {operation}")
        if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
            return OllamaConnectionError(f"Cannot connect to Ollama while {operation}")
        return OllamaException(f"Ollama failed while {operation}")

    @staticmethod
    def _readiness_message(readiness: OllamaReadiness) -> str:
        missing = [*readiness.missing_required, *readiness.missing_optional]
        if not missing:
            return "All configured Ollama models are available"
        return f"Missing Ollama models: {', '.join(missing)}"
