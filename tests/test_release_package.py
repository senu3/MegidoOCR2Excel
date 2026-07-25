from __future__ import annotations

import hashlib
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

from scripts.build_release import (
    OPTIONAL_PUBLIC_FILES,
    PUBLIC_FILES,
    USER_GUIDE_IMAGES,
    build_release,
    collect_release_files,
    project_version,
    update_project_version,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleasePackageTests(unittest.TestCase):
    def test_public_manifest_contains_only_runtime_and_user_files(self) -> None:
        files = collect_release_files(PROJECT_ROOT)
        self.assertTrue(set(PUBLIC_FILES).issubset(files))
        self.assertTrue(set(USER_GUIDE_IMAGES).issubset(files))
        self.assertIn(Path("megido_ocr_excel/application.py"), files)
        for relative_path in files:
            self.assertNotIn("tests", relative_path.parts)
            self.assertNotIn("scripts", relative_path.parts)
            self.assertNotIn(".venv", relative_path.parts)
            self.assertNotIn("zuban", relative_path.as_posix().lower())
            self.assertNotIn("__pycache__", relative_path.parts)
            self.assertNotIn(relative_path.suffix.lower(), {".pyc", ".pyo"})

    def test_zuban_is_declared_only_as_a_development_dependency(self) -> None:
        pyproject = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        runtime = pyproject["project"]["dependencies"]
        development = pyproject["dependency-groups"]["dev"]

        self.assertFalse(
            any(str(requirement).lower().startswith("zuban") for requirement in runtime)
        )
        self.assertIn("zuban==0.9.0", development)

    def test_release_build_is_deterministic_and_checksum_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp_root = Path(temp_name)
            first = build_release(PROJECT_ROOT, temp_root / "first")
            second = build_release(PROJECT_ROOT, temp_root / "second")

            self.assertEqual(first.version, project_version(PROJECT_ROOT))
            self.assertEqual(
                first.archive_path.read_bytes(), second.archive_path.read_bytes()
            )
            self.assertEqual(
                first.sha256,
                hashlib.sha256(first.archive_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                first.checksum_path.read_text(encoding="ascii"),
                f"{first.sha256}  {first.archive_path.name}\n",
            )

            root_name = first.archive_path.stem
            expected = {
                f"{root_name}/{path.as_posix()}" for path in first.files
            }
            with zipfile.ZipFile(first.archive_path) as archive:
                self.assertEqual(set(archive.namelist()), expected)

    def test_license_is_added_automatically_when_present(self) -> None:
        files = collect_release_files(PROJECT_ROOT)
        existing = {
            path for path in OPTIONAL_PUBLIC_FILES if (PROJECT_ROOT / path).is_file()
        }
        self.assertEqual(existing, existing.intersection(files))

    def test_version_update_changes_both_sources_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            package = root / "megido_ocr_excel"
            package.mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nname = "test"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            (package / "__init__.py").write_text(
                '__version__ = "0.1.0"\n', encoding="utf-8"
            )

            self.assertEqual(update_project_version(root, "0.2.0"), ("0.1.0", "0.2.0"))
            self.assertEqual(project_version(root), "0.2.0")
            self.assertIn(
                'version = "0.2.0"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertIn(
                '__version__ = "0.2.0"',
                (package / "__init__.py").read_text(encoding="utf-8"),
            )
            self.assertEqual(update_project_version(root, "0.2.0"), ("0.2.0", "0.2.0"))

    def test_version_update_rejects_invalid_and_older_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            package = root / "megido_ocr_excel"
            package.mkdir()
            pyproject = root / "pyproject.toml"
            package_init = package / "__init__.py"
            pyproject.write_text(
                '[project]\nname = "test"\nversion = "0.2.0"\n',
                encoding="utf-8",
            )
            package_init.write_text(
                '__version__ = "0.2.0"\n', encoding="utf-8"
            )
            original = (pyproject.read_bytes(), package_init.read_bytes())

            for value in ("0.1.9", "v0.3.0", "0.3"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    update_project_version(root, value)

            self.assertEqual(
                (pyproject.read_bytes(), package_init.read_bytes()), original
            )

    def test_failed_versioned_build_restores_version_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            package = root / "megido_ocr_excel"
            package.mkdir()
            pyproject = root / "pyproject.toml"
            package_init = package / "__init__.py"
            pyproject.write_text(
                '[project]\nname = "test"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            package_init.write_text(
                '__version__ = "0.1.0"\n', encoding="utf-8"
            )

            with self.assertRaises(FileNotFoundError):
                build_release(root, root / "dist", version="0.2.0")

            self.assertEqual(project_version(root), "0.1.0")


if __name__ == "__main__":
    unittest.main()
