"""Tree-sitter loading plus language-neutral helpers driven by mapping.yaml."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache, cached_property, lru_cache
from pathlib import Path
from typing import Any, cast

import yaml
from tree_sitter import Node, Parser, Tree
from tree_sitter_language_pack import get_parser

LANG_DIR = Path(__file__).parent / "languages"


@dataclass(frozen=True)
class LanguageSpec:
    """Per-language facts read from mapping.yaml; analyzers never hardcode node names."""

    name: str
    grammar: str
    extensions: tuple[str, ...]
    function_nodes: frozenset[str]
    class_nodes: frozenset[str]
    identifier_nodes: frozenset[str]
    block_nodes: frozenset[str]
    terminal_nodes: frozenset[str]
    import_nodes: frozenset[str]
    code_nodes: frozenset[str]
    comment_prefix: str
    snippet_wrapper: str
    entrypoints: frozenset[str]
    entrypoint_prefixes: tuple[str, ...]
    line_rules: tuple[dict[str, Any], ...]


def _spec_from_yaml(data: dict[str, Any]) -> LanguageSpec:
    return LanguageSpec(
        name=data["language"],
        grammar=data["grammar"],
        extensions=tuple(data["extensions"]),
        function_nodes=frozenset(data["function_nodes"]),
        class_nodes=frozenset(data["class_nodes"]),
        identifier_nodes=frozenset(data["identifier_nodes"]),
        block_nodes=frozenset(data["block_nodes"]),
        terminal_nodes=frozenset(data["terminal_nodes"]),
        import_nodes=frozenset(data["import_nodes"]),
        code_nodes=frozenset(data["code_nodes"]),
        comment_prefix=data["comment_prefix"],
        snippet_wrapper=data.get("snippet_wrapper", "{code}"),
        entrypoints=frozenset(data["entrypoints"]),
        entrypoint_prefixes=tuple(data["entrypoint_prefixes"]),
        line_rules=tuple(data["line_rules"]),
    )


@lru_cache(maxsize=1)
def load_languages() -> dict[str, LanguageSpec]:
    """Map file extension to language spec, discovered from languages/*/mapping.yaml."""
    by_ext: dict[str, LanguageSpec] = {}
    for path in sorted(LANG_DIR.glob("*/mapping.yaml")):
        spec = _spec_from_yaml(yaml.safe_load(path.read_text(encoding="utf-8")))
        for ext in spec.extensions:
            by_ext[ext] = spec
    return by_ext


def spec_for(path: Path) -> LanguageSpec | None:
    """Return the language spec for a path, or None when unsupported."""
    return load_languages().get(path.suffix.lower())


@cache
def _parser(grammar: str) -> Parser:
    return get_parser(cast(Any, grammar))


@dataclass
class ParsedFile:
    """A source file with its syntax tree."""

    rel: str
    spec: LanguageSpec
    text: str
    tree: Tree

    @property
    def root(self) -> Node:
        """Root syntax node."""
        return self.tree.root_node

    @property
    def has_error(self) -> bool:
        """True when tree-sitter found syntax errors."""
        return self.root.has_error

    @cached_property
    def lines(self) -> list[str]:
        """Source split into lines."""
        return self.text.splitlines()


def parse_source(rel: str, text: str, spec: LanguageSpec) -> ParsedFile:
    """Parse source text into a ParsedFile."""
    tree = _parser(spec.grammar).parse(text.encode("utf-8"))
    return ParsedFile(rel=rel, spec=spec, text=text, tree=tree)


def node_text(node: Node | None) -> str:
    """Decoded text of a node, empty for None."""
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", "replace")


def start_line(node: Node) -> int:
    """1-based first line of a node."""
    return int(node.start_point[0]) + 1


def end_line(node: Node) -> int:
    """1-based last line of a node."""
    return int(node.end_point[0]) + 1


def walk(
    node: Node, skip: frozenset[str] = frozenset(), skip_ids: frozenset[int] = frozenset()
) -> Iterator[Node]:
    """Pre-order traversal; nodes whose type or id is skipped are yielded but not entered."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        if current is not node and (current.type in skip or current.id in skip_ids):
            continue
        stack.extend(reversed(current.children))


def statements(block: Node | None) -> list[Node]:
    """Non-comment statements of a block, looking through Go's statement_list."""
    if block is None:
        return []
    items = [c for c in block.named_children if c.type != "comment"]
    if len(items) == 1 and items[0].type == "statement_list":
        items = [c for c in items[0].named_children if c.type != "comment"]
    return items


@dataclass
class FunctionInfo:
    """A named function or method in any supported language."""

    name: str
    node: Node
    body: Node | None
    decorated: bool
    exported: bool
    in_class: bool
    class_has_bases: bool


def _function_name(node: Node) -> str:
    name = node_text(node.child_by_field_name("name"))
    parent = node.parent
    if not name and parent is not None and parent.type == "variable_declarator":
        name = node_text(parent.child_by_field_name("name"))
    return name


def _enclosing_class(node: Node, spec: LanguageSpec) -> Node | None:
    parent = node.parent
    while parent is not None:
        if parent.type in spec.class_nodes:
            return parent
        parent = parent.parent
    return None


def _has_bases(cls: Node) -> bool:
    if cls.child_by_field_name("superclasses") is not None:
        return True
    return any(c.type == "class_heritage" for c in cls.children)


def _is_exported(node: Node, name: str, spec: LanguageSpec) -> bool:
    if spec.name == "go":
        return name[:1].isupper()
    parent = node.parent
    for _ in range(4):
        if parent is None:
            return False
        if parent.type == "export_statement":
            return True
        parent = parent.parent
    return False


def functions(pf: ParsedFile) -> list[FunctionInfo]:
    """All named functions and methods in a file."""
    found: list[FunctionInfo] = []
    for node in walk(pf.root):
        if node.type not in pf.spec.function_nodes:
            continue
        name = _function_name(node)
        if not name:
            continue
        cls = _enclosing_class(node, pf.spec)
        parent = node.parent
        found.append(
            FunctionInfo(
                name=name,
                node=node,
                body=node.child_by_field_name("body"),
                decorated=parent is not None and parent.type == "decorated_definition",
                exported=_is_exported(node, name, pf.spec),
                in_class=cls is not None,
                class_has_bases=cls is not None and _has_bases(cls),
            )
        )
    return found


def structure_hash(node: Node) -> tuple[str, int]:
    """Hash of a subtree's node types: identical for renamed copies of the same code."""
    tokens = [n.type for n in walk(node) if n.type != "comment"]
    digest = hashlib.sha256("|".join(tokens).encode("utf-8")).hexdigest()
    return digest, len(tokens)
