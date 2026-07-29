from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageGrab

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from megido_ocr_excel.application import (
    EXPORT_LAYOUT_IMAGE_ROW,
    MODE_EXPORT,
    MODE_REVIEW,
    MODE_TEMPLATE,
    ImageOcrExcelApp,
)
from megido_ocr_excel.apps.megido import CONFIG, PROFILE
from megido_ocr_excel.models import (
    COORDINATE_SPACE_IMAGE,
    CoordinateSettings,
    TemplateField,
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        Path("C:/Windows/Fonts/YuGothB.ttc")
        if bold
        else Path("C:/Windows/Fonts/YuGothM.ttc"),
        Path("C:/Windows/Fonts/meiryob.ttc")
        if bold
        else Path("C:/Windows/Fonts/meiryo.ttc"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    raise FileNotFoundError("ガイド用サンプルに使用できる日本語フォントがありません。")


def _build_sample_images(sample_dir: Path) -> list[Path]:
    sample_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, dialogue in enumerate(
        (
            "これはガイド用のサンプルです。",
            "別の画像でも読み取り範囲を確認できます。",
        ),
        start=1,
    ):
        image = Image.new("RGB", (1080, 720), "#09070d")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (54, 56, 1026, 664),
            radius=28,
            fill="#171220",
            outline="#5d3a80",
            width=3,
        )
        draw.text(
            (92, 92),
            "DOCUMENTATION SAMPLE",
            font=_font(22, bold=True),
            fill="#a779dc",
        )
        draw.text(
            (92, 172),
            f"ガイド用サンプル画像 {index}",
            font=_font(46, bold=True),
            fill="#f3eff8",
        )
        draw.rounded_rectangle(
            (92, 410, 988, 622),
            radius=18,
            fill="#0d0b12",
            outline="#3c2d4d",
            width=2,
        )
        draw.text(
            (126, 438),
            "ガイド係",
            font=_font(34, bold=True),
            fill="#caa3f4",
        )
        draw.text(
            (126, 520),
            dialogue,
            font=_font(35),
            fill="#ffffff",
        )
        path = sample_dir / f"scene-{index:02}.png"
        image.save(path)
        paths.append(path)
    return paths


def _capture(root: ctk.CTk, output_path: Path) -> None:
    root.update()
    root.update_idletasks()
    x = root.winfo_rootx()
    y = root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(
        bbox=(x, y, x + width, y + height),
        all_screens=True,
    ).save(output_path)


def _prepare_sample_state(
    app: ImageOcrExcelApp,
    sample_dir: Path,
    image_paths: list[Path],
) -> None:
    app.workflow_started = True
    app.auto_detection_enabled = False
    app._hide_workflow_choice()
    app.source_folder = sample_dir
    app.image_files = image_paths
    app.image_queue.reset(image_paths)
    app.current_image_index = 0
    app.coordinate_settings = CoordinateSettings(
        coordinate_space=COORDINATE_SPACE_IMAGE
    )
    app.fields = [
        TemplateField(
            "話者",
            112,
            420,
            460,
            492,
            source_width=1080,
            source_height=720,
            ocr_lang="jpn",
        ),
        TemplateField(
            "セリフ本文",
            112,
            506,
            970,
            590,
            source_width=1080,
            source_height=720,
            ocr_lang="jpn",
        ),
    ]
    app.selected_index = 0
    app.export_layout_var.set(EXPORT_LAYOUT_IMAGE_ROW)
    app._load_current_image(auto_ocr=False)
    app.folder_var.set(app._folder_status_text())
    app.output_path = sample_dir / "sample-output.xlsx"
    app.output_var.set(app.output_path.name)
    app._mark_clean()


def _recognize_sample(app: ImageOcrExcelApp) -> None:
    assert app.original_image is not None
    raw_results: list[str] = []
    results: list[str] = []
    for field in app.fields:
        raw, text, error = app.ocr_engine.recognize_field_detail(
            app.original_image,
            app._field_for_ocr(field),
            app.lang_var.get(),
            "",
            app.profile.default_backend,
            app.correction_rules,
            app.coordinate_settings,
            app.text_formatting,
        )
        if error or text is None:
            raise RuntimeError(error or f"{field.name} のOCRに失敗しました。")
        raw_results.append(raw or "")
        results.append(text)
    app.current_raw_results = raw_results
    app.current_results = results
    app.status_var.set("全項目をテストしました。")


def capture_all(output_dir: Path) -> None:
    sample_dir = Path(tempfile.gettempdir()) / "megido-user-guide-sample"
    image_paths = _build_sample_images(sample_dir)

    root = ctk.CTk()
    app = ImageOcrExcelApp(root, PROFILE, CONFIG)
    root.update()
    app._show_workflow_choice()
    root.update()

    _capture(root, output_dir / "start-method.png")

    _prepare_sample_state(app, sample_dir, image_paths)
    app.mode_var.set(MODE_TEMPLATE)
    app._render_side_body()
    app.redraw()
    _capture(root, output_dir / "range-and-columns.png")

    _recognize_sample(app)
    app.mode_var.set(MODE_REVIEW)
    app._render_side_body()
    app.redraw()
    _capture(root, output_dir / "recognition-test-result.png")

    app.mode_var.set(MODE_EXPORT)
    app._render_side_body()
    app.redraw()
    _capture(root, output_dir / "excel-output.png")

    app.open_settings_modal()
    _capture(root, output_dir / "basic-settings.png")

    root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ユーザーガイド用の実UIスクリーンショットを撮影します。"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs" / "images" / "user-guide",
    )
    args = parser.parse_args()
    capture_all(args.output_dir.resolve())


if __name__ == "__main__":
    main()
