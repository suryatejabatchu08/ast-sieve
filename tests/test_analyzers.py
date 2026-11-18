import pytest

from tests.conftest import rules

POSITIVE = {
    "SEC001": ('api_secret = "kT9xQ2mVb7Lp0ZsRw4YdNc8HjGf1AeUi"\n', "a.py"),
    "SEC002": ("import requests\nrequests.get('u', verify=False, timeout=3)\n", "a.py"),
    "SEC003": ("eval(input())\n", "a.py"),
    "SEC004": ("def q(c, u):\n    c.execute(f'SELECT * FROM t WHERE id={u}')\n", "a.py"),
    "GAP001": ("try:\n    x = 1\nexcept Exception:\n    pass\n", "a.py"),
    "GAP002": ("import requests\nrequests.get('http://x')\n", "a.py"),
    "SLP005": ("def encrypt(data):\n    raise NotImplementedError\n", "a.py"),
    "SLP003": ("import os\n", "a.py"),
    "SLP004": ("# value = compute(1, 2)\n# print(value)\n", "a.py"),
    "SEC002_js": ("const a = {rejectUnauthorized: false};\n", "a.js"),
    "GAP001_js": ("try { f(); } catch (e) {}\n", "a.js"),
    "SEC002_go": ("var c = tls.Config{InsecureSkipVerify: true}\n", "a.go"),
}


@pytest.mark.parametrize("name", sorted(POSITIVE))
def test_rule_fires(run, name):
    code, filename = POSITIVE[name]
    assert name.split("_")[0] in rules(run({filename: code}))


NEGATIVE = {
    "SEC001": 'token = os.environ["TOKEN"]\nlabel = "changeme-placeholder"\n',
    "SEC002": "import requests\nrequests.get('u', timeout=3)\n",
    "SEC003": "import ast\nast.literal_eval('1')\n",
    "SEC004": "def q(c, u):\n    c.execute('SELECT * FROM t WHERE id = ?', (u,))\n",
    "GAP001": "import logging\ntry:\n    x = 1\nexcept Exception:\n    logging.exception('x')\n",
    "GAP002": "import requests\nrequests.get('http://x', timeout=3)\n",
    "SLP005": "def add(a, b):\n    return a + b\n",
    "SLP003": "import os\nprint(os.name)\n",
    "SLP004": "# Set up the logger before anything else runs\n",
}


@pytest.mark.parametrize("rule", sorted(NEGATIVE))
def test_clean_code_is_quiet(run, rule):
    assert rule not in rules(run({"a.py": NEGATIVE[rule]}))


def test_unreachable_after_return_but_not_generator_idiom(run):
    flagged = run({"a.py": "def f():\n    return 1\n    print('x')\n"})
    generator = run({"b.py": "def g():\n    return\n    yield 1\n"})
    assert "SLP002" in rules(flagged)
    assert not any(f.file == "b.py" and f.message.startswith("Unreachable") for f in generator)


def test_dead_private_function_but_not_entrypoints(run):
    code = (
        "import functools\n\n\ndef _unused(x):\n    return x\n\n\n"
        "@functools.cache\ndef decorated(x):\n    return x\n\n\ndef main():\n    pass\n"
    )
    dead = [f.message for f in run({"a.py": code}) if f.rule == "SLP002"]
    assert dead == ["Function '_unused' is never reachable from any entrypoint"]


def test_transitively_dead_function_is_found(run):
    code = "def _a():\n    return _b()\n\n\ndef _b():\n    return 1\n"
    assert len([f for f in run({"a.py": code}) if f.rule == "SLP002"]) == 2


def test_renamed_duplicate_is_flagged_but_thin_wrapper_is_not(run):
    body = ("    out = []\n    for r in rows:\n        if r.get('ok'):\n"
            "        {}    out.append({{'v': r['v'] * 2}})\n    return out\n")
    dup = "def one(rows):\n" + body.format("") + "\n\ndef two(rows):\n" + body.format("")
    dup = dup.replace("        if r.get('ok'):\n        ", "        if r.get('ok'):\n")
    wrappers = (
        "def a(x):\n    return call(x, 1, 2, 3, 4, 5)\n\n\n"
        "def b(y):\n    return call(y, 1, 2, 3, 4, 5)\n"
    )
    assert "SLP001" in rules(run({"a.py": dup}))
    assert "SLP001" not in rules(run({"b.py": wrappers}))


def test_empty_test_detected_and_helper_delegation_accepted(run):
    code = (
        "def _check(x):\n    assert x == 1\n\n\ndef test_a():\n    _check(1)\n\n\n"
        "def test_b():\n    assert True\n\n\ndef test_c():\n    x = 1 + 1\n"
    )
    flagged = {f.message for f in run({"test_x.py": code}) if f.rule == "GAP003"}
    assert flagged == {"Test 'test_b' has no meaningful assertion",
                       "Test 'test_c' has no meaningful assertion"}


def test_taint_intra_function_and_sanitizer(run):
    tainted = "import os\n\n\ndef run():\n    name = input()\n    os.system('echo ' + name)\n"
    clean = "import os\n\n\ndef run():\n    n = int(input())\n    os.system('echo ' + str(n))\n"
    assert "TNT001" in rules(run({"a.py": tainted}))
    assert "TNT001" not in rules(run({"b.py": clean}))


def test_taint_one_hop_through_helper(run):
    code = (
        "import os\n\n\ndef helper(cmd):\n    os.system(cmd)\n\n\n"
        "def entry():\n    value = input()\n    helper(value)\n"
    )
    messages = [f.message for f in run({"a.py": code}) if f.rule == "TNT001"]
    assert any("helper()" in m for m in messages)


def test_phantom_dependency_offline_uses_manifest(run):
    files = {
        "requirements.txt": "pyyaml==6.0\n",
        "a.py": "import yaml\nimport ghost_pkg\nimport os\n",
    }
    messages = [f.message for f in run(files) if f.rule == "DEP002"]
    assert len(messages) == 1 and "ghost_pkg" in messages[0]


def test_no_manifest_means_no_dependency_noise(run):
    assert "DEP002" not in rules(run({"a.py": "import ghost_pkg\n"}))


def test_security_findings_in_tests_are_downgraded(run):
    findings = run({"tests/test_x.py": "def test_a():\n    assert eval('1') == 1\n"})
    assert all(f.confidence < 0.4 for f in findings if f.rule == "SEC003")


def test_syntax_error_file_is_reported_and_skipped(run):
    findings = run({"bad.py": "def (:\n"})
    assert rules(findings) == {"PARSE001"}


def test_suppression_with_reason_hides_finding_and_bare_one_does_not(run):
    ok = "eval('1')  # ast-sieve:ignore[SEC003] constant expression in a REPL helper\n"
    bare = "eval('1')  # ast-sieve:ignore[SEC003]\n"
    assert "SEC003" not in rules(run({"a.py": ok}))
    findings = run({"b.py": bare})
    assert "SUP001" in rules(findings) and "SEC003" not in rules(findings)
