"""Orchestration: collect files, run analyzers, apply suppressions, sort and deduplicate."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from ast_sieve.analyzers import ANALYZERS, Context
from ast_sieve.parser import ParsedFile, parse_source, spec_for
from ast_sieve.schemas import Finding
from ast_sieve.walker import iter_source_paths

_SUPPRESS = re.compile(r"(?:#|//)\s*ast-sieve:ignore\[([A-Z0-9, ]+)\]\s*(.*)$")


def project_base(target: Path) -> Path:
    """Directory that relative paths and manifests are resolved against."""
    return target if target.is_dir() else target.parent


def collect(target: Path, excludes: Sequence[str] = ()) -> list[ParsedFile]:
    """Parse every supported source file under target."""
    base = project_base(target)
    files: list[ParsedFile] = []
    for path in iter_source_paths(target, excludes):
        spec = spec_for(path)
        if spec is None:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        files.append(parse_source(path.relative_to(base).as_posix(), text, spec))
    return files


def _suppressions(pf: ParsedFile, line: int) -> tuple[set[str], str, int] | None:
    for number in (line, line - 1):
        if 1 <= number <= len(pf.lines):
            match = _SUPPRESS.search(pf.lines[number - 1])
            if match:
                rules = {r.strip() for r in match.group(1).split(",")}
                return rules, match.group(2).strip(), number
    return None


def _apply_suppressions(findings: list[Finding], files: Sequence[ParsedFile]) -> list[Finding]:
    by_rel = {pf.rel: pf for pf in files}
    kept: list[Finding] = []
    for finding in findings:
        found = _suppressions(by_rel[finding.file], finding.start_line) if finding.file in by_rel \
            else None
        if found is None or finding.rule not in found[0]:
            kept.append(finding)
        elif not found[1]:
            kept.append(Finding(
                rule="SUP001", severity="low", confidence=1.0, file=finding.file,
                start_line=found[2], end_line=found[2],
                message=f"Suppression of {finding.rule} has no justification",
            ))
    return kept


def _is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return (
        "tests" in parts[:-1] or name.startswith("test_") or name.endswith(("_test.py", ".test.js"))
    )


def _downgrade_in_tests(finding: Finding) -> Finding:
    """Security rules matter less in test code: lower confidence instead of deleting."""
    if finding.rule.startswith(("SEC", "TNT")) and _is_test_path(finding.file):
        return finding.model_copy(update={"confidence": round(finding.confidence * 0.4, 2)})
    return finding


def analyze(files: Sequence[ParsedFile], root: Path, online: bool = False) -> list[Finding]:
    """Run all analyzers on parsed files and return sorted, deduplicated findings."""
    ctx = Context(root=root, online=online)
    usable = [pf for pf in files if not pf.has_error]
    findings = [
        Finding(rule="PARSE001", severity="low", confidence=0.9, file=pf.rel, start_line=1,
                end_line=1, message="File has syntax errors and was skipped by analyzers")
        for pf in files if pf.has_error
    ]
    for analyzer in ANALYZERS:
        findings += analyzer(usable, ctx)
    findings = [_downgrade_in_tests(f) for f in _apply_suppressions(findings, files)]
    unique = {(f.rule, f.file, f.start_line): f for f in findings}
    return sorted(unique.values(), key=lambda f: (f.file, f.start_line, f.rule))


def scan(target: Path, excludes: Sequence[str] = (), online: bool = False) -> list[Finding]:
    """Collect and analyze a target path."""
    return analyze(collect(target, excludes), project_base(target), online)
