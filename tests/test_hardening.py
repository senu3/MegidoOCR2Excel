from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import customtkinter as ctk
from PIL import Image

from atomic_io import atomic_save_workbook, atomic_write_text
from megido_app_config import APP_PROFILE
from megido_ocr_excel_app import APP_TITLE, MODE_REVIEW, OCR_MODE_OPTIONS, AutoHideScrollableFrame, ImageOcrExcelApp
from ocr_models import DIALOGUE_ROLE_SPEAKER, DIALOGUE_ROLE_SUPPLEMENT, DIALOGUE_ROLE_TEXT, EXPORT_LAYOUT_DIALOGUE_PAIR, EXPORT_LAYOUT_IMAGE_ROW, LINE_JOIN_NEWLINE, SET_PRESET_HEADING_TEXT, SET_SLOT_HEADING, SET_SLOT_SPEAKER, SET_SLOT_TEXT, TemplateField, set_definition_for_preset


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

    def test_supplement_candidate_panel_renders_and_does_not_dirty_the_app(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root)
        try:
            app.original_image = Image.open(".samples/e.png").convert("RGB")
            app.fields = [
                TemplateField(
                    "話者",
                    60,
                    1260,
                    760,
                    1320,
                    pair_id=1,
                    dialogue_role=DIALOGUE_ROLE_SPEAKER,
                ),
                TemplateField(
                    "補足セリフ候補",
                    154,
                    1084,
                    870,
                    1208,
                    pair_id=1,
                    dialogue_role=DIALOGUE_ROLE_SUPPLEMENT,
                    ocr_line_split="detected",
                )
            ]
            app.current_results = ["話者結果", "候補結果"]
            app.current_raw_results = ["話者結果", "候補結果"]
            app.selected_index = 0
            app.mode_var.set(MODE_REVIEW)

            previous_body = app.side_body
            app._render_side_body()
            app.select_review_field(1)

            descendants = []
            pending = list(app.review_detail_host.winfo_children())
            while pending:
                widget = pending.pop()
                descendants.append(widget)
                pending.extend(widget.winfo_children())
            textboxes = [
                widget for widget in descendants if isinstance(widget, ctk.CTkTextbox)
            ]

            self.assertTrue(app.side_body.winfo_children())
            self.assertIsNot(app.side_body, previous_body)
            self.assertFalse(previous_body.winfo_exists())
            self.assertEqual(app.selected_index, 1)
            self.assertEqual(textboxes[0].get("1.0", "end-1c"), "候補結果")
            self.assertFalse(app.dirty)
            with patch.object(root, "destroy") as destroy:
                app.request_close()
            destroy.assert_called_once()
        finally:
            root.destroy()


