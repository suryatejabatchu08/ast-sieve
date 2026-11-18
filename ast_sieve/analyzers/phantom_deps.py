"""Dependency hygiene: imports that no manifest declares, or packages that do not exist."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from ast_sieve.parser import ParsedFile, node_text, start_line, walk
from ast_sieve.schemas import Finding
from ast_sieve.walker import DEFAULT_EXCLUDES

if TYPE_CHECKING:
    from ast_sieve.analyzers import Context

ALIASES = {
    "yaml": "pyyaml", "cv2": "opencv-python", "pil": "pillow", "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "dotenv": "python-dotenv",
    "jwt": "pyjwt", "git": "gitpython", "attr": "attrs", "crypto": "pycryptodome",
    "openssl": "pyopenssl", "mysqldb": "mysqlclient", "psycopg2": "psycopg2-binary",
    "tree_sitter_language_pack": "tree-sitter-language-pack", "tree_sitter": "tree-sitter",
}
NODE_BUILTINS = {
    "fs", "path", "http", "https", "os", "crypto", "child_process", "util", "events", "stream",
    "url", "zlib", "assert", "buffer", "net", "tls", "readline", "querystring", "timers", "vm",
    "worker_threads", "cluster", "dns", "process", "module",
}
_JS_IMPORT = re.compile(
    r"""(?:import\s[^'"\n]*?from\s*|import\s*|require\(\s*)['"]([^'"]+)['"]"""
)
_REQ_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*")
_cache: dict[tuple[str, str], bool | None] = {}


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _manifest_paths(root: Path, pattern: str) -> list[Path]:
    base = root if root.is_dir() else root.parent
    return [
        p for p in sorted(base.rglob(pattern))
        if not any(part in DEFAULT_EXCLUDES for part in p.relative_to(base).parts)
    ]


def _python_declared(root: Path) -> tuple[set[str], list[tuple[Path, int, str]], bool]:
    declared: set[str] = set()
    entries: list[tuple[Path, int, str]] = []
    paths = _manifest_paths(root, "requirements*.txt")
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _REQ_NAME.match(line.strip())
            if match and not line.strip().startswith("-"):
                declared.add(_normalize(match.group()))
                entries.append((path, number, match.group()))
    for path in _manifest_paths(root, "pyproject.toml"):
        paths.append(path)
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
        extras = [d for group in project.get("optional-dependencies", {}).values() for d in group]
        for dep in [*project.get("dependencies", []), *extras]:
            match = _REQ_NAME.match(dep)
            if match:
                declared.add(_normalize(match.group()))
    return declared, entries, bool(paths)


def _node_declared(root: Path) -> tuple[set[str], list[tuple[Path, int, str]], bool]:
    declared: set[str] = set()
    entries: list[tuple[Path, int, str]] = []
    paths = _manifest_paths(root, "package.json")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for name in data.get(section, {}):
                declared.add(name)
                lines = text.splitlines()
                number = next((i for i, ln in enumerate(lines, 1) if f'"{name}"' in ln), 1)
                entries.append((path, number, name))
    return declared, entries, bool(paths)


def _exists(registry: str, name: str) -> bool | None:
    """True/False from the public registry, None when it could not be checked."""
    key = (registry, name)
    if key not in _cache:
        url = f"https://pypi.org/pypi/{name}/json" if registry == "pypi" \
            else f"https://registry.npmjs.org/{name}"
        try:
            status = httpx.get(url, timeout=6.0, follow_redirects=True).status_code
            _cache[key] = False if status == 404 else (True if status == 200 else None)
        except httpx.HTTPError:
            _cache[key] = None
    return _cache[key]


def _local_names(files: Sequence[ParsedFile]) -> set[str]:
    names: set[str] = set()
    for pf in files:
        for part in pf.rel.split("/"):
            names.add(part.rsplit(".", 1)[0])
    return names


def _python_imports(pf: ParsedFile) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in walk(pf.root):
        if node.type == "import_statement":
            for child in node.children_by_field_name("name"):
                aliased = child.type == "aliased_import"
                dotted = child.child_by_field_name("name") if aliased else child
                found.append((node_text(dotted).split(".")[0], start_line(node)))
        elif node.type == "import_from_statement":
            module = node_text(node.child_by_field_name("module_name"))
            if module and not module.startswith("."):
                found.append((module.split(".")[0], start_line(node)))
    return found


def _js_imports(pf: ParsedFile) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for number, line in enumerate(pf.lines, start=1):
        for spec in _JS_IMPORT.findall(line):
            if spec.startswith((".", "/")) or spec.startswith("node:"):
                continue
            parts = spec.split("/")
            found.append(("/".join(parts[:2]) if spec.startswith("@") else parts[0], number))
    return found


def _finding(rule: str, file: str, line: int, message: str, confidence: float,
             evidence: str) -> Finding:
    return Finding(
        rule=rule, severity="high" if rule == "DEP001" else "low", confidence=confidence,
        file=file, start_line=line, end_line=line, message=message, evidence=evidence,
    )


def _python_findings(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    declared, entries, has_manifest = _python_declared(ctx.root)
    if not has_manifest:
        return []
    local = _local_names(files)
    findings: list[Finding] = []
    for pf in (f for f in files if f.spec.name == "python"):
        for name, line in _python_imports(pf):
            dist = ALIASES.get(name.lower(), name)
            known = name in sys.stdlib_module_names or name in local
            if known or _normalize(dist) in declared or _normalize(name) in declared:
                continue
            if ctx.online and _exists("pypi", dist) is False:
                findings.append(_finding(
                    "DEP001", pf.rel, line, f"Package '{dist}' does not exist on PyPI", 0.9,
                    f"import {name}"))
            else:
                findings.append(_finding(
                    "DEP002", pf.rel, line, f"Import '{name}' is not stdlib, local or declared",
                    0.4, f"import {name}"))
    base = ctx.root if ctx.root.is_dir() else ctx.root.parent
    if ctx.online:
        for path, number, name in entries:
            if _exists("pypi", name) is False:
                findings.append(_finding(
                    "DEP001", path.relative_to(base).as_posix(), number,
                    f"Package '{name}' does not exist on PyPI", 0.9, name))
    return findings


def _js_findings(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    declared, _, has_manifest = _node_declared(ctx.root)
    if not has_manifest:
        return []
    findings: list[Finding] = []
    for pf in (f for f in files if f.spec.name in {"javascript", "typescript"}):
        for name, line in _js_imports(pf):
            if name in NODE_BUILTINS or name in declared:
                continue
            if ctx.online and _exists("npm", name) is False:
                findings.append(_finding(
                    "DEP001", pf.rel, line, f"Package '{name}' does not exist on npm", 0.9, name))
            else:
                findings.append(_finding(
                    "DEP002", pf.rel, line, f"Import '{name}' is not declared in package.json",
                    0.4, name))
    return findings


def analyze(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    """Check imports against manifests; with --online also against the public registries."""
    return _python_findings(files, ctx) + _js_findings(files, ctx)
