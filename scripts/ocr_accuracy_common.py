from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from megido_ocr_excel.config import APP_PROFILE
from megido_ocr_excel.ocr.dialogue_detector import detect_complete_dialogue_pairs, include_supplement_candidates
from megido_ocr_excel.ocr.engine import OcrEngine, apply_correction_rules, apply_postprocess, clean_text, detect_tesseract, format_detected_text, prepare_for_ocr, scaled_field
from megido_ocr_excel.models import CoordinateSettings, OCR_PREPROCESS_OPTIONS, OCR_SCALE_OPTIONS, SET_SLOT_SPEAKER, SET_SLOT_TEXT, TemplateField
from megido_ocr_excel.templates import coordinate_settings_from_template, correction_rules_from_template, fields_from_template, load_template, text_formatting_from_template

try:
    import pytesseract
except ImportError:
    pytesseract = None


@dataclass
class AccuracyRow:
    image: str
    expected: str
    actual: str
    similarity: float
    exact: bool
    normalized_match: bool
    error: str


@dataclass(frozen=True)
class ExpectedSetRow:
    speaker: str
    text: str


def build_parser(
    field_name: str,
    default_psm: int,
    default_preprocess: str,
    default_scale: str,
    default_threshold: int,
    default_lang: str,
    default_line_split: str,
    default_line_padding: int,
    default_line_detect_threshold: int,
    default_line_detect_min_ratio: float,
    default_line_detect_gap: int,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{field_name} のOCR精度を測定します。")
    parser.add_argument("--samples-dir", type=Path, default=ROOT / ".samples")
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="任意のテンプレートで測定する場合だけ指定します。",
    )
    parser.add_argument("--field", default=field_name)
    parser.add_argument("--lang", default=default_lang)
    parser.add_argument("--backend", choices=["tesseract", "paddle"], default=APP_PROFILE.default_backend)
    parser.add_argument("--tesseract", default="")
    parser.add_argument("--tessdata-dir", type=Path, default=None)
    parser.add_argument("--psm", type=int, default=default_psm)
    parser.add_argument("--oem", type=int, default=3)
    parser.add_argument("--preprocess", choices=OCR_PREPROCESS_OPTIONS, default=default_preprocess)
    parser.add_argument("--scale", choices=OCR_SCALE_OPTIONS, default=default_scale)
    parser.add_argument("--threshold", type=int, default=default_threshold)
    parser.add_argument("--line-split", choices=["none", "fixed", "expected", "detected"], default=default_line_split)
    parser.add_argument("--line-count", type=int, default=3, help="--line-split fixed の分割行数。")
    parser.add_argument("--line-padding", type=int, default=default_line_padding, help="行分割時に各行へ追加する上下余白px。")
    parser.add_argument("--line-detect-threshold", type=int, default=default_line_detect_threshold, help="--line-split detected で黒画素とみなす明度。")
    parser.add_argument("--line-detect-min-ratio", type=float, default=default_line_detect_min_ratio, help="--line-split detected で行とみなす黒画素数の横幅比率。")
    parser.add_argument("--line-detect-gap", type=int, default=default_line_detect_gap, help="--line-split detected で同一行として結合する縦方向gap。")
    parser.add_argument("--match-space-normalized", action="store_true", help="比較時だけ空白、改行、全角スペースを除外します。")
    parser.add_argument("--limit", type=int, default=0, help="先頭N件だけ測定します。0なら全件。")
    parser.add_argument("--csv-out", type=Path, default=None)
    parser.add_argument("--save-crops", type=Path, default=None)
    return parser


