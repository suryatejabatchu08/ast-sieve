# Benchmark

## Seeded benchmark: `demo-messy-repo/`

35 planted issues in Python, JavaScript and Go (`expected.json`), plus clean control files that
must stay silent: a decorated route and `main` that look uncalled, `except` blocks that log or
re-raise, a test with real assertions, `import yaml` with `pyyaml` declared, two functions that
look alike but differ structurally, a JS `catch` that logs, a Go `err` check that logs.

Ground truth lines are derived from code snippets chosen independently of the scanner output
(each entry stores its anchor snippet, and a test asserts the anchor is on the stated line).

| Mode | Precision | Recall | F1 | TP / FP / FN |
|---|---|---|---|---|
| offline (default) | 1.00 | 1.00 | 1.00 | 35 / 0 / 0 |
| `--online` | 1.00 | 1.00 | 1.00 | 35 / 0 / 0 |

Reproduce: `python scripts/evaluate.py` and `python scripts/evaluate.py --online`.

**Caveat:** I wrote the benchmark and the analyzers together, and one analyzer bug (anonymous
callbacks counted as dead code) was found by this benchmark and fixed in the analyzer. Perfect
scores here mean "no regressions", not "perfect accuracy".

## Unlabelled real-world runs

Scanning real libraries exposed false-positive classes the benchmark did not, and each was fixed
in the analyzer rather than in the benchmark:

| Observed on | False positive | Fix |
|---|---|---|
| httpx | `return` followed by `yield` reported as unreachable code | generator idiom excluded |
| httpx | thin `get`/`head`/`options` wrappers reported as duplicates | duplicates need at least 3 statements |
| httpx, rich | `raise NotImplementedError` / `pass` in base-class methods | confidence lowered for methods |
| rich | `# fmt: off` reported as commented-out code | formatter directives excluded |
| rich | `sys.argv` into `open()` reported as taint | `open` removed as a sink |
| httpx, typer | public methods reported dead | public methods never reported |
| networkx | 299 tests with assertions delegated to helpers | assertion helpers followed, 3 hops |
| networkx | `pickle`/`eval` inside tests | security confidence lowered in test paths |
| typer | names used only in string annotations reported as unused imports | quoted names count as uses |

| Library | Files | LOC | Findings (conf >= 0.4) | Time |
|---|---|---|---|---|
| httpx | 23 | 8,828 | 17 | 1.1 s |
| typer | 34 | 13,418 | 29 | 1.6 s |
| rich | 100 | 38,515 | 29 | 4.2 s |
| pydantic | 106 | 46,895 | 104 | 6.1 s |
| networkx | 583 | 197,909 | 394 | 24.2 s |

These findings were **not** hand-labelled, so no precision is claimed for them. Samples were
reviewed to find false-positive classes. Remaining noise includes GAP003 on intentional smoke
tests, GAP001 on deliberate `except SomeError: pass`, and low-confidence public-function dead code.
