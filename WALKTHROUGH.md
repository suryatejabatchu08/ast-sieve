# Demo walkthrough (about 3 minutes)

1. **Setup (10 s)**: `pip install -e ".[dev]"`. No API key, no network needed.
2. **Scan an unfamiliar polyglot repo**: `ast-sieve scan demo-messy-repo`. Point out the
   severity-sorted table, the confidence column and the "auto-fixable" count.
3. **One finding with evidence**: the taint path in `python/handlers.py`. `lookup()` passes
   `request.args.get("id")` to `find_user()`, which concatenates it into SQL. It is reported at the
   call site (TNT001, one hop) and at the sink (SEC004).
4. **Slop**: `parse_invoices` is a renamed copy of `parse_orders` (SLP001), `validate_token`
   just returns `True` (SLP005), and a commented-out block is detected by parsing the comment
   with the Python grammar (SLP004).
5. **Hallucinated dependency**: `ast-sieve scan demo-messy-repo --online` reports
   `fastapi_secure_utils` (PyPI) and `left-pad-pro` (npm) as nonexistent packages.
6. **Clean controls**: the decorated Flask route and `main` look uncalled but are not reported.
7. **Fix with proof**: `ast-sieve fix demo-messy-repo --dry-run` prints a unified diff. Explain the
   loop: apply in memory, re-parse, re-scan the whole project, accept only if the target is gone
   and nothing new appears. `--apply` writes the files.
8. **Numbers**: `python scripts/evaluate.py` (35 seeded issues), then
   `ast-sieve scan . --exclude tests,demo-messy-repo` returning no findings on its own source.
9. **Limits**: taint is heuristic and Python-only, fixes are Python-only.