def run_accuracy(
    field_name: str,
    default_psm: int,
    default_preprocess: str = "default",
    default_scale: str = "auto",
    default_threshold: int = 180,
    default_lang: str = "",
    default_line_split: str = "none",
    default_line_padding: int = 12,
    default_line_detect_threshold: int = 90,
    default_line_detect_min_ratio: float = 0.015,
    default_line_detect_gap: int = 10,
    default_match_space_normalized: bool = False,
) -> int:
    args = build_parser(
        field_name,
        default_psm,
        default_preprocess,
        default_scale,
        default_threshold,
        default_lang,
        default_line_split,
        default_line_padding,
        default_line_detect_threshold,
        default_line_detect_min_ratio,
        default_line_detect_gap,
    ).parse_args()
    if default_match_space_normalized:
        args.match_space_normalized = True
    if args.backend == "tesseract" and pytesseract is None:
        print("pytesseract がインストールされていません。", file=sys.stderr)
        return 2

    template: dict = {}
    if args.template is not None:
        template = load_template(
            args.template, expected_profile_id=APP_PROFILE.profile_id
        )
        args.coordinate_settings = coordinate_settings_from_template(template)
        args.text_formatting = text_formatting_from_template(
            template, APP_PROFILE.text_formatting_settings()
        )
        args.correction_rules = correction_rules_from_template(template)
        fields = fields_from_template(template)
    else:
        args.coordinate_settings = APP_PROFILE.coordinate_settings()
        args.text_formatting = APP_PROFILE.text_formatting_settings()
        args.correction_rules = []
        fields = APP_PROFILE.auto_detection_fields()
    field = find_field(fields, args.field)
    if field is None:
        names = ", ".join(item.name for item in fields)
        print(f"測定対象の項目がありません: {args.field}（候補: {names}）", file=sys.stderr)
        return 2

    tesseract = args.tesseract or str(template.get("tesseract_path") or "") or detect_tesseract()
    args.tesseract = tesseract
    if args.backend == "tesseract" and tesseract:
        pytesseract.pytesseract.tesseract_cmd = tesseract

    lang = args.lang or str(template.get("lang") or "") or APP_PROFILE.default_lang
    args.lang = lang
    pairs = sample_pairs(args.samples_dir, args.limit)
    if not pairs:
        print(f"測定対象がありません: {args.samples_dir}", file=sys.stderr)
        return 2

    if args.save_crops:
        args.save_crops.mkdir(parents=True, exist_ok=True)

    engine = OcrEngine()
    rows: list[AccuracyRow] = []
    for image_path, csv_path in pairs:
        expected_sets = read_expected_sets(csv_path)
        expected_values = expected_values_for_field(expected_sets, field)
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as exc:
            rows.extend(
                accuracy_rows_for_unreadable_image(
                    image_path.name, expected_values, str(exc)
                )
            )
            continue

        detected_fields, detection_error = measurement_fields(
            image, fields, field, args.coordinate_settings
        )
        row_count = max(len(expected_values), len(detected_fields), 1)
        count_error = detection_count_error(
            len(expected_values), len(detected_fields), detection_error
        )
        for index in range(row_count):
            expected = expected_values[index] if index < len(expected_values) else ""
            if index < len(detected_fields):
                actual, error = recognize_image(
                    image,
                    detected_fields[index],
                    args,
                    engine,
                    expected,
                    f"{image_path.stem}_{index + 1}",
                )
            else:
                actual, error = "", count_error
            if count_error and not error:
                error = count_error
            label = (
                image_path.name
                if row_count == 1
                else f"{image_path.name}#{index + 1}"
            )
            rows.append(build_accuracy_row(label, expected, actual, error))

    print_report(args.field, args, rows)
    if args.csv_out:
        write_csv(args.csv_out, rows)
        print(f"csv: {args.csv_out}")
    return 1 if any(row.error for row in rows) else 0


def find_field(fields: list[TemplateField], name: str) -> TemplateField | None:
    for field in fields:
        if field.name == name:
            return field
    return None


def sample_pairs(samples_dir: Path, limit: int) -> list[tuple[Path, Path]]:
    pairs = []
    for csv_path in sorted(samples_dir.glob("*.csv"), key=sample_sort_key):
        image_path = csv_path.with_suffix(".png")
        if image_path.exists():
            pairs.append((image_path, csv_path))
    return pairs[:limit] if limit > 0 else pairs


