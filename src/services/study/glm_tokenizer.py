"""GLM-5.3's own tokenizer for admission; prepared explicitly, never fetched at runtime.

Counting the serialized request with it over-counts what GLM reports by about 15% (the JSON
wrapping), so it only refuses early; bytes / 3 over-counted by a further 12-24% and refused
follow-ups that fit (paper benchmark, 3 November 2026).
"""

import hashlib
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

GLM_TOKENIZER_PATH = Path("data/pc-app/tokenizer/glm-5.3-tokenizer.json")
GLM_TOKENIZER_URL = ("https://huggingface.co/zai-org/GLM-5.3/resolve/"
                     "ba32f8c19c8738e2c57c71798c601d477a7bf844/tokenizer.json")
# The file's LFS SHA-256 as published by the Hub (paths-info), not its xet hash.
GLM_TOKENIZER_SHA256 = "19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d"
MAX_GLM_TOKENIZER_BYTES = 24 * 1024 * 1024
TOKENIZERS_VERSION = "0.22.1"


def verify_glm_tokenizer() -> bytes:
    if version("tokenizers") != TOKENIZERS_VERSION:
        raise ValueError("Local tokenizer package differs from the pinned version")
    if GLM_TOKENIZER_PATH.stat().st_size > MAX_GLM_TOKENIZER_BYTES:
        raise ValueError("Local GLM tokenizer exceeds its size limit")
    data = GLM_TOKENIZER_PATH.read_bytes()
    if hashlib.sha256(data).hexdigest() != GLM_TOKENIZER_SHA256:
        raise ValueError("Local GLM tokenizer differs from the pinned file")
    return data


@lru_cache(maxsize=1)
def _tokenizer(path: Path, size: int, modified: int):
    # Keyed by the file's identity, so it is verified and loaded once, and again only if the file changes.
    from tokenizers import Tokenizer

    return Tokenizer.from_str(verify_glm_tokenizer().decode("utf-8"))


def clear_cache() -> None:
    _tokenizer.cache_clear()


def count_glm_tokens(serialized: str) -> int | None:
    """Tokens in the serialized request, or None when the verified tokenizer is unavailable."""
    try:
        stat = GLM_TOKENIZER_PATH.stat()
        tokenizer = _tokenizer(GLM_TOKENIZER_PATH, stat.st_size, stat.st_mtime_ns)
    except Exception:  # noqa: BLE001 - a missing or unverified tokenizer falls back to the byte estimate
        return None
    return len(tokenizer.encode(serialized, add_special_tokens=False).ids)
