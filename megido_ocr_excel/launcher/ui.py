from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from megido_ocr_excel.launcher.core import (
    LauncherBusy,
    LauncherCancelled,
    LauncherError,
    LauncherPaths,
    LauncherService,
    LauncherStatus,
    SingleInstanceLock,
    explain_uv_installation,
    launcher_paths,
)
from megido_ocr_excel.ui.theme import THEME


logger = logging.getLogger("megido_ocr_excel.launcher")
PALETTE = THEME.palette
FONT_FAMILY = THEME.fonts.family


class LauncherWindow:
    def __init__(
        self,
        root: tk.Tk,
        service: LauncherService,
        status: LauncherStatus,
        *,
        force_repair: bool = False,
    ) -> None:
        self.root = root
        self.service = service
        self.status = status
        self.force_repair = force_repair
        self.running = False
        self.finished = False
        self.exit_code = 0
        self._output_lines: list[str] = []

        self.root.title("Megido OCR to Excel — ランチャー")
        self.root.geometry("600x420")
        self.root.minsize(560, 400)
        self.root.configure(background=PALETTE.app_bg)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)
        self._configure_styles()
        self._build()
        self._center_window()
        self.show_initial_state()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Launcher.Horizontal.TProgressbar",
            troughcolor=PALETTE.border_subtle,
            background=PALETTE.info,
            bordercolor=PALETTE.border_subtle,
            lightcolor=PALETTE.info,
            darkcolor=PALETTE.info,
            thickness=6,
        )

    def _build(self) -> None:
        outer = tk.Frame(self.root, background=PALETTE.app_bg)
        outer.grid(row=0, column=0, sticky="nsew", padx=28, pady=24)
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        header = tk.Frame(outer, background=PALETTE.app_bg)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        icon = tk.Canvas(
            header,
            width=38,
            height=38,
            background=PALETTE.surface_alt,
            highlightthickness=1,
            highlightbackground=PALETTE.border,
        )
        icon.pack(side="left", padx=(0, 12))
        self._draw_scan_icon(icon)
        heading = tk.Frame(header, background=PALETTE.app_bg)
        heading.pack(side="left", fill="x", expand=True)
        tk.Label(
            heading,
            text="Megido OCR to Excel",
            background=PALETTE.app_bg,
            foreground=PALETTE.text,
            anchor="w",
            font=(FONT_FAMILY, 16, "bold"),
        ).pack(fill="x")
        tk.Label(
            heading,
            text="実行環境ランチャー",
            background=PALETTE.app_bg,
            foreground=PALETTE.muted,
            anchor="w",
            font=(FONT_FAMILY, 10),
        ).pack(fill="x", pady=(2, 0))

        self.panel = tk.Frame(
            outer,
            background=PALETTE.surface,
            highlightthickness=1,
            highlightbackground=PALETTE.border,
        )
        self.panel.grid(row=1, column=0, sticky="nsew")
        self.panel.grid_rowconfigure(0, weight=1)
        self.panel.grid_columnconfigure(0, weight=1)

        content = tk.Frame(self.panel, background=PALETTE.surface)
        content.grid(row=0, column=0, sticky="nsew", padx=24, pady=22)
        content.grid_rowconfigure(3, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self.status_title = tk.Label(
            content,
            text="",
            background=PALETTE.surface,
            foreground=PALETTE.text,
            anchor="w",
            font=(FONT_FAMILY, 14, "bold"),
        )
        self.status_title.grid(row=0, column=0, sticky="ew")
        self.status_note = tk.Label(
            content,
            text="",
            background=PALETTE.surface,
            foreground=PALETTE.muted,
            anchor="w",
            justify="left",
            wraplength=500,
            font=(FONT_FAMILY, 10),
        )
        self.status_note.grid(row=1, column=0, sticky="ew", pady=(8, 16))

        self.progress = ttk.Progressbar(
            content,
            mode="indeterminate",
            style="Launcher.Horizontal.TProgressbar",
        )
        self.progress.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        self.progress.grid_remove()

        self.detail = ScrolledText(
            content,
            height=7,
            wrap="word",
            background=PALETTE.input_bg,
            foreground=PALETTE.text,
            insertbackground=PALETTE.text,
            selectbackground=PALETTE.selected_row,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE.border_subtle,
            font=("Consolas", 9),
            padx=10,
            pady=8,
        )
        self.detail.configure(state="disabled")
        self.detail.grid(row=3, column=0, sticky="nsew", pady=(0, 4))
        self.detail.grid_remove()

        self.actions = tk.Frame(content, background=PALETTE.surface)
        self.actions.grid(row=4, column=0, sticky="ew", pady=(18, 0))

    @staticmethod
    def _draw_scan_icon(canvas: tk.Canvas) -> None:
        color = PALETTE.primary
        width = 2
        canvas.create_line(10, 15, 10, 10, 15, 10, fill=color, width=width)
        canvas.create_line(23, 10, 28, 10, 28, 15, fill=color, width=width)
        canvas.create_line(10, 23, 10, 28, 15, 28, fill=color, width=width)
        canvas.create_line(23, 28, 28, 28, 28, 23, fill=color, width=width)
        canvas.create_line(15, 19, 23, 19, fill=color, width=width)

    def _center_window(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _button(
        self,
        text: str,
        command,
        *,
        primary: bool = False,
        danger: bool = False,
    ) -> tk.Button:
        if primary:
            background = PALETTE.primary
            active = PALETTE.primary_hover
            foreground = PALETTE.on_color
        elif danger:
            background = PALETTE.danger
            active = PALETTE.danger_hover
            foreground = PALETTE.on_color
        else:
            background = PALETTE.secondary
            active = PALETTE.secondary_hover
            foreground = PALETTE.text
        return tk.Button(
            self.actions,
            text=text,
            command=command,
            background=background,
            activebackground=active,
            foreground=foreground,
            activeforeground=foreground,
            disabledforeground=PALETTE.muted,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE.border,
            highlightcolor=PALETTE.info,
            cursor="hand2",
            font=(FONT_FAMILY, 10, "bold" if primary else "normal"),
            padx=16,
            pady=8,
        )

    def _clear_actions(self) -> None:
        for child in self.actions.winfo_children():
            child.destroy()

    def _set_detail(self, text: str, *, visible: bool) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if text:
            self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")
        if visible:
            self.detail.grid()
        else:
            self.detail.grid_remove()

    def show_initial_state(self) -> None:
        self.progress.grid_remove()
        self._set_detail("", visible=False)
        self._clear_actions()
        if not self.status.uv_path:
            self.show_error(explain_uv_installation(), allow_retry=False)
            return
        if self.force_repair:
            title = "実行環境を修復"
            note = (
                "PaddleOCRを含む実行環境を、uv.lockに記録された構成へ戻します。"
                "個人ファイルやOCR認識モデルは削除しません。"
            )
            action_text = "修復を開始"
        elif self.status.first_setup:
            title = "初回セットアップ"
            note = (
                "PaddleOCRとアプリの実行に必要なパッケージをダウンロードします。\n"
                "ネットワーク通信と数分程度の時間がかかる場合があります。"
            )
            action_text = "セットアップを開始"
        else:
            title = "アプリを更新"
            note = (
                "uv.lockに記録された依存関係へ実行環境を同期します。"
                "OCR認識モデルとテンプレートは変更しません。"
            )
            action_text = "更新を開始"
        self.status_title.configure(text=title, foreground=PALETTE.text)
        self.status_note.configure(text=note)
        start = self._button(action_text, self.start_prepare, primary=True)
        start.pack(side="right")
        close = self._button("終了", self.request_close)
        close.pack(side="right", padx=(0, 8))
        start.focus_set()

    def start_prepare(self) -> None:
        if self.running:
            return
        self.running = True
        self._output_lines = []
        self._clear_actions()
        self._set_detail("", visible=False)
        self.status_title.configure(text="実行環境を準備しています", foreground=PALETTE.info)
        self.status_note.configure(
            text="必要なパッケージを確認しています。この画面を閉じずにお待ちください。"
        )
        self.progress.grid()
        self.progress.start(12)
        cancel = self._button("セットアップを中止", self.cancel_prepare)
        cancel.pack(side="right")
        cancel.focus_set()

        def on_output(line: str) -> None:
            self._output_lines.append(line)
            self._output_lines = self._output_lines[-40:]

        def worker() -> None:
            try:
                self.service.prepare(on_output)
            except LauncherCancelled as error:
                self.root.after(0, lambda value=error: self.finish_cancelled(value))
            except Exception as error:
                logger.exception("Launcher preparation failed")
                self.root.after(0, lambda value=error: self.finish_error(value))
            else:
                self.root.after(0, self.finish_success)

        threading.Thread(target=worker, name="launcher-setup", daemon=True).start()

    def cancel_prepare(self) -> None:
        if not self.running:
            return
        if not messagebox.askyesno(
            "セットアップを中止",
            "実行環境のセットアップを中止しますか？\n次回起動時にもう一度実行できます。",
            parent=self.root,
        ):
            return
        self.status_title.configure(text="中止しています", foreground=PALETTE.warning)
        self.status_note.configure(text="現在の処理を終了しています。しばらくお待ちください。")
        for child in self.actions.winfo_children():
            child.configure(state="disabled")
        self.service.cancel()

    def finish_cancelled(self, error: Exception) -> None:
        self.running = False
        self.progress.stop()
        self.progress.grid_remove()
        self._clear_actions()
        self.status_title.configure(text="セットアップを中止しました", foreground=PALETTE.warning)
        self.status_note.configure(text=str(error))
        retry = self._button("もう一度試す", self.start_prepare, primary=True)
        retry.pack(side="right")
        close = self._button("終了", self.request_close)
        close.pack(side="right", padx=(0, 8))
        retry.focus_set()

    def finish_error(self, error: Exception) -> None:
        self.running = False
        self.progress.stop()
        self.progress.grid_remove()
        detail = str(error).strip() or "不明なエラーが発生しました。"
        if self._output_lines:
            output = "\n".join(self._output_lines[-20:])
            if output not in detail:
                detail = f"{detail}\n\n--- uv output ---\n{output}"
        self.show_error(detail, allow_retry=True)

    def show_error(self, detail: str, *, allow_retry: bool) -> None:
        self._clear_actions()
        self.status_title.configure(text="実行環境を準備できませんでした", foreground=PALETTE.danger)
        self.status_note.configure(
            text="内容を確認して再試行してください。診断情報はランチャーログにも保存されています。"
        )
        self._set_detail(detail, visible=True)
        if allow_retry:
            retry = self._button("再試行", self.start_prepare, primary=True)
            retry.pack(side="right")
            retry.focus_set()
        close = self._button("終了", self.request_close)
        close.pack(side="right", padx=(0, 8))
        logs = self._button("ログを開く", self.open_log_folder)
        logs.pack(side="left")

    def finish_success(self) -> None:
        self.running = False
        self.finished = True
        self.progress.stop()
        self.progress.grid_remove()
        self._clear_actions()
        self._set_detail("", visible=False)
        self.status_title.configure(text="準備が完了しました", foreground=PALETTE.success)
        self.status_note.configure(text="Megido OCR to Excelを起動します。")
        self.root.after(450, self.launch_application)

    def launch_application(self) -> None:
        try:
            self.service.launch_application()
        except Exception as error:
            logger.exception("Failed to launch application")
            self.finished = False
            self.finish_error(error)
            return
        self.root.destroy()

    def open_log_folder(self) -> None:
        folder = self.service.paths.log_dir
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as error:
            messagebox.showerror(
                "ログを開けません",
                f"次のフォルダーを手動で開いてください。\n\n{folder}\n\n{error}",
                parent=self.root,
            )

    def request_close(self) -> None:
        if self.running:
            self.cancel_prepare()
            return
        self.root.destroy()


def run_gui(
    service: LauncherService,
    status: LauncherStatus,
    *,
    force_repair: bool,
) -> int:
    root = tk.Tk()
    window = LauncherWindow(root, service, status, force_repair=force_repair)
    root.mainloop()
    return window.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Megido OCR to Excel launcher")
    parser.add_argument("--repair", action="store_true", help="実行環境を再同期する")
    parser.add_argument("--check", action="store_true", help="準備状態をJSONで表示する")
    parser.add_argument(
        "--project-root",
        type=Path,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None, *, project_root: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    root_path = (
        args.project_root.resolve()
        if args.project_root is not None
        else (project_root or Path(__file__).resolve().parents[2]).resolve()
    )
    paths = launcher_paths(root_path)
    service = LauncherService(paths)
    status = service.status(force_repair=args.repair)
    if args.check:
        print(
            json.dumps(
                {
                    "ready": status.ready,
                    "reason": status.reason,
                    "first_setup": status.first_setup,
                    "uv_available": status.uv_path is not None,
                    "runtime_dir": str(paths.runtime_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if status.ready else 2

    lock = SingleInstanceLock(paths.lock_path)
    try:
        lock.acquire()
    except LauncherBusy as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("ランチャーを起動できません", str(error), parent=root)
        root.destroy()
        return 3
    try:
        if status.ready and not args.repair:
            service.launch_application()
            return 0
        return run_gui(service, status, force_repair=args.repair)
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
