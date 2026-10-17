"""Opt-in remote OCR candidate, separate from the text tutor and its limits."""

import asyncio
import base64
import hashlib
import json
import math
from pathlib import Path

import httpx
from pydantic import SecretStr
from src.services.hf.client import _unique_object
from src.services.study.content import EvidenceBlock, PaperContent, render_page
from src.services.study.store import StudyStore
from src.services.study.tutor import URL, TutorError, host_memory_mib

# Publisher's image-only chat shape: https://huggingface.co/lightonai/LightOnOCR-2-1B
OCR_MODEL = "lightonai/LightOnOCR-2-1B:featherless-ai"


class RemoteOCR:
    def __init__(self, token: SecretStr, store: StudyStore, *, client=None, memory=host_memory_mib):
        self.store, self.memory = store, memory
        self.client = client or httpx.AsyncClient(headers={"Authorization": "Bearer " + token.get_secret_value()},
            timeout=httpx.Timeout(60, connect=5), follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1))
        self._owned = client is None

    async def aclose(self):
        if self._owned:
            await self.client.aclose()

    async def extract_page(self, job_id: str, image: bytes) -> str:
        free = self.memory()
        if not math.isfinite(free) or free < 600:
            raise TutorError("study_memory_unavailable")
        if not image.startswith(b"\x89PNG\r\n\x1a\n") or not 8 < len(image) <= 2_000_000:
            raise TutorError("ocr_image_invalid")
        payload = {"model": OCR_MODEL, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()}}]}],
            "max_tokens": 2500, "temperature": 0, "stream": False}
        sequence = self.store.reserve_attempt(job_id, "ocr_page", OCR_MODEL)
        state = "unknown"
        try:
            async with asyncio.timeout(65):
                async with self.client.stream("POST", URL, json=payload) as response:
                    if response.status_code != 200:
                        state = "failed"
                        raise TutorError("ocr_provider_unavailable")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if len(body) + len(chunk) > 131072:
                            raise TutorError("ocr_response_limit")
                        body.extend(chunk)
            raw = json.loads(body, object_pairs_hook=_unique_object)
            if len(raw["choices"]) != 1:
                raise ValueError
            choice = raw["choices"][0]
            message, usage = choice["message"], raw["usage"]
            text = message["content"]
            if (choice["finish_reason"] != "stop" or message.get("tool_calls") or message.get("refusal")
                    or type(text) is not str or not 5 <= len(text.strip()) <= 16000
                    or type(usage.get("prompt_tokens")) is not int or not 0 < usage["prompt_tokens"] <= 25000
                    or type(usage.get("completion_tokens")) is not int or not 0 < usage["completion_tokens"] <= 2500):
                raise ValueError
            state = "succeeded"
            return text.replace("\r\n", "\n").replace("\r", "\n").strip()
        except TutorError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception:
            raise TutorError("ocr_response_invalid_or_unavailable") from None
        finally:
            self.store.settle_attempt(job_id, sequence, state)

    async def enrich(self, document: PaperContent, path: Path, job_id: str) -> PaperContent:
        blocks = list(document.blocks)
        provenance = list(document.ocr_provenance)
        missing = list(document.missing_pages)
        # At most two pages, leaving two of the four job attempts for teaching.
        for page in missing[:2]:
            image = await asyncio.to_thread(render_page, path, page)
            text = await self.extract_page(job_id, image)
            for index, start in enumerate(range(0, len(text), 1800), 1):
                blocks.append(EvidenceBlock(id=f"p{page}b{index}", page=page, section=f"OCR page {page}",
                                            text=text[start:start + 1800], origin="ocr"))
            provenance.append({"page": page, "model": OCR_MODEL, "image_sha256": hashlib.sha256(image).hexdigest(),
                               "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
            missing.remove(page)
        raw = document.model_dump()
        # OCR remains partial/needs visual review, even if all pages were transcribed.
        raw.update(blocks=[b.model_dump() for b in sorted(blocks, key=lambda b: (b.page or 0, b.id))],
                   missing_pages=missing, coverage="partial_text", ocr_provenance=provenance)
        return PaperContent.model_validate(raw)
