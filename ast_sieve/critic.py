"""Optional LLM critic: asks an OpenAI-compatible model to refute ambiguous findings.

The critic can only remove findings, never add them. It fails open: any error keeps the finding.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from ast_sieve.parser import ParsedFile
from ast_sieve.schemas import Finding

CONTEXT_LINES = 8
SYSTEM_PROMPT = (
    "You review static-analysis findings. Try to disprove the finding using the code shown. "
    'Reply with JSON only: {"valid": true|false, "reason": "<one sentence>"}. '
    "Say valid=false only when the code clearly shows the finding is a false positive."
)


class ChatClient(Protocol):
    """The slice of the OpenAI client the critic uses."""

    @property
    def chat(self) -> Any:
        """Namespace exposing completions.create()."""


def make_client(base_url: str | None, api_key: str) -> ChatClient:
    """Create an OpenAI-compatible client (requires the optional 'llm' extra)."""
    from openai import OpenAI

    return OpenAI(base_url=base_url, api_key=api_key)


def _snippet(pf: ParsedFile, finding: Finding) -> str:
    first = max(finding.start_line - CONTEXT_LINES, 1)
    last = min(finding.end_line + CONTEXT_LINES, len(pf.lines))
    return "\n".join(f"{n}: {pf.lines[n - 1]}" for n in range(first, last + 1))


def review(client: ChatClient, model: str, finding: Finding, pf: ParsedFile) -> bool:
    """True when the finding should be kept."""
    prompt = (
        f"Rule: {finding.rule} ({finding.rule_name})\nMessage: {finding.message}\n"
        f"File: {finding.file} lines {finding.start_line}-{finding.end_line}\n\n"
        f"Code:\n{_snippet(pf, finding)}"
    )
    try:
        response = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        verdict = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return bool(verdict.get("valid", True))
    except Exception:  # the critic must never break a scan
        return True


def filter_findings(
    findings: Sequence[Finding], files: Sequence[ParsedFile], client: ChatClient, model: str,
    ambiguous_below: float = 0.9, workers: int = 4,
) -> tuple[list[Finding], list[Finding]]:
    """Split findings into (kept, dropped) by asking the critic about ambiguous ones."""
    by_rel = {pf.rel: pf for pf in files}
    ambiguous = [f for f in findings if f.confidence < ambiguous_below and f.file in by_rel]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        verdicts = list(pool.map(lambda f: review(client, model, f, by_rel[f.file]), ambiguous))
    dropped_ids = {id(f) for f, keep in zip(ambiguous, verdicts, strict=True) if not keep}
    kept = [f for f in findings if id(f) not in dropped_ids]
    return kept, [f for f in findings if id(f) in dropped_ids]
