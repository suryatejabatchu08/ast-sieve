"""Pydantic models shared by analyzers, fixers and reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]
SEVERITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3}

RULES: dict[str, tuple[str, str]] = {
    "SEC001": ("hardcoded-secret", "Secret or credential embedded in source"),
    "SEC002": ("weak-crypto", "Weak hash or disabled TLS verification"),
    "SEC003": ("dangerous-sink", "Call that executes or deserializes untrusted data"),
    "SEC004": ("sql-injection", "SQL built by string concatenation or formatting"),
    "TNT001": ("taint-path", "Untrusted input reaches a dangerous sink"),
    "SLP001": ("duplicate-code", "Function structurally identical to another one"),
    "SLP002": ("dead-code", "Unreachable statement or function never used"),
    "SLP003": ("unused-import", "Imported name is never referenced"),
    "SLP004": ("commented-out-code", "Comment block that is actually code"),
    "SLP005": ("stub-body", "Function body that does not implement what its name promises"),
    "SLP006": ("marker-density", "Many unresolved work-in-progress markers"),
    "GAP001": ("empty-catch", "Error is caught and silently ignored"),
    "GAP002": ("missing-timeout", "Network call without a timeout"),
    "GAP003": ("empty-test", "Test without a meaningful assertion"),
    "DEP001": ("nonexistent-package", "Dependency does not exist on the public registry"),
    "DEP002": ("undeclared-import", "Import not stdlib, not local and not in any manifest"),
    "SUP001": ("bare-suppression", "Suppression comment without a justification"),
    "PARSE001": ("syntax-error", "File has syntax errors and was skipped"),
}


class Finding(BaseModel):
    """One issue with its location, evidence and confidence."""

    rule: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    file: str
    start_line: int
    end_line: int
    message: str
    evidence: str = ""
    fixable: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        """Line-independent identity used to compare findings across edits."""
        return (self.rule, self.file, self.message)

    @property
    def rule_name(self) -> str:
        """Human readable rule name."""
        return RULES.get(self.rule, (self.rule, ""))[0]
