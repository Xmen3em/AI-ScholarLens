"""Prepare isolated API build files and audit preserved local/live state."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import httpx
from src.commands.evaluate_retrieval import snapshot

OUT = Path("test_output/selector_reliability")


def hashes(paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file() and "__pycache__" not in p.parts}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("context", "preserve", "audit"))
    parser.add_argument("--variant", choices=("map", "string"), default="map")
    args = parser.parse_args()
    if args.action == "context":
        root = OUT / ("api-context-string" if args.variant == "string" else "api-context")
        root.mkdir(parents=True, exist_ok=True)
        for name in ("Dockerfile", "pyproject.toml", "uv.lock"):
            shutil.copyfile(name, root / name)
        for path in Path("src").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, root / path)
        (OUT / ("api-build-string.yml" if args.variant == "string" else "api-build.yml")).write_text(
            'services:\n  api:\n    build:\n      context: "/mnt/d/Personal projects/AI-ScholarLens/' + root.as_posix() + '"\n',
            encoding="utf-8",
        )
        print("Prepared isolated API build context")
    elif args.action == "preserve":
        target = OUT / "prior_artifacts.json"
        if target.exists():
            raise ValueError("Prior-artifact snapshot already exists")
        paths = [p for p in Path("test_output").rglob("*") if OUT not in p.parents and not any(x in p.parts for x in ("pytest_cache", "__pycache__"))]
        target.write_text(json.dumps(hashes(paths), indent=2), encoding="utf-8")
        print("Saved prior artifact fingerprints")
    else:
        initial = json.loads((OUT / "initial.json").read_text(encoding="utf-8"))
        existing = hashes(Path(p) for p in initial["hashes"])
        changes = [p for p, h in initial["hashes"].items() if existing.get(p) != h]
        prior = json.loads((OUT / "prior_artifacts.json").read_text(encoding="utf-8"))
        unchanged_artifacts = hashes(Path(p) for p in prior) == prior
        frozen = json.loads(Path("evaluation/quality_fixes/preservation.json").read_text(encoding="utf-8"))["frozen_files_sha256"]
        frozen_equal = hashes(Path(p) for p in frozen) == frozen
        finalized_path = OUT / ("finalized_string_source.json" if args.variant == "string" else "finalized_source.json")
        finalized = json.loads(finalized_path.read_text(encoding="utf-8"))
        # Preserve the snapshot's key spelling: Path() changes '/' to '\\' on
        # Windows, which must not manufacture a source-content mismatch.
        final_hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in finalized}
        source_equal = final_hashes == finalized
        with httpx.Client(timeout=30) as client:
            state, _, _ = snapshot(client, "http://localhost:8000/api/v1", "http://localhost:9200")
            models = client.get("http://localhost:11434/api/tags").json()
        model_digests = lambda tags: {m["name"]: m["digest"] for m in tags["models"]}
        audit = dict(initial_file_count=len(initial["hashes"]), changed_initial_files=changes,
                     prior_artifact_count=len(prior), prior_artifacts_unchanged=unchanged_artifacts,
                     frozen_v1_unchanged=frozen_equal, finalized_runtime_and_labels_unchanged=source_equal,
                     corpus_unchanged=state == initial["state"], state=state,
                     model_digests_unchanged=model_digests(models) == model_digests(initial["models"]),
                     model_digests=model_digests(models))
        (OUT / "preservation.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
