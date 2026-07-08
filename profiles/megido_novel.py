from __future__ import annotations


PROFILE_ID = "megido_novel"
PROFILE_NAME = "Megido novel screenshot"

DEFAULT_BACKEND = "paddle"
DEFAULT_LANG = "jpn+eng"

DEFAULT_FIELD_OCR = {
    "ocr_backend": "default",
    "ocr_preprocess": "default",
    "ocr_scale": "auto",
    "ocr_threshold": 180,
    "ocr_psm": 6,
    "ocr_lang": "",
    "ocr_line_split": "none",
    "ocr_line_padding": 12,
    "ocr_line_detect_threshold": 90,
    "ocr_line_detect_min_ratio": 0.015,
    "ocr_line_detect_gap": 10,
}

FIELD_OCR_PRESETS = {
    "話者": {
        **DEFAULT_FIELD_OCR,
        "ocr_preprocess": "default",
        "ocr_scale": "auto",
        "ocr_threshold": 180,
        "ocr_lang": "jpn",
    },
    "セリフ本文": {
        **DEFAULT_FIELD_OCR,
        "ocr_preprocess": "default",
        "ocr_scale": "auto",
        "ocr_threshold": 180,
        "ocr_lang": "jpn",
        "ocr_line_split": "detected",
    },
}


def field_family(field_name: str) -> str:
    if field_name.startswith("話者"):
        return "話者"
    if field_name.startswith("セリフ本文") or field_name.startswith("セリフ"):
        return "セリフ本文"
    return field_name


def field_ocr_preset(field_name: str) -> dict:
    return FIELD_OCR_PRESETS.get(field_family(field_name), DEFAULT_FIELD_OCR).copy()


def has_field_ocr_preset(field_name: str) -> bool:
    return field_family(field_name) in FIELD_OCR_PRESETS
