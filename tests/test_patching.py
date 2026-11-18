import shutil
from pathlib import Path

from ast_sieve import patching
from ast_sieve.engine import analyze, collect
from tests.conftest import BENCH


def _copy_bench(tmp_path: Path) -> Path:
    target = tmp_path / "bench"
    shutil.copytree(BENCH, target)
    return target


def test_fixes_are_verified_and_remove_their_findings(tmp_path):
    root = _copy_bench(tmp_path)
    before = collect(root)
    after, results = patching.fix_project(before, root)
    applied = [r for r in results if r.applied]
    assert {r.finding.rule for r in applied} >= {"SEC002", "SLP003", "GAP001", "SLP002", "SLP004"}
    remaining = {(f.rule, f.file) for f in analyze(after, root)}
    assert ("SLP003", "python/services.py") not in remaining
    assert ("SLP004", "python/services.py") not in remaining
    assert all(not pf.has_error for pf in after)


def test_fixing_never_adds_findings_the_scan_did_not_already_have(tmp_path):
    root = _copy_bench(tmp_path)
    before = collect(root)
    old = {f.key for f in analyze(before, root)}
    after, _ = patching.fix_project(before, root)
    assert {f.key for f in analyze(after, root)} <= old


def test_dry_run_leaves_files_untouched_and_apply_writes(tmp_path):
    root = _copy_bench(tmp_path)
    before = collect(root)
    original = (root / "python/handlers.py").read_text()
    after, _ = patching.fix_project(before, root)
    assert patching.unified_diff(before, after).startswith("--- a/")
    assert (root / "python/handlers.py").read_text() == original
    assert patching.write_changes(root, before, after) >= 1
    assert "verify=True" in (root / "python/handlers.py").read_text()


def test_patch_that_breaks_syntax_is_rejected(tmp_path, monkeypatch):
    root = tmp_path
    (root / "a.py").write_text("import os\n")
    monkeypatch.setitem(patching.FIXERS, "SLP003", lambda pf, f: "def (:\n")
    after, results = patching.fix_project(collect(root), root)
    assert [r.applied for r in results] == [False]
    assert "re-parse" in results[0].reason
    assert after[0].text == "import os\n"


def test_patch_that_does_not_fix_the_finding_is_rejected(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("import os\n")
    monkeypatch.setitem(patching.FIXERS, "SLP003", lambda pf, f: pf.text)
    _, results = patching.fix_project(collect(tmp_path), tmp_path)
    assert results[0].reason == "targeted finding still present"


def test_patch_that_introduces_a_new_finding_is_rejected(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("import os\n")
    monkeypatch.setitem(patching.FIXERS, "SLP003", lambda pf, f: "eval('1')\n")
    _, results = patching.fix_project(collect(tmp_path), tmp_path)
    assert not results[0].applied and "new finding" in results[0].reason


def test_partial_unused_import_keeps_used_names(tmp_path):
    (tmp_path / "a.py").write_text("from os import path, sep\nprint(path)\n")
    after, results = patching.fix_project(collect(tmp_path), tmp_path)
    assert results[0].applied and after[0].text.startswith("from os import path\n")
