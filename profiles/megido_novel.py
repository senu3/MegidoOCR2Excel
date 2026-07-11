from __future__ import annotations

from profiles.base import FieldPreset, OcrProfile

COORDINATE_DEFAULTS = {
    "coordinate_space": "content",
    "black_threshold": 8,
    "min_nonblack_ratio": 0.01,
    "stable_run": 6,
    "aspect_ratio_tolerance": 0.08,
}

FIELD_OCR_DEFAULTS = {
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

PROFILE = OcrProfile(
    profile_id="megido_novel",
    name="Megido novel screenshot",
    app_title="Megido OCR to Excel",
    default_backend="paddle",
    default_lang="jpn+eng",
    coordinate_defaults=COORDINATE_DEFAULTS,
    default_field_ocr=FIELD_OCR_DEFAULTS,
    field_presets=(
        FieldPreset(
            family="話者",
            prefixes=("話者",),
            ocr={
                "ocr_preprocess": "default",
                "ocr_scale": "auto",
                "ocr_threshold": 180,
                "ocr_lang": "jpn",
            },
        ),
        FieldPreset(
            family="セリフ本文",
            prefixes=("セリフ本文", "セリフ"),
            ocr={
                "ocr_preprocess": "default",
                "ocr_scale": "auto",
                "ocr_threshold": 180,
                "ocr_lang": "jpn",
                "ocr_line_split": "detected",
            },
        ),
    ),
)
