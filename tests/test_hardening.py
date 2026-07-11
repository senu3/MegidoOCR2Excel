from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk

from atomic_io import atomic_save_workbook, atomic_write_text
from megido_ocr_excel_app import APP_TITLE, ImageOcrExcelApp
from ocr_models import TemplateField


class _FailingWorkbook:
    def save(self, filename: str | Path) -> None:
        Path(filename).write_bytes(b"partial workbook")
        raise OSError("simulated disk failure")


class _SuccessfulWorkbook:
    def save(self, filename: str | Path) -> None:
        Path(filename).write_bytes(b"complete workbook")


class AtomicSaveTests(unittest.TestCase):
    def test_failed_workbook_save_preserves_existing_file_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "result.xlsx"
            output.write_bytes(b"original workbook")

            with self.assertRaisesRegex(OSError, "simulated disk failure"):
                atomic_save_workbook(_FailingWorkbook(), output)

            self.assertEqual(output.read_bytes(), b"original workbook")
            self.assertEqual(list(root.glob(".result-*.xlsx")), [])

    def test_successful_workbook_save_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.xlsx"
            output.write_bytes(b"original workbook")

            atomic_save_workbook(_SuccessfulWorkbook(), output)

            self.assertEqual(output.read_bytes(), b"complete workbook")

    def test_failed_text_replace_preserves_existing_template_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "template.json"
            output.write_text("original", encoding="utf-8")

            with patch("atomic_io.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaisesRegex(PermissionError, "locked"):
                    atomic_write_text(output, "replacement")

            self.assertEqual(output.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(root.glob(".template-*.json")), [])


class DirtyStateTests(unittest.TestCase):
    def test_dirty_indicators_unsaved_cancel_and_busy_close_protection(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root)
        try:
            self.assertFalse(app.dirty)

            app.export_sheet_var.set("Changed")

            self.assertTrue(app.dirty)
            self.assertEqual(root.title(), f"{APP_TITLE} *")
            self.assertEqual(app.template_var.get(), "未保存 *")

            with patch("megido_ocr_excel_app.messagebox.askyesnocancel", return_value=None):
                allowed = app._confirm_unsaved_changes("終了する")

            self.assertFalse(allowed)
            self.assertTrue(app.dirty)

            app.busy = True
            with patch("megido_ocr_excel_app.messagebox.showwarning") as showwarning:
                app.request_close()

            showwarning.assert_called_once()
            self.assertTrue(root.winfo_exists())

            app._mark_clean()
            self.assertFalse(app.dirty)
            self.assertEqual(root.title(), APP_TITLE)
            self.assertEqual(app.template_var.get(), "未保存")

            app.fields = [TemplateField("話者", 0, 0, 10, 10)]
            app.set_field_enabled(0, False)
            self.assertTrue(app.dirty)

            with tempfile.TemporaryDirectory() as temp_dir:
                app.template_path = Path(temp_dir) / "existing.json"
                with (
                    patch("megido_ocr_excel_app.filedialog.asksaveasfilename") as save_dialog,
                    patch("megido_ocr_excel_app.save_template") as template_writer,
                ):
                    saved = app.save_template()

                self.assertTrue(saved)
                save_dialog.assert_not_called()
                template_writer.assert_called_once()
                self.assertFalse(app.dirty)

                app._mark_dirty()
                with (
                    patch("megido_ocr_excel_app.save_template", side_effect=PermissionError("locked")),
                    patch("megido_ocr_excel_app.messagebox.showerror") as showerror,
                ):
                    saved = app.save_template()

                self.assertFalse(saved)
                self.assertTrue(app.dirty)
                showerror.assert_called_once()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
