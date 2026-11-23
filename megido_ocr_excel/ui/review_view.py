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

    ctk.CTkButton(
        body,
        text="この画像をテスト",
        image=ICONS.get("scan", 16, THEME.palette.on_color),
        compound="left",
        command=app.ocr_current_image,
        width=138,
        height=THEME.layout.entry_height,
        font=UI_FONT_SMALL,
        fg_color=COLOR_PRIMARY,
        hover_color=COLOR_PRIMARY_HOVER,
    ).pack(fill="x", padx=16, pady=(0, 8), before=scroller._parent_frame)

    app._ensure_review_selection()
    app.result_vars = []
    for idx, field in enumerate(app.fields):
        if not field.enabled:
            continue
        app._review_result_row(scroller, idx)



def render_comparison(parent, crop, text, multiline):
    image = ctk.CTkImage(light_image=crop, size=(1, 1)) if crop is not None else None
    preview = ctk.CTkLabel(parent, text="" if image else "範囲画像なし", image=image,
                           width=1, height=28, fg_color=THEME.palette.canvas_bg,
                           corner_radius=4, font=UI_FONT_SMALL)
    value = ctk.CTkLabel(parent, text=text, width=1, height=28, anchor="w",
                         justify="left", font=THEME.fonts.normal)
    last_width = None

    def layout(width):
        nonlocal last_width
        if width == last_width or width < 2:
            return
        last_width = width
        stacked = width < 270 or (width < 440 and (multiline or (crop and crop.width > 560)))
        image_width = width if stacked else width // 2
        text_width = width if stacked else width - image_width - 8
        parent.grid_columnconfigure(0, weight=1 if stacked else 0,
                                    minsize=0 if stacked else round(parent._apply_widget_scaling(image_width)))
        parent.grid_columnconfigure(1, weight=0 if stacked else 1)
        preview.grid(row=0, column=0, sticky="ew")
        value.grid(row=int(stacked), column=0 if stacked else 1, sticky="ew",
                   padx=(0 if stacked else 8, 0), pady=(4 if stacked else 0, 0))
        value.configure(wraplength=max(1, text_width - 4))
        if image:
            scale = min(image_width / crop.width, 112 / crop.height, 1)
            image.configure(size=(max(1, int(crop.width * scale)), max(1, int(crop.height * scale))))

    parent.bind("<Configure>", lambda event: layout(round(parent._reverse_widget_scaling(event.width))))
    layout(300)
    return value
