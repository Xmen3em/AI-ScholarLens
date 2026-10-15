"""Check the local tokenizer offline; --download explicitly prepares public BPE data."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import httpx
from src.services.hf import tokenizer


def prepare(*, download: bool = False) -> dict:
    target = tokenizer.VOCABULARY_PATH.resolve()
    allowed = Path.cwd().resolve() / "data/pc-app/tokenizer"
    if not target.is_relative_to(allowed) or target == allowed:
        raise ValueError("Tokenizer must stay in its ignored local directory")
    if target.exists():
        tokenizer.verify_vocabulary()
        return {"status": "tokenizer_verified", "outbound_http_requests": 0, "inference_attempts": 0}
    if not download:
        return {"status": "tokenizer_preparation_required", "outbound_http_requests": 0, "inference_attempts": 0}
    data = bytearray()
    with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
        with client.stream("GET", tokenizer.VOCABULARY_URL) as response:
            response.raise_for_status()
            for block in response.iter_bytes(chunk_size=65536):
                if len(data) + len(block) > tokenizer.MAX_VOCABULARY_BYTES:
                    raise ValueError("Tokenizer download exceeds its size limit")
                data.extend(block)
    if hashlib.sha256(data).hexdigest() != tokenizer.VOCABULARY_SHA256:
        raise ValueError("Downloaded tokenizer differs from the published vocabulary")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    tokenizer.verify_vocabulary()
    return {"status": "tokenizer_prepared", "bytes": len(data), "sha256": tokenizer.VOCABULARY_SHA256,
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
