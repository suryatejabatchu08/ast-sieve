#!/usr/bin/env python3
"""Throwaway script to test tree-sitter API with Python, JS, and Go snippets."""

from tree_sitter_language_pack import get_language, get_parser


def test_parser(lang_name: str, code: str, node_type: str) -> list[str]:
    """Parse code and extract top-level function names."""
    try:
        parser = get_parser(lang_name)
        get_language(lang_name)
        tree = parser.parse(code.encode())
        root = tree.root_node

        functions = []

        def walk(node):
            if node.type == node_type:
                # Find the function name
                for child in node.children:
                    if child.type in ("identifier", "function_declaration", "name"):
                        functions.append(child.text.decode())
                        break
            for child in node.children:
                walk(child)

        walk(root)
        return functions
    except Exception as e:
        return [f"ERROR: {e}"]


def main():
    # Python snippet
    python_code = '''
def hello():
    print("hello")

def add(a, b):
    return a + b

class Foo:
    def method(self):
        pass
'''

    # JavaScript snippet
    js_code = '''
function greet(name) {
    return "Hello " + name;
}

const add = (a, b) => a + b;

class Bar {
    method() {
        return 42;
    }
}
'''

    # Go snippet
    go_code = '''
package main

func Hello() {
    println("hello")
}

func Add(a, b int) int {
    return a + b
}

type Baz struct{}

func (b Baz) Method() int {
    return 1
}
'''

    print("=" * 60)
    print("Testing tree-sitter-language-pack")
    print("=" * 60)

    # Test Python
    print("\n[Python]")
    print(f"Code:\n{python_code}")
    py_funcs = test_parser("python", python_code, "function_definition")
    print(f"Top-level functions found: {py_funcs}")

    # Test JavaScript
    print("\n[JavaScript]")
    print(f"Code:\n{js_code}")
    js_funcs = test_parser("javascript", js_code, "function_declaration")
    print(f"Top-level functions found: {js_funcs}")

    # Test TypeScript (same grammar as JS)
    print("\n[TypeScript]")
    ts_funcs = test_parser("typescript", js_code, "function_declaration")
    print(f"Top-level functions found: {ts_funcs}")

    # Test Go
    print("\n[Go]")
    print(f"Code:\n{go_code}")
    go_funcs = test_parser("go", go_code, "function_declaration")
    print(f"Top-level functions found: {go_funcs}")

    print("\n" + "=" * 60)
    print("Version info:")
    import tree_sitter
    import tree_sitter_language_pack
    print(f"  tree-sitter: {tree_sitter.__version__}")
    print(f"  tree-sitter-language-pack: {tree_sitter_language_pack.__version__}")


if __name__ == "__main__":
    main()
