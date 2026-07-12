from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import customtkinter as ctk

from atomic_io import atomic_save_workbook, atomic_write_text
from megido_app_config import APP_PROFILE
from megido_ocr_excel_app import APP_TITLE, AutoHideScrollableFrame, ImageOcrExcelApp
from ocr_models import DIALOGUE_ROLE_SPEAKER, DIALOGUE_ROLE_TEXT, EXPORT_LAYOUT_DIALOGUE_PAIR, TemplateField


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


class AutoHideScrollableFrameTests(unittest.TestCase):
    def test_scrollbar_appears_only_when_content_overflows(self) -> None:
        frame = AutoHideScrollableFrame.__new__(AutoHideScrollableFrame)
        frame._orientation = "vertical"
        frame._scrollbar_visibility_job = "pending"
        frame._scrollbar_is_visible = True
        frame._parent_canvas = MagicMock()
        frame._parent_canvas.winfo_height.return_value = 120
        frame._scrollbar = MagicMock()

        frame._parent_canvas.bbox.return_value = (0, 0, 260, 36)
        frame._update_scrollbar_visibility()
        frame._scrollbar.grid_remove.assert_called_once()
        frame._scrollbar.grid.assert_not_called()

        frame._parent_canvas.bbox.return_value = (0, 0, 260, 324)
        frame._update_scrollbar_visibility()
        frame._scrollbar.grid.assert_called_once()


class WorkflowChoiceTests(unittest.TestCase):
    def _logic_only_app(self) -> ImageOcrExcelApp:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.profile = APP_PROFILE
        app._dirty_tracking_suspended = False
        app.workflow_started = False
        app.auto_detection_enabled = False
        app.auto_detection_base_fields = []
        app.fields = []
        app.selected_index = None
        app.export_layout_var = MagicMock()
        app.mode_var = MagicMock()
        app.open_image_folder = MagicMock(return_value=True)
        app._mark_clean = MagicMock()
        app._show_workflow_choice = MagicMock()
        app._render_side_body = MagicMock()
        return app

    def test_auto_detection_choice_creates_internal_conversation_fields(self) -> None:
        app = self._logic_only_app()

        app.start_auto_detection_workflow()

        self.assertTrue(app.workflow_started)
        self.assertTrue(app.auto_detection_enabled)
        self.assertEqual(len(app.fields), 2)
        self.assertEqual(app.fields[0].dialogue_role, DIALOGUE_ROLE_SPEAKER)
        self.assertEqual(app.fields[1].dialogue_role, DIALOGUE_ROLE_TEXT)
        self.assertEqual(app.fields[1].ocr_line_split, "detected")
        app.open_image_folder.assert_called_once()

    def test_new_template_choice_keeps_the_field_list_empty(self) -> None:
        app = self._logic_only_app()

        app.start_new_template_workflow()

        self.assertTrue(app.workflow_started)
        self.assertFalse(app.auto_detection_enabled)
        self.assertEqual(app.fields, [])
        app.open_image_folder.assert_called_once()


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


