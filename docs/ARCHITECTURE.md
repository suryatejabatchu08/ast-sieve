# AST-Sieve: Architecture

## 1. Pipeline
```
walker -> parser -> symbol table + call graph -> analyzers -> findings
       -> (optional LLM critic) -> fixers -> patch verifier -> report
```
Everything up to `findings` is deterministic and offline. The critic and
`--online` checks are opt-in.

## 2. Modules
```
ast_sieve/
  cli.py          Typer app: scan, fix
  config.py       YAML + CLI flag loading (small, typed)
  schemas.py      Pydantic: Finding, Location, SymbolTable, Patch
  walker.py       Gitignore-aware file collection, --staged, --exclude
  parser.py       tree-sitter loading, .scm queries, symbol table builder
  callgraph.py    NetworkX graph of definitions and call edges
  analyzers/
    __init__.py   Analyzer protocol + registry
    gaps.py       GAP001-002
    slop.py       SLP001-006
    security.py   SEC001-004
    taint.py      TNT001
    phantom_deps.py  DEP001-002
    empty_tests.py   GAP003
  critic.py       Optional OpenAI-compatible reviewer
  patching.py     Fixers, unified diffs, verification loop
  report.py       text (rich), JSON, SARIF 2.1.0
  languages/
    python/ queries.scm, mapping.yaml
    javascript/ queries.scm, mapping.yaml   (also used for TypeScript)
    go/ queries.scm, mapping.yaml
demo-messy-repo/  Seeded benchmark + expected.json
scripts/evaluate.py
tests/
```

## 3. Data model
```
Finding: id, rule, severity (low|medium|high), confidence (0..1),
         file, start_line, end_line, message, evidence, fix (optional)
```
Findings are sorted by (file, line, rule) and deduplicated on
(rule, file, start_line).

## 4. Language-agnostic parsing
Tree-sitter node names differ per language, so analyzers never touch raw node
types. Each language directory supplies:
- `queries.scm`: captures such as `@function`, `@call`, `@import`, `@catch`,
  `@string`, `@comment`.
- `mapping.yaml`: language facts (entrypoint names, test name patterns,
  dangerous sinks, taint sources, stdlib list source).

The parser turns captures into a language-neutral `SymbolTable`: functions
(name, span, params, body hash), calls, imports, string literals, catch
blocks, comments. Analyzers consume only this table and the call graph.
Files containing tree-sitter error nodes are reported once as unparseable and
skipped by analyzers.

## 5. Analyzer design notes

**Clone detection (SLP001).** Walk each function body, replace identifiers
and literals with positional placeholders, serialize node types only, hash
with SHA-256. Ignore functions under a minimum node count to avoid trivial
matches. Equal hashes form a clone group.

**Dead code (SLP002).** Unreachable statements after `return`/`raise`/`break`.
Uncalled functions are flagged only when they are not entrypoints. Entrypoint
heuristic: `main`, names in `mapping.yaml`, decorated functions, exported
names, test functions, dunder methods, names appearing in `__all__`. Borderline
cases get lower confidence and go to the critic when enabled.

**Taint (TNT001).** Sources and sinks come from `mapping.yaml`. Within a
function, propagate taint through assignments, string formatting and
concatenation. Across functions, follow call-graph edges by name up to
`max_hops` (default 2), mapping arguments to parameters. Confidence decreases
per hop and when a sanitizer-like call is on the path. This is heuristic,
and reports say so.

**Phantom dependencies (DEP001/002).** Offline: collect imports, subtract
stdlib (`sys.stdlib_module_names` for Python), local modules found by the
walker, and names declared in manifests, using an import-to-package alias
map (`yaml` -> `pyyaml`, `cv2` -> `opencv-python`). Remainder is DEP002 at
low confidence. Online (`--online`): query PyPI or npm for each declared or
imported package, cache results, and report missing ones as DEP001.

**Secrets (SEC001).** Regex for known token shapes plus Shannon entropy
threshold on string literals, with a variable-name hint (`key`, `token`,
`secret`, `password`) and an allowlist for obvious placeholders in docs.

**Empty tests (GAP003).** Test functions identified by name and file
patterns. Flag bodies with no assertion calls, or with only constant
assertions such as `assert True`.

## 6. Fixers and the verification loop
Fixers produce a unified diff for one finding. A patch is accepted only if
all steps pass, otherwise it is discarded:
1. Apply to an in-memory copy of the file.
2. Re-parse: zero tree-sitter error nodes.
3. Re-run analyzers on that file: the target finding is gone and no new
   finding appears.
4. Write to disk (`--apply`) or print the diff (`--dry-run`).

Verification is implemented for Python. Other languages are scan-only.

## 7. LLM critic (optional)
Disabled by default. Uses an OpenAI-compatible client with `base_url`,
`model` and the API key read from an environment variable. For each
ambiguous finding it may call read-only tools (`read_span`, `find_callers`,
`grep`) and returns `valid`, `reason`. Invalid findings are dropped and the
reason is logged. Calls are concurrent with a semaphore and a timeout. If
the endpoint is unreachable, the scan continues without the critic.

## 8. Output
- **text:** rich table sorted by severity, plus a one-line summary.
- **json:** list of findings plus run metadata.
- **sarif:** SARIF 2.1.0 with rule metadata and locations.

## 9. Config
`.ast-sieve.yaml` at the repo root: enabled analyzers, severity threshold,
exclude globs, taint `max_hops` and `min_confidence`, critic settings.
CLI flags override the file. Defaults must work with no file.

## 10. Suppressions and dogfooding
Inline suppression: `# ast-sieve:ignore[RULE] reason`. A reason is required;
a suppression without one is itself a finding. `SELF_AUDIT.md` lists every
suppression in this repo with its justification. Dogfood command:
`ast-sieve scan . --exclude tests,fixtures,demo-messy-repo`.

Rule-definition files legitimately contain words like TODO. Hygiene checks
that grep for such words exclude `analyzers/slop.py` and `analyzers/gaps.py`.

## 11. Testing
- Unit: each analyzer on small fixtures with known findings.
- Integration: scan the benchmark, assert against `expected.json`.
- Property: for every accepted patch, re-scan shows no regressions.
- `scripts/evaluate.py`: precision, recall, F1 against `expected.json`.
- Coverage targets: 80% on analyzers, 70% overall.

## 12. Tooling
Python 3.11+, `uv`, `ruff`, `mypy`, `pytest`, `vulture`, `typer`, `rich`,
`pydantic`, `pyyaml`, `networkx`, `tree-sitter`, `tree-sitter-language-pack`,
`httpx`, optional `openai`.