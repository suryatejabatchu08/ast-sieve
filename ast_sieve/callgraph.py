"""Name-based call graph used for dead-code reachability."""

from __future__ import annotations

import re
from collections.abc import Sequence

import networkx as nx
from tree_sitter import Node

from ast_sieve.parser import FunctionInfo, ParsedFile, functions, node_text, walk

_QUOTED = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")


def _is_entrypoint(fi: FunctionInfo, pf: ParsedFile, exported_names: set[str]) -> bool:
    spec = pf.spec
    dunder = fi.name.startswith("__") and fi.name.endswith("__")
    framework_hook = fi.in_class and fi.class_has_bases and not fi.name.startswith("_")
    return (
        fi.decorated
        or fi.exported
        or dunder
        or framework_hook
        or fi.name in spec.entrypoints
        or fi.name in exported_names
        or fi.name.startswith(spec.entrypoint_prefixes)
    )


def _names_a_function(node: Node, pf: ParsedFile) -> bool:
    """True for `name` in `const name = () => ...`, which defines rather than uses it."""
    parent = node.parent
    if parent is None or parent.type != "variable_declarator":
        return False
    value = parent.child_by_field_name("value")
    return value is not None and value.type in pf.spec.function_nodes


def _identifiers(root: Node, pf: ParsedFile, skip_ids: frozenset[int]) -> set[str]:
    return {
        node_text(node)
        for node in walk(root, skip_ids=skip_ids)
        if node.type in pf.spec.identifier_nodes and not _names_a_function(node, pf)
    }


def _all_exports(files: Sequence[ParsedFile]) -> set[str]:
    names: set[str] = set()
    for pf in files:
        if "__all__" in pf.text:
            names.update(_QUOTED.findall(pf.text))
    return names


def dead_functions(files: Sequence[ParsedFile]) -> list[tuple[ParsedFile, FunctionInfo]]:
    """Functions unreachable from module-level code, entrypoints or exports."""
    graph: nx.DiGraph = nx.DiGraph()
    defs: list[tuple[ParsedFile, FunctionInfo]] = []
    exported_names = _all_exports(files)
    roots: set[str] = set()
    for pf in files:
        named = functions(pf)
        # Named functions are entered only through the graph; anonymous callbacks run
        # where they are written, so their bodies count as module-level references.
        roots |= _identifiers(pf.root, pf, frozenset(fi.node.id for fi in named))
        for fi in named:
            defs.append((pf, fi))
            graph.add_node(fi.name)
            if _is_entrypoint(fi, pf, exported_names):
                roots.add(fi.name)
    for pf, fi in defs:
        for name in _identifiers(fi.body or fi.node, pf, frozenset()):
            if name in graph and name != fi.name:
                graph.add_edge(fi.name, name)
    reachable = set(roots)
    for name in roots:
        if name in graph:
            reachable |= nx.descendants(graph, name)
    return [(pf, fi) for pf, fi in defs if fi.name not in reachable]
