import json
import shutil

from typer.testing import CliRunner

from ast_sieve.cli import app
from tests.conftest import BENCH

runner = CliRunner()


def test_scan_json_output_and_exit_code():
    result = runner.invoke(app, ["scan", str(BENCH), "--format", "json"])
    payload = json.loads(result.stdout)
    assert result.exit_code == 1
    assert payload["tool"] == "ast-sieve" and len(payload["findings"]) >= 30


def test_fail_on_never_returns_zero():
    assert runner.invoke(app, ["scan", str(BENCH), "--fail-on", "never"]).exit_code == 0


def test_sarif_is_valid_shape():
    result = runner.invoke(app, ["scan", str(BENCH), "--format", "sarif", "--fail-on", "never"])
    log = json.loads(result.stdout)
    run = log["runs"][0]
    assert log["version"] == "2.1.0" and run["results"] and run["tool"]["driver"]["rules"]
    assert run["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"] >= 1


def test_exclude_skips_paths():
    args = ["scan", str(BENCH), "--format", "json", "--fail-on", "never"]
    args += ["--exclude", "python,js,go"]
    result = runner.invoke(app, args)
    assert json.loads(result.stdout)["findings"] == []


def test_fix_dry_run_then_apply(tmp_path):
    root = tmp_path / "b"
    shutil.copytree(BENCH, root)
    handlers = root / "python" / "handlers.py"
    original = handlers.read_text()
    dry = runner.invoke(app, ["fix", str(root), "--dry-run"])
    assert dry.exit_code == 0 and "verify=True" in dry.stdout
    assert handlers.read_text() == original
    runner.invoke(app, ["fix", str(root), "--apply"])
    assert handlers.read_text() != original
