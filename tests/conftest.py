from __future__ import annotations

from pathlib import Path

import pytest

from ast_sieve.engine import scan
from ast_sieve.schemas import Finding

BENCH = Path(__file__).resolve().parent.parent / "demo-messy-repo"


@pytest.fixture
def run(tmp_path: Path):
    """Write files into a temp project and scan it: run({'a.py': code}) -> findings."""

    calls = iter(range(1000))

    def _run(files: dict[str, str], **kwargs: object) -> list[Finding]:
        project = tmp_path / f"project{next(calls)}"
        for name, text in files.items():
            target = project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return scan(project, **kwargs)  # type: ignore[arg-type]

    return _run


def rules(findings: list[Finding]) -> set[str]:
    return {f.rule for f in findings}
