# AST-Sieve

Read before doing anything:
@docs/PRD.md
@docs/ARCHITECTURE.md

## Working rules
- Build one milestone at a time (M1 to M5, see PRD section 9). Plan first, then implement.
- Make the matching entries in demo-messy-repo/expected.json pass. Never edit expected.json to make a test pass.
- Python 3.11+, type hints on public functions, Google-style docstrings, functions under 50 lines, modules under 300 lines.
- No dead code, no leftover TODO/FIXME, no placeholder text. This repo is a slop detector and must be clean.
- Do not invent the arena.json schema. Ask me for it.
- Never put API keys or the hackathon entry key in any file or prompt.

## Definition of done for each milestone
1. `uv run pytest -x -q` passes
2. `uv run ruff check ast_sieve` and `uv run mypy ast_sieve` are clean
3. `uv run vulture ast_sieve` shows only justified items
4. `uv run python scripts/evaluate.py` shows the milestone targets
5. AI_LOG.md has an entry and the session is exported to ai-logs/
6. Committed with a conventional commit message

## Commands
uv sync --dev
uv run pytest -x -q
uv run python scripts/evaluate.py
uv run ast-sieve scan . --exclude tests,fixtures,demo-messy-repo