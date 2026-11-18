"""Heuristic taint tracking (Python): sources to sinks within a function, plus one call hop."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from tree_sitter import Node

from ast_sieve.parser import (
    ParsedFile,
    end_line,
    functions,
    node_text,
    start_line,
    walk,
)
from ast_sieve.schemas import Finding

if TYPE_CHECKING:
    from ast_sieve.analyzers import Context

SOURCE_CALLS = {"input", "raw_input"}
SOURCE_PREFIXES = ("request.", "sys.argv", "os.environ")
SANITIZERS = {"quote", "escape", "int", "float", "bool", "len", "basename", "secure_filename"}
_SHELL = {"os.system", "os.popen", "eval", "exec", "pickle.loads"}
_FIRST_ARG_ONLY = (".execute", ".executemany", ".raw")
_FUNCS = frozenset({"function_definition"})


def is_tainted(node: Node, tainted: set[str]) -> bool:
    """True when the expression can carry untrusted data."""
    if node.type == "call":
        name = node_text(node.child_by_field_name("function"))
        if name.rsplit(".", 1)[-1] in SANITIZERS:
            return False
        if name in SOURCE_CALLS or name.startswith(SOURCE_PREFIXES):
            return True
    elif node.type in {"attribute", "subscript"} and node_text(node).startswith(SOURCE_PREFIXES):
        return True
    elif node.type == "identifier":
        return node_text(node) in tainted
    return any(is_tainted(child, tainted) for child in node.named_children)


def _propagate(scope: Node, tainted: set[str]) -> None:
    kinds = {"assignment", "augmented_assignment"}
    assignments = [n for n in walk(scope, _FUNCS) if n.type in kinds]
    for _ in range(2):
        for node in assignments:
            left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
            if left is None or right is None or left.type != "identifier":
                continue
            if is_tainted(right, tainted):
                tainted.add(node_text(left))


def _sink_args(call: Node) -> list[Node]:
    """Arguments of a dangerous call that must not be tainted; empty for ordinary calls."""
    name = node_text(call.child_by_field_name("function"))
    args_node = call.child_by_field_name("arguments")
    args = list(args_node.named_children) if args_node is not None else []
    if name in _SHELL:
        return args
    if name.startswith("subprocess.") and "shell=True" in node_text(args_node):
        return args[:1]
    if name.endswith(_FIRST_ARG_ONLY):
        return args[:1]
    return []


def _param_names(fn: Node) -> list[str]:
    params = fn.child_by_field_name("parameters")
    names: list[str] = []
    for child in params.named_children if params is not None else []:
        ident = child if child.type == "identifier" else child.child_by_field_name("name")
        if ident is None and child.named_children:
            ident = child.named_children[0]
        text = node_text(ident)
        if text and text not in {"self", "cls"}:
            names.append(text)
    return names


def _param_sinks(pf: ParsedFile) -> dict[str, set[int]]:
    """Which positional parameters of each function flow into a dangerous sink."""
    summary: dict[str, set[int]] = {}
    for fi in functions(pf):
        for index, param in enumerate(_param_names(fi.node)):
            tainted = {param}
            _propagate(fi.node, tainted)
            for call in walk(fi.node, _FUNCS):
                if call.type == "call" and any(is_tainted(a, tainted) for a in _sink_args(call)):
                    summary.setdefault(fi.name, set()).add(index)
    return summary


def _scopes(pf: ParsedFile) -> list[Node]:
    return [pf.root, *(fi.node for fi in functions(pf))]


def _finding(pf: ParsedFile, call: Node, message: str, confidence: float) -> Finding:
    return Finding(
        rule="TNT001", severity="high", confidence=confidence, file=pf.rel,
        start_line=start_line(call), end_line=end_line(call), message=message,
        evidence=node_text(call).splitlines()[0],
    )


def analyze(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    """Report untrusted input reaching dangerous calls, directly or through one call hop."""
    findings: list[Finding] = []
    summaries: dict[str, set[int]] = {}
    python_files = [pf for pf in files if pf.spec.name == "python"]
    for pf in python_files:
        for name, indexes in _param_sinks(pf).items():
            summaries.setdefault(name, set()).update(indexes)
    for pf in python_files:
        for scope in _scopes(pf):
            tainted: set[str] = set()
            _propagate(scope, tainted)
            for call in (n for n in walk(scope, _FUNCS) if n.type == "call"):
                name = node_text(call.child_by_field_name("function"))
                if any(is_tainted(a, tainted) for a in _sink_args(call)):
                    findings.append(_finding(
                        pf, call, f"Untrusted input reaches {name}()", 0.9))
                    continue
                callee = name.rsplit(".", 1)[-1]
                args_node = call.child_by_field_name("arguments")
                args = [a for a in (args_node.named_children if args_node else [])
                        if a.type != "keyword_argument"]
                if any(i < len(args) and is_tainted(args[i], tainted)
                       for i in summaries.get(callee, ())):
                    findings.append(_finding(
                        pf, call, f"Untrusted input flows through {callee}() into a dangerous sink",
                        0.7))
    return findings
