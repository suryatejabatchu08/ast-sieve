# AST-Sieve: Product Requirements

## 1. Problem
AI-assisted code ships with security holes, duplicated or dead code, stubs
that look finished, tests that assert nothing, and imports of packages that
do not exist. Existing scanners either miss these or flood users with false
positives. Teams need one tool, usable on any repo, whose findings can be
trusted and whose fixes are proven safe.

## 2. Product in one sentence
A CLI agent that parses any repository into a syntax tree and call graph,
finds security issues, slop, coding gaps and loose ends with deterministic
analyzers, and ships only fixes that prove themselves.

## 3. Goals
1. Findings are reproducible and carry evidence (file, lines, reason, confidence).
2. Works fully offline with no API key. An LLM is an optional critic.
3. Architecture agnostic: no assumptions about framework, layout or monorepo shape.
4. No fix is emitted unless it applies, re-parses, removes the finding and adds none.
5. Measured quality: precision and recall against a seeded benchmark.

## 4. Non-goals
- Real inter-procedural data-flow analysis. Taint is heuristic and labelled so.
- PyPI release, IDE plugins, a web UI.
- Languages beyond Python, JavaScript/TypeScript and Go.
- Auto-fixing security findings that need design judgment.

## 5. Language support (honest scope)
| Language | Analyzers |
|---|---|
| Python | All analyzers, call graph, taint, patch verifier |
| JavaScript / TypeScript | Core: secrets, empty catch, stubs, dead code, eval/exec sinks, unused imports |
| Go | Core: secrets, empty error handling, stubs, dead code, exec sinks |

Adding a language means adding a `.scm` query file and a `mapping.yaml`, not code.

## 6. Features

### 6.1 Rule catalogue
| Rule ID | Category | Description |
|---|---|---|
| `SEC001` hardcoded-secret | Security | High-entropy or pattern-matched secrets in string literals |
| `SEC002` weak-crypto | Security | MD5/SHA1 for security use, `verify=False`, insecure TLS flags |
| `SEC003` dangerous-sink | Security | `eval`, `exec`, `os.system`, `subprocess(shell=True)`, `innerHTML` |
| `SEC004` sql-injection | Security | String-built SQL passed to execute-like calls |
| `TNT001` taint-path | Security | Untrusted source reaches dangerous sink (intra-function, up to 2 call hops) |
| `SLP001` duplicate-code | Slop | Functions with equal normalized AST hash (renamed copies) |
| `SLP002` dead-code | Slop | Unreachable statements, uncalled private functions (entrypoint-aware) |
| `SLP003` unused-import | Slop | Imports never referenced |
| `SLP004` commented-out-code | Slop | Comment blocks that parse as code |
| `SLP005` stub-body | Slop | Bodies that are `pass`, `...`, `NotImplementedError`, or return a dummy literal |
| `SLP006` marker-density | Slop | Excess TODO/FIXME-style markers per 100 lines |
| `GAP001` empty-catch | Gaps | Empty or swallow-only `except`/`catch`/ignored Go errors |
| `GAP002` missing-error-handling | Gaps | Network, file or subprocess calls with no error path |
| `GAP003` empty-test | Gaps | Tests with no assertions or only trivial ones |
| `DEP001` nonexistent-package | Slop | Imported package does not exist on PyPI/npm (`--online`) |
| `DEP002` undeclared-import | Slop | Import not stdlib, not local, not in manifest (offline, low confidence) |

Every finding has: rule ID, severity, confidence 0.0-1.0, file, start/end line,
evidence text, optional suggested fix.

### 6.2 Fixers (deterministic, Python)
Dead-code removal, unused imports, commented-out code, `verify=False`,
empty-except (replace with logged handling). Nothing else is auto-fixed.

### 6.3 Optional LLM critic
OpenAI-compatible client, configurable `base_url`, off by default. Reviews
ambiguous findings with read-only tools (read span, find callers, grep) and
may mark a finding invalid. Never creates findings.

## 7. CLI
```
ast-sieve scan [PATH] [--staged] [--format text|json|sarif] [--online] [--exclude GLOBS] [--config FILE]
ast-sieve fix  [PATH] [--dry-run | --apply]
```
Exit code 1 when findings at or above the severity threshold exist.

## 8. Acceptance criteria
1. `scan` on `demo-messy-repo/` reports at least 80% of seeded issues (recall) and flags none of the clean control files (precision >= 90%).
2. `fix --apply` on a copy of the benchmark removes the fixable findings, and every applied patch passes the verification loop.
3. `scan .` on this repo, excluding fixtures and the benchmark, reports zero unsuppressed findings.
4. Works with no network and no API key.
5. `scripts/evaluate.py` prints precision, recall and F1.

## 9. Milestones and cut list
| Milestone | Content |
|---|---|
| M1 | Schemas, benchmark repo + `expected.json`, `evaluate.py`, Python parser, call graph |
| M2 | Gap and slop analyzers, text/JSON output, `scan` CLI, `--exclude` |
| M3 | Security, taint, phantom deps, empty tests |
| M4 | JS/TS and Go core analyzers, fixers, patch verifier (Python) |
| M5 | LLM critic, SARIF, Dockerfile, CI, self-audit, README, walkthrough |

Cut order if behind schedule: Docker, LLM critic, SARIF, `--staged`.
Never cut: benchmark, patch verifier, README, AI log.

## 10. Deliverables
README.md, AI_LOG.md, arena.json (schema from the platform, not invented),
WALKTHROUGH.md, SELF_AUDIT.md, BEFORE_AFTER.md, BENCHMARK.md, demo video.