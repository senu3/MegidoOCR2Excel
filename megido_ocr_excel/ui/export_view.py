from __future__ import annotations
from typing import TYPE_CHECKING
from megido_ocr_excel.ui.icons import ICONS
from megido_ocr_excel.ui.theme import THEME
from megido_ocr_excel.ui.tooltip import add_tooltip
from megido_ocr_excel.ui.workflow_style import COLOR_BORDER
from megido_ocr_excel.ui.workflow_style import COLOR_CTA
from megido_ocr_excel.ui.workflow_style import COLOR_CTA_HOVER
from megido_ocr_excel.ui.workflow_style import COLOR_MUTED
from megido_ocr_excel.ui.workflow_style import COLOR_SECONDARY
from megido_ocr_excel.ui.workflow_style import COLOR_SECONDARY_HOVER
from megido_ocr_excel.ui.workflow_style import COLOR_SURFACE
from megido_ocr_excel.ui.workflow_style import COLOR_SURFACE_ALT
from megido_ocr_excel.ui.workflow_style import COLOR_TEXT
from megido_ocr_excel.ui.workflow_style import COLOR_UTILITY_HOVER
from megido_ocr_excel.ui.workflow_style import UI_FONT_BOLD
from megido_ocr_excel.ui.workflow_style import UI_FONT_SMALL
from tkinter import BOTH
from tkinter import BOTTOM
from tkinter import TOP
import customtkinter as ctk

if TYPE_CHECKING:
    from megido_ocr_excel.application import ImageOcrExcelApp


def render(self: ImageOcrExcelApp) -> None:
    body = self.side_body
    assert body is not None

    content = ctk.CTkScrollableFrame(
        body,
        corner_radius=0,
        fg_color=COLOR_SURFACE,
        scrollbar_button_color=COLOR_SECONDARY,
        scrollbar_button_hover_color=COLOR_SECONDARY_HOVER,
    )
    content.pack(side=TOP, fill=BOTH, expand=True)

    panel = ctk.CTkFrame(
        content,
        corner_radius=THEME.layout.panel_radius,
        fg_color=COLOR_SURFACE_ALT,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    panel.pack(fill="x", padx=16, pady=(0, 10))
    panel.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        panel,
        text="画像フォルダ",
        anchor="w",
        font=UI_FONT_SMALL,
        text_color=COLOR_TEXT,
    ).grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=(12, 2))
    ctk.CTkLabel(
        panel,
        textvariable=self.folder_var,
        anchor="w",
        font=UI_FONT_SMALL,
        text_color=COLOR_MUTED,
        wraplength=210,
    ).grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(0, 8))
    ctk.CTkButton(
        panel,
        text="変更",
        image=ICONS.get("folder", 16, COLOR_TEXT),
        compound="left",
        command=self.open_image_folder,
        width=104,
        height=THEME.layout.entry_height,
        corner_radius=THEME.layout.control_radius,
        font=UI_FONT_SMALL,
        fg_color=COLOR_SECONDARY,
        hover_color=COLOR_SECONDARY_HOVER,
        border_width=1,
        border_color=COLOR_BORDER,
    ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(0, 12), pady=(12, 8))
    ctk.CTkLabel(
        panel,
        text="出力ファイル",
        anchor="w",
        font=UI_FONT_SMALL,
        text_color=COLOR_TEXT,
    ).grid(row=2, column=0, sticky="ew", padx=(12, 8), pady=(2, 2))
    ctk.CTkLabel(
        panel,
        textvariable=self.output_var,
        anchor="w",
        font=UI_FONT_SMALL,
        text_color=COLOR_MUTED,
        wraplength=210,
    ).grid(row=3, column=0, sticky="ew", padx=(12, 8), pady=(0, 12))
    ctk.CTkButton(
        panel,
        text="選択",
        image=ICONS.get("table", 16, COLOR_TEXT),
        compound="left",
        command=self.select_output_file,
        width=104,
        height=THEME.layout.entry_height,
        corner_radius=THEME.layout.control_radius,
        font=UI_FONT_SMALL,
        fg_color=COLOR_SECONDARY,
        hover_color=COLOR_SECONDARY_HOVER,
        border_width=1,
        border_color=COLOR_BORDER,
        text_color=COLOR_TEXT,
    ).grid(row=2, column=1, rowspan=2, sticky="e", padx=(0, 12), pady=(2, 12))

    self._render_image_queue(content)
    self._render_excel_output_settings(content)

    enabled_count = len(self._enabled_fields())
    image_count = len(self.image_queue.included_files())
    self._render_export_structure_summary(content, image_count, enabled_count)

    actions = ctk.CTkFrame(body, fg_color=COLOR_SURFACE)
    actions.pack(side=BOTTOM, fill="x", padx=16, pady=(8, 14))
    actions.grid_columnconfigure(0, weight=1)
    retry_count = (
        len(self.image_queue.failed_files()) if self.last_export_result else 0
    )
    self.retry_button = ctk.CTkButton(
        actions,
        text=f"失敗分を再実行（{retry_count}）",
        image=ICONS.get("refresh", 17, COLOR_TEXT),
        compound="left",
        command=self.retry_failed_images,
        state="normal" if retry_count else "disabled",
        height=THEME.layout.primary_button_height,
        corner_radius=THEME.layout.control_radius,
        font=UI_FONT_SMALL,
        fg_color=COLOR_SECONDARY,
        hover_color=COLOR_SECONDARY_HOVER,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    self.retry_button.grid(
        row=0,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(0, 6),
    )
    ctk.CTkButton(
        actions,
        text="Excel出力",
        image=ICONS.get("table", 18, THEME.palette.on_color),
        compound="left",
        command=self.export_to_excel,
        height=THEME.layout.export_button_height,
        corner_radius=THEME.layout.control_radius,
        font=UI_FONT_BOLD,
        fg_color=COLOR_CTA,
        hover_color=COLOR_CTA_HOVER,
    ).grid(row=1, column=0, sticky="ew", padx=(0, 4))
    self.export_more_button = ctk.CTkButton(
        actions,
        text="",
        image=ICONS.get("more", 18, COLOR_MUTED),
        command=lambda: None,
        width=40,
        height=THEME.layout.export_button_height,
        corner_radius=THEME.layout.control_radius,
        fg_color="transparent",
        hover_color=COLOR_UTILITY_HOVER,
        border_width=0,
    )
    self.export_more_button.configure(
        command=lambda button=self.export_more_button: (
            self.show_export_actions_menu(button)
        )
    )
    self.export_more_button.grid(row=1, column=1)
    add_tooltip(
        self.export_more_button,
        "その他の出力",
    )
    ctk.CTkLabel(
        actions,
        text="Excelがない場合は、右のメニューからCSVで保存できます。",
        anchor="e",
        font=UI_FONT_SMALL,
        text_color=COLOR_MUTED,
    ).grid(row=2, column=0, columnspan=2, sticky="e", pady=(3, 0))

