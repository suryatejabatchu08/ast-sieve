"""Slop detectors: renamed duplicates, stub bodies and unresolved-marker density."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tree_sitter import Node

from ast_sieve.parser import (
    FunctionInfo,
    ParsedFile,
    end_line,
    functions,
    node_text,
    start_line,
    statements,
    structure_hash,
    walk,
)
from ast_sieve.schemas import Finding

if TYPE_CHECKING:
    from ast_sieve.analyzers import Context

MIN_CLONE_NODES = 30
MIN_CLONE_STATEMENTS = 3  # thin one-call wrappers are not copy-paste slop
MARKER = re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b")
PROMISE_VERBS = (
    "validate", "verify", "sanitize", "encrypt", "decrypt", "authenticate", "authorize",
    "check", "hash", "scan", "process",
)
_UNIMPLEMENTED = re.compile(r"not[ _]?implemented|unimplemented|todo", re.IGNORECASE)
_PLACEHOLDER_VALUES = {"{}", "[]", '""', "''"}
_PLACEHOLDER_TEXT = re.compile(r"placeholder|dummy|stub|fake|not implemented", re.IGNORECASE)


def _clones(files: Sequence[ParsedFile]) -> list[Finding]:
    groups: dict[tuple[str, str], list[tuple[ParsedFile, FunctionInfo]]] = defaultdict(list)
    for pf in files:
        for fi in functions(pf):
            dunder = fi.name.startswith("__")
            if dunder or fi.name.lower().startswith("test") or fi.body is None:
                continue
            digest, size = structure_hash(fi.node)
            if size >= MIN_CLONE_NODES and len(statements(fi.body)) >= MIN_CLONE_STATEMENTS:
                groups[(pf.spec.name, digest)].append((pf, fi))
    findings: list[Finding] = []
    for members in groups.values():
        first_pf, first_fi = members[0]
        for pf, fi in members[1:]:
            findings.append(Finding(
                rule="SLP001", severity="medium", confidence=0.85, file=pf.rel,
                start_line=start_line(fi.node), end_line=end_line(fi.node),
                message=f"'{fi.name}' has the same structure as '{first_fi.name}'",
                evidence=f"original: {first_pf.rel}:{start_line(first_fi.node)}",
            ))
    return findings


def _python_stub(fi: FunctionInfo, pf: ParsedFile) -> tuple[str, float] | None:
    if fi.body is None or (fi.name.startswith("__") and fi.name.endswith("__")):
        return None
    if fi.node.parent is not None and re.search(
        r"abstractmethod|overload", node_text(fi.node.parent)[:200]
    ):
        return None
    items = statements(fi.body)
    if items and items[0].type == "expression_statement" and items[0].children[0].type == "string":
        items = items[1:]
    if len(items) != 1:
        return None
    stmt, text = items[0], node_text(items[0])
    if stmt.type == "pass_statement":
        return "body is only 'pass'", 0.8
    if stmt.type == "ellipsis":
        return "body is only '...'", 0.7
    if stmt.type == "raise_statement" and "NotImplementedError" in text:
        return "raises NotImplementedError", 0.9
    if stmt.type == "return_statement" and stmt.named_child_count == 1:
        value = node_text(stmt.named_children[0])
        if value in {"True", "False", "None"} and fi.name.lower().startswith(PROMISE_VERBS):
            return f"promises work but only returns {value}", 0.7
        if value in _PLACEHOLDER_VALUES or _PLACEHOLDER_TEXT.search(value):
            return f"returns a dummy value ({value})", 0.6
    return None


def _brace_stub(fi: FunctionInfo, pf: ParsedFile) -> tuple[str, float] | None:
    if fi.body is None or fi.body.type not in {"statement_block", "block"}:
        return None
    if fi.name in pf.spec.entrypoints:
        return None
    items = statements(fi.body)
    weight = 0.5 if pf.spec.name == "go" else 0.6
    if not items:
        return "empty body", weight
    text = node_text(items[0])
    if len(items) == 1 and text.startswith(("throw", "panic")) and _UNIMPLEMENTED.search(text):
        return "throws or panics as unimplemented", 0.9
    return None


def _stubs(pf: ParsedFile) -> list[Finding]:
    detect = _python_stub if pf.spec.name == "python" else _brace_stub
    findings: list[Finding] = []
    for fi in functions(pf):
        hit = detect(fi, pf)
        if hit is None:
            continue
        reason, confidence = hit
        if fi.in_class and fi.class_has_bases:
            confidence = min(confidence, 0.35)  # likely an intentional override
        elif fi.in_class and "NotImplementedError" in reason:
            confidence = min(confidence, 0.5)  # idiomatic abstract method
        findings.append(Finding(
            rule="SLP005", severity="medium", confidence=confidence, file=pf.rel,
            start_line=start_line(fi.node), end_line=end_line(fi.node),
            message=f"'{fi.name}' looks unimplemented: {reason}",
            evidence=node_text(fi.node).splitlines()[0],
        ))
    return findings


def _markers(pf: ParsedFile) -> list[Finding]:
    hits: list[Node] = [
        n for n in walk(pf.root) if n.type == "comment" and MARKER.search(node_text(n))
    ]
    if len(hits) < 3 or len(hits) * 100 / max(len(pf.lines), 1) <= 5:
        return []
    return [Finding(
        rule="SLP006", severity="low", confidence=0.8, file=pf.rel,
        start_line=start_line(hits[0]), end_line=end_line(hits[-1]),
        message="High density of unresolved markers (TODO, FIXME, HACK, XXX)",
        evidence=node_text(hits[0]),
    )]


def analyze(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    """Run slop detectors over all files."""
    findings = _clones(files)
    for pf in files:
        findings += _stubs(pf) + _markers(pf)
    return findings
