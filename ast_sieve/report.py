"""Output formats: rich text table, JSON and SARIF 2.1.0."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence

from rich.console import Console
from rich.table import Table

from ast_sieve import __version__
from ast_sieve.schemas import RULES, SEVERITY_RANK, Finding

_STYLE = {"high": "bold red", "medium": "yellow", "low": "cyan"}
_SARIF_LEVEL = {"high": "error", "medium": "warning", "low": "note"}


def render_text(findings: Sequence[Finding], console: Console) -> None:
    """Print a severity-sorted table and a one-line summary."""
    if not findings:
        console.print("[green]No findings.[/green]")
        return
    table = Table(show_lines=False)
    for column in ("Sev", "Rule", "Location", "Conf", "Message"):
        table.add_column(column, overflow="fold")
    ordered = sorted(findings, key=lambda f: (-SEVERITY_RANK[f.severity], f.file, f.start_line))
    for f in ordered:
        table.add_row(
            f"[{_STYLE[f.severity]}]{f.severity}[/]", f"{f.rule} {f.rule_name}",
            f"{f.file}:{f.start_line}", f"{f.confidence:.2f}", f.message,
        )
    console.print(table)
    counts = Counter(f.severity for f in findings)
    fixable = sum(1 for f in findings if f.fixable)
    console.print(
        f"{len(findings)} findings: {counts['high']} high, {counts['medium']} medium, "
        f"{counts['low']} low ({fixable} auto-fixable)"
    )


def to_json(findings: Sequence[Finding]) -> str:
    """Findings plus run metadata as JSON."""
    payload = {"tool": "ast-sieve", "version": __version__,
               "findings": [f.model_dump() for f in findings]}
    return json.dumps(payload, indent=2)


def to_sarif(findings: Sequence[Finding]) -> str:
    """SARIF 2.1.0 log with rule metadata and physical locations."""
    used = sorted({f.rule for f in findings})
    rules = [
        {"id": rule, "name": RULES.get(rule, (rule, ""))[0],
         "shortDescription": {"text": RULES.get(rule, ("", rule))[1]}}
        for rule in used
    ]
    results = [
        {
            "ruleId": f.rule,
            "level": _SARIF_LEVEL[f.severity],
            "message": {"text": f.message},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": f.file},
                "region": {"startLine": f.start_line, "endLine": f.end_line},
            }}],
            "properties": {"confidence": f.confidence, "evidence": f.evidence},
        }
        for f in findings
    ]
    log = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "ast-sieve", "version": __version__,
                                      "rules": rules}}, "results": results}],
    }
    return json.dumps(log, indent=2)
