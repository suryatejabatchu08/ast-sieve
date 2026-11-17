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