from __future__ import annotations
from typing import TYPE_CHECKING
from megido_ocr_excel.models import EXPORT_LAYOUT_SET
from megido_ocr_excel.models import set_validation_error
from megido_ocr_excel.ui.icons import ICONS
from megido_ocr_excel.ui.scrollable import AutoHideScrollableFrame
from megido_ocr_excel.ui.theme import THEME
from megido_ocr_excel.ui.workflow_style import COLOR_BORDER
from megido_ocr_excel.ui.workflow_style import COLOR_DANGER
from megido_ocr_excel.ui.workflow_style import COLOR_MUTED
from megido_ocr_excel.ui.workflow_style import COLOR_PRIMARY
from megido_ocr_excel.ui.workflow_style import COLOR_PRIMARY_HOVER
from megido_ocr_excel.ui.workflow_style import COLOR_SECONDARY
from megido_ocr_excel.ui.workflow_style import COLOR_SECONDARY_HOVER
from megido_ocr_excel.ui.workflow_style import COLOR_SURFACE_ALT
from megido_ocr_excel.ui.workflow_style import COLOR_TEXT
from megido_ocr_excel.ui.workflow_style import EXPORT_LAYOUT_BY_DISPLAY
from megido_ocr_excel.ui.workflow_style import EXPORT_LAYOUT_DISPLAY
from megido_ocr_excel.ui.workflow_style import UI_FONT_SMALL
from tkinter import BOTH
from tkinter import TOP
import customtkinter as ctk

if TYPE_CHECKING:
    from megido_ocr_excel.application import ImageOcrExcelApp


def render(self: ImageOcrExcelApp) -> None:
    body = self.side_body
    assert body is not None
    self.field_check_vars = []
    self.field_row_widgets = []
    self.field_row_by_index = {}
    self.field_drag_handle_by_index = {}
    self.set_drop_section_by_id = {}
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
        command=lambda display: self._set_export_layout(
            EXPORT_LAYOUT_BY_DISPLAY[display], layout_menu
        )
    )
    layout_menu.set(EXPORT_LAYOUT_DISPLAY[self.export_layout_var.get()])
    layout_menu.grid(row=0, column=1, sticky="ew")
    if self.export_layout_var.get() == EXPORT_LAYOUT_SET:
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
            values=list(self.profile.set_preset_display.values()),
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
            command=lambda value: self._set_set_preset(value, preset_menu)
        )
        preset_menu.set(self.set_preset_var.get())
        preset_menu.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(
            body,
            text=THEME.copy.set_layout_note,
            anchor="w",
            justify="left",
            font=UI_FONT_SMALL,
            text_color=COLOR_MUTED,
            wraplength=350,
        ).pack(fill="x", padx=16, pady=(0, 6))
        set_error = (
            set_validation_error(self._enabled_fields(), self.set_definition)
            if self.fields
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
        pending = self.pending_set_id is not None
        button_text = self._set_creation_button_text()
        ctk.CTkButton(
            action,
            text=button_text,
            image=ICONS.get("plus", 16, THEME.palette.on_color),
            compound="left",
            command=self.begin_set_creation,
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
                command=self.cancel_set_creation,
                width=68,
                height=THEME.layout.entry_height,
                corner_radius=THEME.layout.control_radius,
                font=UI_FONT_SMALL,
                fg_color=COLOR_SECONDARY,
                hover_color=COLOR_SECONDARY_HOVER,
                border_width=1,
                border_color=COLOR_BORDER,
            ).grid(row=0, column=1, padx=(6, 0))
    else:
        ctk.CTkLabel(
            body,
            text=THEME.copy.image_layout_note,
            anchor="w",
            justify="left",
            font=UI_FONT_SMALL,
            text_color=COLOR_MUTED,
            wraplength=350,
        ).pack(fill="x", padx=16, pady=(0, 6))

    scroller = AutoHideScrollableFrame(
        body,
        corner_radius=THEME.layout.panel_radius,
        fg_color=COLOR_SURFACE_ALT,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    scroller.pack(side=TOP, fill=BOTH, expand=True, padx=16, pady=(0, 10))
    self.template_fields_scroller = scroller
    if (
        not self.fields
        and self.export_layout_var.get() != EXPORT_LAYOUT_SET
    ):
        self._empty_state(
            scroller,
            "項目がありません",
            "画像上で範囲をドラッグ",
            THEME.copy.saved_template_hint,
            icon="scan",
        )
    elif self.export_layout_var.get() == EXPORT_LAYOUT_SET:
        self._render_set_fields(scroller)
    else:
        for idx, field in enumerate(self.fields):
            self._field_row(scroller, idx)

