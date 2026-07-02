from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from ocr_models import TemplateField

try:
    import pytesseract
except ImportError:
    pytesseract = None

if pytesseract is not None:
    TesseractNotFoundError = pytesseract.TesseractNotFoundError
    TesseractError = pytesseract.TesseractError
else:
    class TesseractNotFoundError(Exception):
        pass

    class TesseractError(Exception):
        pass


DEFAULT_LANG = "jpn+eng"
DEFAULT_BACKEND = "paddle"


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
        region.ocr_backend,
        region.ocr_preprocess,
        region.ocr_scale,
        region.ocr_threshold,
        region.ocr_psm,
        region.ocr_lang,
        region.ocr_line_split,
        region.ocr_line_padding,
        region.ocr_line_detect_threshold,
        region.ocr_line_detect_min_ratio,
        region.ocr_line_detect_gap,
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


def detect_line_bands(
    image: Image.Image,
    threshold: int = 90,
    min_ratio: float = 0.015,
    gap: int = 10,
    padding: int = 12,
) -> list[tuple[int, int]]:
    gray = ImageOps.grayscale(image)
    pixels = gray.load()
    min_count = max(3, int(image.width * min_ratio))
    rows: list[int] = []
    for y in range(gray.height):
        count = 0
        for x in range(gray.width):
            if pixels[x, y] < threshold:
                count += 1
        if count >= min_count:
            rows.append(y)

    if not rows:
        return [(0, image.height)]

    bands: list[tuple[int, int]] = []
    start = previous = rows[0]
    for y in rows[1:]:
        if y - previous <= gap:
            previous = y
            continue
        add_detected_band(bands, image.height, start, previous, padding)
        start = previous = y
    add_detected_band(bands, image.height, start, previous, padding)
    return bands or [(0, image.height)]


def add_detected_band(bands: list[tuple[int, int]], height: int, start: int, end: int, padding: int) -> None:
    if end - start <= 8:
        return
    bands.append((max(0, start - padding), min(height, end + padding)))


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


def resolve_backend(field: TemplateField, backend: str = DEFAULT_BACKEND) -> str:
    field_backend = getattr(field, "ocr_backend", "default") or "default"
    if field_backend != "default":
        return field_backend
    return backend if backend in {"tesseract", "paddle"} else DEFAULT_BACKEND


def paddle_lang(lang: str) -> str:
    value = (lang or "").lower()
    if "jpn" in value or "japan" in value:
        return "japan"
    if "eng" in value or value == "en":
        return "en"
    return "japan"


def extract_paddle_texts(result: Any) -> list[str]:
    if result is None:
        return []
    if isinstance(result, str):
        return [result] if result.strip() else []
    if isinstance(result, dict):
        texts: list[str] = []
        found_text_key = False
        for key in ("rec_text", "rec_texts", "text", "texts", "label"):
            if key in result:
                found_text_key = True
                texts.extend(extract_paddle_texts(result[key]))
        if found_text_key:
            return texts
        if not texts:
            for value in result.values():
                texts.extend(extract_paddle_texts(value))
        return texts
    if isinstance(result, (list, tuple)):
        if len(result) == 2 and isinstance(result[0], str) and isinstance(result[1], (float, int)):
            return [result[0]]
        texts: list[str] = []
        for value in result:
            texts.extend(extract_paddle_texts(value))
        return texts
    for attr in ("to_dict", "json"):
        method = getattr(result, attr, None)
        if callable(method):
            try:
                return extract_paddle_texts(method())
            except Exception:
                pass
    return []