class FieldNameInteractionTests(unittest.TestCase):
    def _logic_only_app(self) -> ImageOcrExcelApp:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.fields = []
        app.current_results = []
        app.current_raw_results = []
        app.correction_rules = []
        app.editing_name_index = None
        app.editing_name_value = ""
        app.editing_name_error = ""
        app.editing_name_entry = None
        app.editing_name_error_label = None
        app.selected_index = None
        app.original_image = None
        app.profile = APP_PROFILE
        app.status_var = MagicMock()
        app.export_layout_var = MagicMock()
        app._mark_dirty = MagicMock()
        app._render_side_body = MagicMock()
        app.redraw = MagicMock()
        return app

    def test_inline_edit_rejects_duplicates_and_keeps_original_for_blank(self) -> None:
        app = self._logic_only_app()
        app.fields = [TemplateField("話者", 0, 0, 10, 10), TemplateField("本文", 0, 10, 10, 20)]
        app.current_results = ["", ""]
        app.current_raw_results = ["", ""]
        app.editing_name_index = 0

        app.commit_inline_name_edit(0, "本文")

        self.assertEqual(app.fields[0].name, "話者")
        self.assertEqual(app.editing_name_index, 0)
        self.assertIn("既に使用", app.editing_name_error)

        app.commit_inline_name_edit(0, "新しい話者")

        self.assertEqual(app.fields[0].name, "新しい話者")
        self.assertIsNone(app.editing_name_index)

        app.editing_name_index = 0
        app.commit_inline_name_edit(0, "   ")

        self.assertEqual(app.fields[0].name, "新しい話者")
        self.assertIsNone(app.editing_name_index)

    def test_field_selection_updates_the_recognition_detail_panel(self) -> None:
        app = self._logic_only_app()
        app.fields = [TemplateField("話者", 0, 0, 10, 10)]
        app._select_field_index = MagicMock()

        app.select_field(0)

        app._select_field_index.assert_called_once_with(
            0, update_review_detail=True
        )

    def test_supplement_candidate_can_be_approved_as_the_next_dialogue(self) -> None:
        app = self._logic_only_app()
        app.supplement_candidates_approved = False
        app.current_detection_reason = ""

        app.approve_supplement_candidate()

        self.assertTrue(app.supplement_candidates_approved)
        self.assertIn("次の会話", app.current_detection_reason)
        app._render_side_body.assert_called_once()

    def test_duplicate_is_undoable_and_clears_dialogue_assignment(self) -> None:
        app = self._logic_only_app()
        app.export_layout_var.get.return_value = EXPORT_LAYOUT_DIALOGUE_PAIR
        app.fields = [TemplateField("話者1", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER)]
        app.current_results = ["recognized"]
        app.current_raw_results = ["raw"]

        app.duplicate_field_at(0)

        self.assertEqual(len(app.fields), 2)
        self.assertEqual(app.fields[1].name, "話者1 のコピー")
        self.assertEqual(app.fields[1].pair_id, 0)
        self.assertEqual(app.fields[1].dialogue_role, "")
        self.assertEqual(app.current_results[1], "")
        self.assertEqual(app.undo_action["type"], "add")

    def test_drag_visual_highlights_row_and_handle(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        row = MagicMock()
        handle = MagicMock()
        app.selected_index = 0
        app.field_row_by_index = {0: row}
        app.field_drag_handle_by_index = {0: handle}

        app._set_field_drag_visual(0, True)

        self.assertEqual(row.configure.call_args.kwargs["fg_color"], "#302047")
        self.assertEqual(row.configure.call_args.kwargs["border_color"], "#b77af5")
        self.assertEqual(handle.configure.call_args.kwargs["fg_color"], "#8b49df")

        app._set_field_drag_visual(0, False)

        self.assertEqual(row.configure.call_args.kwargs["fg_color"], "#241936")
        self.assertEqual(handle.configure.call_args.kwargs["fg_color"], "transparent")

    def test_dialogue_role_text_enables_line_splitting(self) -> None:
        app = self._logic_only_app()
        app.fields = [TemplateField("本文", 0, 0, 10, 10, ocr_line_split="none")]
        app.current_results = ["recognized"]
        app.current_raw_results = ["raw"]

        app.set_field_dialogue_role(0, "セリフ")

        self.assertEqual(app.fields[0].dialogue_role, DIALOGUE_ROLE_TEXT)
        self.assertEqual(app.fields[0].ocr_line_split, "detected")
        self.assertEqual(app.current_results[0], "")
        self.assertEqual(app.current_raw_results[0], "")
        app._mark_dirty.assert_called_once()

    def test_unselected_dialogue_pair_draws_only_the_outer_outline(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.canvas = MagicMock()
        app.canvas.create_rectangle.side_effect = [10, 11]
        app.canvas.create_text.return_value = 12
        app.zoom = 1.0
        app.selected_index = None
        app.canvas_pair_handles = {}

        app._draw_pair_handle(1, (0, 1), {0: (10, 10, 30, 20), 1: (10, 22, 80, 50)})

        app.canvas.create_rectangle.assert_called_once()
        self.assertEqual(app.canvas_pair_handles[1]["outline"], 10)
        self.assertIsNone(app.canvas_pair_handles[1]["handle"])
        app.canvas.create_text.assert_not_called()

    def test_dragging_to_another_dialogue_pair_swaps_the_same_role(self) -> None:
        app = self._logic_only_app()
        app.fields = [
            TemplateField(
                "話者1", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER
            ),
            TemplateField(
                "話者2", 0, 10, 10, 20, pair_id=2, dialogue_role=DIALOGUE_ROLE_SPEAKER
            ),
        ]

        app.move_field_to_dialogue_pair(0, 2)

        self.assertEqual(app.fields[0].pair_id, 2)
        self.assertEqual(app.fields[1].pair_id, 1)
        app._mark_dirty.assert_called_once()
        self.assertIn("入れ替え", app.status_var.set.call_args.args[0])

    def test_dragging_to_unassigned_removes_the_pair_membership(self) -> None:
        app = self._logic_only_app()
        app.fields = [
            TemplateField(
                "セリフ1", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_TEXT
            )
        ]

        app.move_field_to_dialogue_pair(0, 0)

        self.assertEqual(app.fields[0].pair_id, 0)
        self.assertEqual(app.fields[0].dialogue_role, DIALOGUE_ROLE_TEXT)


if __name__ == "__main__":
    unittest.main()
