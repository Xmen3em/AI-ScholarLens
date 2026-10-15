"""Explicit local GPT-OSS BPE admission; never fetch tokenizer data at runtime."""

import base64
import hashlib
import json
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

from src.services.hf.client import HFGenerationError

VOCABULARY_PATH = Path("data/pc-app/tokenizer/o200k_base.tiktoken")
VOCABULARY_URL = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
VOCABULARY_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
MAX_VOCABULARY_BYTES = 8 * 1024 * 1024
MAX_SCHEMA_BYTES = 7168
MAX_PAYLOAD_BYTES = 65536
# The published o200k_base splitting expression is also used by o200k_harmony.
# Source: openai/tiktoken 0.14.0, tiktoken_ext/openai_public.py (MIT).
PATTERN = "|".join([
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"\p{N}{1,3}", r" ?[^\s\p{L}\p{N}]+[\r\n/]*", r"\s*[\r\n]+", r"\s+(?!\S)", r"\s+",
])


def verify_vocabulary() -> bytes:
    if version("tiktoken") != "0.14.0":
        raise ValueError("Local tokenizer package differs from the pinned version")
    if VOCABULARY_PATH.stat().st_size > MAX_VOCABULARY_BYTES:
        raise ValueError("Local tokenizer exceeds its size limit")
    data = VOCABULARY_PATH.read_bytes()
    if hashlib.sha256(data).hexdigest() != VOCABULARY_SHA256:
        raise ValueError("Local tokenizer differs from the pinned vocabulary")
    return data


@lru_cache(maxsize=1)
def _encoding(data: bytes):
    import tiktoken

    ranks = {}
    for line in data.splitlines():
        token, rank = line.split()
        ranks[base64.b64decode(token, validate=True)] = int(rank)
    # Ordinary encoding cannot interpret untrusted text as Harmony control tokens.
    return tiktoken.Encoding(name="scholarlens_o200k_ordinary", pat_str=PATTERN,
                             mergeable_ranks=ranks, special_tokens={})


def count_input_tokens(serialized: str) -> int:
    return len(_encoding(verify_vocabulary()).encode_ordinary(serialized))


class CerebrasInputAdmission:
    def _input_units(self, payload: dict, serialized: str) -> int:
        if payload["model"] != "openai/gpt-oss-120b:cerebras":
            raise HFGenerationError("Tokenized admission requires the registered Cerebras model")
        schema = payload.get("response_format", {}).get("json_schema", {}).get("schema", {})
        if (len(serialized.encode("utf-8")) > MAX_PAYLOAD_BYTES
                or len(json.dumps(schema, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_SCHEMA_BYTES):
            raise HFGenerationError("Hosted payload or schema exceeds the frozen byte limit")
        return count_input_tokens(serialized)
