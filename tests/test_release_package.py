from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_release import (
    OPTIONAL_PUBLIC_FILES,
    PUBLIC_FILES,
    build_release,
    collect_release_files,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleasePackageTests(unittest.TestCase):
    def test_public_manifest_contains_only_runtime_and_user_files(self) -> None:
        files = collect_release_files(PROJECT_ROOT)
        self.assertTrue(set(PUBLIC_FILES).issubset(files))
        self.assertIn(Path("megido_ocr_excel/application.py"), files)
        for relative_path in files:
            self.assertNotIn("tests", relative_path.parts)
            self.assertNotIn("scripts", relative_path.parts)
            self.assertNotIn("__pycache__", relative_path.parts)
            self.assertNotIn(relative_path.suffix.lower(), {".pyc", ".pyo"})

    def test_release_build_is_deterministic_and_checksum_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp_root = Path(temp_name)
            first = build_release(PROJECT_ROOT, temp_root / "first")
            second = build_release(PROJECT_ROOT, temp_root / "second")

            self.assertEqual(first.version, "0.1.0")
            self.assertEqual(first.archive_path.read_bytes(), second.archive_path.read_bytes())
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


if __name__ == "__main__":
    unittest.main()
