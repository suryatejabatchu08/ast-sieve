"""Command line interface: scan and fix."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ast_sieve import report
from ast_sieve.engine import analyze, collect, project_base
from ast_sieve.parser import ParsedFile
from ast_sieve.patching import fix_project, unified_diff, write_changes
from ast_sieve.schemas import SEVERITY_RANK, Finding
from ast_sieve.walker import staged_files

app = typer.Typer(add_completion=False, help="Find security issues, slop, gaps and loose ends.")
console = Console()


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _critic(
    findings: list[Finding], files: list[ParsedFile], model: str, base_url: str | None
) -> list[Finding]:
    from ast_sieve.critic import filter_findings, make_client

    client = make_client(base_url, os.environ.get("AST_SIEVE_LLM_KEY", "none"))
    kept, dropped = filter_findings(findings, files, client, model)
    console.print(f"[dim]critic dropped {len(dropped)} of {len(findings)} findings[/dim]",
                  highlight=False)
    return kept


@app.command()
def scan(
    path: Annotated[Path, typer.Argument(help="File or directory to scan")] = Path("."),
    fmt: Annotated[str, typer.Option("--format", help="text, json or sarif")] = "text",
    online: Annotated[bool, typer.Option(help="Check packages against PyPI and npm")] = False,
    exclude: Annotated[str, typer.Option(help="Comma-separated glob patterns to skip")] = "",
    min_confidence: Annotated[float, typer.Option(help="Hide findings below this")] = 0.4,
    fail_on: Annotated[str, typer.Option(help="low, medium, high or never")] = "medium",
    staged: Annotated[bool, typer.Option(help="Only report files staged in git")] = False,
    critic: Annotated[bool, typer.Option(help="Let an LLM refute ambiguous findings")] = False,
    llm_model: Annotated[str, typer.Option(envvar="AST_SIEVE_LLM_MODEL")] = "gpt-4o-mini",
    llm_base_url: Annotated[str | None, typer.Option(envvar="AST_SIEVE_LLM_BASE_URL")] = None,
) -> None:
    """Scan PATH and report findings."""
    base = project_base(path)
    files = collect(path, _split(exclude))
    findings = [f for f in analyze(files, base, online) if f.confidence >= min_confidence]
    if staged:
        wanted = staged_files(base)
        findings = [f for f in findings if f.file in wanted]
    if critic:
        findings = _critic(findings, files, llm_model, llm_base_url)
    if fmt == "json":
        typer.echo(report.to_json(findings))
    elif fmt == "sarif":
        typer.echo(report.to_sarif(findings))
    else:
        report.render_text(findings, console)
    threshold = SEVERITY_RANK.get(fail_on, 99)
    if any(SEVERITY_RANK[f.severity] >= threshold for f in findings):
        raise typer.Exit(1)


@app.command()
def fix(
    path: Annotated[Path, typer.Argument(help="Directory to fix")] = Path("."),
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply", help="Preview or write")] = True,
    exclude: Annotated[str, typer.Option(help="Comma-separated glob patterns to skip")] = "",
    patch_file: Annotated[Path | None, typer.Option(help="Also write the diff here")] = None,
    min_confidence: Annotated[float, typer.Option(help="Only fix findings at or above")] = 0.6,
) -> None:
    """Apply verified fixes. Nothing is written unless --apply is passed."""
    base = project_base(path)
    before = collect(path, _split(exclude))
    after, results = fix_project(before, base, min_confidence=min_confidence)
    for r in results:
        mark = "[green]applied [/green]" if r.applied else "[red]rejected[/red]"
        console.print(f"{mark} {r.finding.rule} {r.finding.file}:{r.finding.start_line} "
                      f"- {r.reason}", highlight=False)
    diff = unified_diff(before, after)
    if patch_file is not None:
        patch_file.write_text(diff, encoding="utf-8")
    if dry_run:
        typer.echo(diff or "No verified fixes available.")
        return
    console.print(f"wrote {write_changes(base, before, after)} file(s)")
