from __future__ import annotations

import re
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from ocr_models import TemplateField

try:
    import pytesseract
except ImportError:
    pytesseract = None


DEFAULT_LANG = "jpn+eng"


def detect_tesseract() -> str:
    found = shutil.which("tesseract")
    if found:
        return found
    default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    return str(default) if default.exists() else ""


def fill_missing_field_source_size(fields: list[TemplateField], image_size: tuple[int, int]) -> None:
    width, height = image_size
    for field in fields:
        if not field.source_width or not field.source_height:
            field.source_width = width
            field.source_height = height


def scaled_field(field: TemplateField, image: Image.Image | None) -> TemplateField:
    region = field.normalized()
    if image is None or not region.source_width or not region.source_height:
        return region
    target_width, target_height = image.size
    scale_x = target_width / region.source_width
    scale_y = target_height / region.source_height
    x1 = round(region.x1 * scale_x)
    y1 = round(region.y1 * scale_y)
    x2 = round(region.x2 * scale_x)
    y2 = round(region.y2 * scale_y)
    x1, x2 = sorted((max(0, min(target_width, x1)), max(0, min(target_width, x2))))
    y1, y2 = sorted((max(0, min(target_height, y1)), max(0, min(target_height, y2))))
    return TemplateField(
        region.name,
        x1,
        y1,
        x2,
        y2,
        region.enabled,
        target_width,
        target_height,
        region.postprocess,
        region.replace_from,
        region.replace_to,
        region.remove_text,
        region.ocr_preprocess,
        region.ocr_scale,
        region.ocr_threshold,
        region.ocr_psm,
        region.ocr_lang,
    )


def prepare_for_ocr(
    image: Image.Image,
    preprocess: str = "default",
    scale: str = "auto",
    threshold: int = 180,
) -> Image.Image:
    if preprocess == "outline-threshold":
        image = crop_dark_content(image, threshold=120, margin=20)
        image = ImageOps.expand(image, border=30, fill="white")
    elif preprocess == "white-glyph":
        return prepare_white_glyph(image, scale, threshold)

    scale_value = 3 if scale == "auto" and max(image.size) < 500 else 2 if scale == "auto" else int(scale)
    image = image.resize((image.width * scale_value, image.height * scale_value), Image.Resampling.LANCZOS)
    image = ImageOps.grayscale(image)
    if preprocess == "gray":
        return image

    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = image.filter(ImageFilter.SHARPEN)
    if preprocess == "default":
        return image

    thresholded = image.point(lambda value: 255 if value >= threshold else 0)
    if preprocess == "invert-threshold":
        return ImageOps.invert(thresholded)
    return thresholded


def prepare_white_glyph(image: Image.Image, scale: str = "auto", threshold: int = 190) -> Image.Image:
    gray = ImageOps.grayscale(image)
    min_near = gray.filter(ImageFilter.MinFilter(5))
    bright_mask = gray.point(lambda value: 255 if value >= threshold else 0)
    dark_near = min_near.point(lambda value: 255 if value <= 100 else 0)
    glyph = ImageChops.multiply(bright_mask, dark_near)
    image = ImageOps.invert(glyph)
    image = crop_black_content(image, margin=12)
    image = ImageOps.expand(image, border=24, fill="white")
    scale_value = 3 if scale == "auto" and max(image.size) < 500 else 2 if scale == "auto" else int(scale)
    return image.resize((image.width * scale_value, image.height * scale_value), Image.Resampling.LANCZOS)


def crop_dark_content(image: Image.Image, threshold: int, margin: int) -> Image.Image:
    gray = ImageOps.grayscale(image)
    pixels = gray.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(gray.height):
        for x in range(gray.width):
            if pixels[x, y] < threshold:
                xs.append(x)
                ys.append(y)

    if not xs:
        return image

    box = (
        max(0, min(xs) - margin),
        max(0, min(ys) - margin),
        min(image.width, max(xs) + margin),
        min(image.height, max(ys) + margin),
    )
    return image.crop(box)


def crop_black_content(image: Image.Image, margin: int) -> Image.Image:
    bbox = image.point(lambda value: 255 if value < 128 else 0).getbbox()
    if bbox is None:
        return image
    left, top, right, bottom = bbox
    box = (
        max(0, left - margin),
        max(0, top - margin),
        min(image.width, right + margin),
        min(image.height, bottom + margin),
    )
    return image.crop(box)


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return " ".join(line for line in lines if line).strip()


def apply_postprocess(text: str, field: TemplateField) -> str:
    value = text
    if field.replace_from:
        value = value.replace(field.replace_from, field.replace_to)
    for token in [part.strip() for part in field.remove_text.split(",") if part.strip()]:
        value = value.replace(token, "")
    value = " ".join(value.split()).strip()

    if field.postprocess == "数字のみ":
        return re.sub(r"\D+", "", value)
    if field.postprocess == "数値抽出":
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
        return match.group(0).replace(",", ".") if match else ""
    if field.postprocess == "英数字のみ":
        return re.sub(r"[^0-9A-Za-z]+", "", value)
    return value


class OcrEngine:
    def recognize_field_detail(
        self,
        image: Image.Image,
        field: TemplateField,
        lang: str = DEFAULT_LANG,
        tesseract_path: str = "",
    ) -> tuple[str | None, str | None, str | None]:
        if pytesseract is None:
            return None, None, "OCRライブラリ pytesseract がインストールされていません。"

        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        region = scaled_field(field, image)
        if (region.x2 - region.x1) < 1 or (region.y2 - region.y1) < 1:
            return None, None, "読み取り範囲が画像外、または小さすぎます。"

        crop = image.crop((region.x1, region.y1, region.x2, region.y2))
        prepared = prepare_for_ocr(crop, field.ocr_preprocess, field.ocr_scale, field.ocr_threshold)
        ocr_lang = field.ocr_lang.strip() or lang.strip() or DEFAULT_LANG
        psm = field.ocr_psm or 6
        try:
            raw_text = pytesseract.image_to_string(prepared, lang=ocr_lang, config=f"--oem 3 --psm {psm}")
        except pytesseract.TesseractNotFoundError:
            return None, None, "Tesseractが見つかりません。設定で実行ファイルのパスを指定してください。"
        except pytesseract.TesseractError as exc:
            return None, None, str(exc)

        cleaned = clean_text(raw_text)
        return cleaned, apply_postprocess(cleaned, field), None

    def recognize_field(
        self,
        image: Image.Image,
        field: TemplateField,
        lang: str = DEFAULT_LANG,
        tesseract_path: str = "",
    ) -> tuple[str | None, str | None]:
        _raw_text, value, error = self.recognize_field_detail(image, field, lang, tesseract_path)
        return value, error