class PaddleBackend:
    def __init__(self) -> None:
        self.instances: dict[str, Any] = {}

    def recognize(self, image: Image.Image, lang: str) -> str:
        ocr = self._instance(lang)
        result = self._run_ocr(ocr, image)
        return " ".join(extract_paddle_texts(result)).strip()

    def _instance(self, lang: str) -> Any:
        paddle_language = paddle_lang(lang)
        if paddle_language in self.instances:
            return self.instances[paddle_language]
        try:
            os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError("PaddleOCRがインストールされていません。`uv sync --extra paddle` で追加してください。") from exc

        candidates = [
            {
                "lang": paddle_language,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            },
            {"lang": paddle_language, "use_angle_cls": False, "show_log": False},
            {"lang": paddle_language, "use_angle_cls": False},
            {"lang": paddle_language},
        ]
        last_error: Exception | None = None
        for kwargs in candidates:
            try:
                instance = PaddleOCR(**kwargs)
                self.instances[paddle_language] = instance
                return instance
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"PaddleOCRの初期化に失敗しました: {last_error}")

    def _run_ocr(self, ocr: Any, image: Image.Image) -> Any:
        image = image.convert("RGB")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "ocr_crop.png"
            image.save(image_path)
            predict_method = getattr(ocr, "predict", None)
            if callable(predict_method):
                try:
                    return predict_method(
                        str(image_path),
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                    )
                except TypeError:
                    try:
                        return predict_method(input=str(image_path))
                    except TypeError:
                        return predict_method(str(image_path))
            ocr_method = getattr(ocr, "ocr", None)
            if callable(ocr_method):
                for kwargs in ({"det": False, "cls": False}, {"det": False}, {}):
                    try:
                        return ocr_method(str(image_path), **kwargs)
                    except TypeError:
                        continue
        return None


class OcrEngine:
    def __init__(self) -> None:
        self.paddle_backend: PaddleBackend | None = None

    def recognize_field_detail(
        self,
        image: Image.Image,
        field: TemplateField,
        lang: str = DEFAULT_LANG,
        tesseract_path: str = "",
        backend: str = DEFAULT_BACKEND,
    ) -> tuple[str | None, str | None, str | None]:
        backend_name = resolve_backend(field, backend)
        if backend_name == "tesseract" and pytesseract is None:
            return None, None, "OCRライブラリ pytesseract がインストールされていません。"

        if backend_name == "tesseract" and tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        region = scaled_field(field, image)
        if (region.x2 - region.x1) < 1 or (region.y2 - region.y1) < 1:
            return None, None, "読み取り範囲が画像外、または小さすぎます。"

        crop = image.crop((region.x1, region.y1, region.x2, region.y2))
        ocr_lang = field.ocr_lang.strip() or lang.strip() or DEFAULT_LANG
        psm = field.ocr_psm or 6
        config = f"--oem 3 --psm {psm}"
        try:
            if field.ocr_line_split == "detected":
                raw_text = self.recognize_detected_lines(crop, field, ocr_lang, config, backend_name)
            else:
                prepared = prepare_for_ocr(crop, field.ocr_preprocess, field.ocr_scale, field.ocr_threshold)
                raw_text = self.recognize_prepared(prepared, ocr_lang, config, backend_name)
        except TesseractNotFoundError:
            return None, None, "Tesseractが見つかりません。設定で実行ファイルのパスを指定してください。"
        except TesseractError as exc:
            return None, None, str(exc)
        except RuntimeError as exc:
            return None, None, str(exc)
        except Exception as exc:
            if backend_name == "paddle":
                return None, None, f"PaddleOCRエラー: {exc}"
            raise

        cleaned = clean_text(raw_text)
        return cleaned, apply_postprocess(cleaned, field), None

    def recognize_prepared(self, image: Image.Image, lang: str, config: str, backend: str) -> str:
        if backend == "paddle":
            if self.paddle_backend is None:
                self.paddle_backend = PaddleBackend()
            return self.paddle_backend.recognize(image, lang)
        return pytesseract.image_to_string(image, lang=lang, config=config)

    def recognize_detected_lines(self, crop: Image.Image, field: TemplateField, lang: str, config: str, backend: str) -> str:
        parts: list[str] = []
        bands = detect_line_bands(
            crop,
            field.ocr_line_detect_threshold,
            field.ocr_line_detect_min_ratio,
            field.ocr_line_detect_gap,
            field.ocr_line_padding,
        )
        for y1, y2 in bands:
            line_crop = crop.crop((0, y1, crop.width, y2))
            prepared = prepare_for_ocr(line_crop, field.ocr_preprocess, field.ocr_scale, field.ocr_threshold)
            text = self.recognize_prepared(prepared, lang, config, backend)
            cleaned = clean_text(text)
            if cleaned:
                parts.append(cleaned)
        return " ".join(parts)

    def recognize_field(
        self,
        image: Image.Image,
        field: TemplateField,
        lang: str = DEFAULT_LANG,
        tesseract_path: str = "",
        backend: str = DEFAULT_BACKEND,
    ) -> tuple[str | None, str | None]:
        _raw_text, value, error = self.recognize_field_detail(image, field, lang, tesseract_path, backend)
        return value, error
