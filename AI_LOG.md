# AI Log

Tool: Claude Code. All sessions are exported to /ai-logs.

## Entry format
### [#] Module / task
- **Prompt (summary):**
- **What Claude produced:**
- **What I changed or rejected, and why:**
- **Result (tests, benchmark):**

### 1. Spec revision rounds 1 and 2 (CLAUDE.md)
- **Prompt (summary):** Asked Claude Code to plan AST-Sieve and write CLAUDE.md,
  then revised it twice after my review.
- **Corrected:** wrong parser package (tree-sitter-languages is unmaintained);
  undefined milestones; missing taint analysis; local-only LLM too heavy;
  offline claim contradicted phantom-dependency check; fixers that add `Any`
  or add phantom packages to the manifest; scope far too large for 24h.
- **Result:** Moved the spec into docs/PRD.md and docs/ARCHITECTURE.md with a
  short CLAUDE.md importing them.

### 2. Planning assistance
- Spec review and drafting of PRD/ARCHITECTURE were done in a separate Claude
  chat (claude.ai) and then given to Claude Code as the source of truth.

### 3. Tree-sitter smoke test
- **Produced:** working version set (tree-sitter 0.26.1,
  tree-sitter-language-pack 1.25.2) and a parse test for Python/JS/TS/Go.
- **Findings:** JS needs `arrow_function` and `method_definition` captures;
  Go needs `method_declaration`; Python class methods already captured.
  These go into the .scm query files.
- **Decision:** kept pyproject pins aligned to versions that actually ran.

### M1 (struggle and pivot)
- **What happened:** Claude Code spent 2+ hours rewriting tree-sitter .scm
  queries against failing tests.
- **My decision:** dropped query files in favor of Python node-walking with
  YAML node-type mappings; cut taint hops, call graph, SARIF, Docker and the
  LLM critic; JS/Go get text-level rules only.
- **Why:** deadline; query-syntax debugging was not converging.

### 5. Claude Code M1 stalled; pivot (my decision)
- **What happened:** Claude Code spent 2+ hours on M1, rewriting tree-sitter `.scm` query files
  against failing tests without converging.
- **My decision:** stop it, drop `.scm` queries, walk the tree in Python with node-type names in
  `mapping.yaml`, and cut scope (SARIF/Docker/critic became optional, JS/Go lighter, fixers Python-only).

### 6. Implementation finished in a Claude chat session with code execution
- **Prompt (summary):** asked Claude to build the whole project in the chat (sandbox with Python,
  tree-sitter, pytest) following docs/PRD.md and docs/ARCHITECTURE.md.
- **What Claude produced:** the `ast_sieve` package (parser, call graph, 6 analyzers, patch
  verification loop, SARIF/JSON/text reports, optional LLM critic, CLI), the seeded benchmark and
  `expected.json`, `scripts/evaluate.py`, 58 tests, README and supporting docs.
- **Process:** benchmark first, then analyzers, then run on real libraries (httpx, typer, rich,
  pydantic, networkx) to find false positives.

### 7. Bugs found and fixed during the build (Claude's mistakes, caught by running things)
- Brace expansion in `mkdir` silently failed in `sh`, leaving a literal `{python,...}` folder
  and missing mapping files; noticed from the error output and redone.
- `GAP001` excluded `pass` bodies by mistake; Python `...` is a direct block child, not an
  `expression_statement`. Found by reading the code while reviewing, before the first real run.
- The benchmark exposed that anonymous callbacks (Express handlers) were skipped by the call
  graph, so functions used only inside them were reported dead. Fixed in the analyzer, not the benchmark.
- Real-library runs exposed 9 false-positive classes (return-then-yield, thin wrappers, abstract
  methods, `# fmt: off`, `sys.argv` into `open`, public methods, assertion helpers, pickle in
  tests, string annotations). Each was fixed in the analyzer (listed in BENCHMARK.md).
- The test fixture reused one directory per test, so a second scan saw the first scan's files;
  the failing tests exposed it.
- Claude wrote a vacuous test assertion (`assert ... or True`); I removed it.
- `pyproject.toml` pins from the Claude Code session did not match the versions that actually ran;
  replaced with the verified set and added the missing console entry point and package data.

### 8. Verification and what is NOT verified
- Verified by running: 58 tests pass, 92% coverage, ruff and mypy clean, vulture clean, 0 findings
  when scanning the repo itself, clean-venv `pip install .` works, `--staged` and `--online` work.
- The critic's unit tests use a fake client. I also ran it once against `openai/gpt-oss-120b` on
  Groq: my first attempt used the wrong base URL, so requests went to OpenAI and failed silently
  (the critic fails open, so the output looked normal). After setting the Groq URL, a direct call
  returned valid JSON and the `--critic` scan dropped 0 of 35 findings. No accuracy evaluation.
- **Not verified:** the Dockerfile (no Docker in the sandbox), the GitHub Actions workflow (never
  ran on GitHub).
- The benchmark was written alongside the analyzers, so its 1.00 scores are regression guards,
  not an independent accuracy measurement. This is stated in README and BENCHMARK.md.