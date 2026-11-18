from pathlib import Path

from ast_sieve.parser import functions, load_languages, parse_source, spec_for, structure_hash


def _names(ext: str, code: str) -> list[str]:
    spec = load_languages()[ext]
    return [fi.name for fi in functions(parse_source("x" + ext, code, spec))]


def test_python_methods_and_functions():
    assert _names(".py", "def a(): pass\nclass C:\n    def m(self): pass\n") == ["a", "m"]


def test_javascript_arrow_and_method_are_captured():
    code = "const add = (a, b) => a + b;\nclass B { run() {} }\nfunction f() {}\n"
    assert set(_names(".js", code)) == {"add", "run", "f"}


def test_go_methods_are_captured():
    code = "package p\nfunc Hello() {}\nfunc (b Baz) Method() int { return 1 }\n"
    assert _names(".go", code) == ["Hello", "Method"]


def test_unknown_extension_has_no_spec():
    assert spec_for(Path("notes.txt")) is None


def test_structure_hash_ignores_names_but_not_structure():
    spec = load_languages()[".py"]
    a = parse_source("a.py", "def f(x):\n    return x + 1\n", spec)
    b = parse_source("b.py", "def g(y):\n    return y + 2\n", spec)
    c = parse_source("c.py", "def h(y):\n    return y * 2\n", spec)
    hash_a, hash_b, hash_c = (structure_hash(p.root)[0] for p in (a, b, c))
    assert hash_a == hash_b
    assert hash_a != hash_c


def test_syntax_errors_are_detected():
    spec = load_languages()[".py"]
    assert parse_source("bad.py", "def (:\n", spec).has_error
