from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import customtkinter as ctk
from PIL import Image

from megido_ocr_excel import __version__
from tests.private_samples import private_sample_test
from megido_ocr_excel.persistence import atomic_save_workbook, atomic_write_text
from megido_ocr_excel.apps.megido import CONFIG as APP_CONFIG
from megido_ocr_excel.apps.megido import PROFILE as APP_PROFILE
from megido_ocr_excel.application import (
    EXPORT_LAYOUT_DISPLAY,
    MODE_EXPORT,
    MODE_REVIEW,
    MODE_TEMPLATE,
    OCR_MODE_OPTIONS,
    AutoHideScrollableFrame,
    ImageOcrExcelApp,
)
from megido_ocr_excel.application import COLOR_PRIMARY, COLOR_SECONDARY
from megido_ocr_excel.ui.theme import THEME
from megido_ocr_excel.ocr.environment import (
    OCR_ENV_LOCATION_ERROR,
    OCR_ENV_READY,
    OCR_ENV_SETUP,
    OCR_ENV_UNAVAILABLE,
    OCR_ENV_VERIFY,
    OcrEnvironmentStatus,
)
from megido_ocr_excel.operations import OperationCancelled
from megido_ocr_excel.models import (
    EXPORT_LAYOUT_IMAGE_ROW,
    EXPORT_LAYOUT_OPTIONS,
    EXPORT_LAYOUT_SET,
    LINE_JOIN_NEWLINE,
    TemplateField,
)
from megido_ocr_excel.set_definitions import (
    HEADING_TEXT_SET_DEFINITION,
    SET_SLOT_HEADING,
    SET_SLOT_SPEAKER,
    SET_SLOT_SUPPLEMENT,
    SET_SLOT_TEXT,
)
from tests.tk_test_utils import destroy_tk_root


def descendants_of(widget):
    descendants = []
    pending = [widget]
    while pending:
        current = pending.pop()
        descendants.append(current)
        pending.extend(current.winfo_children())
    return descendants


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

            with patch("megido_ocr_excel.persistence.os.replace", side_effect=PermissionError("locked")):
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


class CoordinateStatusTests(unittest.TestCase):
    def _logic_only_app(self) -> ImageOcrExcelApp:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = MODE_REVIEW
        app.original_image = object()
        app.coordinate_settings = APP_PROFILE.coordinate_settings()
        app.current_content_rect = (0, 0, 100, 100)
        app.coordinate_status_var = MagicMock()
        app.coordinate_status_label = MagicMock()
        return app

    def test_content_correction_is_shown_in_review_status_bar(self) -> None:
        app = self._logic_only_app()

        app._update_coordinate_status_display()

        app.coordinate_status_var.set.assert_called_once_with("補正: 黒余白基準")
        app.coordinate_status_label.configure.assert_called_once_with(
            text_color=THEME.palette.toolbar_muted
        )
        app.coordinate_status_label.grid.assert_called_once_with()

    def test_detection_fallback_uses_neutral_status(self) -> None:
        app = self._logic_only_app()
        app.current_content_rect = None

        app._update_coordinate_status_display()

        app.coordinate_status_var.set.assert_called_once_with(
            "補正: 画像全体（黒余白未検出）"
        )
        app.coordinate_status_label.configure.assert_called_once_with(
            text_color=THEME.palette.toolbar_muted
        )

    def test_coordinate_status_is_hidden_outside_review(self) -> None:
        app = self._logic_only_app()
        app.mode_var.get.return_value = MODE_EXPORT

        app._update_coordinate_status_display()

        app.coordinate_status_var.set.assert_called_once_with("")
        app.coordinate_status_label.grid_remove.assert_called_once_with()


