"""Resolve bounded arXiv inputs without fetching user-controlled URLs."""

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST, ai_scope_query

API_URL = "https://export.arxiv.org/api/query"
XML_LIMIT = 512_000
ATOM = "{http://www.w3.org/2005/Atom}"
MODERN = re.compile(r"(\d{4})\.\d{4,5}(?:v[1-9]\d{0,3})?")
LEGACY = re.compile(r"[A-Za-z][A-Za-z.-]{1,24}/(\d{4})\d{3}(?:v[1-9]\d{0,3})?")


class StudyInputError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class StudyPaper(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    arxiv_id: str = Field(min_length=8, max_length=48)
    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(max_length=30)
    abstract: str = Field(min_length=1, max_length=10_000)
    categories: list[str] = Field(min_length=1, max_length=30)
    published: str = Field(min_length=10, max_length=40)

    @property
    def source_url(self) -> str:
        return "https://arxiv.org/abs/" + self.arxiv_id

    @property
    def pdf_url(self) -> str:
        return "https://arxiv.org/pdf/" + self.arxiv_id


def valid_id(value: str, *, versioned: bool = False) -> bool:
    match = MODERN.fullmatch(value) or LEGACY.fullmatch(value)
    return bool(match and 1 <= int(match[1][2:]) <= 12 and (not versioned or re.search(r"v[1-9]\d*$", value)))


def normalize_input(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or not 1 <= len(value) <= 500 or any(ord(c) < 32 and not c.isspace() for c in value):
        raise StudyInputError("invalid_paper_input")
    value = " ".join(value.split())
    if not value:
        raise StudyInputError("invalid_paper_input")
    if value.lower().startswith("arxiv:"):
        value = value[6:].strip()
    if value.startswith(("arxiv.org/", "www.arxiv.org/")):
        value = "https://" + value
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
        try:
            url = urlsplit(value)
            if (url.scheme not in {"https", "http"} or url.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
                    or url.port not in {None, 443} or url.username or url.password):
                raise ValueError
            match = re.fullmatch(r"/(?:abs|pdf|html)/(.+?)(?:\.pdf)?/?", url.path)
            if not match or not valid_id(match[1]):
                raise ValueError
            return "id", match[1]
        except ValueError:
            raise StudyInputError("unsupported_paper_url") from None
    if valid_id(value):
        return "id", value
    if re.match(r"^\d{4}\.", value) or re.match(r"^[A-Za-z.-]+/\d", value):
        raise StudyInputError("invalid_paper_input")
    return "title", value


def _text(entry: ET.Element, field: str) -> str:
    return " ".join((entry.findtext(ATOM + field) or "").split())


def parse_metadata(body: bytes, requested: str | None) -> list[StudyPaper]:
    if len(body) > XML_LIMIT:
        raise StudyInputError("metadata_too_large")
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", body, re.IGNORECASE):
        raise StudyInputError("invalid_metadata")
    try:
        root = ET.fromstring(body)
        if root.tag != ATOM + "feed":
            raise ValueError
        entries = root.findall(ATOM + "entry")
        if len(entries) > (1 if requested else 3):
            raise ValueError
        papers = []
        for entry in entries:
            raw_id = urlsplit(_text(entry, "id"))
            identity = raw_id.path.removeprefix("/abs/")
            if raw_id.hostname != "arxiv.org" or not valid_id(identity, versioned=True):
                raise ValueError
            if requested and (identity != requested if re.search(r"v\d+$", requested)
                              else re.sub(r"v\d+$", "", identity) != requested):
                raise StudyInputError("version_mismatch")
            categories = [row.attrib.get("term", "") for row in entry.findall(ATOM + "category")]
            if not set(categories) & AI_CATEGORY_ALLOWLIST:
                if requested:
                    raise StudyInputError("outside_ai_scope")
                continue
            published = _text(entry, "published")
            datetime.fromisoformat(published.replace("Z", "+00:00"))
            papers.append(StudyPaper(arxiv_id=identity, title=_text(entry, "title"),
                                     authors=[_text(row, "name") for row in entry.findall(ATOM + "author")],
                                     abstract=_text(entry, "summary"), categories=categories, published=published))
        return papers
    except StudyInputError:
        raise
    except (ET.ParseError, ValueError, TypeError, ValidationError):
        raise StudyInputError("invalid_metadata") from None


class ArxivIntake:
    def __init__(self, client: httpx.AsyncClient, *, delay: float = 3):
        self.client, self.delay = client, delay
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def resolve(self, value: str) -> list[StudyPaper]:
        kind, value = normalize_input(value)
        params = {"max_results": "1" if kind == "id" else "3", "start": "0"}
        if kind == "id":
            params["id_list"] = value
        else:
            # User title tokens cannot introduce an arXiv query operator.
            title = " ".join(re.findall(r"[^\W_]+", value, re.UNICODE))
            if not title:
                raise StudyInputError("invalid_paper_input")
            params.update(search_query=f'ti:"{title}" AND ({ai_scope_query()})', sortBy="relevance")
        async with self._lock:
            await asyncio.sleep(max(0, self.delay - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            try:
                async with self.client.stream("GET", API_URL, params=params, follow_redirects=False, timeout=20) as response:
                    if response.status_code != 200:
                        raise StudyInputError("arxiv_unavailable")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if len(body) + len(chunk) > XML_LIMIT:
                            raise StudyInputError("metadata_too_large")
                        body.extend(chunk)
            except httpx.HTTPError:
                raise StudyInputError("arxiv_unavailable") from None
        return parse_metadata(bytes(body), value if kind == "id" else None)
