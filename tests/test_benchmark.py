import json

from scripts.evaluate import expected_set, score
from tests.conftest import BENCH


def test_every_expected_entry_points_at_a_real_line():
    data = json.loads((BENCH / "expected.json").read_text(encoding="utf-8"))
    for entry in data["findings"]:
        lines = (BENCH / entry["file"]).read_text(encoding="utf-8").splitlines()
        assert entry["anchor"] in lines[entry["line"] - 1], entry


def test_offline_quality_gate():
    result = score(online=False, min_confidence=0.4)
    assert result["recall"] >= 0.9, result["fn"]
    assert result["precision"] >= 0.9, result["fp"]


def test_clean_control_files_have_no_findings():
    result = score(online=False, min_confidence=0.0)
    noisy = [item for item in result["fp"] if "clean" in item[0]]
    assert noisy == []


def test_online_rule_replaces_offline_rule():
    offline, online = expected_set(False), expected_set(True)
    assert any(rule == "DEP002" for _, rule, _ in offline)
    assert any(rule == "DEP001" for _, rule, _ in online)