def sample_sort_key(path: Path) -> tuple[int, str]:
    return (int(path.stem), path.name) if path.stem.isdigit() else (10_000, path.name)


def read_expected_sets(csv_path: Path) -> list[ExpectedSetRow]:
    rows = list(csv.reader(csv_path.read_text(encoding="utf-8-sig").splitlines()))
    expected: list[ExpectedSetRow] = []
    pending_speaker: str | None = None
    for row in rows:
        if len(row) < 2:
            continue
        key, value = row[0].strip(), row[1]
        if key == "話者":
            pending_speaker = value
            continue
        if key not in {"セリフ本文", "補足", "補足セリフ"}:
            continue
        speaker = (
            pending_speaker
            if pending_speaker is not None
            else expected[-1].speaker
            if expected
            else ""
        )
        expected.append(ExpectedSetRow(speaker, value))
        pending_speaker = None
    return expected


def expected_values_for_field(
    expected: list[ExpectedSetRow], field: TemplateField
) -> list[str]:
    if field.slot_key == SET_SLOT_SPEAKER or field.name.startswith("話者"):
        return [row.speaker for row in expected]
    return [row.text for row in expected]


def measurement_fields(
    image: Image.Image,
    template_fields: list[TemplateField],
    requested_field: TemplateField,
    coordinate_settings: CoordinateSettings,
) -> tuple[list[TemplateField], str]:
    config = APP_PROFILE.dialogue_log_detection
    if config is None or requested_field.slot_key not in {
        SET_SLOT_SPEAKER,
        SET_SLOT_TEXT,
    }:
        return [requested_field], ""
    detection = include_supplement_candidates(
        detect_complete_dialogue_pairs(
            image,
            template_fields,
            coordinate_settings,
            config,
        )
    )
    if not detection.groups:
        return [], detection.review_reason or "会話を自動検出できませんでした。"
    field_index = 1 if requested_field.slot_key == SET_SLOT_SPEAKER else 2
    return [group[field_index] for group in detection.groups], ""


def detection_count_error(
    expected_count: int, detected_count: int, detection_error: str = ""
) -> str:
    if detection_error:
        return detection_error
    if expected_count == detected_count:
        return ""
    return (
        f"検出件数が正解データと一致しません。"
        f"正解 {expected_count} 件 / 検出 {detected_count} 件"
    )


def accuracy_rows_for_unreadable_image(
    image_name: str, expected_values: list[str], error: str
) -> list[AccuracyRow]:
    values = expected_values or [""]
    row_count = len(values)
    return [
        build_accuracy_row(
            image_name if row_count == 1 else f"{image_name}#{index + 1}",
            expected,
            "",
            f"画像を開けませんでした: {error}",
        )
        for index, expected in enumerate(values)
    ]


def build_accuracy_row(
    image: str, expected: str, actual: str, error: str = ""
) -> AccuracyRow:
    exact = not error and expected == actual
    normalized_match = not error and is_match(expected, actual)
    return AccuracyRow(
        image,
        expected,
        actual,
        score_text(expected, actual),
        exact,
        normalized_match,
        error,
    )


