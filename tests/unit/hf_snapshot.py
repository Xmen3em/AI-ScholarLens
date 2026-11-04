"""The week-7 arXiv source-review snapshot some HF pilot tests read: 14 MB, local only, never committed."""

from pathlib import Path

import pytest

SNAPSHOT = Path("tests/test_output/week7-source-review-20261013-01")
requires_snapshot = pytest.mark.skipif(not (SNAPSHOT / "state.json").exists(),
                                       reason="needs the local week-7 arXiv snapshot, which is not committed")
