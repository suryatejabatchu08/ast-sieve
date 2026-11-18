"""Security rules: secrets, weak crypto, dangerous sinks and SQL built from strings."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tree_sitter import Node

from ast_sieve.parser import ParsedFile, end_line, node_text, start_line, walk
from ast_sieve.schemas import Finding, Severity

if TYPE_CHECKING:
    from ast_sieve.analyzers import Context

_NAMED_SECRET = re.compile(
    r"""(?i)\b\w*(?:secret|token|passw(?:or)?d|api[_-]?key|private[_-]?key|auth[_-]?key"""
    r"""|access[_-]?key)\w*["']?\s*(?::=|=|:)\s*["'`]([^"'`\n]{8,})["'`]"""
)
_KNOWN_TOKEN = re.compile(
    r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z_\-]{35}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
_PLACEHOLDER = re.compile(
    r"example|changeme|your[_-]|xxx|placeholder|dummy|sample|<|>|\$\{|\{\{|%s|os\.environ|getenv",
    re.IGNORECASE,
)
_SHELL_FUNCS = {"os.system", "os.popen"}
_SUBPROCESS = re.compile(r"^subprocess\.(?:run|call|Popen|check_output|check_call)$")
_DESERIALIZE = {"pickle.loads", "pickle.load", "marshal.loads"}
_SQL_METHODS = (".execute", ".executemany", ".raw")


def entropy(value: str) -> float:
    """Shannon entropy in bits per character."""
    counts = Counter(value)
    return -sum(c / len(value) * math.log2(c / len(value)) for c in counts.values())


def _finding(pf: ParsedFile, rule: str, severity: Severity, confidence: float, node: Node,
             message: str, fixable: bool = False) -> Finding:
    return Finding(
        rule=rule, severity=severity, confidence=confidence, file=pf.rel,
        start_line=start_line(node), end_line=end_line(node), message=message,
        evidence=node_text(node).splitlines()[0], fixable=fixable,
    )


def _secret_findings(pf: ParsedFile) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(pf.lines, start=1):
        named = _NAMED_SECRET.search(line)
        known = _KNOWN_TOKEN.search(line)
        value = named.group(1) if named else ""
        looks_secret = (
            named and " " not in value and not value.startswith("http")
            and not _PLACEHOLDER.search(value) and entropy(value) >= 3.0
        )
        if not (known or looks_secret):
            continue
        findings.append(Finding(
            rule="SEC001", severity="high", confidence=0.95 if known else 0.85, file=pf.rel,
            start_line=number, end_line=number, message="Hardcoded secret or credential",
            evidence=line.strip()[:60] + ("..." if len(line.strip()) > 60 else ""),
        ))
    return findings


def _line_rule_findings(pf: ParsedFile) -> list[Finding]:
    findings: list[Finding] = []
    comment = pf.spec.comment_prefix
    for number, line in enumerate(pf.lines, start=1):
        if line.strip().startswith((comment, "*", "/*")):
            continue
        for rule in pf.spec.line_rules:
            if re.search(rule["pattern"], line):
                findings.append(Finding(
                    rule=rule["rule"], severity=rule["severity"], confidence=rule["confidence"],
                    file=pf.rel, start_line=number, end_line=number,
                    message=rule["message"], evidence=line.strip()[:80],
                ))
    return findings


def _keyword(call: Node, name: str) -> str | None:
    args = call.child_by_field_name("arguments")
    for arg in args.named_children if args is not None else []:
        if arg.type == "keyword_argument" and node_text(arg.child_by_field_name("name")) == name:
            return node_text(arg.child_by_field_name("value"))
    return None


def _builds_sql_string(arg: Node) -> bool:
    if arg.type == "string":
        return any(c.type == "interpolation" for c in arg.children)
    if arg.type == "binary_operator":
        op = node_text(arg.child_by_field_name("operator"))
        return op in {"+", "%"} and any(n.type == "string" for n in walk(arg))
    if arg.type == "call":
        return node_text(arg.child_by_field_name("function")).endswith(".format")
    return False


def _python_call(pf: ParsedFile, call: Node) -> list[Finding]:
    name = node_text(call.child_by_field_name("function"))
    args = call.child_by_field_name("arguments")
    first = args.named_children[0] if args is not None and args.named_child_count else None
    out: list[Finding] = []
    if _keyword(call, "verify") == "False":
        out.append(_finding(pf, "SEC002", "high", 0.95, call,
                            "TLS certificate verification disabled (verify=False)", True))
    if name in {"hashlib.md5", "hashlib.sha1"}:
        out.append(_finding(pf, "SEC002", "medium", 0.7, call, "Weak hash algorithm (MD5 or SHA1)"))
    if name == "ssl._create_unverified_context":
        out.append(_finding(pf, "SEC002", "high", 0.9, call, "TLS verification disabled"))
    if name in {"eval", "exec"}:
        out.append(_finding(pf, "SEC003", "high", 0.9, call, f"Dangerous call: {name}()"))
    if name in _SHELL_FUNCS or (_SUBPROCESS.match(name) and _keyword(call, "shell") == "True"):
        out.append(_finding(pf, "SEC003", "high", 0.8, call, f"Shell command execution: {name}()"))
    if name in _DESERIALIZE or (name == "yaml.load" and "Loader" not in node_text(args)):
        out.append(_finding(pf, "SEC003", "medium", 0.8, call, f"Unsafe deserialization: {name}()"))
    if name.endswith(_SQL_METHODS) and first is not None and _builds_sql_string(first):
        out.append(_finding(pf, "SEC004", "high", 0.85, call,
                            "SQL built from string formatting or concatenation"))
    return out


def analyze(files: Sequence[ParsedFile], ctx: Context) -> list[Finding]:
    """Run security rules over all files."""
    findings: list[Finding] = []
    for pf in files:
        findings += _secret_findings(pf) + _line_rule_findings(pf)
        if pf.spec.name != "python":
            continue
        for node in walk(pf.root):
            if node.type == "call":
                findings += _python_call(pf, node)
    return findings