def recognize_image(
    image: Image.Image,
    field: TemplateField,
    args: argparse.Namespace,
    engine: OcrEngine,
    expected: str = "",
    output_stem: str = "sample",
) -> tuple[str, str]:
    region = scaled_field(field, image, args.coordinate_settings)
    if (region.x2 - region.x1) < 1 or (region.y2 - region.y1) < 1:
        return "", "読み取り範囲が画像外、または小さすぎます。"

    crop = image.crop((region.x1, region.y1, region.x2, region.y2))
    if args.backend == "paddle":
        return recognize_with_engine(image, field, args, engine)

    if args.line_split != "none":
        return recognize_lines(crop, field, args, expected, output_stem)

    prepared = prepare_for_ocr(crop, args.preprocess, args.scale, args.threshold)
    if args.save_crops:
        prepared.save(args.save_crops / f"{output_stem}_{field.name}.png")

    try:
        raw_text = pytesseract.image_to_string(prepared, lang=args.lang.strip() or APP_PROFILE.default_lang, config=ocr_config(args))
    except pytesseract.TesseractNotFoundError:
        return "", "Tesseractが見つかりません。"
    except pytesseract.TesseractError as exc:
        return "", str(exc)

    corrected = apply_correction_rules(
        clean_text(raw_text), field, args.correction_rules
    )
    return apply_postprocess(corrected, field), ""


def recognize_with_engine(image: Image.Image, field: TemplateField, args: argparse.Namespace, engine: OcrEngine) -> tuple[str, str]:
    adjusted = replace(
        field,
        ocr_backend=args.backend,
        ocr_preprocess=args.preprocess,
        ocr_scale=args.scale,
        ocr_threshold=args.threshold,
        ocr_psm=args.psm,
        ocr_lang=args.lang,
        ocr_line_split=args.line_split if args.line_split in {"none", "detected"} else "none",
        ocr_line_padding=args.line_padding,
        ocr_line_detect_threshold=args.line_detect_threshold,
        ocr_line_detect_min_ratio=args.line_detect_min_ratio,
        ocr_line_detect_gap=args.line_detect_gap,
    )
    _raw, value, error = engine.recognize_field_detail(
        image,
        adjusted,
        args.lang,
        args.tesseract,
        args.backend,
        args.correction_rules,
        coordinate_settings=args.coordinate_settings,
        text_formatting=args.text_formatting,
    )
    return value or "", error or ""


def recognize_lines(crop: Image.Image, field: TemplateField, args: argparse.Namespace, expected: str, image_stem: str) -> tuple[str, str]:
    bands = line_bands(crop, args, expected)
    parts: list[str] = []
    errors: list[str] = []

    for index, (y1, y2) in enumerate(bands):
        line_crop = crop.crop((0, y1, crop.width, y2))
        prepared = prepare_for_ocr(line_crop, args.preprocess, args.scale, args.threshold)
        if args.save_crops:
            prepared.save(args.save_crops / f"{image_stem}_{field.name}_line{index + 1}.png")
        try:
            raw_text = pytesseract.image_to_string(prepared, lang=args.lang.strip() or APP_PROFILE.default_lang, config=ocr_config(args))
        except pytesseract.TesseractNotFoundError:
            return "", "Tesseractが見つかりません。"
        except pytesseract.TesseractError as exc:
            errors.append(str(exc))
            continue
        cleaned = clean_text(raw_text)
        if cleaned:
            parts.append(cleaned)

    formatted = format_detected_text("\n".join(parts), args.text_formatting)
    corrected = apply_correction_rules(formatted, field, args.correction_rules)
    value = apply_postprocess(corrected, field, preserve_whitespace=True)
    return value, " / ".join(errors)


def line_bands(crop: Image.Image, args: argparse.Namespace, expected: str) -> list[tuple[int, int]]:
    if args.line_split == "detected":
        return detect_line_bands(crop, args)

    line_count = count_expected_lines(expected) if args.line_split == "expected" else max(1, args.line_count)
    height = crop.height
    bands = []
    for index in range(line_count):
        y1 = round(height * index / line_count)
        y2 = round(height * (index + 1) / line_count)
        bands.append((max(0, y1 - args.line_padding), min(height, y2 + args.line_padding)))
    return bands


