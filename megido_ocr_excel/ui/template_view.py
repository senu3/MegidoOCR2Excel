from __future__ import annotations
from typing import TYPE_CHECKING
import customtkinter as ctk

from megido_ocr_excel.models import (
    EXPORT_LAYOUT_SET,
    set_validation_error,
)
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
    COLOR_DANGER,
    COLOR_MUTED,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SECONDARY,
    COLOR_SECONDARY_HOVER,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    EXPORT_LAYOUT_BY_DISPLAY,
    EXPORT_LAYOUT_DISPLAY,
    UI_FONT_SMALL,
)
from tkinter import (
    BOTH,
    TOP,
)

if TYPE_CHECKING:
    from megido_ocr_excel.application import ImageOcrExcelApp


def render(app: ImageOcrExcelApp) -> None:
    body = app.side_body
    assert body is not None
    app.field_check_vars = []
    app.field_row_widgets = []
    app.field_row_by_index = {}
    app.field_drag_handle_by_index = {}
    app.set_drop_section_by_id = {}
    layout_row = ctk.CTkFrame(body, fg_color="transparent")
    layout_row.pack(fill="x", padx=16, pady=(2, 8))
    layout_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        layout_row,
        text="Excelの行単位",
        anchor="w",
        font=UI_FONT_SMALL,
        text_color=COLOR_MUTED,
    ).grid(row=0, column=0, sticky="w", padx=(0, 8))
    layout_menu = ctk.CTkOptionMenu(
        layout_row,
        values=list(EXPORT_LAYOUT_DISPLAY.values()),
        height=THEME.layout.entry_height,
        font=UI_FONT_SMALL,
        fg_color=COLOR_SECONDARY,
        button_color=COLOR_PRIMARY,
        button_hover_color=COLOR_PRIMARY_HOVER,
        dropdown_fg_color=COLOR_SURFACE_ALT,
        dropdown_hover_color=COLOR_SECONDARY_HOVER,
        text_color=COLOR_TEXT,
    )
    layout_menu.configure(
        command=lambda display: app._set_export_layout(
            EXPORT_LAYOUT_BY_DISPLAY[display], layout_menu
        )
    )
    layout_menu.set(EXPORT_LAYOUT_DISPLAY[app.export_layout_var.get()])
    layout_menu.grid(row=0, column=1, sticky="ew")
    if app.export_layout_var.get() == EXPORT_LAYOUT_SET:
        preset_row = ctk.CTkFrame(body, fg_color="transparent")
        preset_row.pack(fill="x", padx=16, pady=(0, 8))
        preset_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            preset_row,
            text="項目の組み合わせ",
            anchor="w",
            font=UI_FONT_SMALL,
            text_color=COLOR_MUTED,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        preset_menu = ctk.CTkOptionMenu(
            preset_row,
            values=list(app.profile.set_preset_display.values()),
            height=THEME.layout.entry_height,
            font=UI_FONT_SMALL,
            fg_color=COLOR_SECONDARY,
            button_color=COLOR_PRIMARY,
            button_hover_color=COLOR_PRIMARY_HOVER,
            dropdown_fg_color=COLOR_SURFACE_ALT,
            dropdown_hover_color=COLOR_SECONDARY_HOVER,
            text_color=COLOR_TEXT,
        )
        preset_menu.configure(
            command=lambda value: app._set_set_preset(value, preset_menu)
        )
        preset_menu.set(app.set_preset_var.get())
        preset_menu.grid(row=0, column=1, sticky="ew")
        set_error = (
            set_validation_error(app._enabled_fields(), app.set_definition)
            if app.fields
            else None
        )
        if set_error:
            ctk.CTkLabel(
                body,
                text=set_error,
                image=ICONS.get("alert_circle", 16, COLOR_DANGER),
                compound="left",
                anchor="w",
                justify="left",
                font=UI_FONT_SMALL,
                text_color=COLOR_DANGER,
                wraplength=320,
            ).pack(fill="x", padx=16, pady=(0, 6))
        action = ctk.CTkFrame(body, fg_color="transparent")
        action.pack(fill="x", padx=16, pady=(0, 8))
        action.grid_columnconfigure(0, weight=1)
        pending = app.pending_set_id is not None
        button_text = app._set_creation_button_text()
        ctk.CTkButton(
            action,
            text=button_text,
            image=ICONS.get("plus", 16, THEME.palette.on_color),
            compound="left",
            command=app.begin_set_creation,
            height=THEME.layout.entry_height,
            corner_radius=THEME.layout.control_radius,
            font=UI_FONT_SMALL,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
        ).grid(row=0, column=0, sticky="ew")
        if pending:
            ctk.CTkButton(
                action,
                text="中止",
                image=ICONS.get("x", 15, COLOR_TEXT),
                compound="left",
                command=app.cancel_set_creation,
                width=68,
                height=THEME.layout.entry_height,
                corner_radius=THEME.layout.control_radius,
                font=UI_FONT_SMALL,
                fg_color=COLOR_SECONDARY,
                hover_color=COLOR_SECONDARY_HOVER,
                border_width=1,
                border_color=COLOR_BORDER,
            ).grid(row=0, column=1, padx=(6, 0))
    scroller = AutoHideScrollableFrame(
        body,
        corner_radius=THEME.layout.panel_radius,
        fg_color=COLOR_SURFACE_ALT,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    scroller.pack(side=TOP, fill=BOTH, expand=True, padx=16, pady=(0, 10))
    app.template_fields_scroller = scroller
    if (
        not app.fields
        and app.export_layout_var.get() != EXPORT_LAYOUT_SET
    ):
        app._empty_state(
            scroller,
            "項目がありません",
            "画像上で範囲をドラッグ",
            THEME.copy.saved_template_hint,
            icon="scan",
        )
    elif app.export_layout_var.get() == EXPORT_LAYOUT_SET:
        app._render_set_fields(scroller)
    else:
        for idx, field in enumerate(app.fields):
            app._field_row(scroller, idx)

