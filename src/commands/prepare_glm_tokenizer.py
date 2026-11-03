"""Check GLM-5.3's local tokenizer offline; --download explicitly fetches the pinned file."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import httpx
from src.services.study import glm_tokenizer


def prepare(*, download: bool = False, transport: httpx.BaseTransport | None = None) -> dict:
    target = glm_tokenizer.GLM_TOKENIZER_PATH.resolve()
    allowed = Path.cwd().resolve() / "data/pc-app/tokenizer"
    if not target.is_relative_to(allowed) or target == allowed:
        raise ValueError("Tokenizer must stay in its ignored local directory")
    if target.exists():
        glm_tokenizer.verify_glm_tokenizer()
        return {"status": "tokenizer_verified", "outbound_http_requests": 0, "inference_attempts": 0}
    if not download:
        return {"status": "tokenizer_preparation_required", "outbound_http_requests": 0, "inference_attempts": 0}
    data = bytearray()
    # The Hub redirects to its CDN; the pinned hash, not the host, is what is trusted.
    with httpx.Client(timeout=60, trust_env=False, follow_redirects=True, max_redirects=3, transport=transport) as client:
        with client.stream("GET", glm_tokenizer.GLM_TOKENIZER_URL) as response:
            response.raise_for_status()
            for block in response.iter_bytes(chunk_size=65536):
                if len(data) + len(block) > glm_tokenizer.MAX_GLM_TOKENIZER_BYTES:
                    raise ValueError("Tokenizer download exceeds its size limit")
                data.extend(block)
    if hashlib.sha256(data).hexdigest() != glm_tokenizer.GLM_TOKENIZER_SHA256:
        raise ValueError("Downloaded tokenizer differs from the pinned file")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    glm_tokenizer.verify_glm_tokenizer()
    return {"status": "tokenizer_prepared", "bytes": len(data), "sha256": glm_tokenizer.GLM_TOKENIZER_SHA256,
            "outbound_http_requests": 1, "inference_attempts": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(download=args.download)))
    except Exception:
        print(json.dumps({"status": "tokenizer_not_prepared", "inference_attempts": 0}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
