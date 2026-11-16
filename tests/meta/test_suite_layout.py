"""The test suite's own layout: every test folder is collected, and tests share helpers only through support modules.

A folder without `__init__.py` is skipped by `unittest discover` without a word; a test module that imports another
test module, or a test class that inherits another one's tests, runs those tests twice.
"""
import ast
import unittest
from pathlib import Path

from tests.support import REPO_ROOT

TESTS = REPO_ROOT / "tests"


def modules() -> dict[Path, ast.Module]:
    """Every Python file under `tests/`, parsed."""
    return {p: ast.parse(p.read_text(encoding="utf-8")) for p in sorted(TESTS.rglob("*.py"))
            if "__pycache__" not in p.parts}


def test_methods(node: ast.ClassDef) -> list[str]:
    """The names of the test methods a class defines itself."""
    return [m.name for m in node.body if isinstance(m, ast.FunctionDef) and m.name.startswith("test")]


def classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    """{name: class} for the classes a module defines at the top level."""
    return {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}


def imported_modules(tree: ast.Module) -> list[str]:
    """The absolute names of the modules a file imports."""
    found = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    return found + [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]


class SuiteLayoutTests(unittest.TestCase):
    def test_every_folder_with_tests_is_a_package(self):
        folders = {p.parent for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts}
        missing = [str(f.relative_to(REPO_ROOT)) for f in sorted(folders) if not (f / "__init__.py").is_file()]
        self.assertEqual(missing, [], "unittest discover skips a folder without __init__.py")

    def test_no_module_imports_a_test_module(self):
        for path, tree in modules().items():
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                bad = [m for m in imported_modules(tree) if m.startswith("tests.") and m.split(".")[-1].startswith("test_")]
                self.assertEqual(bad, [], "move shared helpers to a support module")

    def test_support_modules_hold_no_tests(self):
        for path, tree in modules().items():
            if path.name.startswith("test_"):
                continue
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                self.assertEqual({n: test_methods(c) for n, c in classes(tree).items() if test_methods(c)}, {})

    def test_no_test_class_inherits_another_ones_tests(self):
        for path, tree in modules().items():
            local = classes(tree)
            for name, node in local.items():
                bases = [b.id for b in node.bases if isinstance(b, ast.Name) and b.id in local]
                with self.subTest(path=path.name, cls=name):
                    self.assertEqual([b for b in bases if test_methods(local[b])], [],
                                     "inherit a base without tests, not a class with tests")
