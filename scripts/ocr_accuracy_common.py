from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ocr_engine import DEFAULT_LANG, apply_postprocess, clean_text, detect_tesseract, prepare_for_ocr, scaled_field
from ocr_models import OCR_PREPROCESS_OPTIONS, OCR_SCALE_OPTIONS, TemplateField
from template_store import fields_from_template, load_template

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
    matched: bool
    error: str


def build_parser(
    field_name: str,
    default_psm: int,
    default_preprocess: str,
    default_scale: str,
    default_threshold: int,
    default_lang: str,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{field_name} のOCR精度を測定します。")
    parser.add_argument("--samples-dir", type=Path, default=ROOT / ".samples")
    parser.add_argument("--template", type=Path, default=ROOT / ".samples" / "megido_novel_template.json")
    parser.add_argument("--field", default=field_name)
    parser.add_argument("--lang", default=default_lang)
    parser.add_argument("--tesseract", default="")
    parser.add_argument("--psm", type=int, default=default_psm)
    parser.add_argument("--oem", type=int, default=3)
    parser.add_argument("--preprocess", choices=OCR_PREPROCESS_OPTIONS, default=default_preprocess)
    parser.add_argument("--scale", choices=OCR_SCALE_OPTIONS, default=default_scale)
    parser.add_argument("--threshold", type=int, default=default_threshold)
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
) -> int:
    args = build_parser(
        field_name,
        default_psm,
        default_preprocess,
        default_scale,
        default_threshold,
        default_lang,
    ).parse_args()
    if pytesseract is None:
        print("pytesseract がインストールされていません。", file=sys.stderr)
        return 2

    template = load_template(args.template)
    fields = fields_from_template(template)
    field = find_field(fields, args.field)
    if field is None:
        names = ", ".join(item.name for item in fields)
        print(f"テンプレートに項目がありません: {args.field}（候補: {names}）", file=sys.stderr)
        return 2

    tesseract = args.tesseract or str(template.get("tesseract_path") or "") or detect_tesseract()
    if tesseract:
        pytesseract.pytesseract.tesseract_cmd = tesseract

    lang = args.lang or str(template.get("lang") or "") or DEFAULT_LANG
    args.lang = lang
    pairs = sample_pairs(args.samples_dir, args.limit)
    if not pairs:
        print(f"測定対象がありません: {args.samples_dir}", file=sys.stderr)
        return 2

    if args.save_crops:
        args.save_crops.mkdir(parents=True, exist_ok=True)

    rows: list[AccuracyRow] = []
    for image_path, csv_path in pairs:
        expected = read_expected(csv_path, field.name)
        actual, error = recognize(image_path, field, args)
        similarity = score_text(expected, actual)
        rows.append(AccuracyRow(image_path.name, expected, actual, similarity, is_match(expected, actual), error))

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


def recognize(image_path: Path, field: TemplateField, args: argparse.Namespace) -> tuple[str, str]:
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as exc:
        return "", f"画像を開けませんでした: {exc}"

    region = scaled_field(field, image)
    if (region.x2 - region.x1) < 1 or (region.y2 - region.y1) < 1:
        return "", "読み取り範囲が画像外、または小さすぎます。"

    crop = image.crop((region.x1, region.y1, region.x2, region.y2))
    prepared = prepare_for_ocr(crop, args.preprocess, args.scale, args.threshold)
    if args.save_crops:
        prepared.save(args.save_crops / f"{image_path.stem}_{field.name}.png")

    config = f"--oem {args.oem} --psm {args.psm}"
    try:
        raw_text = pytesseract.image_to_string(prepared, lang=args.lang.strip() or DEFAULT_LANG, config=config)
    except pytesseract.TesseractNotFoundError:
        return "", "Tesseractが見つかりません。"
    except pytesseract.TesseractError as exc:
        return "", str(exc)

    return apply_postprocess(clean_text(raw_text), field), ""

def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", "", value)


def score_text(expected: str, actual: str) -> float:
    return SequenceMatcher(None, normalize_text(expected), normalize_text(actual)).ratio()


def is_match(expected: str, actual: str) -> bool:
    return expected == actual


def print_report(field_name: str, args: argparse.Namespace, rows: list[AccuracyRow]) -> None:
    avg = sum(row.similarity for row in rows) / len(rows) if rows else 0.0
    matched = sum(1 for row in rows if row.matched)
    print(f"field: {field_name}")
    print(f"settings: preprocess={args.preprocess} scale={args.scale} threshold={args.threshold} psm={args.psm} oem={args.oem} lang={args.lang or DEFAULT_LANG}")
    print(f"samples: {len(rows)}  avg_similarity: {avg:.3f}  match: {matched}/{len(rows)}")
    for row in rows:
        marker = "OK" if row.matched else "NG"
        print(f"{row.image}: {marker} similarity={row.similarity:.3f}")
        if row.error:
            print(f"  error: {row.error}")
        print(f"  expected: {row.expected}")
        print(f"  actual  : {row.actual}")


def write_csv(path: Path, rows: list[AccuracyRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["image", "expected", "actual", "similarity", "matched", "error"])
        for row in rows:
            writer.writerow([row.image, row.expected, row.actual, f"{row.similarity:.6f}", row.matched, row.error])
