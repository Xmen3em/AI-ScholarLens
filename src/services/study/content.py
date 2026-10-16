"""Bounded source acquisition with page provenance and isolated PDF processing."""

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal
from uuid import uuid4

import anyio
import httpx
from pydantic import BaseModel, ConfigDict, Field
from src.services.study.intake import StudyPaper, valid_id


class ContentError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class EvidenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^(?:p\d+b\d+|abstract\d+)$", max_length=32)
    page: int | None = Field(default=None, ge=1, le=45)
    section: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=1800)
    origin: Literal["pdf_text", "ocr", "abstract"] = "pdf_text"


class PaperContent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    paper: StudyPaper
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_revision: str = Field(min_length=1, max_length=80)
    page_count: int = Field(ge=0, le=45)
    blocks: list[EvidenceBlock] = Field(max_length=300)
    missing_pages: list[int] = Field(max_length=45)
    truncated_pages: list[int] = Field(default_factory=list, max_length=45)
    coverage: Literal["full_text", "partial_text", "needs_ocr", "abstract_only"]


def _worker(path: Path, action: str, page: int | None = None, *, timeout: float = 30) -> dict:
    script = Path(__file__).with_name("pdf_worker.py").resolve()
    # The parser receives no API credentials and never imports local settings.
    env = {name: value for name, value in os.environ.items() if name.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    arguments = [sys.executable, "-I", str(script), str(path.resolve()), action]
    if page is not None:
        arguments.append(str(page))
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=timeout, env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode or len(result.stdout) > 3_000_000:
            raise ContentError("pdf_processing_failed")
        raw = json.loads(result.stdout)
        if not isinstance(raw, dict) or "error" in raw:
            raise ValueError
        return raw
    except subprocess.TimeoutExpired:
        raise ContentError("pdf_processing_timeout") from None
    except (OSError, ValueError):
        raise ContentError("pdf_processing_failed") from None


def extract_document(path: Path, paper: StudyPaper) -> PaperContent:
    raw = _worker(path, "extract")
    return PaperContent.model_validate({**raw, "paper": paper,
                                       "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


def render_page(path: Path, page: int) -> bytes:
    raw = _worker(path, "render", page)
    try:
        data = base64.b64decode(raw["image"], validate=True)
        if len(data) > 2_000_000 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError
        return data
    except (ValueError, KeyError, TypeError):
        raise ContentError("pdf_render_failed") from None


class PaperContentService:
    def __init__(self, root: Path, client: httpx.AsyncClient, *, max_bytes: int = 20 * 1024 * 1024):
        if root.is_symlink():
            raise ContentError("unsafe_source_directory")
        self.root, self.client, self.max_bytes = root.resolve(), client, max_bytes
        self._lock = asyncio.Lock()

    def source_path(self, paper: StudyPaper) -> Path:
        if not valid_id(paper.arxiv_id, versioned=True):
            raise ContentError("invalid_source_identity")
        path = self.root / (hashlib.sha256(paper.arxiv_id.encode()).hexdigest() + ".pdf")
        if path.is_symlink():
            raise ContentError("unsafe_source_path")
        return path

    async def acquire(self, paper: StudyPaper) -> PaperContent:
        async with self._lock:
            path = self.source_path(paper)
            cache = path.with_suffix(".json")
            if cache.is_symlink():
                raise ContentError("unsafe_source_path")
            if path.exists() and cache.exists():
                try:
                    if cache.stat().st_size > 2_000_000 or path.stat().st_size > self.max_bytes:
                        raise ValueError
                    saved = PaperContent.model_validate_json(cache.read_bytes())
                    if saved.paper.arxiv_id != paper.arxiv_id or saved.source_sha256 != hashlib.sha256(path.read_bytes()).hexdigest():
                        raise ValueError
                    return saved
                except ValueError:
                    raise ContentError("source_cache_invalid") from None
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".part-" + uuid4().hex)
            try:
                async with self.client.stream("GET", paper.pdf_url, follow_redirects=False, timeout=30) as response:
                    if response.status_code != 200 or "application/pdf" not in response.headers.get("content-type", ""):
                        raise ContentError("pdf_unavailable")
                    size = 0
                    with temporary.open("xb") as target:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            size += len(chunk)
                            if size > self.max_bytes:
                                raise ContentError("pdf_size_limit")
                            target.write(chunk)
                with temporary.open("rb") as source:
                    if source.read(5) != b"%PDF-":
                        raise ContentError("invalid_pdf")
                document = await anyio.to_thread.run_sync(extract_document, temporary, paper)
                os.replace(temporary, path)
                cache.write_text(document.model_dump_json(), encoding="utf-8")
                return document
            except httpx.HTTPError:
                raise ContentError("pdf_unavailable") from None
            finally:
                temporary.unlink(missing_ok=True)
