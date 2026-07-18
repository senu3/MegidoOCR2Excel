from __future__ import annotations

import argparse
from pathlib import Path
import sys

import customtkinter as ctk
from PIL import ImageGrab

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import megido_ocr_excel.application as app_module
from megido_ocr_excel.ocr.environment import (
    OCR_ENV_LOCATION_ERROR,
    OCR_ENV_READY,
    OCR_ENV_SETUP,
    OCR_ENV_UNAVAILABLE,
    OCR_ENV_VERIFY,
    OcrEnvironmentSettings,
    OcrEnvironmentStatus,
)


VALIDATION_STATES = (
    "setup",
    "checking",
    "check-failed",
    "location-error",
    "unavailable",
    "ready",
)


def status_for_state(state: str) -> OcrEnvironmentStatus:
    cache_dir = Path.home() / ".paddlex-ui-validation"
    states = {
        "setup": (
            OCR_ENV_SETUP,
            "準備が必要",
            "認識モデルを取得します。初回は時間がかかります。",
        ),
        "checking": (
            OCR_ENV_VERIFY,
            "確認が必要",
            "認識モデルを確認してください。",
        ),
        "check-failed": (
            OCR_ENV_VERIFY,
            "確認が必要",
            "認識モデルを確認してください。",
        ),
        "location-error": (
            OCR_ENV_LOCATION_ERROR,
            "保存先を確認",
            "指定した保存先が見つかりません。",
        ),
        "unavailable": (
            OCR_ENV_UNAVAILABLE,
            "再インストールが必要",
            "PaddleOCRの実行ファイルが不足しています。",
        ),
        "ready": (
            OCR_ENV_READY,
            "準備完了",
            "PaddleOCRを使用できます。",
        ),
    }
    status, label, detail = states[state]
    return OcrEnvironmentStatus(status, label, detail, cache_dir, "auto")


class ValidationOcrEnvironmentManager:
    """In-memory OCR state used only by the manual UI validation launcher."""

    def __init__(self, status: OcrEnvironmentStatus) -> None:
        self.status = status
        self.settings = OcrEnvironmentSettings()

    @property
    def cache_dir(self) -> Path:
        return self.status.cache_dir

    @property
    def cache_mode_label(self) -> str:
        return "自動管理"

    def apply_to_process(self) -> Path:
        return self.cache_dir

    def quick_status(self) -> OcrEnvironmentStatus:
        return self.status

    def verify(self, _verifier) -> OcrEnvironmentStatus:
        return self.status

    def invalidate_verification(self) -> None:
        return

    def use_custom_cache(self, path: Path) -> None:
        self.status = OcrEnvironmentStatus(
            OCR_ENV_VERIFY,
            "確認が必要",
            "認識モデルを確認してください。",
            Path(path),
            "custom",
        )
        self.settings = OcrEnvironmentSettings("custom", str(path), "")

    def use_automatic_cache(self) -> None:
        self.settings = OcrEnvironmentSettings()


class ValidationImageOcrExcelApp(app_module.ImageOcrExcelApp):
    def _start_ocr_environment_startup_check(self) -> None:
        """Freeze the checking state so its progress UI can be inspected."""

    def prepare_ocr_environment(self) -> None:
        self.status_var.set(
            "UI検証モードではOCRの取得・確認処理を実行しません。"
        )


def run_validation(state: str, screenshot: Path | None = None) -> None:
    status = status_for_state(state)
    manager = ValidationOcrEnvironmentManager(status)
    app_module.OcrEnvironmentManager = lambda: manager

    root = ctk.CTk()
    app = ValidationImageOcrExcelApp(root)
    root.title(f"{root.title()} [UI検証: {state}]")

    if state == "check-failed":
        app._finish_ocr_startup_check_error(
            RuntimeError("認識モデルを読み込めませんでした。")
        )

    if screenshot is not None:
        def capture() -> None:
            root.update_idletasks()
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

        root.after(700, capture)

    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR準備画面を端末設定へ影響させずに表示します。"
    )
    parser.add_argument(
        "--state",
        choices=VALIDATION_STATES,
        default="setup",
        help="再現するOCR準備状態（既定: setup）",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="指定した画像へ画面を保存して終了する",
    )
    args = parser.parse_args()
    run_validation(args.state, args.screenshot)


if __name__ == "__main__":
    main()