class StatusToneTests(unittest.TestCase):
    def test_warning_status_resets_when_the_message_changes(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.status_var = MagicMock()
        app.status_label = MagicMock()

        app._set_warning_status("会話を自動検出できませんでした。")

        app.status_var.set.assert_called_once_with(
            "会話を自動検出できませんでした。"
        )
        app.status_label.configure.assert_called_once_with(
            text_color=THEME.palette.warning
        )

        app._reset_status_text_color()

        app.status_label.configure.assert_called_with(
            text_color=THEME.palette.toolbar_text
        )


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
        app._hide_workflow_choice = MagicMock()
        app._render_side_body = MagicMock()
        app.status_var = MagicMock()
        return app

    def test_auto_detection_choice_creates_internal_conversation_fields(self) -> None:
        app = self._logic_only_app()

        app.start_auto_detection_workflow()

        self.assertTrue(app.workflow_started)
        self.assertTrue(app.auto_detection_enabled)
        self.assertEqual(len(app.fields), 2)
        self.assertEqual(app.fields[0].slot_key, SET_SLOT_SPEAKER)
        self.assertEqual(app.fields[1].slot_key, SET_SLOT_TEXT)
        self.assertEqual(app.fields[1].ocr_line_split, "detected")
        app._hide_workflow_choice.assert_called_once()
        app.open_image_folder.assert_called_once()

    def test_new_template_choice_keeps_the_field_list_empty(self) -> None:
        app = self._logic_only_app()

        app.start_new_template_workflow()

        self.assertTrue(app.workflow_started)
        self.assertFalse(app.auto_detection_enabled)
        self.assertEqual(app.fields, [])
        app._hide_workflow_choice.assert_called_once()
        app.open_image_folder.assert_called_once()

    def test_closing_workflow_choice_keeps_images_and_choices_unselected(self) -> None:
        app = self._logic_only_app()

        app.continue_without_workflow_choice()

        self.assertTrue(app.workflow_started)
        self.assertFalse(app.auto_detection_enabled)
        self.assertEqual(app.fields, [])
        app._hide_workflow_choice.assert_called_once_with()
        app.open_image_folder.assert_not_called()
        app.status_var.set.assert_called_once_with(
            "画像フォルダは選択されていません。"
            "上部の「画像フォルダを選択」から開始できます。"
        )

    def test_workflow_choice_uses_a_translucent_modal_layer(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            if app.ocr_setup_modal is not None and app.ocr_setup_modal.visible:
                app.defer_ocr_setup()
            modal = app.workflow_choice_modal
            self.assertIsNotNone(modal)
            self.assertIs(modal.backdrop.master, root)
            self.assertIs(
                app.workflow_choice_overlay, modal.panel
            )
            self.assertAlmostEqual(modal.backdrop_alpha, 0.66)
            self.assertTrue(modal.visible)
            labels = []
            buttons = []
            pending = list(app.workflow_choice_overlay.winfo_children())
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if isinstance(widget, ctk.CTkLabel):
                    labels.append(widget.cget("text"))
                elif isinstance(widget, ctk.CTkButton):
                    buttons.append(widget.cget("text"))
            self.assertIn("開始方法を選択", labels)
            self.assertCountEqual(
                buttons,
                ["会話を自動検出", "新規テンプレートを作成", ""],
            )
            self.assertIs(
                modal._default_action,
                app.workflow_choice_primary_button,
            )

            app._hide_workflow_choice()
            self.assertFalse(modal.visible)
            self.assertEqual(modal.backdrop.state(), "withdrawn")
            self.assertEqual(modal.window.state(), "withdrawn")

            app._show_workflow_choice()
            self.assertTrue(modal.visible)
        finally:
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_workflow_choice_escape_and_close_continue_without_selection(self) -> None:
        root = ctk.CTk()
        root.geometry("900x700+10000+10000")
        with patch.object(
            ImageOcrExcelApp, "continue_without_workflow_choice"
        ) as continue_without_selection:
            app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            if app.ocr_setup_modal is not None and app.ocr_setup_modal.visible:
                app.defer_ocr_setup()
            root.update()

            app.workflow_choice_modal.window.event_generate(
                "<Escape>", when="now"
            )
            root.update()

            continue_without_selection.assert_called_once_with()

            close_button = next(
                widget
                for widget in descendants_of(app.workflow_choice_modal.panel)
                if isinstance(widget, ctk.CTkButton)
                and widget.cget("text") == ""
            )
            close_button.invoke()

            self.assertEqual(continue_without_selection.call_count, 2)
        finally:
            if app.ocr_setup_modal is not None:
                app.ocr_setup_modal.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_empty_field_state_points_to_the_template_overflow_menu(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            labels = []
            pending = list(app.side_body.winfo_children())
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if isinstance(widget, ctk.CTkLabel):
                    labels.append(widget.cget("text"))

            self.assertIn("項目がありません", labels)
            self.assertIn("画像上で範囲をドラッグ", labels)
            self.assertIn(
                "保存済みテンプレートは右上のメニューから読み込めます。",
                labels,
            )
        finally:
            if app.ocr_setup_modal is not None:
                app.ocr_setup_modal.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_shortcuts_are_blocked_until_workflow_is_selected(self) -> None:
        app = self._logic_only_app()
        command = MagicMock(return_value="handled")
        event = object()

        self.assertEqual(app._dispatch_shortcut(command, event), "break")
        command.assert_not_called()
        app._show_workflow_choice.assert_called_once()

        app.workflow_started = True
        self.assertEqual(app._dispatch_shortcut(command, event), "handled")
        command.assert_called_once_with(event)

    def test_shortcuts_are_blocked_while_an_operation_is_running(self) -> None:
        app = self._logic_only_app()
        app.workflow_started = True
        app.busy = True
        command = MagicMock(return_value="handled")

        self.assertEqual(app._dispatch_shortcut(command, object()), "break")
        command.assert_not_called()

    @private_sample_test
    def test_supplement_candidate_panel_renders_and_does_not_dirty_the_app(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.original_image = Image.open(".samples/e.png").convert("RGB")
            app.fields = [
                TemplateField(
                    "話者",
                    60,
                    1260,
                    760,
                    1320,
                    set_id=1,
                    slot_key=SET_SLOT_SPEAKER,
                ),
                TemplateField(
                    "補足セリフ候補",
                    154,
                    1084,
                    870,
                    1208,
                    set_id=1,
                    slot_key=SET_SLOT_SUPPLEMENT,
                    ocr_line_split="detected",
                )
            ]
            app.current_results = ["話者結果", "候補結果"]
            app.current_raw_results = ["話者結果", "候補結果"]
            app.selected_index = 0
            app.mode_var.set(MODE_REVIEW)

            previous_body = app.side_body
            app._render_side_body()
            first_row = app.field_row_by_index[0]
            scroller = app.review_result_scroller
            with (
                patch.object(app, "_review_scroll_fraction", return_value=0.35),
                patch.object(app, "_restore_review_scroll") as restore_scroll,
            ):
                app.select_review_field(1)
                root.update_idletasks()

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
            self.assertIs(app.field_row_by_index[0], first_row)
            self.assertIs(app.review_result_scroller, scroller)
            restore_scroll.assert_called_once_with(0.35)
            self.assertEqual(textboxes[0].get("1.0", "end-1c"), "候補結果")
            self.assertFalse(app.dirty)
            with patch.object(root, "destroy") as destroy:
                app.request_close()
            destroy.assert_called_once()
        finally:
            destroy_tk_root(root)

    @private_sample_test
    def test_recognition_test_hides_raw_ocr(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app._hide_workflow_choice()
            app.original_image = Image.open(".samples/1.png").convert("RGB")
            app.fields = [
                TemplateField(
                    "セリフ本文",
                    40,
                    1600,
                    1040,
                    1880,
                    ocr_line_split="detected",
                )
            ]
            app.current_results = ["一行目　二行目"]
            app.current_raw_results = ["一行目\n二行目"]
            app.selected_index = 0
            app.mode_var.set(MODE_REVIEW)
            app._render_side_body()

            descendants = descendants_of(app.side_body)
            labels = [
                widget.cget("text")
                for widget in descendants
                if isinstance(widget, ctk.CTkLabel)
            ]
            textboxes = [
                widget for widget in descendants if isinstance(widget, ctk.CTkTextbox)
            ]

            self.assertNotIn("生OCR", labels)
            self.assertEqual(len(textboxes), 1)
            self.assertEqual(
                textboxes[0].get("1.0", "end-1c"), "一行目　二行目"
            )
        finally:
            destroy_tk_root(root)

    @private_sample_test
    def test_recognition_test_uses_concise_copy_and_actions(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app._hide_workflow_choice()
            app.original_image = Image.open(".samples/1.png").convert("RGB")
            app.fields = [TemplateField("話者", 40, 1500, 800, 1600)]
            app.current_results = [""]
            app.current_raw_results = [""]
            app.selected_index = 0
            app.mode_var.set(MODE_REVIEW)
            app._render_side_body()

            descendants = descendants_of(app.side_body)
            labels = [
                widget.cget("text")
                for widget in descendants
                if isinstance(widget, ctk.CTkLabel)
            ]
            buttons = [
                widget
                for widget in descendants
                if isinstance(widget, ctk.CTkButton)
            ]
            row_labels = [
                widget.cget("text")
                for widget in app.field_row_by_index[0].winfo_children()
                if isinstance(widget, ctk.CTkLabel)
            ]

            self.assertIn(THEME.copy.recognition_test_note, labels)
            self.assertIn("テキスト整形：全角空白・全角化", labels)
            self.assertEqual(row_labels, ["#1", "話者", "未テスト"])
            app.current_results[0] = "話者の結果"
            app._refresh_recognition_results()
            self.assertEqual(app.review_textbox.get("1.0", "end-1c"), "話者の結果")
            self.assertEqual(app.review_value_labels[0].cget("text"), "話者の結果")
            app.current_results[0] = ""
            app.editor.entries[0].tested = True
            app._refresh_recognition_results()
            self.assertEqual(app.review_textbox.get("1.0", "end-1c"), "文字なし")
            self.assertIn("全項目をテスト", [button.cget("text") for button in buttons])
            self.assertIn(
                "選択項目をテスト", [button.cget("text") for button in buttons]
            )
            batch_button = next(
                button for button in buttons if button.cget("text") == "全項目をテスト"
            )
            self.assertEqual(batch_button.cget("height"), THEME.layout.entry_height)
        finally:
            destroy_tk_root(root)


class OcrSetupOnboardingTests(unittest.TestCase):
    @staticmethod
    def _status(state: str, *, ready: bool) -> OcrEnvironmentStatus:
        labels = {
            OCR_ENV_READY: ("準備完了", "必要な認識モデルを確認しました。"),
            OCR_ENV_SETUP: (
                "認識モデルが必要",
                "通信環境により時間がかかる場合があります。",
            ),
            OCR_ENV_VERIFY: (
                "確認が必要",
                "既存の認識モデルはまだこのアプリで確認されていません。",
            ),
            OCR_ENV_LOCATION_ERROR: (
                "保存先を確認",
                "指定した保存先にアクセスできません。",
            ),
            OCR_ENV_UNAVAILABLE: (
                "ランチャーで修復が必要",
                "PaddleOCRの実行環境が不足しています。",
            ),
        }
        label, detail = labels[state]
        status = OcrEnvironmentStatus(
            state,
            label,
            detail,
            Path("C:/models"),
            "auto",
        )
        self_ready = status.ready
        if self_ready != ready:
            raise AssertionError("test status readiness mismatch")
        return status

    def _app_with_status(
        self, root: ctk.CTk, status: OcrEnvironmentStatus
    ) -> tuple[ImageOcrExcelApp, MagicMock]:
        with patch(
            "megido_ocr_excel.application.OcrEnvironmentManager"
        ) as manager_type:
            manager = manager_type.return_value
            manager.apply_to_process.return_value = status.cache_dir
            manager.quick_status.return_value = status
            app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        return app, manager

    @staticmethod
    def _destroy(app: ImageOcrExcelApp, root: ctk.CTk) -> None:
        if app.ocr_setup_modal is not None:
            app.ocr_setup_modal.destroy()
        if app.workflow_choice_modal is not None:
            app.workflow_choice_modal.destroy()
        destroy_tk_root(root)

    def test_unprepared_startup_precedes_workflow_and_can_be_deferred(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        status = self._status(OCR_ENV_SETUP, ready=False)
        app, _manager = self._app_with_status(root, status)
        try:
            self.assertTrue(app.ocr_setup_modal.visible)
            self.assertFalse(app.workflow_choice_modal.visible)
            labels = [
                widget.cget("text")
                for widget in descendants_of(app.ocr_setup_modal.panel)
                if isinstance(widget, ctk.CTkLabel)
            ]
            buttons = [
                widget.cget("text")
                for widget in descendants_of(app.ocr_setup_modal.panel)
                if isinstance(widget, ctk.CTkButton)
            ]
            self.assertIn("OCR認識モデルをダウンロード", labels)
            self.assertIn("認識モデルが必要", labels)
            self.assertTrue(
                any("実行環境と認識モデルが必要" in text for text in labels)
            )
            self.assertFalse(any("初回のみ" in text for text in labels))
            self.assertIn("ダウンロードして準備", buttons)
            self.assertIn("今は準備せず、範囲編集へ", buttons)
            self.assertIn("モデル保存先を変更", buttons)

            command = MagicMock()
            self.assertEqual(app._dispatch_shortcut(command, object()), "break")
            command.assert_not_called()
            self.assertFalse(app.workflow_choice_modal.visible)

            app.defer_ocr_setup()

            self.assertFalse(app.ocr_setup_modal.visible)
            self.assertTrue(app.workflow_choice_modal.visible)
            self.assertTrue(app.ocr_readiness_banner.winfo_manager())
            self.assertEqual(app.ocr_readiness_button.cget("text"), "準備")
        finally:
            self._destroy(app, root)

    def test_app_close_from_ocr_setup_keeps_unsaved_confirmation(self) -> None:
        root = ctk.CTk()
        root.geometry("900x700+10000+10000")
        status = self._status(OCR_ENV_SETUP, ready=False)
        app, _manager = self._app_with_status(root, status)
        try:
            root.update()
            self.assertTrue(app.ocr_setup_modal.visible)
            if sys.platform.startswith("win"):
                self.assertIsNone(root.grab_current())

            app._mark_dirty()
            with patch.object(
                app.dialogs, "askyesnocancel", return_value=None
            ) as ask_unsaved:
                root.tk.eval(root.protocol("WM_DELETE_WINDOW"))

            ask_unsaved.assert_called_once()
            self.assertTrue(root.winfo_exists())
            self.assertTrue(app.ocr_setup_modal.visible)
        finally:
            self._destroy(app, root)

    def test_ready_startup_shows_workflow_directly(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        status = self._status(OCR_ENV_READY, ready=True)
        app, _manager = self._app_with_status(root, status)
        try:
            self.assertFalse(app.ocr_setup_modal.visible)
            self.assertTrue(app.workflow_choice_modal.visible)
            self.assertFalse(app.ocr_readiness_banner.winfo_manager())
        finally:
            self._destroy(app, root)

    def test_ready_setup_overlay_only_offers_continue(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        ready = self._status(OCR_ENV_READY, ready=True)
        app, _manager = self._app_with_status(root, ready)
        try:
            app.show_ocr_setup()

            self.assertEqual(app.ocr_setup_primary_button.cget("text"), "続ける")
            self.assertEqual(app.ocr_setup_secondary_button.winfo_manager(), "")
            self.assertEqual(app.ocr_setup_settings_button.winfo_manager(), "")
            self.assertEqual(
                app.ocr_setup_modal._focus_order,
                (app.ocr_setup_primary_button,),
            )

            app.ocr_setup_modal._on_escape(None)

            self.assertFalse(app.ocr_setup_modal.visible)
            self.assertTrue(app.workflow_choice_modal.visible)
            self.assertNotIn("未準備", app.status_var.get())
        finally:
            self._destroy(app, root)

    def test_location_error_does_not_repeat_settings_action(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        location_error = self._status(OCR_ENV_LOCATION_ERROR, ready=False)
        app, _manager = self._app_with_status(root, location_error)
        try:
            self.assertEqual(
                app.ocr_setup_primary_button.cget("text"),
                "保存先を確認",
            )
            self.assertEqual(app.ocr_setup_settings_button.winfo_manager(), "")
            self.assertNotIn(
                app.ocr_setup_settings_button,
                app.ocr_setup_modal._focus_order,
            )
        finally:
            self._destroy(app, root)

    def test_unverified_models_wait_for_explicit_confirmation(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        verify = self._status(OCR_ENV_VERIFY, ready=False)
        app, manager = self._app_with_status(root, verify)
        try:
            self.assertTrue(app.ocr_setup_modal.visible)
            self.assertEqual(
                app.ocr_setup_primary_button.cget("text"), "確認して更新"
            )
            self.assertEqual(
                app.ocr_setup_primary_button.cget("state"), "normal"
            )
            self.assertEqual(app.ocr_setup_primary_button.winfo_manager(), "grid")
            self.assertEqual(
                app.ocr_setup_title_label.cget("text"),
                "OCR認識モデルを確認",
            )
            self.assertEqual(app.ocr_readiness_button.cget("text"), "確認")
            manager.verify.assert_not_called()
        finally:
            self._destroy(app, root)

    def test_deferred_setup_keeps_persistent_unprepared_indicator(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        verify = self._status(OCR_ENV_VERIFY, ready=False)
        app, _manager = self._app_with_status(root, verify)
        try:
            app.defer_ocr_setup()
            self.assertFalse(app.ocr_setup_modal.visible)
            self.assertTrue(app.workflow_choice_modal.visible)
            self.assertTrue(app.ocr_readiness_banner.winfo_manager())
            self.assertIn("確認が必要", app.ocr_readiness_label.cget("text"))
        finally:
            self._destroy(app, root)

    def test_gated_action_resumes_after_success(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        setup = self._status(OCR_ENV_SETUP, ready=False)
        ready = self._status(OCR_ENV_READY, ready=True)
        app, manager = self._app_with_status(root, setup)
        action = MagicMock()
        try:
            self.assertFalse(app._require_ocr_ready(action))
            self.assertTrue(app.ocr_setup_modal.visible)
            self.assertEqual(
                app.ocr_setup_secondary_button.cget("text"),
                "今回は認識せず戻る",
            )
            manager.quick_status.return_value = ready

            app._finish_ocr_setup_success()
            root.update()

            action.assert_called_once_with()
            self.assertIsNone(app._pending_ocr_action)
        finally:
            self._destroy(app, root)

    def test_explicit_prepare_uses_child_process_before_recording_ready(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        setup = self._status(OCR_ENV_SETUP, ready=False)
        ready = self._status(OCR_ENV_READY, ready=True)
        app, manager = self._app_with_status(root, setup)
        manager.cache_dir = setup.cache_dir
        manager.record_verified.return_value = ready
        app.ocr_setup_runner.run = MagicMock()
        try:
            with patch("megido_ocr_excel.application.threading.Thread") as thread_type:
                app.prepare_ocr_environment()
                self.assertTrue(app.ocr_setup_modal.visible)
                self.assertFalse(app.loading_modal.visible)
                self.assertTrue(app.busy)
                self.assertEqual(
                    app.ocr_setup_title_label.cget("text"),
                    "OCR認識モデルを準備しています",
                )
                self.assertEqual(
                    app.ocr_setup_status_label.cget("text"), "準備中"
                )
                self.assertEqual(
                    app.ocr_setup_secondary_button.cget("text"),
                    "準備をキャンセル",
                )
                self.assertEqual(
                    app.ocr_setup_secondary_button.cget("fg_color"),
                    "transparent",
                )
                self.assertEqual(
                    app.ocr_setup_secondary_button.cget("border_width"), 0
                )
                self.assertEqual(
                    app.ocr_setup_primary_button.winfo_manager(), ""
                )
                self.assertEqual(
                    app.ocr_setup_progress.winfo_manager(), "grid"
                )
                worker = thread_type.call_args.kwargs["target"]
                worker()
            manager.quick_status.return_value = ready
            root.after(80, root.quit)
            root.mainloop()

            app.ocr_setup_runner.run.assert_called_once()
            manager.record_verified.assert_called_once_with()
            self.assertEqual(app.status_var.get(), "OCRの準備が完了しました。")
            self.assertTrue(app.ocr_setup_modal.visible)
            self.assertEqual(
                app.ocr_setup_title_label.cget("text"),
                "OCRの準備が完了しました",
            )
            self.assertEqual(
                app.ocr_setup_primary_button.cget("text"), "続ける"
            )
            self.assertEqual(
                app.ocr_setup_secondary_button.winfo_manager(), ""
            )
        finally:
            self._destroy(app, root)

    def test_escape_from_gated_ocr_setup_discards_action(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        setup = self._status(OCR_ENV_SETUP, ready=False)
        app, _manager = self._app_with_status(root, setup)
        action = MagicMock()
        app.workflow_started = True
        try:
            self.assertFalse(app._require_ocr_ready(action))

            self.assertEqual(app.ocr_setup_modal._on_escape(None), "break")
            root.update()

            action.assert_not_called()
            self.assertIsNone(app._pending_ocr_action)
            self.assertFalse(app.ocr_setup_modal.visible)
            self.assertIn("範囲編集", app.status_var.get())
        finally:
            self._destroy(app, root)

    def test_unavailable_runtime_hands_repair_to_launcher_then_closes(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        unavailable = self._status(OCR_ENV_UNAVAILABLE, ready=False)
        app, _manager = self._app_with_status(root, unavailable)
        try:
            self.assertEqual(
                app.ocr_setup_primary_button.cget("text"),
                "ランチャーで修復",
            )
            self.assertIn(
                "選ぶとアプリを終了",
                app.ocr_setup_subtitle_label.cget("text"),
            )
            self.assertEqual(app.ocr_readiness_button.cget("text"), "修復")
            self.assertEqual(app.ocr_setup_settings_button.winfo_manager(), "")
            with (
                patch.object(app.dialogs, "askyesno", return_value=True),
                patch.object(app, "_confirm_unsaved_changes", return_value=True),
                patch(
                    "megido_ocr_excel.application.launch_repair_handoff"
                ) as launch_repair,
                patch.object(root, "destroy") as destroy,
            ):
                app.repair_ocr_runtime()

            launch_repair.assert_called_once()
            destroy.assert_called_once_with()
        finally:
            self._destroy(app, root)

    def test_failed_model_check_uses_retry_copy(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        verify = self._status(OCR_ENV_VERIFY, ready=False)
        app, _manager = self._app_with_status(root, verify)
        try:
            app.ocr_environment_last_error = (
                "準備に失敗しました: 認識モデルを読み込めませんでした。"
            )
            app._refresh_ocr_setup_overlay()

            self.assertEqual(
                app.ocr_setup_title_label.cget("text"),
                "OCR認識モデルを準備できませんでした",
            )
            self.assertEqual(
                app.ocr_setup_primary_button.cget("text"),
                "もう一度確認",
            )
        finally:
            self._destroy(app, root)

    def test_restart_required_hands_off_to_normal_launcher(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        setup = self._status(OCR_ENV_SETUP, ready=False)
        app, _manager = self._app_with_status(root, setup)
        app.ocr_environment_restart_required = True
        app._refresh_ocr_setup_overlay()
        try:
            self.assertEqual(
                app.ocr_setup_primary_button.cget("text"),
                "アプリを再起動",
            )
            self.assertEqual(app.ocr_readiness_button.cget("text"), "再起動")
            with (
                patch.object(app, "_confirm_unsaved_changes", return_value=True),
                patch(
                    "megido_ocr_excel.application.launch_application_handoff"
                ) as launch_app,
                patch.object(root, "destroy") as destroy,
            ):
                app.restart_for_ocr_cache_change()

            launch_app.assert_called_once()
            destroy.assert_called_once_with()
        finally:
            self._destroy(app, root)

    def test_repair_handoff_keeps_app_open_when_unsaved_flow_is_cancelled(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        unavailable = self._status(OCR_ENV_UNAVAILABLE, ready=False)
        app, _manager = self._app_with_status(root, unavailable)
        try:
            with (
                patch.object(app.dialogs, "askyesno", return_value=True),
                patch.object(app, "_confirm_unsaved_changes", return_value=False),
                patch(
                    "megido_ocr_excel.application.launch_repair_handoff"
                ) as launch_repair,
                patch.object(root, "destroy") as destroy,
            ):
                app.repair_ocr_runtime()

            launch_repair.assert_not_called()
            destroy.assert_not_called()
        finally:
            self._destroy(app, root)


class DirtyStateTests(unittest.TestCase):
    def test_dirty_indicators_unsaved_cancel_and_busy_close_cancellation(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            self.assertFalse(app.dirty)

            settings_window = MagicMock()
            app.fields = [TemplateField("本文", 0, 0, 10, 10)]
            app.current_results = ["変更前"]
            app.current_raw_results = ["raw"]
            app._apply_settings(
                settings_window,
                app._lang_display(app.lang_var.get()),
                "改行",
                True,
            )

            self.assertEqual(app.text_formatting.line_join, LINE_JOIN_NEWLINE)
            self.assertTrue(app.text_formatting.fullwidth_ascii)
            self.assertTrue(app.image_text_correction_enabled)
            self.assertIn("この設定は未保存です", app.status_var.get())
            self.assertIn("右パネルの［保存］", app.status_var.get())
            self.assertEqual(app.current_results, [""])
            self.assertEqual(app.current_raw_results, [""])
            self.assertTrue(app.dirty)
            settings_window.destroy.assert_called_once()
            app._mark_clean()

            app.export_sheet_var.set("Changed")

            self.assertTrue(app.dirty)
            self.assertEqual(root.title(), f"{APP_CONFIG.app_title} *")
            self.assertEqual(
                app.template_var.get(), "新規テンプレート（未保存） *"
            )

            with patch.object(app.dialogs, "askyesnocancel", return_value=None):
                allowed = app._confirm_unsaved_changes("終了する")

            self.assertFalse(allowed)
            self.assertTrue(app.dirty)

            app.busy = True
            app._operation_cancel_event = threading.Event()
            with patch.object(
                app.dialogs, "askyesno", return_value=False
            ) as ask_cancel:
                app.confirm_cancel_current_operation()

            ask_cancel.assert_called_once()
            self.assertFalse(app._operation_cancel_event.is_set())

            with patch.object(app.dialogs, "askyesno", return_value=True):
                app.confirm_cancel_current_operation()

            self.assertTrue(app._operation_cancel_event.is_set())
            app._operation_cancel_event = threading.Event()
            with patch.object(
                app.dialogs, "askyesno", return_value=True
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
            self.assertEqual(root.title(), APP_CONFIG.app_title)
            self.assertEqual(
                app.template_var.get(), "新規テンプレート（未保存）"
            )

            app.fields = [TemplateField("話者", 0, 0, 10, 10)]
            app.set_field_enabled(0, False)
            self.assertTrue(app.dirty)

            with tempfile.TemporaryDirectory() as temp_dir:
                app.template_path = Path(temp_dir) / "existing.json"
                with (
                    patch("megido_ocr_excel.application.filedialog.asksaveasfilename") as save_dialog,
                    patch("megido_ocr_excel.application.save_template") as template_writer,
                ):
                    saved = app.save_template()

                self.assertTrue(saved)
                save_dialog.assert_not_called()
                template_writer.assert_called_once()
                self.assertTrue(
                    template_writer.call_args.args[1]["profile_options"][
                        "image_text_correction"
                    ]
                )
                self.assertFalse(app.dirty)

                save_as_path = Path(temp_dir) / "renamed.json"
                with (
                    patch(
                        "megido_ocr_excel.application.filedialog.asksaveasfilename",
                        return_value=str(save_as_path),
                    ) as save_dialog,
                    patch("megido_ocr_excel.application.save_template") as template_writer,
                ):
                    saved = app.save_template_as()

                self.assertTrue(saved)
                self.assertEqual(app.template_path, save_as_path)
                self.assertEqual(
                    save_dialog.call_args.kwargs["initialfile"], "existing.json"
                )
                template_writer.assert_called_once()

                app._mark_dirty()
                with (
                    patch("megido_ocr_excel.application.save_template", side_effect=PermissionError("locked")),
                    patch.object(app.dialogs, "showerror") as showerror,
                ):
                    saved = app.save_template()

                self.assertFalse(saved)
                self.assertTrue(app.dirty)
                showerror.assert_called_once()
        finally:
            destroy_tk_root(root)

    def test_basic_settings_toggle_profile_image_correction(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            self.assertTrue(app.image_text_correction_enabled)
            self.assertIsNotNone(app.ocr_engine.image_text_corrector)
            self.assertIs(
                app.ocr_engine.image_text_fallback,
                app.profile.image_text_fallback,
            )

            app._apply_settings(
                MagicMock(),
                app._lang_display(app.lang_var.get()),
                "全角スペース",
                app.text_formatting.fullwidth_ascii,
                False,
            )

            self.assertFalse(app.image_text_correction_enabled)
            self.assertIsNone(app.ocr_engine.image_text_corrector)
            self.assertIs(
                app.ocr_engine.image_text_fallback,
                app.profile.image_text_fallback,
            )
            self.assertTrue(app.dirty)

            app._apply_settings(
                MagicMock(),
                app._lang_display(app.lang_var.get()),
                "全角スペース",
                app.text_formatting.fullwidth_ascii,
                True,
            )

            self.assertTrue(app.image_text_correction_enabled)
            self.assertIs(
                app.ocr_engine.image_text_corrector,
                app.profile.image_text_corrector,
            )
        finally:
            destroy_tk_root(root)

    def test_basic_settings_status_reflects_template_save_state(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            settings_args = (
                app._lang_display(app.lang_var.get()),
                "全角スペース",
                app.text_formatting.fullwidth_ascii,
            )

            app.template_path = Path("saved-template.json")
            app._mark_clean()
            app._apply_settings(MagicMock(), *settings_args, False)
            self.assertIn("変更は未保存です", app.status_var.get())
            self.assertIn("上書き", app.status_var.get())

            app._mark_clean()
            app._apply_settings(MagicMock(), *settings_args, False)
            self.assertIn("保存済み", app.status_var.get())

            app._mark_dirty()
            app._apply_settings(MagicMock(), *settings_args, False)
            self.assertIn("未保存の変更があります", app.status_var.get())

            app.template_path = None
            app._mark_clean()
            app._apply_settings(MagicMock(), *settings_args, False)
            self.assertIn("設定は変更されていません（未保存）", app.status_var.get())
            self.assertIn("右パネルの［保存］", app.status_var.get())
        finally:
            destroy_tk_root(root)


class BackgroundOperationStateTests(unittest.TestCase):
    @staticmethod
    def _logic_only_app() -> ImageOcrExcelApp:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.root = MagicMock()
        app.root.after.side_effect = lambda _delay, callback: callback()
        app.status_var = MagicMock()
        app.dialogs = MagicMock()
        app.busy = False
        app._operation_cancel_event = None
        app._close_after_cancel = False
        app._show_loading = MagicMock()
        app._hide_loading = MagicMock()
        app._confirm_unsaved_changes = MagicMock(return_value=True)
        return app

    @staticmethod
    def _run_worker(app: ImageOcrExcelApp, *args, **kwargs) -> None:
        with patch("megido_ocr_excel.application.threading.Thread") as thread_type:
            app._run_background(*args, **kwargs)
            thread_type.return_value.start.assert_called_once_with()
            thread_type.call_args.kwargs["target"]()

    def test_success_is_finalized_before_completion_ui_and_app_close(self) -> None:
        app = self._logic_only_app()
        observations: list[tuple[str, bool, object, bool]] = []

        def observe(stage: str) -> None:
            observations.append(
                (
                    stage,
                    app.busy,
                    app._operation_cancel_event,
                    app._hide_loading.called,
                )
            )

        def on_success(result: str) -> None:
            self.assertEqual(result, "complete")
            observe("success")
            app.request_close()

        self._run_worker(
            app,
            "Excel出力中です。",
            lambda: "complete",
            on_success,
            on_finally=lambda: observe("finally"),
        )

        self.assertEqual(
            observations,
            [
                ("finally", False, None, True),
                ("success", False, None, True),
            ],
        )
        app.dialogs.askyesno.assert_not_called()
        app.root.destroy.assert_called_once_with()

    def test_error_ui_is_shown_after_operation_state_is_finalized(self) -> None:
        app = self._logic_only_app()
        observations: list[tuple[bool, object, bool]] = []

        def work() -> None:
            raise RuntimeError("simulated failure")

        def on_error(error: Exception) -> None:
            self.assertEqual(str(error), "simulated failure")
            observations.append(
                (
                    app.busy,
                    app._operation_cancel_event,
                    app._hide_loading.called,
                )
            )

        self._run_worker(app, "処理中です。", work, MagicMock(), on_error)

        self.assertEqual(observations, [(False, None, True)])

    def test_cancel_ui_is_finalized_before_deferred_app_close(self) -> None:
        app = self._logic_only_app()
        app._close_after_cancel = True
        app.request_close = MagicMock()
        observations: list[tuple[bool, object, bool]] = []

        def work() -> None:
            raise OperationCancelled()

        def on_cancel() -> None:
            observations.append(
                (
                    app.busy,
                    app._operation_cancel_event,
                    app.request_close.called,
                )
            )

        self._run_worker(
            app,
            "処理中です。",
            work,
            MagicMock(),
            on_cancel=on_cancel,
        )

        self.assertEqual(observations, [(False, None, False)])
        app.request_close.assert_called_once_with()


class PaddleBackendPolicyTests(unittest.TestCase):
    def _logic_only_app(self) -> ImageOcrExcelApp:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.profile = APP_PROFILE
        app.dialogs = MagicMock()
        return app

    def test_non_paddle_template_is_rejected(self) -> None:
        app = self._logic_only_app()
        field = TemplateField(
            "本文", 0, 0, 10, 10, ocr_backend="tesseract"
        )
        data = {"ocr_backend": "tesseract"}

        error = app._template_backend_error(data, [field])

        self.assertIn("PaddleOCR用テンプレートだけ", error)
        self.assertEqual(field.ocr_backend, "tesseract")

    def test_paddle_template_is_accepted(self) -> None:
        app = self._logic_only_app()
        field = TemplateField("本文", 0, 0, 10, 10, ocr_backend="paddle")

        self.assertEqual(
            app._template_backend_error({"ocr_backend": "paddle"}, [field]),
            "",
        )

    def test_ocr_field_copy_ignores_item_level_backend_override(self) -> None:
        field = TemplateField(
            "本文", 0, 0, 10, 10, ocr_backend="tesseract"
        )

        ocr_field = ImageOcrExcelApp._field_for_ocr(field)

        self.assertEqual(ocr_field.ocr_backend, "default")
        self.assertEqual(field.ocr_backend, "tesseract")

    def test_template_save_uses_profile_backend_and_no_executable_path(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.fields = [
                TemplateField(
                    "本文", 0, 0, 10, 10, ocr_backend="tesseract"
                )
            ]
            with tempfile.TemporaryDirectory() as temp_dir:
                app.template_path = Path(temp_dir) / "template.json"
                with (
                    patch(
                        "megido_ocr_excel.application.build_template_data",
                        return_value={},
                    ) as builder,
                    patch("megido_ocr_excel.application.save_template"),
                ):
                    self.assertTrue(app.save_template())

            self.assertEqual(builder.call_args.kwargs["ocr_backend"], "paddle")
            self.assertEqual(builder.call_args.kwargs["tesseract_path"], "")
            self.assertEqual(app.fields[0].ocr_backend, "default")
        finally:
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)


class OcrEnvironmentUiPolicyTests(unittest.TestCase):
    def test_long_environment_path_is_compacted_from_the_middle(self) -> None:
        value = r"C:\Users\player\AppData\Local\MegidoOCR2Excel\models"

        compact = ImageOcrExcelApp._compact_path(value, limit=30)

        self.assertEqual(len(compact), 30)
        self.assertIn("…", compact)
        self.assertTrue(compact.startswith("C:\\Users"))
        self.assertTrue(compact.endswith("models"))

    def test_environment_cache_is_applied_before_engine_use(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        with patch(
            "megido_ocr_excel.application.OcrEnvironmentManager"
        ) as manager_type:
            manager = manager_type.return_value
            manager.apply_to_process.return_value = Path("C:/models")
            app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            manager.apply_to_process.assert_called_once_with()
            self.assertEqual(
                app.ocr_environment_active_cache_dir,
                Path("C:/models").resolve(),
            )
        finally:
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)


class TemplateToolbarTests(unittest.TestCase):
    def test_toolbar_is_persistent_and_save_emphasizes_pending_changes(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            toolbar = app.template_toolbar
            self.assertIsNotNone(toolbar)
            self.assertIs(toolbar.master, app.side_body.master)
            self.assertEqual(app.template_save_button.cget("state"), "disabled")

            app.fields = [TemplateField("本文", 0, 0, 10, 10)]
            app._mark_dirty()
            self.assertEqual(app.template_save_button.cget("state"), "normal")
            self.assertEqual(app.template_save_button.cget("fg_color"), COLOR_PRIMARY)
            self.assertEqual(app.template_save_button.cget("border_width"), 0)

            app.mode_var.set(MODE_REVIEW)
            app._render_side_body()
            self.assertTrue(toolbar.winfo_exists())
            self.assertIs(app.template_toolbar, toolbar)

            app._mark_clean()
            self.assertEqual(
                app.template_save_button.cget("fg_color"), COLOR_SECONDARY
            )
            self.assertEqual(app.template_save_button.cget("border_width"), 1)
        finally:
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)


class ModalConsistencyTests(unittest.TestCase):
    def test_fixed_range_confirmation_uses_the_themed_warning_dialog(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.image_path = Path("sample.png")
            with patch.object(
                app.dialogs, "askyesno", return_value=True
            ) as askyesno:
                confirmed = app._confirm_fixed_range_switch()

            self.assertTrue(confirmed)
            self.assertEqual(askyesno.call_args.args[0], "固定範囲へ切り替え")
            self.assertIn("sample.png", askyesno.call_args.args[1])
            self.assertEqual(askyesno.call_args.kwargs["kind"], "warning")
            self.assertEqual(
                askyesno.call_args.kwargs["yes_text"],
                "固定範囲に切り替える",
            )
        finally:
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_settings_uses_the_shared_borderless_modal(self) -> None:
        root = ctk.CTk()
        root.geometry("900x700+10000+10000")
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app._hide_workflow_choice()
            root.update()
            app.open_settings_modal()
            root.update()

            modal = app.settings_modal
            self.assertIsNotNone(modal)
            self.assertTrue(modal.visible)
            self.assertTrue(bool(modal.window.overrideredirect()))
            self.assertLessEqual(modal.window.winfo_height(), root.winfo_height())
            texts = [
                str(widget.cget("text"))
                for widget in descendants_of(modal.panel)
                if "text" in widget.keys()
            ]
            self.assertIn("適用", texts)
            self.assertNotIn("診断ログ", texts)
            self.assertNotIn("フォルダーを開く", texts)
            if sys.platform.startswith("win"):
                self.assertIsNone(root.grab_current())
            else:
                self.assertEqual(modal.window.grab_current(), modal.window)

            labels = [
                widget.cget("text")
                for widget in descendants_of(modal.panel)
                if isinstance(widget, ctk.CTkLabel)
            ]
            self.assertIn("基本設定", labels)
            self.assertIn(f"バージョン {__version__}", labels)
            self.assertIn("OCR言語", labels)
            self.assertIn("OCR環境", labels)
            self.assertNotIn("PaddleOCR（固定）", labels)
            self.assertNotIn("OCRバックエンド", labels)
            self.assertNotIn("Tesseractパス", labels)
            checkbox_texts = [
                widget.cget("text")
                for widget in descendants_of(modal.panel)
                if isinstance(widget, ctk.CTkCheckBox)
            ]
            self.assertIn(
                "横線記号（一・ー・――）を画像形状で補正",
                checkbox_texts,
            )

            buttons = [
                widget
                for widget in descendants_of(modal.panel)
                if isinstance(widget, ctk.CTkButton)
            ]
            environment_button = next(
                button for button in buttons if button.cget("text") == "環境設定"
            )
            language_combo = next(
                widget
                for widget in descendants_of(modal.panel)
                if isinstance(widget, ctk.CTkComboBox)
            )
            language_combo.set("English のみ")
            environment_button.invoke()
            root.update()

            self.assertFalse(modal.visible)
            environment_modal = app.ocr_environment_modal
            self.assertIsNotNone(environment_modal)
            self.assertTrue(environment_modal.visible)
            self.assertTrue(bool(environment_modal.window.overrideredirect()))
            self.assertLessEqual(
                environment_modal.window.winfo_height(), root.winfo_height()
            )
            environment_labels = [
                widget
                for widget in descendants_of(environment_modal.panel)
                if isinstance(widget, ctk.CTkLabel)
            ]
            environment_label_texts = [
                widget.cget("text") for widget in environment_labels
            ]
            self.assertIn("OCR環境設定", environment_label_texts)
            self.assertIn("PaddleOCR（固定）", environment_label_texts)
            self.assertIn("診断ログ", environment_label_texts)
            self.assertFalse(
                any(
                    "テンプレートには含まれません" in text
                    for text in environment_label_texts
                )
            )
            environment_buttons = [
                widget
                for widget in descendants_of(environment_modal.panel)
                if isinstance(widget, ctk.CTkButton)
            ]
            button_texts = [button.cget("text") for button in environment_buttons]
            self.assertIn("開く", button_texts)
            self.assertIn("変更", button_texts)
            self.assertIn("フォルダーを開く", button_texts)
            self.assertIn("完了", button_texts)
            self.assertNotIn("保存", button_texts)
            self.assertTrue(
                any(
                    text in {"確認して更新", "ダウンロードして準備"}
                    for text in button_texts
                )
            )
            open_button = next(
                button
                for button in environment_buttons
                if button.cget("text") == "開く"
            )
            change_button = next(
                button
                for button in environment_buttons
                if button.cget("text") == "変更"
            )
            verify_button = next(
                button
                for button in environment_buttons
                if button.cget("text")
                in {"確認して更新", "ダウンロードして準備"}
            )
            self.assertIs(open_button.master, change_button.master)
            self.assertIsNot(open_button.master, verify_button.master)

            environment_modal.window.event_generate("<Escape>", when="tail")
            root.update()
            self.assertIsNone(app.ocr_environment_modal)
            self.assertTrue(modal.visible)
            self.assertEqual(language_combo.get(), "English のみ")

            modal.window.event_generate("<Escape>", when="tail")
            root.update()
            self.assertIsNone(app.settings_modal)
        finally:
            if app.ocr_environment_modal is not None:
                app.ocr_environment_modal.destroy()
            if app.settings_modal is not None:
                app.settings_modal.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_settings_hide_image_correction_for_profiles_without_it(self) -> None:
        root = ctk.CTk()
        root.geometry("900x700+10000+10000")
        profile = replace(APP_PROFILE, image_text_corrector=None)
        app = ImageOcrExcelApp(root, profile=profile, app_config=APP_CONFIG)
        try:
            app._hide_workflow_choice()
            app.open_settings_modal()
            root.update()

            checkbox_texts = [
                widget.cget("text")
                for widget in descendants_of(app.settings_modal.panel)
                if isinstance(widget, ctk.CTkCheckBox)
            ]
            self.assertNotIn(
                "横線記号（一・ー・――）を画像形状で補正",
                checkbox_texts,
            )
            self.assertFalse(app.image_text_correction_enabled)
            self.assertIsNone(app.ocr_engine.image_text_corrector)
        finally:
            if app.settings_modal is not None:
                app.settings_modal.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_processing_modal_blocks_background_input_until_hidden(self) -> None:
        root = ctk.CTk()
        root.geometry("900x700+10000+10000")
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app._hide_workflow_choice()
            root.update()
            app.busy = True
            app._operation_cancel_event = threading.Event()

            app._show_loading("OCR処理中です。")
            root.update()

            modal = app.loading_modal
            self.assertIsNotNone(modal)
            self.assertTrue(modal.visible)
            if sys.platform.startswith("win"):
                self.assertIsNone(root.grab_current())
            else:
                self.assertEqual(modal.window.grab_current(), modal.window)
            self.assertEqual(modal.backdrop.state(), "normal")

            with patch.object(
                app.dialogs, "askyesno", return_value=True
            ) as ask_cancel:
                root.tk.eval(root.protocol("WM_DELETE_WINDOW"))

            ask_cancel.assert_called_once()
            self.assertTrue(app._operation_cancel_event.is_set())
            self.assertTrue(app._close_after_cancel)
            self.assertTrue(root.winfo_exists())

            app._hide_loading()
            root.update()
            self.assertFalse(modal.visible)
            self.assertEqual(modal.window.state(), "withdrawn")
            self.assertIsNone(root.grab_current())
        finally:
            if app.loading_modal is not None:
                app.loading_modal.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_excel_progress_modal_shows_count_file_and_determinate_progress(self) -> None:
        root = ctk.CTk()
        root.geometry("900x700+10000+10000")
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app._hide_workflow_choice()
            root.update()
            app.busy = True
            app._operation_cancel_event = threading.Event()

            app._show_loading(
                "Excelへ出力しています",
                note="2 / 5 画像\nb2.png",
                progress=0.4,
            )
            root.update()

            self.assertTrue(app.loading_modal.visible)
            self.assertEqual(app.loading_var.get(), "Excelへ出力しています")
            self.assertEqual(app.loading_note_var.get(), "2 / 5 画像\nb2.png")
            self.assertEqual(app.loading_progress.cget("mode"), "determinate")
            self.assertAlmostEqual(app.loading_progress.get(), 0.4)

            with patch.object(app.loading_modal, "show") as reopen:
                app._update_loading(
                    "Excelへ出力しています",
                    note="3 / 5 画像\nb3.png",
                    progress=0.6,
                )
                reopen.assert_not_called()
            root.update()

            self.assertEqual(app.loading_note_var.get(), "3 / 5 画像\nb3.png")
            self.assertAlmostEqual(app.loading_progress.get(), 0.6)
        finally:
            if app.loading_modal is not None:
                app.loading_modal.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)


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
                slot_key=SET_SLOT_SUPPLEMENT,
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
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = MODE_REVIEW
        app.canvas = MagicMock()
        app.canvas_edit_state = None
        app.drag_start = None
        app.drag_rect = None
        app._schedule_side_body_render = MagicMock()

        app._on_mode_change()

        app._schedule_side_body_render.assert_called_once()
        app.redraw.assert_not_called()

    def test_review_canvas_selects_without_starting_an_edit(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.original_image = object()
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = MODE_REVIEW
        app._canvas_selection_hit = MagicMock(return_value=1)
        app._select_field_index = MagicMock()
        app._commit_active_name_edit = MagicMock()

        app._preview_resize_hit = MagicMock(return_value=(None, None))
        app.on_mouse_down(MagicMock())

        app._select_field_index.assert_called_once_with(
            1, update_review_detail=True
        )
        app._commit_active_name_edit.assert_not_called()

    def test_selection_preserves_results_and_undo_until_geometry_changes(self):
        from types import SimpleNamespace

        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.original_image = Image.new("RGB", (200, 160))
            app.coordinate_settings = replace(app.coordinate_settings, coordinate_space="image")
            app.zoom = 1
            app.fields = [TemplateField("本文", 10, 10, 50, 50,
                                        source_width=100, source_height=80)]
            app.current_results[0] = "テスト結果"
            previous = {"type": "previous"}
            app.undo_action = previous
            app.mode_var.set(MODE_TEMPLATE)
            app.redraw()
            press = SimpleNamespace(x=100, y=60)
            app.on_mouse_down(press)
            app.on_mouse_up(press)
            self.assertFalse(app.dirty)
            self.assertEqual(app.fields[0].source_width, 100)
            self.assertEqual(app.current_results[0], "テスト結果")
            self.assertIs(app.undo_action, previous)
            app.on_mouse_down(press)
            end = SimpleNamespace(x=5, y=60)
            app.on_mouse_drag(end)
            self.assertEqual(app.canvas.coords(app.canvas_rects[0]), [20, 20, 28, 100])
            app.on_mouse_up(end)
            self.assertEqual((app.fields[0].x1, app.fields[0].x2), (20, 28))
            app.undo_last_action()
            self.assertEqual(app.current_results[0], "テスト結果")
        finally:
            destroy_tk_root(root)

    def test_set_handle_drag_moves_three_fields_together(self):
        from types import SimpleNamespace

        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.original_image = Image.new("RGB", (200, 160))
            app.coordinate_settings = replace(app.coordinate_settings, coordinate_space="image")
            app.zoom = 1
            app.export_layout_var.set(EXPORT_LAYOUT_SET)
            app.fields = [TemplateField(key, 20, y, 100, y + 16, set_id=1, slot_key=key,
                                        source_width=200, source_height=160)
                          for y, key in zip((20, 50, 80),
                                            (SET_SLOT_SPEAKER, SET_SLOT_TEXT, SET_SLOT_SUPPLEMENT))]
            app.selected_index = 0
            app.mode_var.set(MODE_TEMPLATE)
            app.redraw()
            x1, y1, x2, y2 = app.canvas.coords(app.canvas_set_handles[1]["handle"])
            press = SimpleNamespace(x=int((x1+x2)/2), y=int((y1+y2)/2))
            end = SimpleNamespace(x=press.x+12, y=press.y+6)
            app.on_mouse_down(press)
            app.on_mouse_drag(end)
            app.on_mouse_up(end)
            self.assertEqual([(f.x1, f.y1) for f in app.fields], [(32, 26), (32, 56), (32, 86)])
            app.undo_last_action()
            self.assertEqual([f.y1 for f in app.fields], [20, 50, 80])
        finally:
            destroy_tk_root(root)

    def test_preview_edge_drag_switches_mode_and_commits_same_gesture(self):
        from types import SimpleNamespace

        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.original_image = Image.new("RGB", (200, 160))
            app.coordinate_settings = replace(app.coordinate_settings, coordinate_space="image")
            app.zoom = 1
            for mode, y, dy in [(MODE_REVIEW, 60, 0), (MODE_EXPORT, 100, 12)]:
                with self.subTest(mode=mode):
                    app.fields = [TemplateField("本文", 20, 20, 100, 100,
                                                source_width=200, source_height=160)]
                    app.mode_var.set(mode)
                    app.redraw()
                    press = SimpleNamespace(x=100, y=y)
                    end = SimpleNamespace(x=115, y=y + dy)
                    app.on_mouse_down(press)
                    app.on_mouse_up(press)
                    self.assertEqual(app.mode_var.get(), mode)
                    app.on_mouse_down(press)
                    app.on_mouse_drag(end)
                    self.assertEqual(app.mode_var.get(), MODE_TEMPLATE)
                    app.on_mouse_up(end)
                    self.assertEqual((app.fields[0].x2, app.fields[0].y2), (115, 100 + dy))
                    app.undo_last_action()
                    self.assertEqual((app.fields[0].x2, app.fields[0].y2), (100, 100))
        finally:
            destroy_tk_root(root)

    def test_export_canvas_ignores_selection_and_editing(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.original_image = object()
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = MODE_EXPORT
        app._canvas_selection_hit = MagicMock()
        app._select_field_index = MagicMock()
        app._commit_active_name_edit = MagicMock()

        app._preview_resize_hit = MagicMock(return_value=(None, None))
        app.on_mouse_down(MagicMock())

        app._canvas_selection_hit.assert_not_called()
        app._select_field_index.assert_not_called()
        app._commit_active_name_edit.assert_not_called()

    def test_review_mode_blocks_field_editing_shortcuts(self) -> None:
        app = self._logic_only_app()
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = MODE_REVIEW
        app._focus_is_text_entry = MagicMock(return_value=False)
        app._require_field_selection = MagicMock(return_value=0)
        app.begin_inline_name_edit = MagicMock()
        app._commit_active_name_edit = MagicMock(return_value=True)
        app.undo_action = {"type": "add"}

        self.assertEqual(app.edit_selected_field_name(), "break")
        app.move_selected_field(1)
        self.assertEqual(app.undo_last_action(), "break")

        app._require_field_selection.assert_not_called()
        app.begin_inline_name_edit.assert_not_called()
        app._commit_active_name_edit.assert_not_called()
        self.assertEqual(app.undo_action, {"type": "add"})

    def test_non_template_mouse_release_clears_stale_edit_state(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = MODE_REVIEW
        app.canvas = MagicMock()
        app.canvas_edit_state = {"idx": 0, "mode": "move"}
        app.drag_start = (10, 10)
        app.drag_rect = 42

        app.on_mouse_up(MagicMock())

        self.assertIsNone(app.canvas_edit_state)
        self.assertIsNone(app.drag_start)
        self.assertIsNone(app.drag_rect)
        app.canvas.delete.assert_called_once_with(42)

    def test_template_mouse_release_without_image_clears_stale_edit_state(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.mode_var = MagicMock()
        app.mode_var.get.return_value = MODE_TEMPLATE
        app.original_image = None
        app._clear_canvas_pointer_interaction = MagicMock()

        app.on_mouse_up(MagicMock())

        app._clear_canvas_pointer_interaction.assert_called_once_with()

    def test_export_settings_exclude_layout_and_preflight_links_to_editor(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        host = ctk.CTkFrame(root)
        try:
            app._render_excel_output_settings(host)
            app._render_export_structure_summary(host, 3, 2)
            descendants = []
            pending = list(host.winfo_children())
            while pending:
                widget = pending.pop()
                descendants.append(widget)
                pending.extend(widget.winfo_children())

            option_values = [
                widget.cget("values")
                for widget in descendants
                if isinstance(widget, ctk.CTkOptionMenu)
            ]
            labels = [
                widget.cget("text")
                for widget in descendants
                if isinstance(widget, ctk.CTkLabel)
            ]
            buttons = [
                widget
                for widget in descendants
                if isinstance(widget, ctk.CTkButton)
            ]
            self.assertNotIn(EXPORT_LAYOUT_OPTIONS, option_values)
            self.assertIn(
                EXPORT_LAYOUT_DISPLAY[app.export_layout_var.get()], labels
            )
            self.assertIn("Excelの行単位", labels)
            self.assertNotIn("列構成", labels)
            self.assertNotIn("出力形式", labels)
            navigation = next(
                button
                for button in buttons
                if button.cget("text") == "範囲・列で編集"
            )
            self.assertEqual(navigation.cget("fg_color"), COLOR_SECONDARY)
            self.assertEqual(navigation.cget("border_width"), 1)
            self.assertEqual(int(navigation.grid_info()["row"]), 2)
        finally:
            host.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_csv_export_is_presented_as_a_secondary_action(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app._hide_workflow_choice()
            app.mode_var.set(MODE_EXPORT)
            app._render_side_body()
            buttons = [
                widget
                for widget in descendants_of(app.side_body)
                if isinstance(widget, ctk.CTkButton)
            ]
            excel_button = next(
                button for button in buttons if button.cget("text") == "Excel出力"
            )
            labels = [
                widget.cget("text")
                for widget in descendants_of(app.side_body)
                if isinstance(widget, ctk.CTkLabel)
            ]

            self.assertNotEqual(excel_button.cget("fg_color"), "transparent")
            self.assertEqual(app.template_more_button.cget("text"), "ファイル")
            self.assertNotIn("CSV形式で保存…", [button.cget("text") for button in buttons])
            self.assertFalse(any("CSV" in label for label in labels))
        finally:
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_set_preflight_repeats_item_combination(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        host = ctk.CTkFrame(root)
        try:
            app.export_layout_var.set(EXPORT_LAYOUT_SET)
            app._render_export_structure_summary(host, 3, 2)
            labels = [
                widget.cget("text")
                for widget in descendants_of(host)
                if isinstance(widget, ctk.CTkLabel)
            ]
            navigation = next(
                widget
                for widget in descendants_of(host)
                if isinstance(widget, ctk.CTkButton)
                and widget.cget("text") == "範囲・列で編集"
            )

            self.assertIn("Excelの行単位", labels)
            self.assertIn(EXPORT_LAYOUT_DISPLAY[EXPORT_LAYOUT_SET], labels)
            self.assertIn("項目の組み合わせ", labels)
            self.assertIn("話者＋セリフ", labels)
            self.assertEqual(int(navigation.grid_info()["row"]), 3)
        finally:
            host.destroy()
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_export_layout_navigation_switches_to_template_mode(self) -> None:
        app = self._logic_only_app()
        app.mode_var = MagicMock()
        app.status_var = MagicMock()
        app._on_mode_change = MagicMock()

        app.open_template_mode_from_export()

        app.mode_var.set.assert_called_once_with(MODE_TEMPLATE)
        app.status_var.set.assert_called_once_with(
            "Excelの行単位を変更できます。"
        )
        app._on_mode_change.assert_called_once_with()

    def test_range_panel_uses_excel_row_unit_labels_and_explanations(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app._hide_workflow_choice()
            app.mode_var.set(MODE_TEMPLATE)
            app._render_side_body()
            image_labels = [
                widget.cget("text")
                for widget in descendants_of(app.side_body)
                if isinstance(widget, ctk.CTkLabel)
            ]
            image_menu_values = [
                widget.cget("values")
                for widget in descendants_of(app.side_body)
                if isinstance(widget, ctk.CTkOptionMenu)
            ]

            self.assertIn("Excelの行単位", image_labels)
            self.assertIn(THEME.copy.image_layout_note, image_labels)
            self.assertIn(
                list(EXPORT_LAYOUT_DISPLAY.values()), image_menu_values
            )
            self.assertNotIn("出力形式", image_labels)

            app.export_layout_var.set(EXPORT_LAYOUT_SET)
            app._render_side_body()
            set_labels = [
                widget.cget("text")
                for widget in descendants_of(app.side_body)
                if isinstance(widget, ctk.CTkLabel)
            ]

            self.assertIn("Excelの行単位", set_labels)
            self.assertIn("項目の組み合わせ", set_labels)
            self.assertIn(THEME.copy.set_layout_note, set_labels)
            self.assertNotIn("セット種類", set_labels)
        finally:
            if app.workflow_choice_modal is not None:
                app.workflow_choice_modal.destroy()
            destroy_tk_root(root)

    def test_duplicate_is_undoable_and_clears_set_assignment(self) -> None:
        app = self._logic_only_app()
        app.export_layout_var.get.return_value = EXPORT_LAYOUT_SET
        app.fields = [TemplateField("話者1", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER)]
        app.current_results = ["recognized"]
        app.current_raw_results = ["raw"]

        app.duplicate_field_at(0)

        self.assertEqual(len(app.fields), 2)
        self.assertEqual(app.fields[1].name, "話者1 のコピー")
        self.assertEqual(app.fields[1].set_id, 0)
        self.assertEqual(app.fields[1].slot_key, "")
        self.assertEqual(app.current_results[1], "")
        self.assertEqual(app.undo_action["type"], "add")

    def test_drag_visual_highlights_row_and_handle(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        row = MagicMock()
        handle = MagicMock()
        app.fields = [TemplateField("field", 0, 0, 10, 10)]
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

    def test_text_slot_enables_line_splitting(self) -> None:
        app = self._logic_only_app()
        app.fields = [TemplateField("本文", 0, 0, 10, 10, ocr_line_split="none")]
        app.current_results = ["recognized"]
        app.current_raw_results = ["raw"]

        app.set_field_slot(0, "セリフ")

        self.assertEqual(app.fields[0].slot_key, SET_SLOT_TEXT)
        self.assertEqual(app.fields[0].ocr_line_split, "detected")
        self.assertEqual(app.current_results[0], "")
        self.assertEqual(app.current_raw_results[0], "")
        app._mark_dirty.assert_called_once()

    def test_supplement_slot_enables_line_splitting(self) -> None:
        app = self._logic_only_app()
        app.fields = [TemplateField("補足", 0, 0, 10, 10, ocr_line_split="none")]
        app.current_results = ["recognized"]
        app.current_raw_results = ["raw"]

        app.set_field_slot(0, "補足セリフ")

        self.assertEqual(app.fields[0].slot_key, SET_SLOT_SUPPLEMENT)
        self.assertEqual(app.fields[0].ocr_line_split, "detected")

    def test_field_rows_show_only_the_setting_used_by_the_output_layout(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            field = TemplateField(
                "本文",
                0,
                0,
                10,
                10,
                set_id=1,
                slot_key=SET_SLOT_SPEAKER,
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

            app.export_layout_var.set(EXPORT_LAYOUT_SET)
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
            self.assertEqual(field.slot_key, SET_SLOT_SPEAKER)

            app.set_definition = HEADING_TEXT_SET_DEFINITION
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
            destroy_tk_root(root)

    def test_switching_to_set_layout_creates_set_one_and_assigns_existing_fields(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.fields = [
                TemplateField("話者", 0, 0, 10, 10),
                TemplateField("セリフ本文", 0, 10, 10, 20),
            ]
            app.current_results = ["old", "old"]
            app.current_raw_results = ["raw", "raw"]

            app.export_layout_var.set(EXPORT_LAYOUT_SET)
            app._set_export_layout(EXPORT_LAYOUT_SET)

            self.assertEqual([field.set_id for field in app.fields], [1, 1])
            self.assertEqual(
                [field.slot_key for field in app.fields],
                [SET_SLOT_SPEAKER, SET_SLOT_TEXT],
            )
            self.assertEqual(app._set_ids(), [1])
            self.assertIsNone(app.pending_set_id)
            self.assertEqual(app.current_results, ["", ""])
            root.update_idletasks()
        finally:
            destroy_tk_root(root)

    @private_sample_test
    def test_switching_auto_detection_to_image_rows_fixes_the_current_coordinate_source(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.export_layout_var = MagicMock()
        app.export_layout_var.get.return_value = EXPORT_LAYOUT_SET
        app.original_image = Image.open(".samples/1.png").convert("RGB")
        app.coordinate_settings = APP_PROFILE.coordinate_settings()
        app.current_content_rect = None
        app.fields = [TemplateField("話者", 55, 1523, 697, 1620)]
        app.auto_detection_enabled = True
        app.auto_detection_base_fields = [replace(app.fields[0])]
        app.pending_set_id = None
        app.pending_slot_key = ""
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
        app.export_layout_var.get.return_value = EXPORT_LAYOUT_SET
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
        menu.set.assert_called_once_with(
            EXPORT_LAYOUT_DISPLAY[EXPORT_LAYOUT_SET]
        )
        app._schedule_side_body_render.assert_not_called()
        app.redraw.assert_not_called()
        self.assertEqual(
            app.status_var.set.call_args.args[0], "自動検出を継続します。"
        )

    def test_empty_set_one_remains_available_and_preset_change_reassigns_fields(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        app = ImageOcrExcelApp(root, APP_PROFILE, APP_CONFIG)
        try:
            app.export_layout_var.set(EXPORT_LAYOUT_SET)
            app._set_export_layout(EXPORT_LAYOUT_SET)
            self.assertEqual(app._set_ids(), [1])
            self.assertEqual(app.pending_set_id, 1)
            self.assertEqual(app.pending_slot_key, SET_SLOT_SPEAKER)

            app.cancel_set_creation()
            app.begin_set_creation()
            self.assertEqual(app.pending_set_id, 1)

            app.fields = [
                TemplateField("見出し", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER),
                TemplateField("本文", 0, 10, 10, 20, set_id=1, slot_key=SET_SLOT_TEXT),
            ]
            with patch.object(app.dialogs, "askyesno", return_value=True):
                app._set_set_preset("見出し＋本文")

            self.assertEqual([field.set_id for field in app.fields], [1, 1])
            self.assertEqual(
                [field.slot_key for field in app.fields],
                [SET_SLOT_HEADING, SET_SLOT_TEXT],
            )
            root.update_idletasks()
        finally:
            destroy_tk_root(root)

    def test_unselected_set_draws_only_the_outer_outline(self) -> None:
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.canvas = MagicMock()
        app.canvas.create_rectangle.side_effect = [10, 11]
        app.canvas.create_text.return_value = 12
        app.zoom = 1.0
        app.selected_index = None
        app.canvas_set_handles = {}

        app._draw_set_handle(1, (0, 1), {0: (10, 10, 30, 20), 1: (10, 22, 80, 50)})

        app.canvas.create_rectangle.assert_called_once()
        self.assertEqual(app.canvas_set_handles[1]["outline"], 10)
        self.assertIsNone(app.canvas_set_handles[1]["handle"])
        app.canvas.create_text.assert_not_called()

    def test_dragging_to_another_set_swaps_the_same_role(self) -> None:
        app = self._logic_only_app()
        app.fields = [
            TemplateField(
                "話者1", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER
            ),
            TemplateField(
                "話者2", 0, 10, 10, 20, set_id=2, slot_key=SET_SLOT_SPEAKER
            ),
        ]

        app.move_field_to_set(0, 2)

        self.assertEqual(app.fields[0].set_id, 2)
        self.assertEqual(app.fields[1].set_id, 1)
        app._mark_dirty.assert_called_once()
        self.assertIn("入れ替え", app.status_var.set.call_args.args[0])

    def test_dragging_to_unassigned_removes_the_pair_membership(self) -> None:
        app = self._logic_only_app()
        app.fields = [
            TemplateField(
                "セリフ1", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_TEXT
            )
        ]

        app.move_field_to_set(0, 0)

        self.assertEqual(app.fields[0].set_id, 0)
        self.assertEqual(app.fields[0].slot_key, SET_SLOT_TEXT)


if __name__ == "__main__":
    unittest.main()
