"""Export the reviewed offline RAG explainer; no app settings or inference."""

import argparse
import json
from pathlib import Path

from src.services.study.visual_learning.models import VisualError
from src.services.study.visual_learning.viewer import export_demo


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a source-checked offline RAG visual lesson.")
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing output is never overwritten.")
    args = parser.parse_args()
    try:
        manifest = export_demo(args.output)
    except (VisualError, OSError) as exc:
        code = str(exc) if isinstance(exc, VisualError) else "export_io_failed"
        print(json.dumps({"error": code}))
        return 1
    print(json.dumps({"viewer": str((args.output / "index.html").resolve()),
                      "scope": manifest["scope"], "png_phases": manifest["png_phases"], "inference_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
