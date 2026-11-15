from __future__ import annotations
from typing import TYPE_CHECKING
import customtkinter as ctk

from megido_ocr_excel.ui.icons import (
    ICONS,
)
from megido_ocr_excel.ui.scrollable import (
    AutoHideScrollableFrame,
)
from megido_ocr_excel.ui.theme import (
    THEME,
)
from megido_ocr_excel.ui.workflow_style import (
    COLOR_BORDER,
    COLOR_MUTED,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    UI_FONT_SMALL,
)
from tkinter import (
    BOTH,
    BOTTOM,
    TOP,
)

if TYPE_CHECKING:
    from megido_ocr_excel.application import ImageOcrExcelApp


def render(app: ImageOcrExcelApp) -> None:
    side_body = app.side_body
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
    app.review_result_scroller = scroller
    scroller.pack(side=TOP, fill=BOTH, expand=True, padx=16, pady=(2, 10))
    if not app.fields:
        app._empty_state(
            scroller,
            "読み取り項目がありません",
            "「範囲・列」で読み取り範囲を作成してください。",
            icon="table",
        )
        return
    if not app.original_image:
        app._empty_state(
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
        text=app._text_formatting_summary(),
        anchor="w",
        font=UI_FONT_SMALL,
        text_color=COLOR_MUTED,
    ).grid(row=0, column=0, sticky="ew", padx=(2, 8))
    ctk.CTkButton(
        toolbar,
        text="全項目をテスト",
        image=ICONS.get("scan", 16, THEME.palette.on_color),
        compound="left",
        command=app.ocr_current_image,
        width=138,
        height=THEME.layout.entry_height,
        font=UI_FONT_SMALL,
        fg_color=COLOR_PRIMARY,
        hover_color=COLOR_PRIMARY_HOVER,
    ).grid(row=0, column=1, sticky="e")

    app._ensure_review_selection()
    app.result_vars = []
    for idx, field in enumerate(app.fields):
        if not field.enabled:
            continue
        app._review_result_row(scroller, idx)

    app.review_detail_host = ctk.CTkFrame(
        body, corner_radius=0, fg_color=COLOR_SURFACE
    )
    app.review_detail_host.pack(side=BOTTOM, fill="x")
    app._render_postprocess_panel(app.review_detail_host)

