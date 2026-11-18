# Self-audit

`ast-sieve scan . --exclude tests,demo-messy-repo` on this repository (20 source files):

- **0 findings at any confidence**, 0 suppressions (`# ast-sieve:ignore` appears nowhere).
- `ruff check ast_sieve tests scripts`: clean.
- `mypy ast_sieve`: clean (18 files).
- `vulture ast_sieve --min-confidence 70`: nothing reported.
- `pytest`: 58 passed, 92% line coverage (analyzers 83-97%).

## Honest notes

- The exclusions are `tests` (deliberately contain vulnerable and sloppy snippets as inputs) and
  `demo-messy-repo` (the planted-issue benchmark).
- The tool did not catch every slip in this repo. A meaningless `assert ... or True` in a test and
  a test fixture that reused one directory across scans were found by review and test failures,
  not by AST-Sieve.
- Running the tool on real libraries (see BENCHMARK.md) drove most of the analyzer calibration.
