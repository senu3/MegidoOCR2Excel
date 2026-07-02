from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPLATE_VERSION = 3
POSTPROCESS_OPTIONS = ["そのまま", "数字のみ", "数値抽出", "英数字のみ"]
OCR_PREPROCESS_OPTIONS = ["default", "gray", "threshold", "invert-threshold", "outline-threshold", "white-glyph"]
OCR_SCALE_OPTIONS = ["auto", "2", "3", "4"]


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
    ocr_preprocess: str = "default"
    ocr_scale: str = "auto"
    ocr_threshold: int = 180
    ocr_psm: int = 6
    ocr_lang: str = ""

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
            self.ocr_preprocess,
            self.ocr_scale,
            self.ocr_threshold,
            self.ocr_psm,
            self.ocr_lang,
        )

    def to_dict(self) -> dict:
        return asdict(self.normalized())


def field_from_dict(item: dict) -> TemplateField:
    postprocess = str(item.get("postprocess") or "そのまま")
    if postprocess not in POSTPROCESS_OPTIONS:
        postprocess = "そのまま"
    ocr_preprocess = str(item.get("ocr_preprocess") or "default")
    if ocr_preprocess not in OCR_PREPROCESS_OPTIONS:
        ocr_preprocess = "default"
    ocr_scale = str(item.get("ocr_scale") or "auto")
    if ocr_scale not in OCR_SCALE_OPTIONS:
        ocr_scale = "auto"

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
        ocr_preprocess,
        ocr_scale,
        int(item.get("ocr_threshold") or 180),
        int(item.get("ocr_psm") or 6),
        str(item.get("ocr_lang") or ""),
    ).normalized()
