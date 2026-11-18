"""Deterministic fixers and the closed verification loop (Python files only).

A patch is accepted only if it re-parses without syntax errors, the targeted finding is gone
and no new finding appears. Removing dead code may expose unused imports, so new SLP003 and
SLP002 findings are tolerated after a SLP002 fix and cleaned up by later iterations.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ast_sieve.analyzers.unused import import_entries
from ast_sieve.engine import analyze
from ast_sieve.parser import ParsedFile, end_line, node_text, parse_source, start_line, walk
from ast_sieve.schemas import Finding

MAX_FIXES = 200
_ALLOWED_NEW = {"SLP002": {"SLP002", "SLP003"}}


@dataclass
class FixResult:
    """Outcome of one attempted fix."""

    finding: Finding
    applied: bool
    reason: str


def _replace_lines(pf: ParsedFile, first: int, last: int, new: list[str]) -> str:
    lines = pf.text.splitlines(keepends=True)
    return "".join([*lines[: first - 1], *new, *lines[last:]])


def _fix_remove_lines(pf: ParsedFile, finding: Finding) -> str | None:
    last = finding.end_line
    lines = pf.lines
    if finding.rule == "SLP002" and last < len(lines) and not lines[last].strip():
        last += 1  # drop one trailing blank line left behind by a removed function
    text = _replace_lines(pf, finding.start_line, last, [])
    return re.sub(r"\n{4,}", "\n\n\n", text).rstrip("\n") + "\n"


def _fix_unused_import(pf: ParsedFile, finding: Finding) -> str | None:
    node = next((n for n in pf.root.children
                 if n.type in pf.spec.import_nodes and start_line(n) == finding.start_line), None)
    if node is None:
        return None
    unused = set(finding.meta.get("unused", []))
    kept = [text for name, text in import_entries(node) if name not in unused]
    if not kept:
        return _replace_lines(pf, start_line(node), end_line(node), [])
    if node.type == "import_from_statement":
        module = node_text(node.child_by_field_name("module_name"))
        statement = f"from {module} import {', '.join(kept)}"
    else:
        statement = f"import {', '.join(kept)}"
    return _replace_lines(pf, start_line(node), end_line(node), [statement + "\n"])


def _fix_verify_true(pf: ParsedFile, finding: Finding) -> str | None:
    line = pf.lines[finding.start_line - 1]
    fixed = re.sub(r"verify\s*=\s*False", "verify=True", line)
    if fixed == line:
        return None
    return _replace_lines(pf, finding.start_line, finding.start_line, [fixed + "\n"])


def _import_insert_line(pf: ParsedFile) -> int:
    """Line number after which a new top-level import can be inserted."""
    last = 0
    for index, node in enumerate(pf.root.children):
        docstring = index == 0 and node.type == "expression_statement" \
            and node.children[0].type == "string"
        if node.type in {*pf.spec.import_nodes, "future_import_statement"} or docstring:
            last = end_line(node)
    return last


def _fix_log_except(pf: ParsedFile, finding: Finding) -> str | None:
    node = next((n for n in walk(pf.root)
                 if n.type == "except_clause" and start_line(n) == finding.start_line), None)
    body = next((c for c in reversed(node.named_children) if c.type == "block"), None) \
        if node is not None else None
    if body is None or not body.named_children:
        return None
    stmt = body.named_children[0]
    indent = " " * stmt.start_point[1]
    log = f'{indent}logging.getLogger(__name__).exception("Ignored exception")\n'
    text = _replace_lines(pf, start_line(stmt), end_line(stmt), [log])
    if not re.search(r"^\s*(?:import logging|from logging)\b", text, re.MULTILINE):
        insert_at = _import_insert_line(pf)
        lines = text.splitlines(keepends=True)
        lines.insert(insert_at, "import logging\n")
        text = "".join(lines)
    return text


def _fix_verify_or_log(pf: ParsedFile, finding: Finding) -> str | None:
    if finding.rule == "SEC002":
        return _fix_verify_true(pf, finding)
    return _fix_log_except(pf, finding)


FIXERS: dict[str, Callable[[ParsedFile, Finding], str | None]] = {
    "SLP002": _fix_remove_lines,
    "SLP003": _fix_unused_import,
    "SLP004": _fix_remove_lines,
    "SEC002": _fix_verify_or_log,
    "GAP001": _fix_verify_or_log,
}


def _accept(before: list[Finding], after: list[Finding], target: Finding) -> str | None:
    """Return a rejection reason, or None when the patch proves itself."""
    old, new = Counter(f.key for f in before), Counter(f.key for f in after)
    if new[target.key] >= old[target.key]:
        return "targeted finding still present"
    allowed = _ALLOWED_NEW.get(target.rule, set())
    appeared = {key for key in new if new[key] > old[key] and key[0] not in allowed}
    if appeared:
        return f"introduced new finding: {sorted(appeared)[0][0]}"
    return None


def fix_project(
    files: Sequence[ParsedFile], root: Path, online: bool = False, min_confidence: float = 0.6
) -> tuple[list[ParsedFile], list[FixResult]]:
    """Apply verified fixes; returns the updated files and an outcome for each attempt."""
    current = list(files)
    findings = analyze(current, root, online)
    failed: set[tuple[str, str, int]] = set()
    results: list[FixResult] = []
    for _ in range(MAX_FIXES):
        target = next((f for f in findings if f.fixable and f.confidence >= min_confidence
                       and f.rule in FIXERS and f.file.endswith(".py")
                       and (f.rule, f.file, f.start_line) not in failed), None)
        if target is None:
            break
        failed.add((target.rule, target.file, target.start_line))
        index = next(i for i, pf in enumerate(current) if pf.rel == target.file)
        pf = current[index]
        text = FIXERS[target.rule](pf, target)
        if text is None:
            results.append(FixResult(target, False, "no safe edit available"))
            continue
        patched = parse_source(pf.rel, text, pf.spec)
        if patched.has_error:
            results.append(FixResult(target, False, "patched file does not re-parse cleanly"))
            continue
        candidate = [*current[:index], patched, *current[index + 1:]]
        after = analyze(candidate, root, online)
        reason = _accept(findings, after, target)
        if reason:
            results.append(FixResult(target, False, reason))
            continue
        current, findings = candidate, after
        failed = {k for k in failed if k[1] != target.file}
        results.append(FixResult(target, True, "verified"))
    return current, results


def unified_diff(before: Sequence[ParsedFile], after: Sequence[ParsedFile]) -> str:
    """git-apply compatible diff between two versions of the project."""
    old = {pf.rel: pf.text for pf in before}
    chunks: list[str] = []
    for pf in after:
        if old[pf.rel] != pf.text:
            chunks.extend(difflib.unified_diff(
                old[pf.rel].splitlines(keepends=True), pf.text.splitlines(keepends=True),
                fromfile=f"a/{pf.rel}", tofile=f"b/{pf.rel}"))
    return "".join(chunks)


def write_changes(base: Path, before: Sequence[ParsedFile], after: Sequence[ParsedFile]) -> int:
    """Write changed files to disk; returns how many were written."""
    old = {pf.rel: pf.text for pf in before}
    written = 0
    for pf in after:
        if old[pf.rel] != pf.text:
            (base / pf.rel).write_text(pf.text, encoding="utf-8")
            written += 1
    return written
