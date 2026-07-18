from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from megido_ocr_excel.diagnostics import (
    LOGGER_NAME,
    configure_logging,
    current_log_path,
    default_log_dir,
    shutdown_logging,
)


class DiagnosticLoggingTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_logging()

    def test_default_log_directory_uses_local_app_data(self) -> None:
        directory = default_log_dir(
            {"LOCALAPPDATA": r"C:\Users\player\AppData\Local"},
            Path(r"C:\Users\player"),
        )

        self.assertEqual(
            directory,
            Path(r"C:\Users\player\AppData\Local\MegidoOCR2Excel\logs"),
        )

    def test_logging_writes_utf8_and_reuses_one_managed_handler(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            first_path = configure_logging(directory)
            second_path = configure_logging(directory)
            logger = logging.getLogger(f"{LOGGER_NAME}.test")

            logger.info("日本語の診断メッセージ")
            for handler in logging.getLogger(LOGGER_NAME).handlers:
                handler.flush()

            self.assertEqual(first_path, second_path)
            self.assertEqual(current_log_path(), directory / "app.log")
            self.assertIn(
                "日本語の診断メッセージ",
                current_log_path().read_text(encoding="utf-8"),
            )
            managed = [
                handler
                for handler in logging.getLogger(LOGGER_NAME).handlers
                if getattr(handler, "_megido_ocr_managed", False)
            ]
            self.assertEqual(len(managed), 1)
            shutdown_logging()

    def test_log_file_rotates_with_bounded_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            configure_logging(directory, max_bytes=180, backup_count=2)
            logger = logging.getLogger(f"{LOGGER_NAME}.rotation")

            for index in range(30):
                logger.info("rotation-record-%02d-%s", index, "x" * 60)
            for handler in logging.getLogger(LOGGER_NAME).handlers:
                handler.flush()

            files = sorted(directory.glob("app.log*"))
            self.assertGreater(len(files), 1)
            self.assertLessEqual(len(files), 3)
            shutdown_logging()


if __name__ == "__main__":
    unittest.main()
