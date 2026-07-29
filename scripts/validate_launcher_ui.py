from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

import tkinter as tk
from PIL import ImageGrab

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from megido_ocr_excel.launcher.core import LauncherPaths, LauncherStatus
from megido_ocr_excel.launcher.ui import LauncherWindow
from megido_ocr_excel.apps.megido import CONFIG


VALIDATION_STATES = ("first", "update", "repair", "running", "error")


class ValidationService:
    def __init__(self) -> None:
        root = Path("C:/tmp/megido-launcher-validation")
        self.paths = LauncherPaths(
            project_root=PROJECT_ROOT,
            app_data_dir=root,
            runtime_dir=root / "runtime" / "v1",
            state_path=root / "launcher-state.json",
            log_dir=root / "logs",
            log_path=root / "logs" / "launcher.log",
            lock_path=root / "launcher.lock",
        )
        self.force_reinstall_requested = False

    def prepare(self, on_output=None, *, force_reinstall: bool = False) -> None:
        self.force_reinstall_requested = force_reinstall
        if on_output is not None:
            on_output("Resolved application dependencies")
        time.sleep(10)

    def cancel(self) -> None:
        return

    def launch_application(self) -> None:
        return


def status_for_state(state: str) -> LauncherStatus:
    first_setup = state in {"first", "running", "error"}
    return LauncherStatus(
        ready=False,
        reason=(
            "初回セットアップが必要です。"
            if first_setup
            else "アプリの更新を適用します。"
        ),
        first_setup=first_setup,
        uv_path="C:/tools/uv.exe",
    )


def run(state: str, screenshot: Path) -> None:
    service = ValidationService()
    status = status_for_state(state)
    root = tk.Tk()
    window = LauncherWindow(
        root,
        service,  # type: ignore[arg-type]
        status,
        CONFIG,
        force_repair=state == "repair",
    )
    if state == "running":
        root.after(100, window.start_prepare)
    elif state == "error":
        root.after(
            100,
            lambda: window.show_error(
                "ネットワークへ接続できませんでした。\nuvの設定と接続を確認してください。",
                allow_retry=True,
            ),
        )

    def capture() -> None:
        root.update()
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        width = root.winfo_width()
        height = root.winfo_height()
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(
            bbox=(x, y, x + width, y + height),
            all_screens=True,
        ).save(screenshot)
        root.destroy()

    root.after(800, capture)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="ランチャーUI検証")
    parser.add_argument(
        "--state", choices=VALIDATION_STATES, default="first"
    )
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    run(args.state, args.screenshot)


if __name__ == "__main__":
    main()
