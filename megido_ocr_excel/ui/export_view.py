from __future__ import annotations
from typing import TYPE_CHECKING
from tkinter import Button, ttk
import customtkinter as ctk

from megido_ocr_excel.ui.icons import (
    ICONS,
)
from megido_ocr_excel.ui.theme import (
    THEME,
)
from megido_ocr_excel.ui.workflow_style import (
    native_font,
    COLOR_BORDER,
    COLOR_CTA,
    COLOR_CTA_HOVER,
    COLOR_MUTED,
    COLOR_SECONDARY,
    COLOR_SECONDARY_HOVER,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    UI_FONT_BOLD,
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
    body = app.side_body
    assert body is not None

    if app.export_result_filter and app.last_export_result is not None:
        render_result(app, body)
        return

    content = ctk.CTkScrollableFrame(
        body,
        corner_radius=0,
        fg_color=COLOR_SURFACE,
        scrollbar_button_color=COLOR_SECONDARY,
        scrollbar_button_hover_color=COLOR_SECONDARY_HOVER,
    )
    content.pack(side=TOP, fill=BOTH, expand=True)

    if app.last_export_result is not None:
        def reopen_result():
            app.export_result_filter = "要確認" if app.image_queue.failed_files() else "完了"
            app._render_side_body()
        ctk.CTkButton(content, text="保存結果に戻る", font=UI_FONT_SMALL, command=reopen_result,
                      fg_color=COLOR_SECONDARY).pack(fill="x", padx=16, pady=(0, 8))

    warnings = getattr(app, "aspect_warnings", {}) if app.auto_detection_enabled else {}
    if warnings:
        warning_panel = ctk.CTkFrame(content, fg_color=COLOR_SURFACE_ALT)
        warning_panel.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(warning_panel, text=f"自動検出の対象外  {len(warnings)} 枚",
                     anchor="w", font=UI_FONT_BOLD).pack(fill="x", padx=8)
        for path in warnings:
            ctk.CTkButton(warning_panel, font=UI_FONT_SMALL, text=path.name, anchor="w",
                          fg_color=COLOR_SECONDARY, command=lambda p=path: app.show_queue_image(p)
                          ).pack(fill="x", padx=8, pady=2)

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
        textvariable=app.folder_var,
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
        command=app.open_image_folder,
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
        textvariable=app.output_var,
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
        command=app.select_output_file,
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

    app._render_image_queue(content)
    app._render_excel_output_settings(content)

    enabled_count = len(app._enabled_fields())
    image_count = len(app.image_queue.included_files())
    app._render_export_structure_summary(content, image_count, enabled_count)

    actions = ctk.CTkFrame(body, fg_color=COLOR_SURFACE)
    actions.pack(side=BOTTOM, fill="x", padx=16, pady=(8, 14))
    actions.grid_columnconfigure(0, weight=1)
    ctk.CTkButton(
        actions,
        text="Excel出力",
        image=ICONS.get("table", 18, THEME.palette.on_color),
        compound="left",
        command=app.export_to_excel,
        height=THEME.layout.export_button_height,
        corner_radius=THEME.layout.control_radius,
        font=UI_FONT_BOLD,
        fg_color=COLOR_CTA,
        hover_color=COLOR_CTA_HOVER,
    ).grid(row=0, column=0, sticky="ew")


def render_result(app, body) -> None:
    result = app.last_export_result
    failed = result.failed_records
    completed = [record for record in result.records if not record.errors]
    excluded = {item.path for item in app.image_queue.items if not item.included}
    groups = {
        "要確認": [record for record in failed if record.image_path not in excluded],
        "完了": completed,
    }
    omitted = [record for record in failed if record.image_path in excluded]
    if omitted:
        groups["除外"] = omitted

    def change_group(group):
        app.export_result_filter = group
        if groups.get(group):
            app.show_queue_image(groups[group][0].image_path)
        app._render_side_body()

    def settings():
        app.export_result_filter = ""
        app._render_side_body()

    footer = ctk.CTkFrame(body, fg_color=COLOR_SURFACE_ALT)
    footer.pack(side=BOTTOM, fill="x", padx=10, pady=8)
    path = app.last_export_output_path
    ctk.CTkLabel(footer, text=f"保存済み  ·  {path.name}", anchor="w",
                 wraplength=300, font=UI_FONT_SMALL).pack(fill="x", padx=10, pady=4)
    ctk.CTkButton(footer, text="ブックを開く" if app.last_export_format == "excel" else "CSVを開く",
                  font=UI_FONT_SMALL, command=app.open_saved_output).pack(side="left", padx=8, pady=6)
    ctk.CTkButton(footer, text="出力設定へ", width=92, fg_color=COLOR_SECONDARY,
                  font=UI_FONT_SMALL, command=settings).pack(side="right", padx=8, pady=6)
    tabs = ctk.CTkFrame(body, fg_color="transparent")
    tabs.pack(fill="x", padx=10, pady=6)
    for name, records in groups.items():
        ctk.CTkButton(tabs, font=UI_FONT_SMALL, text=f"{name}  {len(records)}", width=80,
                      fg_color=COLOR_CTA if name == app.export_result_filter else COLOR_SECONDARY,
                      command=lambda key=name: change_group(key)).pack(side="left", padx=2)

    records = groups.get(app.export_result_filter, [])
    style = ttk.Style(body)
    style.configure("Export.Treeview", rowheight=32, background=COLOR_SURFACE_ALT,
                    foreground=COLOR_TEXT, fieldbackground=COLOR_SURFACE_ALT)
    def sync_native_fonts(_event=None):
        style.configure("Export.Treeview", font=native_font(body))
        style.configure("Export.Treeview.Heading", font=native_font(body, UI_FONT_BOLD))
        for widget in detail.winfo_children():
            if isinstance(widget, Button):
                widget.configure(font=native_font(body))

    style.map("Export.Treeview", background=[("selected", COLOR_CTA)],
              foreground=[("selected", THEME.palette.on_color)])
    holder = ctk.CTkFrame(body)
    holder.pack(fill=BOTH, expand=True, padx=10)
    tree = ttk.Treeview(holder, columns=("file", "reason"), show="headings",
                        height=5, selectmode="browse", style="Export.Treeview")
    scroll = ttk.Scrollbar(holder, command=tree.yview)
    scroll.pack(side="right", fill="y")
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(fill=BOTH, expand=True)
    for column, title, width in (("file", "画像", 130), ("reason", "処理結果", 150)):
        tree.heading(column, text=title)
        tree.column(column, width=width, minwidth=45)
    detail = ctk.CTkFrame(body, fg_color=COLOR_SURFACE_ALT)
    detail.pack(fill="x", padx=10, pady=6)

    sync_native_fonts()
    body.bind("<Configure>", sync_native_fonts, add="+")

    def show(record):
        tree.unbind("<Tab>")
        for child in detail.winfo_children():
            child.destroy()
        path = record.image_path
        if app.image_path != path:
            app.show_queue_image(path)
        errors = [error.error for error in record.errors]
        reason = "／".join(dict.fromkeys(errors))
        if reason:
            ctk.CTkLabel(detail, text=reason, wraplength=310, anchor="w",
                         justify="left", font=UI_FONT_SMALL).pack(fill="x", padx=8)
        if app.export_result_filter == "要確認":
            manual = any(error.field in ("セット確認", "セット検出") for error in record.errors)
            def act():
                if manual:
                    app.edit_failed_image(path)
                else:
                    app.retry_failed_images(path)

            action = Button(detail, text="この画像でテンプレート作成" if manual else "この画像を再実行",
                            command=act, background=COLOR_CTA, foreground=THEME.palette.on_color,
                            font=native_font(body), relief="flat", padx=10, pady=4,
                            highlightthickness=2, highlightcolor=THEME.palette.on_color, takefocus=True)
            action.pack(side="left", padx=6, pady=6)
            action.bind("<Return>", lambda _event: action.invoke())
            tree.bind("<Tab>", lambda _event: (action.focus_set(), "break")[1])

            def exclude():
                app.set_queue_item_included(path, False)
                remaining = [r for r in groups["要確認"] if r.image_path != path]
                if remaining:
                    app.show_queue_image(remaining[0].image_path)
                else:
                    app.export_result_filter = "除外"
                app._render_side_body()

            ctk.CTkButton(detail, text="対象から除外", width=90, fg_color=COLOR_SECONDARY,
                          font=UI_FONT_SMALL, command=exclude).pack(side="right", padx=6)

    for idx, record in enumerate(records):
        reason = record.errors[0].error if record.errors else "完了"
        tree.insert("", "end", iid=str(idx), values=(record.image_path.name, reason))
    if records:
        idx = next((i for i,r in enumerate(records) if r.image_path == app.image_path), 0)
        tree.selection_set(str(idx))
        tree.focus(str(idx))
        tree.see(str(idx))
        show(records[idx])
        def select(_event):
            selection = tree.selection()
            if selection:
                show(records[int(selection[0])])
        tree.bind("<<TreeviewSelect>>", select)
    if result.notices or result.report_sheets:
        info = f"通知 {len(result.notices)} 件"
        if result.report_sheets:
            info += "  ·  " + "、".join(result.report_sheets)
        ctk.CTkLabel(body, text=info, wraplength=320, font=UI_FONT_SMALL,
                     text_color=COLOR_MUTED).pack(fill="x", padx=10)
