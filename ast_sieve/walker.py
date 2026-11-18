"""Gitignore-aware source file discovery."""

from __future__ import annotations

import fnmatch
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

from ast_sieve.parser import spec_for

DEFAULT_EXCLUDES = (
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "*.egg-info", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".ast_sieve_cache",
)


def _gitignore_patterns(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [ln.strip().rstrip("/") for ln in lines if ln.strip() and not ln.startswith(("#", "!"))]


def _matches(rel: Path, patterns: Sequence[str]) -> bool:
    rel_text = rel.as_posix()
    for pattern in patterns:
        clean = pattern.lstrip("/")
        if fnmatch.fnmatch(rel_text, clean) or any(fnmatch.fnmatch(p, clean) for p in rel.parts):
            return True
    return False


def iter_source_paths(root: Path, excludes: Sequence[str] = ()) -> Iterator[Path]:
    """Yield supported source files under root, honouring defaults, .gitignore and excludes."""
    if root.is_file():
        yield root
        return
    patterns = [*DEFAULT_EXCLUDES, *excludes, *_gitignore_patterns(root)]
    for path in sorted(root.rglob("*")):
        if path.is_file() and spec_for(path) and not _matches(path.relative_to(root), patterns):
            yield path


def staged_files(base: Path) -> set[str]:
    """Paths (relative to base) with staged changes; empty when not a git repo."""
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--relative"]
    try:
        out = subprocess.run(cmd, cwd=base, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}
