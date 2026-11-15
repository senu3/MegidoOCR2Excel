from __future__ import annotations
from typing import TYPE_CHECKING
from megido_ocr_excel.ui.icons import ICONS
from megido_ocr_excel.ui.scrollable import AutoHideScrollableFrame
from megido_ocr_excel.ui.theme import THEME
from megido_ocr_excel.ui.workflow_style import COLOR_BORDER
from megido_ocr_excel.ui.workflow_style import COLOR_MUTED
from megido_ocr_excel.ui.workflow_style import COLOR_PRIMARY
from megido_ocr_excel.ui.workflow_style import COLOR_PRIMARY_HOVER
from megido_ocr_excel.ui.workflow_style import COLOR_SURFACE
from megido_ocr_excel.ui.workflow_style import COLOR_SURFACE_ALT
from megido_ocr_excel.ui.workflow_style import UI_FONT_SMALL
from tkinter import BOTH
from tkinter import BOTTOM
from tkinter import TOP
import customtkinter as ctk

if TYPE_CHECKING:
    from megido_ocr_excel.application import ImageOcrExcelApp


def render(self: ImageOcrExcelApp) -> None:
    side_body = self.side_body
    assert side_body is not None
    body = ctk.CTkFrame(side_body, corner_radius=0, fg_color=COLOR_SURFACE)
    body.pack(fill=BOTH, expand=True)

    scroller = AutoHideScrollableFrame(
        body,
        height=220,
        corner_radius=THEME.layout.panel_radius,
        fg_color=COLOR_SURFACE_ALT,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    self.review_result_scroller = scroller
    scroller.pack(side=TOP, fill=BOTH, expand=True, padx=16, pady=(2, 10))
    if not self.fields:
        self._empty_state(
            scroller,
            "読み取り項目がありません",
            "「範囲・列」で読み取り範囲を作成してください。",
            icon="table",
        )
        return
    if not self.original_image:
        self._empty_state(
            scroller,
            "画像がありません",
            "上部から画像フォルダを選択してください。",
            icon="folder",
        )
        return

    ctk.CTkLabel(
        body,
        text=THEME.copy.recognition_test_note,
        anchor="w",
        justify="left",
        font=UI_FONT_SMALL,
        text_color=COLOR_MUTED,
        wraplength=350,
    ).pack(fill="x", padx=18, pady=(0, 8), before=scroller._parent_frame)

    toolbar = ctk.CTkFrame(body, corner_radius=0, fg_color="transparent")
    toolbar.pack(fill="x", padx=16, pady=(0, 10), before=scroller._parent_frame)
    toolbar.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        toolbar,
        text=self._text_formatting_summary(),
        anchor="w",
        font=UI_FONT_SMALL,
        text_color=COLOR_MUTED,
    ).grid(row=0, column=0, sticky="ew", padx=(2, 8))
    ctk.CTkButton(
        toolbar,
        text="全項目をテスト",
        image=ICONS.get("scan", 16, THEME.palette.on_color),
        compound="left",
        command=self.ocr_current_image,
        width=138,
        height=THEME.layout.entry_height,
        font=UI_FONT_SMALL,
        fg_color=COLOR_PRIMARY,
        hover_color=COLOR_PRIMARY_HOVER,
    ).grid(row=0, column=1, sticky="e")

    self._ensure_result_buffers()
    self._ensure_review_selection()
    self.result_vars = []
    for idx, field in enumerate(self.fields):
        if not field.enabled:
            continue
        self._review_result_row(scroller, idx)

    self.review_detail_host = ctk.CTkFrame(
        body, corner_radius=0, fg_color=COLOR_SURFACE
    )
    self.review_detail_host.pack(side=BOTTOM, fill="x")
    self._render_postprocess_panel(self.review_detail_host)

