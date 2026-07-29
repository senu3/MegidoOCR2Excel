from __future__ import annotations

from pathlib import Path

from megido_ocr_excel.app_config import ApplicationConfig, ApplicationCopy
from megido_ocr_excel.profiles import get_profile


PROFILE = get_profile("megido_novel")
CONFIG = ApplicationConfig(
    app_id="megido_ocr_excel",
    app_title="Megido OCR to Excel",
    data_directory_name="MegidoOCR2Excel",
    default_template_name="megido-novel-template.json",
    copy=ApplicationCopy(
        workflow_choice_note=(
            "会話画面は自動検出できます。\n"
            "その他の画面は、新規テンプレートで範囲を指定します。"
        ),
        auto_detection_action="会話を自動検出",
        detection_statuses={
            "normal": "通常会話を1件検出しました。",
            "speakerless": "話者なし会話を1件検出しました。",
            "narration": "中央ナレーションを1件検出しました。",
        },
        detection_fallback_status="自動検出結果を確認してください。",
        detection_failure_status=(
            "会話を自動検出できませんでした。読み取り範囲を確認してください。"
        ),
    ),
)


def main() -> None:
    from megido_ocr_excel.application import main as run_application

    run_application(PROFILE, CONFIG)


def launcher_main(
    argv: list[str] | None = None,
    *,
    project_root: Path | None = None,
) -> int:
    from megido_ocr_excel.launcher.ui import main as run_launcher

    return run_launcher(argv, project_root=project_root, app_config=CONFIG)
