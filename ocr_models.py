from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPLATE_VERSION = 4
POSTPROCESS_OPTIONS = ["そのまま", "数字のみ", "数値抽出", "英数字のみ"]
OCR_BACKEND_OPTIONS = ["default", "tesseract", "paddle"]
OCR_PREPROCESS_OPTIONS = ["default", "gray", "threshold", "invert-threshold", "outline-threshold", "white-glyph"]
OCR_SCALE_OPTIONS = ["auto", "2", "3", "4"]
OCR_LINE_SPLIT_OPTIONS = ["none", "detected"]
CORRECTION_ALL_TARGET = "すべて"


@dataclass
class CorrectionRule:
    pattern: str
    replacement: str = ""
    target: str = CORRECTION_ALL_TARGET
    enabled: bool = True

    def normalized(self) -> "CorrectionRule":
        target = (self.target or CORRECTION_ALL_TARGET).strip() or CORRECTION_ALL_TARGET
        return CorrectionRule(
            self.pattern,
            self.replacement,
            target,
            self.enabled,
        )

    def to_dict(self) -> dict:
        return asdict(self.normalized())


@dataclass
class TemplateField:
    name: str
    x1: int
    y1: int
    x2: int
    y2: int
    enabled: bool = True
    source_width: int = 0
    source_height: int = 0
    postprocess: str = "そのまま"
    replace_from: str = ""
    replace_to: str = ""
    remove_text: str = ""
    ocr_backend: str = "default"
    ocr_preprocess: str = "default"
    ocr_scale: str = "auto"
    ocr_threshold: int = 180
    ocr_psm: int = 6
    ocr_lang: str = ""
    ocr_line_split: str = "none"
    ocr_line_padding: int = 12
    ocr_line_detect_threshold: int = 90
    ocr_line_detect_min_ratio: float = 0.015
    ocr_line_detect_gap: int = 10

    def normalized(self) -> "TemplateField":
        x1, x2 = sorted((self.x1, self.x2))
        y1, y2 = sorted((self.y1, self.y2))
        return TemplateField(
            self.name,
            x1,
            y1,
            x2,
            y2,
            self.enabled,
            self.source_width,
            self.source_height,
            self.postprocess,
            self.replace_from,
            self.replace_to,
            self.remove_text,
            self.ocr_backend,
            self.ocr_preprocess,
            self.ocr_scale,
            self.ocr_threshold,
            self.ocr_psm,
            self.ocr_lang,
            self.ocr_line_split,
            self.ocr_line_padding,
            self.ocr_line_detect_threshold,
            self.ocr_line_detect_min_ratio,
            self.ocr_line_detect_gap,
        )

    def to_dict(self) -> dict:
        return asdict(self.normalized())


def field_from_dict(item: dict) -> TemplateField:
    postprocess = str(item.get("postprocess") or "そのまま")
    if postprocess not in POSTPROCESS_OPTIONS:
        postprocess = "そのまま"
    ocr_backend = str(item.get("ocr_backend") or "default")
    if ocr_backend not in OCR_BACKEND_OPTIONS:
        ocr_backend = "default"
    ocr_preprocess = str(item.get("ocr_preprocess") or "default")
    if ocr_preprocess not in OCR_PREPROCESS_OPTIONS:
        ocr_preprocess = "default"
    ocr_scale = str(item.get("ocr_scale") or "auto")
    if ocr_scale not in OCR_SCALE_OPTIONS:
        ocr_scale = "auto"
    ocr_line_split = str(item.get("ocr_line_split") or "none")
    if ocr_line_split not in OCR_LINE_SPLIT_OPTIONS:
        ocr_line_split = "none"

    if "cell" in item:
        name = str(item.get("name") or item.get("cell") or "項目")
    else:
        name = str(item["name"])

    return TemplateField(
        name,
        int(item["x1"]),
        int(item["y1"]),
        int(item["x2"]),
        int(item["y2"]),
        bool(item.get("enabled", True)),
        int(item.get("source_width") or 0),
        int(item.get("source_height") or 0),
        postprocess,
        str(item.get("replace_from") or ""),
        str(item.get("replace_to") or ""),
        str(item.get("remove_text") or ""),
        ocr_backend,
        ocr_preprocess,
        ocr_scale,
        int(item.get("ocr_threshold") or 180),
        int(item.get("ocr_psm") or 6),
        str(item.get("ocr_lang") or ""),
        ocr_line_split,
        int(item.get("ocr_line_padding") or 12),
        int(item.get("ocr_line_detect_threshold") or 90),
        float(item.get("ocr_line_detect_min_ratio") or 0.015),
        int(item.get("ocr_line_detect_gap") or 10),
    ).normalized()


def correction_rule_from_dict(item: dict) -> CorrectionRule:
    return CorrectionRule(
        str(item.get("pattern") or item.get("from") or ""),
        str(item.get("replacement") or item.get("to") or ""),
        str(item.get("target") or CORRECTION_ALL_TARGET),
        bool(item.get("enabled", True)),
    ).normalized()