class DirtyStateTests(unittest.TestCase):
    def test_dirty_indicators_unsaved_cancel_and_busy_close_cancellation(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root)
        try:
            self.assertFalse(app.dirty)

            settings_window = MagicMock()
            app.fields = [TemplateField("本文", 0, 0, 10, 10)]
            app.current_results = ["変更前"]
            app.current_raw_results = ["raw"]
            app._apply_settings(
                settings_window,
                app._lang_display(app.lang_var.get()),
                app.backend_var.get(),
                app.tesseract_var.get(),
                "改行",
                True,
            )

            self.assertEqual(app.text_formatting.line_join, LINE_JOIN_NEWLINE)
            self.assertTrue(app.text_formatting.fullwidth_ascii)
            self.assertEqual(app.current_results, [""])
            self.assertEqual(app.current_raw_results, [""])
            self.assertTrue(app.dirty)
            settings_window.destroy.assert_called_once()
            app._mark_clean()

            app.export_sheet_var.set("Changed")

            self.assertTrue(app.dirty)
            self.assertEqual(root.title(), f"{APP_TITLE} *")
            self.assertEqual(app.template_var.get(), "未保存 *")

            with patch("megido_ocr_excel_app.messagebox.askyesnocancel", return_value=None):
                allowed = app._confirm_unsaved_changes("終了する")

            self.assertFalse(allowed)
            self.assertTrue(app.dirty)

            app.busy = True
            app._operation_cancel_event = threading.Event()
            with patch(
                "megido_ocr_excel_app.messagebox.askyesno", return_value=False
            ) as ask_cancel:
                app.confirm_cancel_current_operation()

            ask_cancel.assert_called_once()
            self.assertFalse(app._operation_cancel_event.is_set())

            with patch(
                "megido_ocr_excel_app.messagebox.askyesno", return_value=True
            ):
                app.confirm_cancel_current_operation()

            self.assertTrue(app._operation_cancel_event.is_set())
            app._operation_cancel_event = threading.Event()
            with patch(
                "megido_ocr_excel_app.messagebox.askyesno", return_value=True
            ) as askyesno:
                app.request_close()

            askyesno.assert_called_once()
            self.assertTrue(app._operation_cancel_event.is_set())
            self.assertTrue(app._close_after_cancel)
            self.assertTrue(root.winfo_exists())
            app.busy = False
            app._operation_cancel_event = None
            app._close_after_cancel = False

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

    def test_supplement_candidate_can_open_range_editing(self) -> None:
        app = self._logic_only_app()
        app.fields = [
            TemplateField(
                "補足セリフ候補",
                0,
                0,
                10,
                10,
                dialogue_role=DIALOGUE_ROLE_SUPPLEMENT,
            )
        ]
        app.selected_index = 0
        app.mode_var = MagicMock()
        app._schedule_side_body_render = MagicMock()

        app.edit_selected_field_range()

        app.mode_var.set.assert_called_once_with("1. 範囲・列")
        app._schedule_side_body_render.assert_called_once()
        app.redraw.assert_called_once()

    def test_canvas_side_panel_render_is_deferred_and_coalesced(self) -> None:
        app = self._logic_only_app()
        app.root = MagicMock()
        app.root.after_idle.return_value = "render-job"
        app._side_render_job = None

        app._schedule_side_body_render()
        app._schedule_side_body_render()

        app.root.after_idle.assert_called_with(app._render_side_body)
        app.root.after_cancel.assert_called_once_with("render-job")

    def test_mode_change_does_not_redraw_the_unchanged_canvas(self) -> None:
        app = self._logic_only_app()
        app._schedule_side_body_render = MagicMock()

        app._on_mode_change()

        app._schedule_side_body_render.assert_called_once()
        app.redraw.assert_not_called()

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

    def test_supplement_role_enables_line_splitting(self) -> None:
        app = self._logic_only_app()
        app.fields = [TemplateField("補足", 0, 0, 10, 10, ocr_line_split="none")]
        app.current_results = ["recognized"]
        app.current_raw_results = ["raw"]

        app.set_field_dialogue_role(0, "補足セリフ")

        self.assertEqual(app.fields[0].dialogue_role, DIALOGUE_ROLE_SUPPLEMENT)
        self.assertEqual(app.fields[0].ocr_line_split, "detected")

    def test_field_rows_show_only_the_setting_used_by_the_output_layout(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root)
        try:
            field = TemplateField(
                "本文",
                0,
                0,
                10,
                10,
                pair_id=1,
                dialogue_role=DIALOGUE_ROLE_SPEAKER,
            )
            app.fields = [field]

            app.export_layout_var.set(EXPORT_LAYOUT_IMAGE_ROW)
            app._render_side_body()
            image_row_menus = [
                widget
                for widget in app.field_row_by_index[0].winfo_children()
                if isinstance(widget, ctk.CTkOptionMenu)
            ]

            self.assertEqual(len(image_row_menus), 1)
            self.assertEqual(image_row_menus[0].cget("values"), OCR_MODE_OPTIONS)
            root.update_idletasks()
            drag_handle = app.field_drag_handle_by_index[0]
            menu_right = image_row_menus[0].winfo_x() + image_row_menus[0].winfo_width()
            self.assertGreaterEqual(drag_handle.winfo_x() - menu_right, 8)

            app.export_layout_var.set(EXPORT_LAYOUT_DIALOGUE_PAIR)
            app._render_side_body()
            dialogue_row_menus = [
                widget
                for widget in app.field_row_by_index[0].winfo_children()
                if isinstance(widget, ctk.CTkOptionMenu)
            ]

            self.assertEqual(len(dialogue_row_menus), 1)
            self.assertEqual(
                dialogue_row_menus[0].cget("values"),
                ["未割当", "話者", "セリフ", "補足セリフ"],
            )
            self.assertEqual(field.dialogue_role, DIALOGUE_ROLE_SPEAKER)

            app.set_definition = set_definition_for_preset(SET_PRESET_HEADING_TEXT)
            app._render_side_body()
            heading_row_menus = [
                widget
                for widget in app.field_row_by_index[0].winfo_children()
                if isinstance(widget, ctk.CTkOptionMenu)
            ]
            self.assertEqual(
                heading_row_menus[0].cget("values"),
                ["未割当", "見出し", "本文"],
            )
        finally:
            root.destroy()

    def test_switching_to_set_layout_creates_set_one_and_assigns_existing_fields(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root)
        try:
            app.fields = [
                TemplateField("話者", 0, 0, 10, 10),
                TemplateField("セリフ本文", 0, 10, 10, 20),
            ]
            app.current_results = ["old", "old"]
            app.current_raw_results = ["raw", "raw"]

            app.export_layout_var.set(EXPORT_LAYOUT_DIALOGUE_PAIR)
            app._set_export_layout(EXPORT_LAYOUT_DIALOGUE_PAIR)

            self.assertEqual([field.set_id for field in app.fields], [1, 1])
            self.assertEqual(
                [field.slot_key for field in app.fields],
                [SET_SLOT_SPEAKER, SET_SLOT_TEXT],
            )
            self.assertEqual(app._dialogue_pair_ids(), [1])
            self.assertIsNone(app.pending_dialogue_pair_id)
            self.assertEqual(app.current_results, ["", ""])
            root.update_idletasks()
        finally:
            root.destroy()

    def test_switching_auto_detection_to_image_rows_fixes_the_current_coordinate_source(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.export_layout_var = MagicMock()
        app.export_layout_var.get.return_value = EXPORT_LAYOUT_DIALOGUE_PAIR
        app.original_image = Image.open(".samples/1.png").convert("RGB")
        app.coordinate_settings = APP_PROFILE.coordinate_settings()
        app.current_content_rect = None
        app.fields = [TemplateField("話者", 55, 1523, 697, 1620)]
        app.auto_detection_enabled = True
        app.auto_detection_base_fields = [replace(app.fields[0])]
        app.pending_dialogue_pair_id = None
        app.pending_dialogue_role = ""
        app.empty_set_ids = set()
        app.status_var = MagicMock()
        app._mark_dirty = MagicMock()
        app._schedule_side_body_render = MagicMock()
        app.redraw = MagicMock()
        app._refresh_content_mapping()

        with patch.object(
            app, "_confirm_fixed_range_switch", return_value=True
        ) as confirm:
            app._set_export_layout(EXPORT_LAYOUT_IMAGE_ROW)

        confirm.assert_called_once_with()
        self.assertFalse(app.auto_detection_enabled)
        self.assertEqual(app.auto_detection_base_fields, [])
        self.assertEqual(
            (app.fields[0].source_width, app.fields[0].source_height),
            app.original_image.size,
        )
        self.assertEqual(
            app.coordinate_settings.source_content_rect,
            app.current_content_rect,
        )
        app.original_image = Image.open(".samples/9.png").convert("RGB")
        app._refresh_content_mapping()
        mapped = app._scaled_field(app.fields[0])
        self.assertEqual((mapped.y1, mapped.y2), (1610, 1706))
        self.assertIn("固定範囲", app.status_var.set.call_args.args[0])

    def test_cancelling_fixed_range_switch_keeps_auto_detection_and_menu_value(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.export_layout_var = MagicMock()
        app.export_layout_var.get.return_value = EXPORT_LAYOUT_DIALOGUE_PAIR
        app.auto_detection_enabled = True
        app.status_var = MagicMock()
        app._schedule_side_body_render = MagicMock()
        app.redraw = MagicMock()
        menu = MagicMock()

        with patch.object(
            app, "_confirm_fixed_range_switch", return_value=False
        ):
            app._set_export_layout(EXPORT_LAYOUT_IMAGE_ROW, menu)

        app.export_layout_var.set.assert_not_called()
        self.assertTrue(app.auto_detection_enabled)
        menu.set.assert_called_once_with(EXPORT_LAYOUT_DIALOGUE_PAIR)
        app._schedule_side_body_render.assert_not_called()
        app.redraw.assert_not_called()
        self.assertEqual(
            app.status_var.set.call_args.args[0], "自動検出を継続します。"
        )

    def test_empty_set_one_remains_available_and_preset_change_reassigns_fields(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root)
        try:
            app.export_layout_var.set(EXPORT_LAYOUT_DIALOGUE_PAIR)
            app._set_export_layout(EXPORT_LAYOUT_DIALOGUE_PAIR)
            self.assertEqual(app._dialogue_pair_ids(), [1])
            self.assertEqual(app.pending_dialogue_pair_id, 1)
            self.assertEqual(app.pending_dialogue_role, SET_SLOT_SPEAKER)

            app.cancel_dialogue_pair_creation()
            app.begin_dialogue_pair_creation()
            self.assertEqual(app.pending_dialogue_pair_id, 1)

            app.fields = [
                TemplateField("見出し", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER),
                TemplateField("本文", 0, 10, 10, 20, set_id=1, slot_key=SET_SLOT_TEXT),
            ]
            with patch("megido_ocr_excel_app.messagebox.askyesno", return_value=True):
                app._set_set_preset("見出し＋本文")

            self.assertEqual([field.set_id for field in app.fields], [1, 1])
            self.assertEqual(
                [field.slot_key for field in app.fields],
                [SET_SLOT_HEADING, SET_SLOT_TEXT],
            )
            root.update_idletasks()
        finally:
            root.destroy()

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
