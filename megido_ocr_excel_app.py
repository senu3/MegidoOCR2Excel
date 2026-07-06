from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from tkinter import BOTH, BOTTOM, HORIZONTAL, LEFT, RIGHT, TOP, VERTICAL, BooleanVar, Canvas, Menu, Scrollbar, StringVar, filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from excel_exporter import ExcelExporter, ExportSettings, validate_export_settings
from megido_app_config import APP_TITLE, DEFAULT_BACKEND, DEFAULT_LANG, IMAGE_EXTENSIONS, PROFILE_ID
from megido_ui_theme import THEME
from ocr_engine import OcrEngine, apply_correction_rules, apply_postprocess, detect_line_bands, detect_tesseract, fill_missing_field_source_size, scaled_field
from ocr_models import CORRECTION_ALL_TARGET, OCR_BACKEND_OPTIONS, CorrectionRule, TemplateField
from profiles.megido_novel import field_ocr_preset, has_field_ocr_preset
from template_store import build_template_data, correction_rules_from_template, fields_from_template, load_template, save_template


UI_FONT_FAMILY = THEME.fonts.family
UI_FONT = THEME.fonts.normal
UI_FONT_SMALL = THEME.fonts.small
UI_FONT_BOLD = THEME.fonts.bold
UI_FONT_TITLE = THEME.fonts.title
UI_FONT_CANVAS = THEME.fonts.canvas

COLOR_BG = THEME.palette.app_bg
COLOR_SURFACE = THEME.palette.surface
COLOR_SURFACE_ALT = THEME.palette.surface_alt
COLOR_BORDER = THEME.palette.border
COLOR_TEXT = THEME.palette.text
COLOR_MUTED = THEME.palette.muted
COLOR_PRIMARY = THEME.palette.primary
COLOR_PRIMARY_HOVER = THEME.palette.primary_hover
COLOR_SECONDARY = THEME.palette.secondary
COLOR_SECONDARY_HOVER = THEME.palette.secondary_hover
COLOR_DANGER = THEME.palette.danger
COLOR_DANGER_HOVER = THEME.palette.danger_hover
COLOR_CTA = THEME.palette.cta
COLOR_CTA_HOVER = THEME.palette.cta_hover
COLOR_CANVAS_BG = THEME.palette.canvas_bg
COLOR_CANVAS_PANEL = THEME.palette.canvas_panel
COLOR_CANVAS_TOOLBAR = THEME.palette.canvas_toolbar

OCR_MODE_OPTIONS = ["範囲全体", "行切り出し"]
MODE_TEMPLATE = "1. 範囲・列"
MODE_REVIEW = "2. OCR確認"
MODE_EXPORT = "3. Excel出力"
ICON_OPEN = "📂"
ICON_SAVE = "💾"
ICON_SETTINGS = "⚙"
ICON_PREV = "‹"
ICON_NEXT = "›"
ICON_RUN = "▶"
ICON_EXCEL = "▦"


class ImageOcrExcelApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(THEME.layout.window_size)
        self.root.minsize(*THEME.layout.min_window_size)
        self.root.option_add("*Font", f"{UI_FONT_FAMILY} 10")

        self.image_path: Path | None = None
        self.image_files: list[Path] = []
        self.current_image_index = -1
        self.source_folder: Path | None = None
        self.output_path: Path | None = None
        self.template_path: Path | None = None

        self.original_image: Image.Image | None = None
        self.preview_image: ImageTk.PhotoImage | None = None
        self.preview_cache_key: tuple[int, float] | None = None
        self.image_item: int | None = None
        self.zoom = 1.0

        self.fields: list[TemplateField] = []
        self.current_results: list[str] = []
        self.current_raw_results: list[str] = []
        # Future correction-rule foundation.
        # Keep this data path even while the editor UI is hidden; template loading/saving
        # and OCR application already support it and will be reused when rules are redesigned.
        self.correction_rules: list[CorrectionRule] = []
        self.correction_rules_expanded = False
        self.result_vars: list[StringVar] = []
        self.field_check_vars: list[BooleanVar] = []
        self.field_row_widgets: list[ctk.CTkFrame] = []
        self.field_row_by_index: dict[int, ctk.CTkFrame] = {}
        self.review_order_label_by_index: dict[int, ctk.CTkLabel] = {}
        self.review_summary_label_by_index: dict[int, ctk.CTkLabel] = {}
        self.selected_index: int | None = None
        self.editing_name_index: int | None = None
        self.dragging_field_index: int | None = None
        self.canvas_edit_state: dict | None = None
        self.undo_action: dict | None = None

        self.drag_start: tuple[int, int] | None = None
        self.drag_rect: int | None = None
        self.canvas_rects: dict[int, int] = {}
        self.canvas_labels: dict[int, int] = {}
        self.canvas_label_bgs: dict[int, int] = {}
        self.ocr_engine = OcrEngine()
        self.excel_exporter = ExcelExporter()

        self.mode_var = StringVar(value=MODE_TEMPLATE)
        self.image_var = StringVar(value="画像未選択")
        self.folder_var = StringVar(value="未選択")
        self.output_var = StringVar(value="未選択")
        self.template_var = StringVar(value="未保存")
        self.image_count_var = StringVar(value="0 / 0")
        self.field_count_var = StringVar(value="0 項目")
        self.status_var = StringVar(value=THEME.copy.initial_status)
        self.progress_var = StringVar(value="")
        self.loading_var = StringVar(value="")
        self.lang_var = StringVar(value=DEFAULT_LANG)
        self.lang_display_var = StringVar(value=self._lang_display(DEFAULT_LANG))
        self.backend_var = StringVar(value=DEFAULT_BACKEND)
        self.tesseract_var = StringVar(value=detect_tesseract())
        self.export_sheet_var = StringVar(value="OCR")
        self.export_write_mode_var = StringVar(value="上書き")
        self.export_start_cell_var = StringVar(value="A1")
        self.export_include_filename_var = BooleanVar(value=True)
        self.export_include_header_var = BooleanVar(value=True)
        self.review_raw_preview_var = StringVar(value="未OCR")
        self.review_processed_preview_var = StringVar(value="未OCR")
        self.review_line_split_var = StringVar(value=OCR_MODE_OPTIONS[0])

        self.side_body: ctk.CTkFrame | None = None
        self.review_detail_host: ctk.CTkFrame | None = None
        self.correction_rules_host: ctk.CTkFrame | None = None
        self.canvas: Canvas
        self.hbar: Scrollbar | None = None
        self.vbar: Scrollbar | None = None
        self.loading_overlay: ctk.CTkFrame | None = None
        self.loading_progress: ctk.CTkProgressBar | None = None
        self.busy = False

        self._build_ui()
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.root.configure(fg_color=COLOR_BG)

        main = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        main.pack(side=TOP, fill=BOTH, expand=True)

        canvas_area = ctk.CTkFrame(main, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_CANVAS_PANEL, border_width=1, border_color=THEME.palette.canvas_border)
        canvas_area.pack(side=LEFT, fill=BOTH, expand=True, padx=(12, 0), pady=12)

        toolbar = ctk.CTkFrame(canvas_area, height=THEME.layout.toolbar_height, corner_radius=0, fg_color=COLOR_CANVAS_TOOLBAR)
        toolbar.pack(side=TOP, fill="x")
        toolbar.pack_propagate(False)
        self._toolbar_button(toolbar, f"{ICON_OPEN} 画像", self.open_image_folder, COLOR_PRIMARY, COLOR_PRIMARY_HOVER, 94).pack(side=LEFT, padx=(12, 4), pady=10)
        ctk.CTkFrame(toolbar, width=1, height=22, fg_color=THEME.palette.toolbar_divider).pack(side=LEFT, padx=8, pady=14)
        self._toolbar_button(toolbar, ICON_SETTINGS, self.open_settings_modal, COLOR_SECONDARY, COLOR_SECONDARY_HOVER, 38).pack(side=LEFT, padx=4, pady=10)
        ctk.CTkLabel(toolbar, textvariable=self.image_var, font=UI_FONT_SMALL, text_color=THEME.palette.toolbar_text, anchor="w").pack(side=LEFT, fill="x", expand=True, padx=(12, 12))
        self._toolbar_button(toolbar, ICON_NEXT, self.next_image, THEME.palette.toolbar_button, THEME.palette.toolbar_button_hover, 34).pack(side=RIGHT, padx=(4, 12), pady=10)
        ctk.CTkLabel(toolbar, textvariable=self.image_count_var, width=72, anchor="center", font=UI_FONT_SMALL, text_color=THEME.palette.toolbar_muted).pack(side=RIGHT)
        self._toolbar_button(toolbar, ICON_PREV, self.previous_image, THEME.palette.toolbar_button, THEME.palette.toolbar_button_hover, 34).pack(side=RIGHT, padx=4, pady=10)

        canvas_frame = ctk.CTkFrame(canvas_area, corner_radius=0, fg_color=COLOR_CANVAS_PANEL)
        canvas_frame.pack(side=TOP, fill=BOTH, expand=True)
        self.canvas = Canvas(canvas_frame, bg=COLOR_CANVAS_BG, highlightthickness=0)
        self.hbar = Scrollbar(canvas_frame, orient=HORIZONTAL, command=self.canvas.xview)
        self.vbar = Scrollbar(canvas_frame, orient=VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self._set_canvas_scrollbars(False, False)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Control-MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Button-3>", self.show_canvas_context_menu)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        status_bar = ctk.CTkFrame(canvas_area, height=THEME.layout.status_bar_height, corner_radius=0, fg_color=COLOR_CANVAS_TOOLBAR)
        status_bar.pack(side=BOTTOM, fill="x")
        status_bar.pack_propagate(False)
        ctk.CTkLabel(status_bar, textvariable=self.status_var, anchor="w", font=UI_FONT_SMALL, text_color=THEME.palette.toolbar_text).pack(side=LEFT, fill="x", expand=True, padx=12)
        ctk.CTkLabel(status_bar, textvariable=self.progress_var, anchor="e", font=UI_FONT_SMALL, text_color=THEME.palette.toolbar_muted).pack(side=RIGHT, padx=12)

        side = ctk.CTkFrame(main, width=THEME.layout.side_panel_width, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE, border_width=1, border_color=COLOR_BORDER)
        side.pack(side=RIGHT, fill="y", padx=(12, 12), pady=12)
        side.pack_propagate(False)

        header = ctk.CTkFrame(side, corner_radius=0, fg_color=COLOR_SURFACE)
        header.pack(side=TOP, fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(header, text=THEME.copy.header, font=UI_FONT_TITLE, text_color=COLOR_TEXT, anchor="w").pack(side=LEFT, fill="x", expand=True)
        ctk.CTkLabel(header, textvariable=self.field_count_var, font=UI_FONT_SMALL, text_color=COLOR_MUTED, anchor="e").pack(side=RIGHT)

        ctk.CTkSegmentedButton(
            side,
            values=[MODE_TEMPLATE, MODE_REVIEW, MODE_EXPORT],
            variable=self.mode_var,
            command=self._on_mode_change,
            font=UI_FONT_SMALL,
            selected_color=COLOR_PRIMARY,
            selected_hover_color=COLOR_PRIMARY_HOVER,
            unselected_color=THEME.palette.segmented_bg,
            unselected_hover_color=THEME.palette.segmented_hover,
            text_color=COLOR_TEXT,
        ).pack(side=TOP, fill="x", padx=16, pady=(0, 10))

        self.side_body = ctk.CTkFrame(side, corner_radius=0, fg_color=COLOR_SURFACE)
        self.side_body.pack(side=TOP, fill=BOTH, expand=True)
        self._render_side_body()
        self._build_loading_overlay()

    def _toolbar_button(self, parent, text: str, command, fg: str, hover: str, width: int) -> ctk.CTkButton:
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=THEME.layout.button_height, font=UI_FONT_SMALL, fg_color=fg, hover_color=hover)

    def _build_loading_overlay(self) -> None:
        overlay = ctk.CTkFrame(
            self.root,
            width=360,
            height=116,
            corner_radius=THEME.layout.panel_radius,
            fg_color=COLOR_SURFACE,
            border_width=1,
            border_color=COLOR_PRIMARY,
        )
        overlay.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(overlay, textvariable=self.loading_var, anchor="center", justify="center", font=UI_FONT_BOLD, text_color=COLOR_TEXT, wraplength=300).grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))
        self.loading_progress = ctk.CTkProgressBar(overlay, mode="indeterminate", height=8, fg_color=COLOR_SECONDARY, progress_color=COLOR_PRIMARY)
        self.loading_progress.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 18))
        self.loading_overlay = overlay
        self.loading_overlay.place_forget()

    def _show_loading(self, message: str) -> None:
        self.loading_var.set(message)
        if self.loading_overlay is not None:
            self.loading_overlay.place(relx=0.5, rely=0.5, anchor="center")
            self.loading_overlay.lift()
        if self.loading_progress is not None:
            self.loading_progress.start()
        self.root.update_idletasks()

    def _update_loading(self, message: str) -> None:
        self.loading_var.set(message)
        if self.loading_overlay is not None:
            self.loading_overlay.lift()
        self.root.update_idletasks()

    def _hide_loading(self) -> None:
        if self.loading_progress is not None:
            self.loading_progress.stop()
        if self.loading_overlay is not None:
            self.loading_overlay.place_forget()
        self.root.update_idletasks()

    def _run_background(self, loading_message: str, work, on_success, on_error=None, on_finally=None) -> None:
        if self.busy:
            self.status_var.set("処理中です。完了までお待ちください。")
            return
        self.busy = True
        self._show_loading(loading_message)

        def finish_success(result) -> None:
            try:
                on_success(result)
            finally:
                finish_common()

        def finish_error(error: Exception) -> None:
            try:
                if on_error is not None:
                    on_error(error)
                else:
                    messagebox.showerror("処理エラー", str(error))
            finally:
                finish_common()

        def finish_common() -> None:
            try:
                if on_finally is not None:
                    on_finally()
            finally:
                self.busy = False
                self._hide_loading()

        def worker() -> None:
            try:
                result = work()
            except Exception as exc:
                self.root.after(0, lambda error=exc: finish_error(error))
            else:
                self.root.after(0, lambda value=result: finish_success(value))

        threading.Thread(target=worker, daemon=True).start()

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-Left>", self.previous_image)
        self.root.bind_all("<Control-Right>", self.next_image)
        self.root.bind_all("<Control-s>", self.save_template)
        self.root.bind_all("<Control-o>", self.load_template)
        self.root.bind_all("<Control-Return>", self.export_to_excel)
        self.root.bind_all("<Alt-Up>", self.move_selected_field_up)
        self.root.bind_all("<Alt-Down>", self.move_selected_field_down)
        self.root.bind_all("<Escape>", self.undo_last_action)
        self.root.bind_all("<Control-z>", self.undo_last_action)
        self.root.bind_all("<Control-Z>", self.undo_last_action)

    def _on_mode_change(self, _value: str | None = None) -> None:
        self._render_side_body()
        self.redraw()

    def _render_side_body(self) -> None:
        if self.side_body is None:
            return
        for child in self.side_body.winfo_children():
            child.destroy()
        self.field_row_by_index = {}
        self.review_order_label_by_index = {}
        self.review_summary_label_by_index = {}
        self.review_detail_host = None
        self.correction_rules_host = None
        self._sync_counts()
        mode = self.mode_var.get()
        if mode == MODE_TEMPLATE:
            self._render_template_mode()
        elif mode == MODE_REVIEW:
            self._render_review_mode()
        else:
            self._render_export_mode()

    def _render_template_mode(self) -> None:
        body = self.side_body
        assert body is not None
        self.field_check_vars = []
        self.field_row_widgets = []
        self.field_row_by_index = {}
        action_row = ctk.CTkFrame(body, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(2, 8))
        action_row.grid_columnconfigure(0, weight=1)
        action_row.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(action_row, text=f"{ICON_OPEN} 読込", command=self.load_template, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HOVER).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(action_row, text=f"{ICON_SAVE} 保存", command=self.save_template, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(body, textvariable=self.template_var, anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED, wraplength=340).pack(fill="x", padx=16, pady=(0, 8))

        scroller = ctk.CTkScrollableFrame(body, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE_ALT, border_width=1, border_color=COLOR_BORDER)
        scroller.pack(side=TOP, fill=BOTH, expand=True, padx=16, pady=(0, 10))
        if not self.fields:
            self._empty_state(scroller, "項目がありません", "画像上で範囲をドラッグ")
        else:
            for idx, field in enumerate(self.fields):
                self._field_row(scroller, idx)

    def _render_review_mode(self) -> None:
        side_body = self.side_body
        assert side_body is not None
        body = ctk.CTkFrame(side_body, corner_radius=0, fg_color=COLOR_SURFACE)
        body.pack(fill=BOTH, expand=True)

        scroller = ctk.CTkFrame(body, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE_ALT, border_width=1, border_color=COLOR_BORDER)
        scroller.pack(side=TOP, fill="x", padx=16, pady=(2, 10))
        if not self.fields:
            self._empty_state(scroller, "テンプレートがありません", "先に読み取り項目を作成")
            return
        if not self.original_image:
            self._empty_state(scroller, "画像がありません", "画像フォルダを選択")
            return

        self._ensure_result_buffers()
        self._ensure_review_selection()
        self.result_vars = []
        for idx, field in enumerate(self.fields):
            if not field.enabled:
                continue
            self._review_result_row(scroller, idx)

        self.review_detail_host = ctk.CTkFrame(body, corner_radius=0, fg_color=COLOR_SURFACE)
        self.review_detail_host.pack(fill="x")
        self._render_postprocess_panel(self.review_detail_host)

    def _review_result_row(self, parent, idx: int) -> None:
        field = self.fields[idx]
        selected = idx == self.selected_index
        row = ctk.CTkFrame(parent, corner_radius=THEME.layout.panel_radius, fg_color=THEME.palette.selected_row if selected else COLOR_SURFACE, border_width=1, border_color=COLOR_PRIMARY if selected else COLOR_BORDER)
        row.pack(fill="x", padx=8, pady=4)
        self.field_row_by_index[idx] = row
        row.grid_columnconfigure(1, weight=1)

        order_label = ctk.CTkLabel(row, text=self._field_order_label(idx), width=42, height=22, font=UI_FONT_SMALL, fg_color=COLOR_PRIMARY if selected else COLOR_SECONDARY, text_color=THEME.palette.on_color, corner_radius=4)
        order_label.grid(row=0, column=0, sticky="w", padx=(8, 8), pady=8)
        self.review_order_label_by_index[idx] = order_label
        ctk.CTkLabel(row, text=field.name, anchor="w", font=UI_FONT_BOLD, text_color=COLOR_TEXT).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=8)
        summary_label = ctk.CTkLabel(row, text=self._postprocess_summary(field), anchor="e", font=UI_FONT_SMALL, text_color=COLOR_MUTED)
        summary_label.grid(row=0, column=2, sticky="e", padx=(0, 8), pady=8)
        self.review_summary_label_by_index[idx] = summary_label

        for widget in [row, *row.winfo_children()]:
            widget.bind("<Button-1>", lambda _event, i=idx: self.select_review_field(i))

    def _render_postprocess_panel(self, parent) -> None:
        idx = self.selected_index
        if idx is None or not (0 <= idx < len(self.fields)) or not self.fields[idx].enabled:
            self._empty_state(parent, "確認対象がありません", "有効な項目を選択")
            return

        panel = ctk.CTkFrame(parent, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE_ALT, border_width=1, border_color=COLOR_BORDER)
        panel.pack(fill="x", padx=16, pady=(0, 12))
        panel.grid_columnconfigure(1, weight=1)

        self._update_review_detail_values()
        self._result_preview(panel)

        ctk.CTkLabel(panel, text="OCR方式", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED).grid(row=1, column=0, sticky="w", padx=(12, 8), pady=2)
        ctk.CTkOptionMenu(panel, variable=self.review_line_split_var, values=OCR_MODE_OPTIONS, command=self.set_selected_field_line_split, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SECONDARY, button_color=COLOR_PRIMARY, button_hover_color=COLOR_PRIMARY_HOVER, dropdown_fg_color=COLOR_SURFACE_ALT, dropdown_hover_color=COLOR_SECONDARY_HOVER, text_color=COLOR_TEXT).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=2)
        ctk.CTkButton(panel, text=f"{ICON_RUN} OCR実行", command=self.ocr_selected_field, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 12))

    def _result_preview(self, parent) -> None:
        preview = ctk.CTkFrame(parent, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE, border_width=1, border_color=COLOR_BORDER)
        preview.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        preview.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(preview, text="生OCR", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED).grid(row=0, column=0, sticky="nw", padx=(8, 8), pady=(5, 0))
        ctk.CTkLabel(preview, textvariable=self.review_raw_preview_var, anchor="w", justify="left", font=UI_FONT_SMALL, text_color=COLOR_TEXT, wraplength=270).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=5)

    # Future correction-rule editor scaffold.
    # Intentionally not rendered from _render_review_mode while the UX is being redesigned.
    # Do not remove without also removing CorrectionRule serialization and OCR plumbing.
    def _render_correction_rules_panel(self) -> None:
        host = self.correction_rules_host
        if host is None or not host.winfo_exists():
            return
        for child in host.winfo_children():
            child.destroy()

        panel = ctk.CTkFrame(host, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE_ALT, border_width=1, border_color=COLOR_BORDER)
        panel.pack(fill="x", padx=16, pady=(0, 12))
        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="補正ルール", anchor="w", font=UI_FONT_BOLD, text_color=COLOR_TEXT).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(header, text=self._accordion_icon(), command=self.toggle_correction_rules_panel, width=30, height=28, font=UI_FONT_BOLD, fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HOVER).grid(row=0, column=1, sticky="e")

        self._correction_result_preview(panel)
        if not self.correction_rules_expanded:
            return
        if not self.correction_rules:
            note = ctk.CTkFrame(panel, fg_color=COLOR_SURFACE, corner_radius=THEME.layout.panel_radius)
            note.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkLabel(note, text="OCRの誤認を置換で補正します。例: ョンで → ヨン", anchor="w", justify="left", font=UI_FONT_SMALL, text_color=COLOR_MUTED, wraplength=310).pack(fill="x", padx=10, pady=10)
            self._correction_add_button(panel)
            return

        scroller = ctk.CTkScrollableFrame(panel, height=190, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE, border_width=1, border_color=COLOR_BORDER)
        scroller.pack(fill=BOTH, expand=True, padx=12, pady=(0, 8))
        for idx, rule in enumerate(self.correction_rules):
            self._correction_rule_row(scroller, idx, rule)
        self._correction_add_button(panel)

    def _accordion_icon(self) -> str:
        return "v" if self.correction_rules_expanded else ">"

    def _correction_result_preview(self, parent) -> None:
        preview = ctk.CTkFrame(parent, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE, border_width=1, border_color=COLOR_BORDER)
        preview.pack(fill="x", padx=12, pady=(0, 8))
        preview.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(preview, text="補正後", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED).grid(row=0, column=0, sticky="nw", padx=(8, 8), pady=7)
        ctk.CTkLabel(preview, textvariable=self.review_processed_preview_var, anchor="w", justify="left", font=UI_FONT_SMALL, text_color=COLOR_TEXT, wraplength=270).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=7)

    def toggle_correction_rules_panel(self) -> None:
        self.correction_rules_expanded = not self.correction_rules_expanded
        self._render_correction_rules_panel()

    def _correction_add_button(self, parent) -> None:
        ctk.CTkButton(parent, text="+ ルールを追加", command=self.add_correction_rule, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER).pack(fill="x", padx=12, pady=(0, 12))

    def _correction_rule_row(self, parent, idx: int, rule: CorrectionRule) -> None:
        row = ctk.CTkFrame(parent, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE_ALT, border_width=1, border_color=COLOR_BORDER)
        row.pack(fill="x", padx=6, pady=5)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, weight=1)

        enabled_var = BooleanVar(value=rule.enabled)
        ctk.CTkCheckBox(row, text="", variable=enabled_var, width=26, command=lambda i=idx, v=enabled_var: self.set_correction_rule_enabled(i, v.get())).grid(row=0, column=0, rowspan=2, sticky="nw", padx=(8, 0), pady=9)

        target_var = StringVar(value=rule.target if rule.target in self._correction_target_options() else CORRECTION_ALL_TARGET)
        ctk.CTkOptionMenu(row, variable=target_var, values=self._correction_target_options(), command=lambda value, i=idx: self.set_correction_rule_target(i, value), height=28, width=104, font=UI_FONT_SMALL, fg_color=COLOR_SECONDARY, button_color=COLOR_PRIMARY, button_hover_color=COLOR_PRIMARY_HOVER, dropdown_fg_color=COLOR_SURFACE_ALT, dropdown_hover_color=COLOR_SECONDARY_HOVER, text_color=COLOR_TEXT).grid(row=0, column=1, sticky="ew", padx=(8, 4), pady=(8, 3))
        ctk.CTkButton(row, text="削除", command=lambda i=idx: self.delete_correction_rule(i), width=52, height=28, font=UI_FONT_SMALL, fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER).grid(row=0, column=2, sticky="e", padx=(4, 8), pady=(8, 3))

        pattern_var = StringVar(value=rule.pattern)
        replacement_var = StringVar(value=rule.replacement)
        pattern_var.trace_add("write", lambda *_args, i=idx, v=pattern_var: self.set_correction_rule_text(i, "pattern", v.get()))
        replacement_var.trace_add("write", lambda *_args, i=idx, v=replacement_var: self.set_correction_rule_text(i, "replacement", v.get()))
        self.result_vars.extend([target_var, pattern_var, replacement_var])
        ctk.CTkEntry(row, textvariable=pattern_var, placeholder_text="置換前", height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SURFACE, border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=(3, 8))
        ctk.CTkEntry(row, textvariable=replacement_var, placeholder_text="置換後", height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SURFACE, border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=1, column=2, sticky="ew", padx=(4, 8), pady=(3, 8))

    def _correction_target_options(self) -> list[str]:
        options = [CORRECTION_ALL_TARGET]
        for field in self.fields:
            if field.name not in options:
                options.append(field.name)
        return options

    def add_correction_rule(self) -> None:
        target = self.fields[self.selected_index].name if self.selected_index is not None and 0 <= self.selected_index < len(self.fields) else CORRECTION_ALL_TARGET
        self.correction_rules.append(CorrectionRule("", "", target, True))
        self.correction_rules_expanded = True
        self.status_var.set("補正ルールを追加しました。")
        self._render_correction_rules_panel()

    def delete_correction_rule(self, idx: int) -> None:
        if not (0 <= idx < len(self.correction_rules)):
            return
        del self.correction_rules[idx]
        self._apply_correction_rules_to_current_results()
        self.status_var.set("補正ルールを削除しました。")
        self._render_correction_rules_panel()

    def set_correction_rule_enabled(self, idx: int, enabled: bool) -> None:
        if not (0 <= idx < len(self.correction_rules)):
            return
        self.correction_rules[idx].enabled = enabled
        self._on_correction_rules_changed()

    def set_correction_rule_target(self, idx: int, target: str) -> None:
        if not (0 <= idx < len(self.correction_rules)):
            return
        self.correction_rules[idx].target = target if target in self._correction_target_options() else CORRECTION_ALL_TARGET
        self._on_correction_rules_changed()

    def set_correction_rule_text(self, idx: int, attr: str, value: str) -> None:
        if not (0 <= idx < len(self.correction_rules)) or attr not in {"pattern", "replacement"}:
            return
        setattr(self.correction_rules[idx], attr, value)
        self._on_correction_rules_changed()

    def _on_correction_rules_changed(self) -> None:
        self._apply_correction_rules_to_current_results()
        self.status_var.set("補正ルールを更新しました。OCR結果に反映されます。")

    def _apply_correction_rules_to_current_results(self) -> None:
        self._ensure_result_buffers()
        for idx, field in enumerate(self.fields):
            raw_text = self.current_raw_results[idx] if idx < len(self.current_raw_results) else ""
            if raw_text:
                corrected = apply_correction_rules(raw_text, field, self.correction_rules)
                self.current_results[idx] = apply_postprocess(corrected, field)
            self._refresh_review_row(idx)
        self._update_review_detail_values()

    def _compact_preview_text(self, value: str, limit: int = 34) -> str:
        value = " ".join(value.split())
        return value if len(value) <= limit else f"{value[:limit - 3]}..."

    def _postprocess_summary(self, field: TemplateField) -> str:
        parts = [self._line_split_display(field.ocr_line_split)]
        if self._has_legacy_postprocess(field):
            parts.append("補正あり")
        return " / ".join(parts)

    def _has_legacy_postprocess(self, field: TemplateField) -> bool:
        return bool(
            field.replace_from
            or field.remove_text
            or (field.postprocess and field.postprocess != "そのまま")
            or self._has_correction_rule_for_field(field)
        )

    def _has_correction_rule_for_field(self, field: TemplateField) -> bool:
        return any(
            rule.enabled and rule.pattern and rule.target in {CORRECTION_ALL_TARGET, field.name}
            for rule in self.correction_rules
        )

    def _line_split_display(self, value: str) -> str:
        return "行切り出し" if value == "detected" else "範囲全体"

    def _line_split_value(self, display: str) -> str:
        return "detected" if display == "行切り出し" else "none"

    def select_review_field(self, idx: int) -> str:
        if not (0 <= idx < len(self.fields)):
            return "break"
        self._select_field_index(idx, update_review_detail=True)
        return "break"

    def set_selected_field_line_split(self, value: str) -> None:
        if self.selected_index is None:
            return
        self.set_field_line_split(self.selected_index, value)

    def set_field_line_split(self, idx: int, value: str) -> None:
        if not (0 <= idx < len(self.fields)):
            return
        field = self.fields[idx]
        field.ocr_line_split = self._line_split_value(value)
        if idx < len(self.current_results):
            self.current_results[idx] = ""
        if idx < len(self.current_raw_results):
            self.current_raw_results[idx] = ""
        self.status_var.set(f"{field.name} のOCR方式を {self._line_split_display(field.ocr_line_split)} に変更しました。")
        self._update_review_detail_values()
        self._refresh_review_row(idx)
        self.redraw()

    def _render_export_mode(self) -> None:
        body = self.side_body
        assert body is not None

        content = ctk.CTkFrame(body, corner_radius=0, fg_color=COLOR_SURFACE)
        content.pack(side=TOP, fill=BOTH, expand=True)

        panel = ctk.CTkFrame(content, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE_ALT, border_width=1, border_color=COLOR_BORDER)
        panel.pack(fill="x", padx=16, pady=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(panel, text="画像フォルダ", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_TEXT).grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=(12, 2))
        ctk.CTkLabel(panel, textvariable=self.folder_var, anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED, wraplength=210).grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(0, 8))
        ctk.CTkButton(panel, text=f"{ICON_OPEN} 変更", command=self.open_image_folder, width=116, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HOVER).grid(row=0, column=1, rowspan=2, sticky="e", padx=(0, 12), pady=(12, 8))
        ctk.CTkLabel(panel, text="出力ファイル", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_TEXT).grid(row=2, column=0, sticky="ew", padx=(12, 8), pady=(2, 2))
        ctk.CTkLabel(panel, textvariable=self.output_var, anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED, wraplength=210).grid(row=3, column=0, sticky="ew", padx=(12, 8), pady=(0, 12))
        ctk.CTkButton(panel, text=f"{ICON_SAVE} 選択", command=self.select_output_file, width=116, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HOVER).grid(row=2, column=1, rowspan=2, sticky="e", padx=(0, 12), pady=(2, 12))

        self._render_excel_output_settings(content)

        enabled_count = len(self._enabled_fields())
        image_count = len(self.image_files)
        summary_text = f"{image_count}画像 / {enabled_count}項目 / {self._export_column_summary()}"
        ctk.CTkLabel(content, text=summary_text, anchor="w", justify="left", font=UI_FONT_SMALL, text_color=COLOR_MUTED, wraplength=330).pack(fill="x", padx=18, pady=(0, 12))

        ctk.CTkButton(body, text=f"{ICON_EXCEL} Excel出力", command=self.export_to_excel, height=THEME.layout.export_button_height, font=UI_FONT_BOLD, fg_color=COLOR_CTA, hover_color=COLOR_CTA_HOVER).pack(side=BOTTOM, fill="x", padx=16, pady=(8, 14))

    def _render_excel_output_settings(self, parent) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE_ALT, border_width=1, border_color=COLOR_BORDER)
        panel.pack(fill="x", padx=16, pady=(0, 10))
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(panel, text="シート名", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(12, 4))
        ctk.CTkEntry(panel, textvariable=self.export_sheet_var, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SURFACE, border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 4))

        ctk.CTkLabel(panel, text="書き込み", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED).grid(row=1, column=0, sticky="w", padx=(12, 8), pady=4)
        ctk.CTkOptionMenu(panel, variable=self.export_write_mode_var, values=["上書き", "追記"], height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SECONDARY, button_color=COLOR_PRIMARY, button_hover_color=COLOR_PRIMARY_HOVER, dropdown_fg_color=COLOR_SURFACE_ALT, dropdown_hover_color=COLOR_SECONDARY_HOVER, text_color=COLOR_TEXT).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=4)

        ctk.CTkLabel(panel, text="開始セル", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED).grid(row=2, column=0, sticky="w", padx=(12, 8), pady=4)
        ctk.CTkEntry(panel, textvariable=self.export_start_cell_var, height=THEME.layout.entry_height, font=UI_FONT_SMALL, fg_color=COLOR_SURFACE, border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=4)

        ctk.CTkCheckBox(panel, text="ファイル名列", variable=self.export_include_filename_var, command=self._render_side_body, font=UI_FONT_SMALL, text_color=COLOR_TEXT, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER).grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))
        ctk.CTkCheckBox(panel, text="ヘッダー行", variable=self.export_include_header_var, command=self._render_side_body, font=UI_FONT_SMALL, text_color=COLOR_TEXT, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER).grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(2, 12))

    def _export_column_summary(self) -> str:
        columns = "ファイル名列あり" if self.export_include_filename_var.get() else "項目のみ"
        header = "ヘッダーあり" if self.export_include_header_var.get() else "ヘッダーなし"
        return f"{columns} / {header}"

    def _empty_state(self, parent, title: str, note: str) -> None:
        box = ctk.CTkFrame(parent, fg_color=COLOR_SURFACE_ALT, corner_radius=THEME.layout.panel_radius)
        box.pack(fill=BOTH, expand=True, padx=12, pady=20)
        ctk.CTkLabel(box, text=title, font=UI_FONT_BOLD, text_color=COLOR_TEXT).pack(pady=(28, 4))
        ctk.CTkLabel(box, text=note, font=UI_FONT_SMALL, text_color=COLOR_MUTED).pack(pady=(0, 28))

    def _field_row(self, parent, idx: int) -> None:
        field = self.fields[idx]
        selected = idx == self.selected_index
        row = ctk.CTkFrame(parent, corner_radius=THEME.layout.panel_radius, fg_color=THEME.palette.selected_row if selected else COLOR_SURFACE, border_width=1, border_color=COLOR_PRIMARY if selected else COLOR_BORDER)
        row.pack(fill="x", padx=8, pady=5)
        self.field_row_widgets.append(row)
        self.field_row_by_index[idx] = row
        row.grid_columnconfigure(2, weight=1)
        var = BooleanVar(value=field.enabled)
        self.field_check_vars.append(var)
        ctk.CTkCheckBox(row, text="", variable=var, width=28, command=lambda i=idx, v=var: self.set_field_enabled(i, v.get())).grid(row=0, column=0, rowspan=2, padx=(8, 0), pady=8)
        ctk.CTkLabel(row, text=self._field_order_label(idx), width=42, height=22, font=UI_FONT_SMALL, fg_color=COLOR_PRIMARY if field.enabled else THEME.palette.disabled_fill, text_color=THEME.palette.on_color, corner_radius=4).grid(row=0, column=1, sticky="w", padx=(4, 6), pady=(8, 2))
        name_widget = self._field_name_widget(row, idx)
        name_widget.grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(8, 2))
        badge_color = THEME.palette.line_badge if field.ocr_line_split == "detected" and field.enabled else COLOR_SECONDARY
        ctk.CTkLabel(row, text=self._line_split_display(field.ocr_line_split), width=78, height=22, font=UI_FONT_SMALL, fg_color=badge_color, text_color=THEME.palette.on_color, corner_radius=4).grid(row=0, column=3, sticky="e", padx=(0, 6), pady=(8, 2))
        detail_label = ctk.CTkLabel(row, text=self._field_size_text(field), anchor="w", font=UI_FONT_SMALL, text_color=COLOR_MUTED)
        detail_label.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(4, 8), pady=(0, 8))
        drag_handle = ctk.CTkLabel(row, text="☰", width=30, font=UI_FONT_BOLD, text_color=COLOR_MUTED)
        drag_handle.grid(row=0, column=4, rowspan=2, sticky="e", padx=(0, 8), pady=8)
        drag_handle.bind("<ButtonPress-1>", lambda event, i=idx: self.start_field_drag(event, i))
        drag_handle.bind("<B1-Motion>", lambda event, i=idx: self.update_field_drag(event, i))
        drag_handle.bind("<ButtonRelease-1>", lambda event, i=idx: self.finish_field_drag(event, i))
        drag_handle.bind("<Button-3>", lambda event, i=idx: self.show_field_context_menu(event, i))
        interactive_children = [child for child in row.winfo_children() if child is not name_widget and child is not drag_handle]
        for widget in interactive_children + [row]:
            widget.bind("<Button-1>", lambda _event, i=idx: self.select_field(i))
            widget.bind("<Button-3>", lambda event, i=idx: self.show_field_context_menu(event, i))
        name_widget.bind("<Button-3>", lambda event, i=idx: self.show_field_context_menu(event, i))
        if self.editing_name_index != idx:
            name_widget.bind("<Button-1>", lambda _event, i=idx: self.select_field(i))
            name_widget.bind("<Double-Button-1>", lambda _event, i=idx: self.begin_inline_name_edit(i))

    def _field_name_widget(self, parent, idx: int):
        field = self.fields[idx]
        if self.editing_name_index != idx:
            return ctk.CTkLabel(parent, text=field.name, anchor="w", font=UI_FONT_BOLD, text_color=COLOR_TEXT if field.enabled else COLOR_MUTED)

        name_var = StringVar(value=field.name)
        entry = ctk.CTkEntry(parent, textvariable=name_var, height=THEME.layout.entry_height, font=UI_FONT_BOLD, fg_color=COLOR_SURFACE_ALT, border_color=COLOR_PRIMARY, text_color=COLOR_TEXT)
        entry.bind("<Return>", lambda _event, i=idx, v=name_var: self.commit_inline_name_edit(i, v.get()))
        entry.bind("<Escape>", lambda _event: self.cancel_inline_name_edit())
        entry.bind("<FocusOut>", lambda _event, i=idx, v=name_var: self.commit_inline_name_edit(i, v.get()))
        entry.after(10, lambda widget=entry: (widget.focus_set(), widget.select_range(0, "end")))
        return entry

    def open_image_folder(self) -> None:
        folder_name = filedialog.askdirectory(title="画像フォルダを選択")
        if not folder_name:
            return
        folder = Path(folder_name)
        files = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
        if not files:
            messagebox.showinfo("画像なし", "選択したフォルダ内に対応画像がありません。")
            return
        self.source_folder = folder
        self.image_files = files
        self.folder_var.set(self._folder_status_text())
        self.current_image_index = 0
        self._load_current_image(auto_ocr=False)
        if self.fields and self.mode_var.get() == MODE_TEMPLATE:
            self.mode_var.set(MODE_REVIEW)
        self._render_side_body()

    def previous_image(self, _event=None) -> None:
        if len(self.image_files) <= 1:
            return
        self.current_image_index = (self.current_image_index - 1) % len(self.image_files)
        self._load_current_image(auto_ocr=False)
        self._render_side_body()

    def next_image(self, _event=None) -> None:
        if len(self.image_files) <= 1:
            return
        self.current_image_index = (self.current_image_index + 1) % len(self.image_files)
        self._load_current_image(auto_ocr=False)
        self._render_side_body()

    def _load_current_image(self, auto_ocr: bool) -> None:
        if not (0 <= self.current_image_index < len(self.image_files)):
            return
        self.image_path = self.image_files[self.current_image_index]
        try:
            self.original_image = Image.open(self.image_path).convert("RGB")
        except Exception as exc:
            messagebox.showerror("画像エラー", f"画像を開けませんでした。\n{exc}")
            return
        fill_missing_field_source_size(self.fields, self.original_image.size)
        self.zoom = self._initial_zoom()
        self.current_results = [""] * len(self.fields)
        self.current_raw_results = [""] * len(self.fields)
        self.image_var.set(self._image_status_text())
        self.image_count_var.set(f"{self.current_image_index + 1} / {len(self.image_files)}")
        self.selected_index = self.selected_index if self.fields else None
        self.canvas_edit_state = None
        self.undo_action = None
        self.redraw()
        if auto_ocr:
            self._show_loading("OCRを準備しています。初回はモデル読み込みに時間がかかります。")
            try:
                self._ocr_all_current(show_errors=False)
            finally:
                self._hide_loading()
        if auto_ocr:
            self.status_var.set("画像を読み込みました。読み取り結果を確認できます。")
        else:
            self.status_var.set("画像を読み込みました。OCR確認タブでOCRを実行できます。")

    def _image_status_text(self) -> str:
        if not self.image_path:
            return "画像未選択"
        return self.image_path.name

    def _folder_status_text(self) -> str:
        if not self.source_folder:
            return "未選択"
        return f"{self.source_folder.name} / {len(self.image_files)}画像"

    def select_output_file(self) -> None:
        file_name = filedialog.asksaveasfilename(
            title="Excel出力先を選択",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not file_name:
            return
        self.output_path = Path(file_name)
        self.output_var.set(self.output_path.name)
        self._render_side_body()

    def save_template(self, _event=None) -> None:
        if not self.fields:
            messagebox.showinfo("項目なし", "保存する読み取り項目がありません。")
            return
        initial = self.template_path.name if self.template_path else THEME.copy.default_template_name
        file_name = filedialog.asksaveasfilename(
            title="テンプレートを保存",
            initialfile=initial,
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not file_name:
            return
        path = Path(file_name)
        if self.original_image:
            fill_missing_field_source_size(self.fields, self.original_image.size)
        data = build_template_data(
            fields=self.fields,
            lang=self.lang_var.get(),
            tesseract_path=self.tesseract_var.get(),
            ocr_backend=self.backend_var.get(),
            output_settings=self._export_settings_dict(),
            correction_rules=self.correction_rules,
            template_name=path.stem,
            profile_id=PROFILE_ID,
        )
        save_template(path, data)
        self.template_path = path
        self.template_var.set(path.name)
        self.status_var.set(f"テンプレートを保存しました: {path.name}")
        self._render_side_body()

    def load_template(self, _event=None) -> None:
        file_name = filedialog.askopenfilename(
            title="テンプレートを読み込み",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not file_name:
            return
        path = Path(file_name)
        try:
            data = load_template(path)
            fields = fields_from_template(data)
        except Exception as exc:
            messagebox.showerror("テンプレートエラー", f"テンプレートを読み込めませんでした。\n{exc}")
            return
        if not fields:
            messagebox.showerror("テンプレートエラー", "読み取り項目がありません。")
            return
        self.fields = fields
        self.correction_rules = correction_rules_from_template(data)
        self.current_results = [""] * len(self.fields)
        self.current_raw_results = [""] * len(self.fields)
        self.selected_index = 0
        self.undo_action = None
        self.template_path = path
        self.template_var.set(path.name)
        self.lang_var.set(data.get("lang") or DEFAULT_LANG)
        self.lang_display_var.set(self._lang_display(self.lang_var.get()))
        backend = str(data.get("ocr_backend") or DEFAULT_BACKEND)
        self.backend_var.set(backend if backend in OCR_BACKEND_OPTIONS and backend != "default" else DEFAULT_BACKEND)
        self._apply_output_settings(data.get("output_settings") or {})
        if data.get("tesseract_path"):
            self.tesseract_var.set(data["tesseract_path"])
        self.status_var.set(f"テンプレートを読み込みました: {path.name}")
        self._render_side_body()
        self.redraw()

    def open_settings_modal(self) -> None:
        self.lang_display_var.set(self._lang_display(self.lang_var.get()))
        window = ctk.CTkToplevel(self.root)
        window.title("設定")
        window.geometry(THEME.layout.settings_size)
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        window.configure(fg_color=COLOR_BG)

        panel = ctk.CTkFrame(window, corner_radius=THEME.layout.panel_radius, fg_color=COLOR_SURFACE, border_width=1, border_color=COLOR_BORDER)
        panel.pack(fill=BOTH, expand=True, padx=18, pady=18)
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(panel, text="OCR設定", anchor="w", font=UI_FONT_TITLE, text_color=COLOR_TEXT).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 14))
        ctk.CTkLabel(panel, text="OCR言語", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_TEXT).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        ctk.CTkComboBox(
            panel,
            variable=self.lang_display_var,
            values=["日本語 + English", "日本語のみ", "English のみ"],
            command=self._sync_lang_from_display,
            height=THEME.layout.entry_height,
            font=UI_FONT,
            dropdown_font=UI_FONT,
            fg_color=COLOR_SURFACE_ALT,
            border_color=COLOR_BORDER,
            button_color=COLOR_PRIMARY,
            button_hover_color=COLOR_PRIMARY_HOVER,
            text_color=COLOR_TEXT,
        ).grid(row=2, column=0, sticky="ew", padx=16)
        ctk.CTkLabel(panel, text="OCRバックエンド", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_TEXT).grid(row=3, column=0, sticky="ew", padx=16, pady=(14, 6))
        tesseract_frame = ctk.CTkFrame(panel, fg_color="transparent")

        def sync_backend_fields(_value: str | None = None) -> None:
            if self.backend_var.get() == "tesseract":
                tesseract_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(14, 0))
            else:
                tesseract_frame.grid_remove()

        ctk.CTkOptionMenu(panel, variable=self.backend_var, values=[value for value in OCR_BACKEND_OPTIONS if value != "default"], command=sync_backend_fields, height=THEME.layout.entry_height, font=UI_FONT, fg_color=COLOR_SECONDARY, button_color=COLOR_PRIMARY, button_hover_color=COLOR_PRIMARY_HOVER, dropdown_fg_color=COLOR_SURFACE_ALT, dropdown_hover_color=COLOR_SECONDARY_HOVER, text_color=COLOR_TEXT).grid(row=4, column=0, sticky="ew", padx=16)
        tesseract_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tesseract_frame, text="Tesseractパス", anchor="w", font=UI_FONT_SMALL, text_color=COLOR_TEXT).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkEntry(tesseract_frame, textvariable=self.tesseract_var, height=THEME.layout.entry_height, font=UI_FONT, fg_color=COLOR_SURFACE_ALT, border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=1, column=0, sticky="ew")
        sync_backend_fields()
        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.grid(row=7, column=0, sticky="ew", padx=16, pady=(20, 16))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(buttons, text="キャンセル", command=window.destroy, height=THEME.layout.row_button_height, font=UI_FONT, fg_color=COLOR_SURFACE, hover_color=THEME.palette.modal_button_hover, border_width=1, border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(buttons, text="保存", command=lambda: self._apply_settings(window), height=THEME.layout.row_button_height, font=UI_FONT, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _apply_settings(self, window: ctk.CTkToplevel) -> None:
        self._sync_lang_from_display()
        if self.backend_var.get() not in OCR_BACKEND_OPTIONS or self.backend_var.get() == "default":
            self.backend_var.set(DEFAULT_BACKEND)
        self.status_var.set("OCR設定を更新しました。")
        window.destroy()

    def select_field(self, idx: int) -> None:
        if not (0 <= idx < len(self.fields)):
            return
        self._select_field_index(idx, update_review_detail=False)

    def _select_field_index(self, idx: int, update_review_detail: bool, redraw_canvas: bool = True) -> None:
        if not (0 <= idx < len(self.fields)):
            return
        if self.selected_index == idx:
            return
        self.selected_index = idx
        self._refresh_selection_rows()
        if update_review_detail and self.mode_var.get() == MODE_REVIEW:
            self._refresh_review_detail_panel()
        if redraw_canvas:
            self.redraw()

    def _refresh_selection_rows(self) -> None:
        for idx, row in list(self.field_row_by_index.items()):
            try:
                if not row.winfo_exists():
                    continue
                self._refresh_review_row(idx)
            except Exception:
                continue

    def _refresh_review_row(self, idx: int) -> None:
        row = self.field_row_by_index.get(idx)
        if row is not None and row.winfo_exists():
            selected = idx == self.selected_index
            row.configure(
                fg_color=THEME.palette.selected_row if selected else COLOR_SURFACE,
                border_color=COLOR_PRIMARY if selected else COLOR_BORDER,
            )
        order_label = self.review_order_label_by_index.get(idx)
        if order_label is not None and order_label.winfo_exists():
            order_label.configure(fg_color=COLOR_PRIMARY if idx == self.selected_index else COLOR_SECONDARY)
        summary = self.review_summary_label_by_index.get(idx)
        if summary is not None and summary.winfo_exists() and 0 <= idx < len(self.fields):
            summary.configure(text=self._postprocess_summary(self.fields[idx]))

    def _refresh_review_detail_panel(self) -> None:
        if self.review_detail_host is None or not self.review_detail_host.winfo_exists():
            return
        self._update_review_detail_values()

    def _update_review_detail_values(self) -> None:
        idx = self.selected_index
        if idx is None or not (0 <= idx < len(self.fields)):
            self.review_raw_preview_var.set("未OCR")
            self.review_processed_preview_var.set("未OCR")
            self.review_line_split_var.set(OCR_MODE_OPTIONS[0])
            return
        field = self.fields[idx]
        self._ensure_result_buffers()
        self.review_raw_preview_var.set(self._compact_preview_text(self.current_raw_results[idx] or "未OCR"))
        self.review_processed_preview_var.set(self._compact_preview_text(self.current_results[idx] or "未OCR"))
        self.review_line_split_var.set(self._line_split_display(field.ocr_line_split))

    def set_field_enabled(self, idx: int, enabled: bool) -> None:
        if 0 <= idx < len(self.fields):
            self.fields[idx].enabled = enabled
            self._sync_counts()
            self.redraw()

    def move_selected_field_up(self, _event=None) -> None:
        self.move_selected_field(-1)

    def move_selected_field_down(self, _event=None) -> None:
        self.move_selected_field(1)

    def move_selected_field(self, direction: int) -> None:
        idx = self._require_field_selection()
        if idx is None:
            return
        self.move_field(idx, direction)

    def move_field(self, idx: int, direction: int) -> None:
        if not (0 <= idx < len(self.fields)):
            return
        self.editing_name_index = None
        new_idx = idx + direction
        if not (0 <= new_idx < len(self.fields)):
            return
        self._ensure_current_results()
        self.fields[idx], self.fields[new_idx] = self.fields[new_idx], self.fields[idx]
        self.current_results[idx], self.current_results[new_idx] = self.current_results[new_idx], self.current_results[idx]
        self.current_raw_results[idx], self.current_raw_results[new_idx] = self.current_raw_results[new_idx], self.current_raw_results[idx]
        self.selected_index = new_idx
        self.status_var.set("項目順を変更しました。Excel出力の列順にも反映されます。")
        self._render_side_body()
        self.redraw()

    def move_field_to(self, source_idx: int, target_idx: int) -> None:
        if not (0 <= source_idx < len(self.fields)):
            return
        target_idx = max(0, min(len(self.fields) - 1, target_idx))
        if source_idx == target_idx:
            self.selected_index = source_idx
            self._render_side_body()
            self.redraw()
            return
        self._ensure_current_results()
        field = self.fields.pop(source_idx)
        result = self.current_results.pop(source_idx)
        raw_result = self.current_raw_results.pop(source_idx)
        self.fields.insert(target_idx, field)
        self.current_results.insert(target_idx, result)
        self.current_raw_results.insert(target_idx, raw_result)
        self.selected_index = target_idx
        self.status_var.set("項目順を変更しました。Excel出力の列順にも反映されます。")
        self._render_side_body()
        self.redraw()

    def start_field_drag(self, _event, idx: int) -> str:
        if not (0 <= idx < len(self.fields)):
            return "break"
        self.editing_name_index = None
        self.dragging_field_index = idx
        self.selected_index = idx
        self.status_var.set(f"{self.fields[idx].name} をドラッグして並び替えます。")
        return "break"

    def update_field_drag(self, event, idx: int) -> str:
        if self.dragging_field_index != idx or not (0 <= idx < len(self.fields)):
            return "break"
        target_idx = self._field_drop_index(event.y_root, idx)
        if target_idx != idx:
            self.status_var.set(f"{self.fields[idx].name} を #{target_idx + 1} に移動")
        return "break"

    def finish_field_drag(self, event, idx: int) -> str:
        if self.dragging_field_index != idx:
            return "break"
        self.dragging_field_index = None
        target_idx = self._field_drop_index(event.y_root, idx)
        self.move_field_to(idx, target_idx)
        return "break"

    def _field_drop_index(self, y_root: int, source_idx: int) -> int:
        if len(self.fields) <= 1:
            return source_idx
        target_idx = 0
        for row_idx, row in enumerate(self.field_row_widgets):
            if row_idx == source_idx:
                continue
            center_y = row.winfo_rooty() + (row.winfo_height() / 2)
            if y_root > center_y:
                target_idx += 1
        return max(0, min(len(self.fields) - 1, target_idx))

    def rename_field_at(self, idx: int) -> None:
        self.begin_inline_name_edit(idx)

    def begin_inline_name_edit(self, idx: int) -> str:
        if not (0 <= idx < len(self.fields)):
            return "break"
        self.selected_index = idx
        self.editing_name_index = idx
        self._render_side_body()
        self.redraw()
        return "break"

    def commit_inline_name_edit(self, idx: int, value: str) -> str:
        if self.editing_name_index != idx or not (0 <= idx < len(self.fields)):
            return "break"
        self.editing_name_index = None
        previous_name = self.fields[idx].name
        name = value.strip() or self.fields[idx].name
        name = self._unique_field_name(name.strip() or self.fields[idx].name, skip_index=idx)
        self.fields[idx].name = name
        self._rename_correction_rule_targets(previous_name, name)
        if self._apply_profile_preset_after_rename(idx, previous_name):
            if idx < len(self.current_results):
                self.current_results[idx] = ""
            if idx < len(self.current_raw_results):
                self.current_raw_results[idx] = ""
        self._render_side_body()
        self.redraw()
        return "break"

    def _rename_correction_rule_targets(self, previous_name: str, name: str) -> None:
        if previous_name == name:
            return
        for rule in self.correction_rules:
            if rule.target == previous_name:
                rule.target = name

    def _apply_profile_preset_after_rename(self, idx: int, previous_name: str) -> bool:
        field = self.fields[idx]
        if not previous_name.startswith("項目") or not has_field_ocr_preset(field.name):
            return False
        preset = field_ocr_preset(field.name)
        for key, value in preset.items():
            setattr(field, key, value)
        return True

    def cancel_inline_name_edit(self) -> str:
        self.editing_name_index = None
        self._render_side_body()
        self.redraw()
        return "break"

    def show_field_context_menu(self, event, idx: int) -> str:
        if not (0 <= idx < len(self.fields)):
            return "break"
        self.editing_name_index = None
        self.selected_index = idx
        self._render_side_body()
        self.redraw()
        menu = Menu(self.root, tearoff=0)
        menu.add_command(label="項目名を編集", command=lambda i=idx: self.rename_field_at(i))
        menu.add_separator()
        menu.add_command(label="削除", command=lambda i=idx: self.delete_field_at(i, confirm=True))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def show_canvas_context_menu(self, event) -> str:
        if not self.original_image:
            return "break"
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        label_hit_idx = self._hit_test_label(canvas_x, canvas_y)
        x, y = self._event_image_point(event)
        hit_idx, _mode = (label_hit_idx, "move") if label_hit_idx is not None else self._hit_test_field(x, y)
        menu = Menu(self.root, tearoff=0)
        if hit_idx is not None:
            self.editing_name_index = None
            self._select_field_index(hit_idx, update_review_detail=True)
            menu.add_command(label="項目名を編集", command=lambda i=hit_idx: self.rename_field_at(i))
            menu.add_command(label="削除", command=lambda i=hit_idx: self.delete_field_at(i, confirm=False))
            menu.add_separator()
        menu.add_command(label="直前の操作を取り消す", command=self.undo_last_action, state="normal" if self.undo_action else "disabled")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def delete_field_at(self, idx: int, confirm: bool = False) -> None:
        if not (0 <= idx < len(self.fields)):
            return
        self.editing_name_index = None
        field_name = self.fields[idx].name
        if confirm and not messagebox.askyesno("項目削除", f"{field_name} を削除しますか。"):
            return
        self._set_undo("delete", idx=idx, field=replace(self.fields[idx]), result=self.current_results[idx] if idx < len(self.current_results) else "", raw_result=self.current_raw_results[idx] if idx < len(self.current_raw_results) else "")
        del self.fields[idx]
        if idx < len(self.current_results):
            del self.current_results[idx]
        if idx < len(self.current_raw_results):
            del self.current_raw_results[idx]
        self.selected_index = min(idx, len(self.fields) - 1) if self.fields else None
        self.status_var.set(f"{field_name} を削除しました。Esc / Ctrl+Z で戻せます。")
        self._render_side_body()
        self.redraw()

    def _require_field_selection(self) -> int | None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.fields)):
            messagebox.showinfo("項目未選択", "読み取り項目を選択してください。")
            return None
        return self.selected_index

    def _set_undo(self, action_type: str, **payload) -> None:
        self.undo_action = {"type": action_type, **payload}

    def _focus_is_text_entry(self) -> bool:
        focused = self.root.focus_get()
        if focused is None:
            return False
        return "Entry" in str(focused.winfo_class())

    def undo_last_action(self, event=None) -> str | None:
        if event is not None and getattr(event, "keysym", "").lower() == "z" and self._focus_is_text_entry():
            return None
        if self.canvas_edit_state is not None or self.drag_start is not None:
            self.canvas_edit_state = None
            self.drag_start = None
            if self.drag_rect:
                self.canvas.delete(self.drag_rect)
                self.drag_rect = None
            self.status_var.set("Canvas操作をキャンセルしました。")
            self.redraw()
            return "break"

        action = self.undo_action
        if not action:
            self.status_var.set("取り消せる直前操作がありません。")
            return "break"

        self.editing_name_index = None
        action_type = action.get("type")
        if action_type == "add":
            self._undo_added_field(action)
        elif action_type == "delete":
            self._undo_deleted_field(action)
        elif action_type == "update_rect":
            self._undo_updated_rect(action)
        else:
            self.status_var.set("取り消せる直前操作がありません。")
            self.undo_action = None
            return "break"

        self.undo_action = None
        self._render_side_body()
        self.redraw()
        return "break"

    def _undo_added_field(self, action: dict) -> None:
        idx = int(action["idx"])
        field = action["field"]
        field_ref = action.get("field_ref")
        remove_idx = idx if 0 <= idx < len(self.fields) and self.fields[idx] == field else None
        if field_ref is not None:
            for candidate_idx, candidate in enumerate(self.fields):
                if candidate is field_ref:
                    remove_idx = candidate_idx
                    break
        if remove_idx is None:
            for candidate_idx, candidate in enumerate(self.fields):
                if candidate == field:
                    remove_idx = candidate_idx
                    break
        if remove_idx is None:
            self.status_var.set("追加した項目が見つからないため、取り消せませんでした。")
            return
        field_name = self.fields[remove_idx].name
        del self.fields[remove_idx]
        if remove_idx < len(self.current_results):
            del self.current_results[remove_idx]
        if remove_idx < len(self.current_raw_results):
            del self.current_raw_results[remove_idx]
        self.selected_index = min(remove_idx, len(self.fields) - 1) if self.fields else None
        self.status_var.set(f"{field_name} の追加を取り消しました。")

    def _undo_deleted_field(self, action: dict) -> None:
        idx = max(0, min(int(action["idx"]), len(self.fields)))
        field = replace(action["field"])
        self.fields.insert(idx, field)
        self.current_results.insert(idx, str(action.get("result") or ""))
        self.current_raw_results.insert(idx, str(action.get("raw_result") or ""))
        self.selected_index = idx
        self.status_var.set(f"{field.name} の削除を取り消しました。")

    def _undo_updated_rect(self, action: dict) -> None:
        idx = int(action["idx"])
        if not (0 <= idx < len(self.fields)):
            self.status_var.set("更新前の項目が見つからないため、取り消せませんでした。")
            return
        field = action["field"]
        current = self.fields[idx]
        current.x1, current.y1, current.x2, current.y2 = field.x1, field.y1, field.x2, field.y2
        current.source_width, current.source_height = field.source_width, field.source_height
        self._ensure_current_results()
        self.current_results[idx] = str(action.get("result") or "")
        self.current_raw_results[idx] = str(action.get("raw_result") or "")
        self.selected_index = idx
        self.status_var.set(f"{current.name} の範囲変更を取り消しました。")

    def redraw(self) -> None:
        self.canvas.delete("all")
        self.canvas_rects.clear()
        self.canvas_labels.clear()
        self.canvas_label_bgs.clear()
        if not self.original_image:
            self._draw_canvas_empty()
            return
        w, h = self.original_image.size
        scaled_width = max(1, int(w * self.zoom))
        scaled_height = max(1, int(h * self.zoom))
        cache_key = (id(self.original_image), self.zoom)
        if self.preview_image is None or self.preview_cache_key != cache_key:
            scaled = self.original_image.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(scaled)
            self.preview_cache_key = cache_key
        self.image_item = self.canvas.create_image(0, 0, anchor="nw", image=self.preview_image)
        self.canvas.configure(scrollregion=(0, 0, scaled_width, scaled_height))
        self._sync_canvas_scrollbars()
        for idx in self._canvas_draw_order():
            self._draw_field(idx)

    def _canvas_draw_order(self) -> list[int]:
        indexes = list(range(len(self.fields)))
        selected = self._active_canvas_selection()
        if selected is None or not (0 <= selected < len(self.fields)):
            return indexes
        return [idx for idx in indexes if idx != selected] + [selected]

    def _active_canvas_selection(self) -> int | None:
        selected = self.selected_index
        if selected is not None and 0 <= selected < len(self.fields):
            return selected
        return None

    def _should_show_canvas_label(self, idx: int) -> bool:
        editing_idx = int(self.canvas_edit_state["idx"]) if self.canvas_edit_state is not None else None
        if editing_idx is not None:
            return editing_idx == idx
        selected = self._active_canvas_selection()
        return selected is None or selected == idx

    def _draw_canvas_empty(self) -> None:
        canvas_w = max(self.canvas.winfo_width(), 900)
        canvas_h = max(self.canvas.winfo_height(), 600)
        self.canvas.configure(scrollregion=(0, 0, canvas_w, canvas_h))
        self._set_canvas_scrollbars(False, False)
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.canvas.create_text(canvas_w / 2, canvas_h / 2 - 20, text=THEME.copy.empty_canvas_title, fill=THEME.palette.empty_title, font=UI_FONT_TITLE)
        self.canvas.create_text(canvas_w / 2, canvas_h / 2 + 12, text=THEME.copy.empty_canvas_note, fill=THEME.palette.empty_note, font=UI_FONT_SMALL)

    def _set_canvas_scrollbars(self, horizontal: bool, vertical: bool) -> None:
        if self.hbar is not None:
            if horizontal:
                self.hbar.grid(row=1, column=0, sticky="ew")
            else:
                self.hbar.grid_remove()
        if self.vbar is not None:
            if vertical:
                self.vbar.grid(row=0, column=1, sticky="ns")
            else:
                self.vbar.grid_remove()

    def _sync_canvas_scrollbars(self) -> None:
        if not self.original_image:
            self._set_canvas_scrollbars(False, False)
            return
        parts = [float(value) for value in str(self.canvas.cget("scrollregion")).split()]
        if len(parts) != 4:
            self._set_canvas_scrollbars(False, False)
            return
        region_w = parts[2] - parts[0]
        region_h = parts[3] - parts[1]
        visible_w = max(1, self.canvas.winfo_width())
        visible_h = max(1, self.canvas.winfo_height())
        self._set_canvas_scrollbars(region_w > visible_w + 1, region_h > visible_h + 1)

    def on_canvas_configure(self, _event=None) -> None:
        self._sync_canvas_scrollbars()

    def _draw_field(self, idx: int) -> None:
        field = scaled_field(self.fields[idx], self.original_image)
        x1, y1, x2, y2 = [value * self.zoom for value in (field.x1, field.y1, field.x2, field.y2)]
        selected = idx == self.selected_index
        selection_active = self._active_canvas_selection() is not None
        show_label = self._should_show_canvas_label(idx)
        line_mode = field.ocr_line_split == "detected"
        if field.enabled:
            if line_mode:
                color = THEME.palette.line_region_selected if selected else THEME.palette.inactive_line_region if selection_active else THEME.palette.line_region
                label_bg = THEME.palette.line_badge
            else:
                color = COLOR_CTA if selected else THEME.palette.inactive_region if selection_active else THEME.palette.enabled_region
                label_bg = COLOR_CTA_HOVER if selected else COLOR_PRIMARY
        else:
            color = THEME.palette.disabled_fill
            label_bg = COLOR_MUTED
        rect_kwargs = {"outline": color, "width": 3 if selected else 1 if selection_active else 2}
        if line_mode and field.enabled:
            rect_kwargs["dash"] = (6, 3)
        rect = self.canvas.create_rectangle(x1, y1, x2, y2, **rect_kwargs)
        if line_mode and field.enabled and self.canvas_edit_state is None and (selected or not selection_active):
            self._draw_field_line_guides(field, selected)
        self.canvas_rects[idx] = rect
        if not show_label:
            return
        label_text = f"{self._field_order_label(idx)} {field.name}"
        if line_mode:
            label_text = f"{label_text} | 行"
        label = self.canvas.create_text(x1 + 10, max(6, y1 - 22), anchor="nw", text=label_text, fill=THEME.palette.on_color, font=UI_FONT_CANVAS)
        label_box = self.canvas.bbox(label)
        if label_box:
            bg = self.canvas.create_rectangle(label_box[0] - 5, label_box[1] - 3, label_box[2] + 5, label_box[3] + 3, fill=label_bg, outline=label_bg)
            self.canvas.tag_lower(bg, label)
            self.canvas_label_bgs[idx] = bg
        self.canvas_labels[idx] = label

    def _draw_field_line_guides(self, field: TemplateField, selected: bool) -> None:
        if self.original_image is None:
            return
        normalized = field.normalized()
        crop = self.original_image.crop((normalized.x1, normalized.y1, normalized.x2, normalized.y2))
        bands = detect_line_bands(
            crop,
            normalized.ocr_line_detect_threshold,
            normalized.ocr_line_detect_min_ratio,
            normalized.ocr_line_detect_gap,
            normalized.ocr_line_padding,
        )
        color = THEME.palette.line_region_selected if selected else THEME.palette.line_guide
        left = normalized.x1 * self.zoom
        right = normalized.x2 * self.zoom
        for band_y1, band_y2 in bands:
            top = (normalized.y1 + band_y1) * self.zoom
            bottom = (normalized.y1 + band_y2) * self.zoom
            self.canvas.create_line(left, top, right, top, fill=color, width=1, dash=(2, 4))
            self.canvas.create_line(left, bottom, right, bottom, fill=color, width=1, dash=(2, 4))

    def _event_image_point(self, event) -> tuple[int, int]:
        return int(self.canvas.canvasx(event.x) / self.zoom), int(self.canvas.canvasy(event.y) / self.zoom)

    def _hit_test_label(self, canvas_x: float, canvas_y: float) -> int | None:
        for idx in reversed(self._canvas_draw_order()):
            item = self.canvas_label_bgs.get(idx) or self.canvas_labels.get(idx)
            if item is None:
                continue
            bbox = self.canvas.bbox(item)
            if not bbox:
                continue
            left, top, right, bottom = bbox
            if left - 4 <= canvas_x <= right + 4 and top - 4 <= canvas_y <= bottom + 4:
                return idx
        return None

    def _hit_test_field(self, x: int, y: int) -> tuple[int | None, str | None]:
        tolerance = max(6.0, 10.0 / max(self.zoom, 0.1))
        for idx in reversed(self._canvas_draw_order()):
            field = scaled_field(self.fields[idx], self.original_image).normalized()
            x1, y1, x2, y2 = field.x1, field.y1, field.x2, field.y2
            width = max(1, x2 - x1)
            height = max(1, y2 - y1)
            resize_x = min(tolerance, max(4.0, width * 0.22))
            resize_y = min(tolerance, max(4.0, height * 0.22))
            inside_x = x1 - tolerance <= x <= x2 + tolerance
            inside_y = y1 - tolerance <= y <= y2 + tolerance

            if x1 <= x <= x2 and y1 <= y <= y2:
                center_x = x1 + resize_x < x < x2 - resize_x
                center_y = y1 + resize_y < y < y2 - resize_y
                if center_x and center_y:
                    return idx, "move"

            near_left = abs(x - x1) <= resize_x
            near_right = abs(x - x2) <= resize_x
            near_top = abs(y - y1) <= resize_y
            near_bottom = abs(y - y2) <= resize_y

            if near_left and near_top:
                return idx, "nw"
            if near_right and near_top:
                return idx, "ne"
            if near_left and near_bottom:
                return idx, "sw"
            if near_right and near_bottom:
                return idx, "se"
            if near_left and inside_y:
                return idx, "w"
            if near_right and inside_y:
                return idx, "e"
            if near_top and inside_x:
                return idx, "n"
            if near_bottom and inside_x:
                return idx, "s"
            if x1 <= x <= x2 and y1 <= y <= y2:
                return idx, "move"
        return None, None

    def _cursor_for_edit_mode(self, mode: str | None) -> str:
        if mode == "move":
            return "fleur"
        if mode in {"e", "w"}:
            return "sb_h_double_arrow"
        if mode in {"n", "s"}:
            return "sb_v_double_arrow"
        if mode:
            return "crosshair"
        return "arrow"

    def on_canvas_motion(self, event) -> None:
        if not self.original_image:
            self.canvas.configure(cursor="arrow")
            return
        if self.canvas_edit_state is not None:
            self.canvas.configure(cursor=self._cursor_for_edit_mode(str(self.canvas_edit_state.get("mode"))))
            return
        if self.drag_start is not None:
            self.canvas.configure(cursor="crosshair")
            return
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        x, y = self._event_image_point(event)
        _idx, mode = self._hit_test_field(x, y)
        if mode and mode != "move":
            self.canvas.configure(cursor=self._cursor_for_edit_mode(mode))
            return
        label_hit_idx = self._hit_test_label(canvas_x, canvas_y)
        if label_hit_idx is not None:
            self.canvas.configure(cursor="fleur")
            return
        self.canvas.configure(cursor=self._cursor_for_edit_mode(mode))

    def _edited_rect_from_state(self, x: int, y: int) -> tuple[int, int, int, int]:
        assert self.canvas_edit_state is not None
        mode = str(self.canvas_edit_state["mode"])
        start_x = int(self.canvas_edit_state["start_x"])
        start_y = int(self.canvas_edit_state["start_y"])
        x1, y1, x2, y2 = self.canvas_edit_state["orig"]
        dx = x - start_x
        dy = y - start_y

        if mode == "move":
            return int(x1 + dx), int(y1 + dy), int(x2 + dx), int(y2 + dy)
        if "w" in mode:
            x1 += dx
        if "e" in mode:
            x2 += dx
        if "n" in mode:
            y1 += dy
        if "s" in mode:
            y2 += dy
        return int(x1), int(y1), int(x2), int(y2)

    def _clamp_rect_to_image(self, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        assert self.original_image is not None
        w, h = self.original_image.size
        x1, y1, x2, y2 = rect
        if self.canvas_edit_state and self.canvas_edit_state.get("mode") == "move":
            width = x2 - x1
            height = y2 - y1
            x1 = max(0, min(w - width, x1))
            y1 = max(0, min(h - height, y1))
            return x1, y1, x1 + width, y1 + height

        x1, x2 = sorted((max(0, min(w, x1)), max(0, min(w, x2))))
        y1, y2 = sorted((max(0, min(h, y1)), max(0, min(h, y2))))
        return x1, y1, x2, y2

    def _set_canvas_edit_preview(self, idx: int, rect: tuple[int, int, int, int]) -> None:
        item = self.canvas_rects.get(idx)
        if item is None:
            return
        x1, y1, x2, y2 = rect
        self.canvas.coords(item, x1 * self.zoom, y1 * self.zoom, x2 * self.zoom, y2 * self.zoom)
        label = self.canvas_labels.get(idx)
        if label is None:
            return
        label_x = x1 * self.zoom + 10
        label_y = max(6, y1 * self.zoom - 22)
        self.canvas.coords(label, label_x, label_y)
        label_box = self.canvas.bbox(label)
        label_bg = self.canvas_label_bgs.get(idx)
        if label_bg is not None and label_box:
            self.canvas.coords(label_bg, label_box[0] - 5, label_box[1] - 3, label_box[2] + 5, label_box[3] + 3)

    def on_mouse_down(self, event) -> None:
        if not self.original_image:
            return
        self.editing_name_index = None
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        x, y = self._event_image_point(event)
        field_hit_idx, field_mode = self._hit_test_field(x, y)
        label_hit_idx = self._hit_test_label(canvas_x, canvas_y)
        if field_hit_idx is not None and field_mode and field_mode != "move":
            hit_idx, mode = field_hit_idx, field_mode
        elif label_hit_idx is not None:
            hit_idx, mode = label_hit_idx, "move"
        else:
            hit_idx, mode = field_hit_idx, field_mode
        if hit_idx is not None and mode is not None:
            field = scaled_field(self.fields[hit_idx], self.original_image).normalized()
            self._select_field_index(hit_idx, update_review_detail=True, redraw_canvas=False)
            self.canvas_edit_state = {
                "idx": hit_idx,
                "mode": mode,
                "start_x": x,
                "start_y": y,
                "orig": (field.x1, field.y1, field.x2, field.y2),
            }
            action_text = "移動中" if mode == "move" else "サイズ調整中"
            self.status_var.set(f"{self.fields[hit_idx].name} の範囲を{action_text}です。")
            self.redraw()
            return

        self.drag_start = (x, y)
        x = self.drag_start[0] * self.zoom
        y = self.drag_start[1] * self.zoom
        self.drag_rect = self.canvas.create_rectangle(x, y, x, y, outline=COLOR_CTA, width=2, dash=(4, 2))

    def on_mouse_drag(self, event) -> None:
        if self.canvas_edit_state is not None:
            idx = int(self.canvas_edit_state["idx"])
            x, y = self._event_image_point(event)
            rect = self._clamp_rect_to_image(self._edited_rect_from_state(x, y))
            self._set_canvas_edit_preview(idx, rect)
            return
        if not self.drag_start or not self.drag_rect:
            return
        x1, y1 = self.drag_start
        x2, y2 = self._event_image_point(event)
        self.canvas.coords(self.drag_rect, x1 * self.zoom, y1 * self.zoom, x2 * self.zoom, y2 * self.zoom)

    def on_mouse_up(self, event) -> None:
        if self.canvas_edit_state is not None:
            idx = int(self.canvas_edit_state["idx"])
            x, y = self._event_image_point(event)
            x1, y1, x2, y2 = self._clamp_rect_to_image(self._edited_rect_from_state(x, y))
            self.canvas_edit_state = None
            if (x2 - x1) < 8 or (y2 - y1) < 8:
                self.redraw()
                return
            field = self.fields[idx]
            before_field = replace(field)
            before_result = self.current_results[idx] if idx < len(self.current_results) else ""
            before_raw_result = self.current_raw_results[idx] if idx < len(self.current_raw_results) else ""
            field.x1, field.y1, field.x2, field.y2 = x1, y1, x2, y2
            field.source_width, field.source_height = self.original_image.size
            if idx < len(self.current_results):
                self.current_results[idx] = ""
            if idx < len(self.current_raw_results):
                self.current_raw_results[idx] = ""
            self.selected_index = idx
            self._set_undo("update_rect", idx=idx, field=before_field, result=before_result, raw_result=before_raw_result)
            self.status_var.set(f"{field.name} の範囲を更新しました。Esc / Ctrl+Z で戻せます。")
            self._render_side_body()
            self.redraw()
            return

        if not self.original_image or not self.drag_start:
            return
        x1, y1 = self.drag_start
        x2, y2 = self._event_image_point(event)
        self.drag_start = None
        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
            self.drag_rect = None

        w, h = self.original_image.size
        x1, x2 = sorted((max(0, min(w, x1)), max(0, min(w, x2))))
        y1, y2 = sorted((max(0, min(h, y1)), max(0, min(h, y2))))
        if (x2 - x1) < 8 or (y2 - y1) < 8:
            return

        name = self._next_field_name()
        source_width, source_height = self.original_image.size
        self.fields.append(TemplateField(name, x1, y1, x2, y2, True, source_width, source_height))
        self.current_results.append("")
        self.current_raw_results.append("")
        self.selected_index = len(self.fields) - 1
        self.mode_var.set(MODE_TEMPLATE)
        self._set_undo("add", idx=self.selected_index, field=replace(self.fields[self.selected_index]), field_ref=self.fields[self.selected_index], result="")
        self.status_var.set(f"{name} を追加しました。Esc / Ctrl+Z で戻せます。")
        self._render_side_body()
        self.redraw()

    def on_mouse_wheel(self, event) -> None:
        if not self.original_image:
            return
        ctrl_pressed = bool(event.state & 0x0004)
        if not ctrl_pressed:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return
        factor = 1.1 if event.delta > 0 else 0.9
        self.zoom = max(0.1, min(4.0, self.zoom * factor))
        self.redraw()

    def ocr_selected_field(self) -> None:
        idx = self._require_field_selection()
        if idx is None:
            return
        if not self.fields[idx].enabled:
            messagebox.showinfo("項目無効", "選択中の読み取り項目が無効です。")
            return
        self.ocr_field_at(idx)

    def ocr_current_image(self) -> None:
        if not self.original_image:
            messagebox.showerror("画像未選択", "先に画像を開いてください。")
            return
        if not self._enabled_fields():
            messagebox.showerror("項目なし", "有効な読み取り項目がありません。")
            return
        image = self.original_image.copy()
        fields = [(idx, replace(field)) for idx, field in enumerate(self.fields)]
        lang = self.lang_var.get()
        tesseract_path = self.tesseract_var.get().strip()
        backend = self.backend_var.get()
        correction_rules = [replace(rule) for rule in self.correction_rules]

        def work() -> tuple[list[str], list[str]]:
            raw_results = [""] * len(fields)
            results = [""] * len(fields)
            for idx, field in fields:
                if not field.enabled:
                    continue
                raw_text, text, error = self.ocr_engine.recognize_field_detail(image, field, lang, tesseract_path, backend, correction_rules)
                if error or text is None:
                    raise RuntimeError(error or f"{field.name} のOCRに失敗しました。")
                raw_results[idx] = raw_text or ""
                results[idx] = text
            return raw_results, results

        def on_success(result: tuple[list[str], list[str]]) -> None:
            self.current_raw_results, self.current_results = result
            self.status_var.set("現在の画像をOCRしました。")
            self._render_side_body()

        def on_error(error: Exception) -> None:
            self.status_var.set("OCRに失敗しました。")
            messagebox.showerror("OCRエラー", str(error))

        self._run_background("OCR中です。初回はPaddleOCRの準備に時間がかかります。", work, on_success, on_error)

    def ocr_field_at(self, idx: int) -> None:
        if not self.original_image:
            messagebox.showerror("画像未選択", "先に画像を開いてください。")
            return
        if not (0 <= idx < len(self.fields)) or not self.fields[idx].enabled:
            return
        image = self.original_image.copy()
        field = replace(self.fields[idx])
        lang = self.lang_var.get()
        tesseract_path = self.tesseract_var.get().strip()
        backend = self.backend_var.get()
        correction_rules = [replace(rule) for rule in self.correction_rules]

        def work() -> tuple[int, str, str]:
            raw_text, text, error = self.ocr_engine.recognize_field_detail(image, field, lang, tesseract_path, backend, correction_rules)
            if error or text is None:
                raise RuntimeError(error or f"{field.name} のOCRに失敗しました。")
            return idx, raw_text or "", text

        def on_success(result: tuple[int, str, str]) -> None:
            result_idx, raw_text, text = result
            if not (0 <= result_idx < len(self.fields)):
                return
            self._ensure_result_buffers()
            self.current_raw_results[result_idx] = raw_text
            self.current_results[result_idx] = text
            self.selected_index = result_idx
            self.status_var.set(f"{self.fields[result_idx].name} をOCRしました。")
            self._render_side_body()

        def on_error(error: Exception) -> None:
            self.status_var.set("OCRに失敗しました。")
            messagebox.showerror("OCRエラー", str(error))

        self._run_background(f"{field.name} をOCR中です。", work, on_success, on_error)

    def _ocr_all_current(self, show_errors: bool) -> bool:
        if not self.original_image:
            return False
        self._ensure_result_buffers()
        for idx, field in enumerate(self.fields):
            if not field.enabled:
                continue
            raw_text, text = self._ocr_field_detail(self.original_image, field, show_errors=show_errors)
            if text is None:
                return False
            self.current_raw_results[idx] = raw_text or ""
            self.current_results[idx] = text
        return True

    def _ocr_field_detail(self, image: Image.Image, field: TemplateField, show_errors: bool) -> tuple[str | None, str | None]:
        raw_text, text, error = self.ocr_engine.recognize_field_detail(image, field, self.lang_var.get(), self.tesseract_var.get().strip(), self.backend_var.get(), self.correction_rules)
        if error and show_errors:
            messagebox.showerror("OCRエラー", error)
        return raw_text, text

    def _export_settings_dict(self) -> dict:
        return {
            "sheet_name": self.export_sheet_var.get(),
            "write_mode": self.export_write_mode_var.get(),
            "start_cell": self.export_start_cell_var.get(),
            "include_filename": self.export_include_filename_var.get(),
            "include_header": self.export_include_header_var.get(),
        }

    def _apply_output_settings(self, settings: dict) -> None:
        self.export_sheet_var.set(str(settings.get("sheet_name") or "OCR"))
        write_mode = str(settings.get("write_mode") or "上書き")
        self.export_write_mode_var.set(write_mode if write_mode in {"上書き", "追記"} else "上書き")
        self.export_start_cell_var.set(str(settings.get("start_cell") or "A1"))
        self.export_include_filename_var.set(bool(settings.get("include_filename", True)))
        self.export_include_header_var.set(bool(settings.get("include_header", True)))

    def _build_export_settings(self) -> tuple[ExportSettings | None, str | None]:
        return validate_export_settings(
            self.export_sheet_var.get(),
            self.export_write_mode_var.get(),
            self.export_start_cell_var.get(),
            self.export_include_filename_var.get(),
            self.export_include_header_var.get(),
        )

    def export_to_excel(self, _event=None) -> None:
        fields = self._enabled_fields()
        if not fields:
            messagebox.showerror("項目なし", "有効な読み取り項目がありません。")
            return
        if not self.image_files:
            messagebox.showerror("画像なし", "画像フォルダを選択してください。")
            return
        if not self.output_path:
            self.select_output_file()
            if not self.output_path:
                return
        settings, error = self._build_export_settings()
        if error or settings is None:
            messagebox.showerror("出力設定エラー", error or "Excel出力設定を確認してください。")
            return
        if settings.write_mode == "上書き" and self.output_path.exists() and not messagebox.askyesno("上書き確認", f"既存ファイルを上書きします。\n{self.output_path}"):
            return

        total = len(self.image_files)
        self.progress_var.set(f"0 / {total}")
        self.status_var.set("Excel出力を開始しました。")
        output_path = self.output_path
        image_files = list(self.image_files)
        export_fields = [replace(field) for field in fields]
        lang = self.lang_var.get()
        tesseract_path = self.tesseract_var.get().strip()
        backend = self.backend_var.get()
        correction_rules = [replace(rule) for rule in self.correction_rules]

        def update_progress(row_index: int, total_count: int, image_path: Path) -> None:
            def apply_update() -> None:
                self.progress_var.set(f"{row_index} / {total_count}")
                self.status_var.set(f"OCR中: {image_path.name}")
                self._update_loading(f"Excel出力中です。{row_index} / {total_count}\n{image_path.name}")

            self.root.after(0, apply_update)

        def work():
            return self.excel_exporter.export(
                output_path,
                image_files,
                export_fields,
                settings,
                lambda image, field: self.ocr_engine.recognize_field(image, field, lang, tesseract_path, backend, correction_rules),
                update_progress,
            )

        def on_success(result) -> None:
            if result.errors:
                self.status_var.set(f"Excelへ出力しました（エラー {len(result.errors)} 件）: {output_path}")
                messagebox.showwarning("完了（エラーあり）", f"{result.total_images} 画像の処理が完了しました。\nエラー {len(result.errors)} 件は Errors シートに出力しました。\n{output_path}")
            else:
                self.status_var.set(f"Excelへ出力しました: {output_path}")
                messagebox.showinfo("完了", f"{result.total_images} 画像をExcelへ出力しました。\n{output_path}")

        def on_error(error: Exception) -> None:
            self.status_var.set("Excel出力に失敗しました。")
            messagebox.showerror("出力エラー", f"Excelへ出力できませんでした。\n{error}")

        def on_finally() -> None:
            self.progress_var.set("")

        self._run_background(f"Excel出力中です。0 / {total}", work, on_success, on_error, on_finally)

    def _initial_zoom(self) -> float:
        if not self.original_image:
            return 1.0
        max_w = max(self.canvas.winfo_width(), 900)
        max_h = max(self.canvas.winfo_height(), 600)
        w, h = self.original_image.size
        return min(1.0, max(0.15, min(max_w / w, max_h / h)))

    def _enabled_fields(self) -> list[TemplateField]:
        return [field for field in self.fields if field.enabled]

    def _ensure_current_results(self) -> None:
        self._ensure_result_buffers()

    def _ensure_result_buffers(self) -> None:
        if len(self.current_results) < len(self.fields):
            self.current_results.extend([""] * (len(self.fields) - len(self.current_results)))
        elif len(self.current_results) > len(self.fields):
            self.current_results = self.current_results[: len(self.fields)]
        if len(self.current_raw_results) < len(self.fields):
            self.current_raw_results.extend([""] * (len(self.fields) - len(self.current_raw_results)))
        elif len(self.current_raw_results) > len(self.fields):
            self.current_raw_results = self.current_raw_results[: len(self.fields)]

    def _ensure_review_selection(self) -> None:
        if self.selected_index is not None and 0 <= self.selected_index < len(self.fields) and self.fields[self.selected_index].enabled:
            return
        for idx, field in enumerate(self.fields):
            if field.enabled:
                self.selected_index = idx
                return
        self.selected_index = None

    def _sync_counts(self) -> None:
        enabled = len(self._enabled_fields())
        total = len(self.fields)
        self.field_count_var.set(f"{enabled} / {total} 項目")

    def _field_order_label(self, idx: int) -> str:
        return f"#{idx + 1}"

    def _field_size_text(self, field: TemplateField) -> str:
        normalized = field.normalized()
        size_text = f"{normalized.x2 - normalized.x1} x {normalized.y2 - normalized.y1}px"
        source_text = f" / 基準 {normalized.source_width}x{normalized.source_height}" if normalized.source_width and normalized.source_height else ""
        return f"{size_text}{source_text}"

    def _unique_field_name(self, name: str, skip_index: int | None = None) -> str:
        used = {field.name for idx, field in enumerate(self.fields) if idx != skip_index}
        if name not in used:
            return name
        base = name
        count = 2
        while f"{base} {count}" in used:
            count += 1
        return f"{base} {count}"

    def _next_field_name(self) -> str:
        index = len(self.fields) + 1
        while True:
            name = f"項目{index}"
            if all(field.name != name for field in self.fields):
                return name
            index += 1

    def _lang_display(self, value: str) -> str:
        labels = {
            "jpn+eng": "日本語 + English",
            "jpn": "日本語のみ",
            "eng": "English のみ",
        }
        return labels.get(value, value or self._lang_display(DEFAULT_LANG))

    def _lang_value(self, display: str) -> str:
        values = {
            "日本語 + English": "jpn+eng",
            "日本語のみ": "jpn",
            "English のみ": "eng",
        }
        return values.get(display, display or DEFAULT_LANG)

    def _sync_lang_from_display(self, display: str | None = None) -> None:
        self.lang_var.set(self._lang_value(display or self.lang_display_var.get()))


def main() -> None:
    root = ctk.CTk()
    ImageOcrExcelApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