def detect_line_bands(crop: Image.Image, args: argparse.Namespace) -> list[tuple[int, int]]:
    gray = ImageOps.grayscale(crop)
    pixels = gray.load()
    min_count = max(3, int(crop.width * args.line_detect_min_ratio))
    rows: list[int] = []
    for y in range(gray.height):
        count = 0
        for x in range(gray.width):
            if pixels[x, y] < args.line_detect_threshold:
                count += 1
        if count >= min_count:
            rows.append(y)

    if not rows:
        return [(0, crop.height)]

    bands: list[tuple[int, int]] = []
    start = previous = rows[0]
    for y in rows[1:]:
        if y - previous <= args.line_detect_gap:
            previous = y
            continue
        add_detected_band(bands, crop.height, start, previous, args.line_padding)
        start = previous = y
    add_detected_band(bands, crop.height, start, previous, args.line_padding)
    return bands or [(0, crop.height)]


def add_detected_band(bands: list[tuple[int, int]], height: int, start: int, end: int, padding: int) -> None:
    if end - start <= 8:
        return
    bands.append((max(0, start - padding), min(height, end + padding)))


def count_expected_lines(expected: str) -> int:
    parts = [part for part in re.split(r"\u3000+", expected) if part.strip()]
    return max(1, len(parts))


def ocr_config(args: argparse.Namespace) -> str:
    config_parts = [f"--oem {args.oem}", f"--psm {args.psm}"]
    if args.tessdata_dir:
        config_parts.append(f"--tessdata-dir {args.tessdata_dir}")
    return " ".join(config_parts)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", "", value)


def score_text(expected: str, actual: str) -> float:
    return SequenceMatcher(None, normalize_text(expected), normalize_text(actual)).ratio()


def is_match(expected: str, actual: str) -> bool:
    return normalize_text(expected) == normalize_text(actual)


def print_report(field_name: str, args: argparse.Namespace, rows: list[AccuracyRow]) -> None:
    avg = sum(row.similarity for row in rows) / len(rows) if rows else 0.0
    exact = sum(1 for row in rows if row.exact)
    normalized = sum(1 for row in rows if row.normalized_match)
    matched = normalized if args.match_space_normalized else exact
    match_label = "space_normalized_match" if args.match_space_normalized else "exact_match"
    print(f"field: {field_name}")
    tessdata = f" tessdata_dir={args.tessdata_dir}" if args.tessdata_dir else ""
    line_split = f" line_split={args.line_split}"
    if args.line_split == "fixed":
        line_split += f" line_count={args.line_count}"
    if args.line_split != "none":
        line_split += f" line_padding={args.line_padding}"
    if args.line_split == "detected":
        line_split += f" line_detect_threshold={args.line_detect_threshold} line_detect_min_ratio={args.line_detect_min_ratio} line_detect_gap={args.line_detect_gap}"
    formatting = (
        f" line_join={args.text_formatting.line_join}"
        f" fullwidth_ascii={args.text_formatting.fullwidth_ascii}"
    )
    print(f"settings: backend={args.backend} preprocess={args.preprocess} scale={args.scale} threshold={args.threshold} psm={args.psm} oem={args.oem} lang={args.lang or APP_PROFILE.default_lang}{tessdata}{line_split}{formatting}")
    if args.match_space_normalized:
        print(f"samples: {len(rows)}  avg_similarity: {avg:.3f}  {match_label}: {matched}/{len(rows)}  exact_match: {exact}/{len(rows)}")
    else:
        print(f"samples: {len(rows)}  avg_similarity: {avg:.3f}  {match_label}: {matched}/{len(rows)}")
    for row in rows:
        marker = "OK" if (row.normalized_match if args.match_space_normalized else row.exact) else "NG"
        print(f"{row.image}: {marker} similarity={row.similarity:.3f}")
        if row.error:
            print(f"  error: {row.error}")
        print(f"  expected: {row.expected}")
        print(f"  actual  : {row.actual}")


def write_csv(path: Path, rows: list[AccuracyRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["image", "expected", "actual", "similarity", "exact", "space_normalized", "error"])
        for row in rows:
            writer.writerow([row.image, row.expected, row.actual, f"{row.similarity:.6f}", row.exact, row.normalized_match, row.error])
