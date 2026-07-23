from __future__ import annotations

from typing import cast

from megido_ocr_excel.profiles.base import (
    CoordinateSettingsValues,
    FieldPreset,
    ImageTextCorrector,
    OcrProfile,
)
from megido_ocr_excel.models import DialogueLogDetectionConfig
from megido_ocr_excel.ocr.glyph_correction import (
    HorizontalGlyphCorrector,
    RepeatedDotCorrector,
)

COORDINATE_DEFAULTS: CoordinateSettingsValues = {
    "coordinate_space": "content",
    "source_content_rect": (0, 219, 1080, 2087),
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
    text_format_defaults={
        "line_join": "fullwidth_space",
        "fullwidth_ascii": True,
    },
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
                "ocr_preprocess": "gray",
                "ocr_scale": "auto",
                "ocr_threshold": 180,
                "ocr_lang": "jpn",
                "ocr_line_split": "detected",
            },
        ),
    ),
    dialogue_log_detection=DialogueLogDetectionConfig(
        anchor_x1_ratio=0.10,
        anchor_x2_ratio=0.29,
        log_top_ratio=0.05,
        log_bottom_ratio=0.911,
        pair_height_ratio=0.123,
        normal_speaker_x1_ratio=0.035,
        normal_dialogue_x1_ratio=0.03,
        normal_dialogue_x2_ratio=0.97,
    ),
    image_text_fallback=cast(
        ImageTextCorrector,
        RepeatedDotCorrector(field_prefixes=("セリフ",)),
    ),
    image_text_corrector=cast(
        ImageTextCorrector,
        HorizontalGlyphCorrector(
            field_prefixes=("セリフ", "補足セリフ"),
            short_glyph="ー",
            long_glyph="一",
            short_max_width_ratio=0.0475,
            long_min_width_ratio=0.0500,
        ),
    ),
)
