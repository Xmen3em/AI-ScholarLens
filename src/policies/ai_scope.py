"""The fixed set of arXiv categories this corpus ingests.

The scope is a code constant rather than a setting on purpose: deployment
configuration must not be able to redirect ingestion outside AI research.
Categories follow arXiv's taxonomy (https://arxiv.org/category_taxonomy).
"""

from typing import Any

AI_CATEGORY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "cs.AI",  # Artificial Intelligence
        "cs.LG",  # Machine Learning
        "cs.CL",  # Computation and Language
        "cs.CV",  # Computer Vision and Pattern Recognition
        "cs.RO",  # Robotics
        "cs.MA",  # Multiagent Systems
        "cs.NE",  # Neural and Evolutionary Computing
        "stat.ML",  # Machine Learning (Statistics)
    }
)


def matches_ai_scope(categories: Any) -> bool:
    """Whether any of a paper's arXiv categories is in the allowlist.

    Cross-listed papers qualify on a secondary category, so every tag participates
    in the match, not just the primary one. Missing or malformed categories are a
    finding for the audit rather than an error, so they return False instead of raising.
    """
    if not isinstance(categories, (list, tuple, set, frozenset)):
        return False
    return any(category in AI_CATEGORY_ALLOWLIST for category in categories if isinstance(category, str))


def ai_scope_query() -> str:
    """The grouped arXiv category clause, e.g. ``(cat:cs.AI OR cat:cs.CL OR ...)``.

    Sorted because a frozenset has no stable iteration order, and the query string
    is asserted on in tests and read in logs.
    """
    return "(" + " OR ".join(f"cat:{category}" for category in sorted(AI_CATEGORY_ALLOWLIST)) + ")"
