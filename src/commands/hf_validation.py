"""Reuse pure frozen inputs within one synchronous, byte-checked validation."""

import copy
import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

FROZEN_ROOT = Path("evaluation/week7_hf")
RESEARCH_CATALOG = Path("docs/research/hf-inference-models-20261013.json")
_ROOT_FILES = ("manifest.json", "fixtures.json", "profile.json", "requests.json", "PROTOCOL.md")
P = ParamSpec("P")
T = TypeVar("T")


def _fingerprints(roots: set[Path]) -> dict[Path, bytes | None]:
    paths = {path.resolve() for path in FROZEN_ROOT.rglob("*") if path.is_file()}
    paths.add(RESEARCH_CATALOG.resolve())
    paths.update(root / name for root in roots for name in _ROOT_FILES)
    return {path: hashlib.sha256(path.read_bytes()).digest() if path.is_file() else None for path in paths}


@dataclass
class _Validation:
    before: dict[Path, bytes | None]
    roots: set[Path] = field(default_factory=set)
    values: dict[tuple, Any] = field(default_factory=dict)

    def watch(self, root: Path) -> None:
        root = root.resolve()
        if root.is_relative_to(FROZEN_ROOT.resolve()) or root in self.roots:
            return
        self.roots.add(root)
        for name in _ROOT_FILES:
            path = root / name
            self.before[path] = hashlib.sha256(path.read_bytes()).digest() if path.is_file() else None


_active: ContextVar[_Validation | None] = ContextVar("hf_frozen_validation", default=None)


@contextmanager
def validation_scope() -> Iterator[None]:
    if _active.get() is not None:
        yield
        return
    state = _Validation(_fingerprints(set()))
    token = _active.set(state)
    try:
        yield
        if _fingerprints(state.roots) != state.before:
            raise ValueError("Frozen inputs changed during validation")
    finally:
        _active.reset(token)


def validation_operation(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def validate(*args: P.args, **kwargs: P.kwargs) -> T:
        with validation_scope():
            return function(*args, **kwargs)

    return validate


def memoized_input(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def load(*args: P.args, **kwargs: P.kwargs) -> T:
        state = _active.get()
        if state is None:
            return function(*args, **kwargs)
        for value in (*args, *kwargs.values()):
            if isinstance(value, Path):
                state.watch(value)
        key = (function, Path.cwd(), args, tuple(sorted(kwargs.items())))
        if key not in state.values:
            state.values[key] = function(*args, **kwargs)
        return cast(T, copy.deepcopy(state.values[key]))

    return load
