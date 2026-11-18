"""Analyzer registry. Each analyzer exposes analyze(files, ctx) -> list[Finding]."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ast_sieve.analyzers import gaps, phantom_deps, security, slop, taint, unused
from ast_sieve.parser import ParsedFile
from ast_sieve.schemas import Finding


@dataclass(frozen=True)
class Context:
    """Run-wide settings shared by analyzers."""

    root: Path
    online: bool = False


Analyzer = Callable[[Sequence[ParsedFile], Context], list[Finding]]

ANALYZERS: tuple[Analyzer, ...] = (
    gaps.analyze,
    slop.analyze,
    unused.analyze,
    security.analyze,
    taint.analyze,
    phantom_deps.analyze,
)
