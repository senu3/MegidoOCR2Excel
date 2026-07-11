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

from megido_app_config import APP_PROFILE
from ocr_engine import OcrEngine, apply_postprocess, clean_text, detect_tesseract, prepare_for_ocr, scaled_field
from ocr_models import OCR_PREPROCESS_OPTIONS, OCR_SCALE_OPTIONS, TemplateField
from template_store import coordinate_settings_from_template, fields_from_template, load_template

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
    parser.add_argument("--template", type=Path, default=ROOT / ".samples" / "megido_novel_template.json")
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

    template = load_template(args.template, expected_profile_id=APP_PROFILE.profile_id)
    args.coordinate_settings = coordinate_settings_from_template(template)
    fields = fields_from_template(template)
    field = find_field(fields, args.field)
    if field is None:
        names = ", ".join(item.name for item in fields)
        print(f"テンプレートに項目がありません: {args.field}（候補: {names}）", file=sys.stderr)
        return 2

    tesseract = args.tesseract or str(template.get("tesseract_path") or "") or detect_tesseract()
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
        expected = read_expected(csv_path, field.name)
        actual, error = recognize(image_path, field, args, engine, expected)
        similarity = score_text(expected, actual)
        exact = expected == actual
        rows.append(AccuracyRow(image_path.name, expected, actual, similarity, exact, is_match(expected, actual), error))

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


def read_expected(csv_path: Path, field_name: str) -> str:
    rows = list(csv.reader(csv_path.read_text(encoding="utf-8-sig").splitlines()))
    data = {row[0]: row[1] for row in rows if len(row) >= 2}
    return data.get(field_name, "")


def recognize(image_path: Path, field: TemplateField, args: argparse.Namespace, engine: OcrEngine, expected: str = "") -> tuple[str, str]:
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as exc:
        return "", f"画像を開けませんでした: {exc}"

    region = scaled_field(field, image, args.coordinate_settings)
    if (region.x2 - region.x1) < 1 or (region.y2 - region.y1) < 1:
        return "", "読み取り範囲が画像外、または小さすぎます。"

    crop = image.crop((region.x1, region.y1, region.x2, region.y2))
    if args.backend == "paddle":
        return recognize_with_engine(image, field, args, engine)

    if args.line_split != "none":
        return recognize_lines(crop, field, args, expected, image_path.stem)

    prepared = prepare_for_ocr(crop, args.preprocess, args.scale, args.threshold)
    if args.save_crops:
        prepared.save(args.save_crops / f"{image_path.stem}_{field.name}.png")

    try:
        raw_text = pytesseract.image_to_string(prepared, lang=args.lang.strip() or APP_PROFILE.default_lang, config=ocr_config(args))
    except pytesseract.TesseractNotFoundError:
        return "", "Tesseractが見つかりません。"
    except pytesseract.TesseractError as exc:
        return "", str(exc)

    return apply_postprocess(clean_text(raw_text), field), ""


def recognize_with_engine(image: Image.Image, field: TemplateField, args: argparse.Namespace, engine: OcrEngine) -> tuple[str, str]:
    adjusted = replace(
        field,
        ocr_backend="paddle",
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
        coordinate_settings=args.coordinate_settings,
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

    if errors:
        return apply_postprocess(" ".join(parts), field), " / ".join(errors)
    return apply_postprocess(" ".join(parts), field), ""


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
    print(f"settings: backend={args.backend} preprocess={args.preprocess} scale={args.scale} threshold={args.threshold} psm={args.psm} oem={args.oem} lang={args.lang or APP_PROFILE.default_lang}{tessdata}{line_split}")
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
