"""Loose ends: dead code, unused imports and commented-out code."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tree_sitter import Node

from ast_sieve.callgraph import dead_functions
from ast_sieve.parser import (
    ParsedFile,
    end_line,
    node_text,
    parse_source,
    start_line,
    walk,
)
from ast_sieve.schemas import Finding

if TYPE_CHECKING:
    from ast_sieve.analyzers import Context

_DIRECTIVE = re.compile(
    r"^\s*(TODO|FIXME|HACK|XXX|NOTE|noqa|type:|pragma|pylint|mypy|pyright|ast-sieve|eslint|"
    r"nolint|istanbul|go:|fmt:|isort:|yapf:|black|flake8|ruff|coverage|!|-\*-)",
    re.IGNORECASE,
)
_QUOTED_NAME = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")


def import_entries(node: Node) -> list[tuple[str, str]]:
    """(bound name, source text) for each name imported by a Python import statement."""
    entries: list[tuple[str, str]] = []
    for child in node.children_by_field_name("name"):
        if child.type == "aliased_import":
            alias = node_text(child.child_by_field_name("alias"))
            entries.append((alias, node_text(child)))
        else:
            text = node_text(child)
            entries.append((text.split(".")[0], text))
    return entries


def _unused_imports(pf: ParsedFile) -> list[Finding]:
    if pf.spec.name != "python" or pf.rel.endswith("__init__.py"):
        return []
    skip = pf.spec.import_nodes
    used = {node_text(n) for n in walk(pf.root, skip) if n.type in pf.spec.identifier_nodes}
    used.update(_QUOTED_NAME.findall(pf.text))  # string annotations and __all__ entries
    findings: list[Finding] = []
    for node in pf.root.children:
        if node.type not in pf.spec.import_nodes or "*" in node_text(node):
            continue
        entries = import_entries(node)
        unused = [name for name, _ in entries if name not in used]
        if not unused:
            continue
        findings.append(Finding(
            rule="SLP003", severity="low", confidence=0.9, file=pf.rel,
            start_line=start_line(node), end_line=end_line(node), fixable=True,
            message=f"Unused import: {', '.join(unused)}",
            evidence=node_text(node).splitlines()[0],
            meta={"unused": unused},
        ))
    return findings


def _dead_code(files: Sequence[ParsedFile]) -> list[Finding]:
    findings: list[Finding] = []
    for pf, fi in dead_functions(files):
        if fi.in_class and not fi.name.startswith("_"):
            continue  # public methods may be called dynamically
        private = fi.name.startswith("_")
        confidence = (0.8 if private else 0.5) if pf.spec.name == "python" else 0.7
        findings.append(Finding(
            rule="SLP002", severity="low", confidence=confidence, file=pf.rel,
            start_line=start_line(fi.node), end_line=end_line(fi.node),
            fixable=pf.spec.name == "python" and confidence >= 0.8,
            message=f"Function '{fi.name}' is never reachable from any entrypoint",
            evidence=node_text(fi.node).splitlines()[0],
            meta={"kind": "function"},
        ))
    return findings


def _unreachable(pf: ParsedFile) -> list[Finding]:
    findings: list[Finding] = []
    for node in walk(pf.root):
        if node.type not in pf.spec.block_nodes:
            continue
        items = [c for c in node.named_children if c.type != "comment"]
        for index, item in enumerate(items):
            if item.type not in pf.spec.terminal_nodes or index == len(items) - 1:
                continue
            rest = items[index + 1:]
            if any(node_text(r).startswith("yield") for r in rest):
                break  # return followed by yield makes a generator
            findings.append(Finding(
                rule="SLP002", severity="medium", confidence=0.9, file=pf.rel,
                start_line=start_line(rest[0]), end_line=end_line(rest[-1]),
                fixable=pf.spec.name == "python",
                message="Unreachable code after return, raise, break or continue",
                evidence=node_text(rest[0]).splitlines()[0],
                meta={"kind": "unreachable"},
            ))
            break
    return findings


def _comment_groups(pf: ParsedFile) -> list[list[Node]]:
    prefix = pf.spec.comment_prefix
    groups: list[list[Node]] = []
    for node in walk(pf.root):
        if node.type != "comment" or not node_text(node).startswith(prefix):
            continue
        row = node.start_point[0]
        if not pf.lines[row].strip().startswith(prefix):
            continue
        if groups and start_line(groups[-1][-1]) == row:
            groups[-1].append(node)
        else:
            groups.append([node])
    return groups


def _looks_like_code(pf: ParsedFile, block: str) -> bool:
    code = pf.spec.snippet_wrapper.replace("{code}", block)
    probe = parse_source("<comment>", code, pf.spec)
    if probe.has_error:
        return False
    return any(n.type in pf.spec.code_nodes for n in walk(probe.root))


def _commented_code(pf: ParsedFile) -> list[Finding]:
    findings: list[Finding] = []
    for group in _comment_groups(pf):
        prefix_len = len(pf.spec.comment_prefix)
        stripped = [node_text(n)[prefix_len:].removeprefix(" ") for n in group]
        if _DIRECTIVE.match(stripped[0]) or not _looks_like_code(pf, "\n".join(stripped)):
            continue
        findings.append(Finding(
            rule="SLP004", severity="low", confidence=0.7, file=pf.rel,
            start_line=start_line(group[0]), end_line=end_line(group[-1]), fixable=True,
            message="Commented-out code", evidence=node_text(group[0]),
        ))
    return findings


def analyze(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    """Run loose-end detectors over all files."""
    findings = _dead_code(files)
    for pf in files:
        findings += _unused_imports(pf) + _unreachable(pf) + _commented_code(pf)
    return findings
