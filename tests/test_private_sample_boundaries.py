from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = PROJECT_ROOT / "tests"


class PrivateSampleBoundaryTests(unittest.TestCase):
    def test_private_sample_references_are_explicitly_marked(self) -> None:
        unmarked: list[str] = []
        for path in TEST_ROOT.glob("test_*.py"):
            if path.resolve() == Path(__file__).resolve():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                uses_samples = any(
                    isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    and ".samples" in child.value
                    for child in ast.walk(node)
                )
                if not uses_samples:
                    continue
                decorators = {
                    decorator.id
                    for decorator in node.decorator_list
                    if isinstance(decorator, ast.Name)
                }
                if "private_sample_test" not in decorators:
                    relative = path.relative_to(PROJECT_ROOT)
                    unmarked.append(f"{relative}:{node.lineno} {node.name}")

        self.assertEqual(unmarked, [], "未分類の非公開サンプル参照があります。")


if __name__ == "__main__":
    unittest.main()
