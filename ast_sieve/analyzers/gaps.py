"""Coding gaps: swallowed errors, missing timeouts and tests that assert nothing."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tree_sitter import Node

from ast_sieve.parser import (
    ParsedFile,
    end_line,
    functions,
    node_text,
    start_line,
    statements,
    walk,
)
from ast_sieve.schemas import Finding

if TYPE_CHECKING:
    from ast_sieve.analyzers import Context

_SWALLOW = {"pass_statement", "continue_statement", "ellipsis"}
_TIMEOUT_CALLS = {
    "requests.get", "requests.post", "requests.put", "requests.delete", "requests.patch",
    "requests.head", "requests.request", "urlopen", "urllib.request.urlopen",
}
_TRIVIAL_ASSERT = re.compile(r"^assert\s+(?:True|1)\s*(?:,.*)?$")
_ASSERT_CALL = re.compile(r"^(?:assert|fail|raises|approx|expect)", re.IGNORECASE)


def _catch_finding(pf: ParsedFile, node: Node, body: Node | None, fixable: bool,
                   confidence: float = 0.85) -> Finding:
    return Finding(
        rule="GAP001", severity="medium", confidence=confidence, file=pf.rel,
        start_line=start_line(node), end_line=end_line(body or node), fixable=fixable,
        message="Error is caught and silently ignored",
        evidence=node_text(node).splitlines()[0],
    )


def _python_catches(pf: ParsedFile) -> list[Finding]:
    findings: list[Finding] = []
    for node in walk(pf.root):
        if node.type != "except_clause":
            continue
        body = next((c for c in reversed(node.named_children) if c.type == "block"), None)
        items = statements(body)
        if not items or any(i.type not in _SWALLOW for i in items):
            continue
        simple = len(items) == 1 and items[0].type != "continue_statement"
        separate_line = body is not None and start_line(body) > start_line(node)
        header = node_text(node).split(":", 1)[0].removeprefix("except").strip()
        broad = header in {"", "Exception", "BaseException"} or header.startswith("Exception ")
        findings.append(_catch_finding(pf, node, body, simple and separate_line,
                                       0.9 if broad else 0.6))
    return findings


def _js_catches(pf: ParsedFile) -> list[Finding]:
    return [
        _catch_finding(pf, n, n.child_by_field_name("body"), False)
        for n in walk(pf.root)
        if n.type == "catch_clause" and not statements(n.child_by_field_name("body"))
    ]


def _go_catches(pf: ParsedFile) -> list[Finding]:
    findings: list[Finding] = []
    for node in walk(pf.root):
        if node.type != "if_statement":
            continue
        condition = node_text(node.child_by_field_name("condition"))
        body = node.child_by_field_name("consequence")
        if re.search(r"\berr\s*!=\s*nil\b", condition) and not statements(body):
            findings.append(_catch_finding(pf, node, body, False))
    return findings


def _call_name(call: Node) -> str:
    return node_text(call.child_by_field_name("function"))


def _missing_timeouts(pf: ParsedFile) -> list[Finding]:
    if pf.spec.name != "python":
        return []
    findings: list[Finding] = []
    for node in walk(pf.root):
        if node.type != "call" or _call_name(node) not in _TIMEOUT_CALLS:
            continue
        if "timeout" in node_text(node.child_by_field_name("arguments")):
            continue
        findings.append(Finding(
            rule="GAP002", severity="low", confidence=0.85, file=pf.rel,
            start_line=start_line(node), end_line=end_line(node),
            message=f"Network call {_call_name(node)}() has no timeout",
            evidence=node_text(node).splitlines()[0],
        ))
    return findings


def _is_test_file(pf: ParsedFile) -> bool:
    name = pf.rel.rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py")


def _asserts_something(body: Node | None) -> bool:
    for node in walk(body) if body is not None else []:
        if node.type == "assert_statement" and not _TRIVIAL_ASSERT.match(node_text(node)):
            return True
        if node.type == "call" and _ASSERT_CALL.match(_call_name(node).rsplit(".", 1)[-1]):
            args = node_text(node.child_by_field_name("arguments"))
            if args not in {"(True)", "(1)"}:
                return True
    return False


def _asserting_helpers(files: Sequence[ParsedFile]) -> set[str]:
    """Names of non-test functions that assert, directly or through other helpers."""
    candidates = [
        fi for pf in files if pf.spec.name == "python" for fi in functions(pf)
        if not fi.name.startswith("test_")
    ]
    helpers = {fi.name for fi in candidates if _asserts_something(fi.body)}
    for _ in range(3):
        helpers |= {fi.name for fi in candidates if _delegates(fi.body, helpers)}
    return helpers


def _delegates(body: Node | None, helpers: set[str]) -> bool:
    return any(
        n.type == "call" and _call_name(n).rsplit(".", 1)[-1] in helpers
        for n in (walk(body) if body is not None else [])
    )


def _empty_tests(pf: ParsedFile, helpers: set[str]) -> list[Finding]:
    if pf.spec.name != "python" or not _is_test_file(pf):
        return []
    return [
        Finding(
            rule="GAP003", severity="medium", confidence=0.85, file=pf.rel,
            start_line=start_line(fi.node), end_line=end_line(fi.node),
            message=f"Test '{fi.name}' has no meaningful assertion",
            evidence=node_text(fi.node).splitlines()[0],
        )
        for fi in functions(pf)
        if fi.name.startswith("test") and not _asserts_something(fi.body)
        and not _delegates(fi.body, helpers)
    ]


def analyze(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    """Run gap detectors over all files."""
    catches = {"python": _python_catches, "javascript": _js_catches,
               "typescript": _js_catches, "go": _go_catches}
    helpers = _asserting_helpers(files)
    findings: list[Finding] = []
    for pf in files:
        findings += catches[pf.spec.name](pf) + _missing_timeouts(pf)
        findings += _empty_tests(pf, helpers)
    return findings
