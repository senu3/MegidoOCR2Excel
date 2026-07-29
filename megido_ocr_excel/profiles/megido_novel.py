from __future__ import annotations

from typing import cast

from PIL import Image

from megido_ocr_excel.profiles.base import (
    AutoDetectionField,
    AutoDetectionStrategy,
    CoordinateSettingsValues,
    FieldPreset,
    ImageTextCorrector,
    OcrProfile,
)
from megido_ocr_excel.set_definitions import (
    CONVERSATION_SET_DEFINITION,
    HEADING_TEXT_SET_DEFINITION,
    SET_PRESET_CONVERSATION,
    SET_SLOT_SPEAKER,
    SET_SLOT_TEXT,
)
from megido_ocr_excel.ocr.glyph_correction import (
    HorizontalGlyphCorrector,
    RepeatedDotCorrector,
)
from megido_ocr_excel.ocr.dialogue_detector import (
    DialogueLogDetectionConfig,
    dialogue_detection_to_set_result,
    detect_dialogue_sets,
    include_supplement_candidates,
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

DIALOGUE_DETECTION = DialogueLogDetectionConfig(
    anchor_x1_ratio=0.10,
    anchor_x2_ratio=0.29,
    log_top_ratio=0.05,
    log_bottom_ratio=0.911,
    pair_height_ratio=0.123,
    normal_speaker_x1_ratio=0.035,
    normal_dialogue_x1_ratio=0.03,
    normal_dialogue_x2_ratio=0.97,
)


def _detect_dialogue_result(
    image: Image.Image,
    fields,
    coordinate_settings,
):
    return detect_dialogue_sets(
        image,
        fields,
        coordinate_settings,
        DIALOGUE_DETECTION,
    )


def _detect_dialogue_sets(image: Image.Image, fields, coordinate_settings):
    return dialogue_detection_to_set_result(
        _detect_dialogue_result(image, fields, coordinate_settings)
    )


def _resolve_dialogue_sets(image: Image.Image, fields, coordinate_settings):
    detection = include_supplement_candidates(
        _detect_dialogue_result(
            image,
            fields,
            coordinate_settings,
        )
    )
    return dialogue_detection_to_set_result(detection)


PROFILE = OcrProfile(
    profile_id="megido_novel",
    name="Megido novel screenshot",
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
    set_definitions=(
        CONVERSATION_SET_DEFINITION,
        HEADING_TEXT_SET_DEFINITION,
    ),
    default_set_preset=SET_PRESET_CONVERSATION,
    auto_detection_field_specs=(
        AutoDetectionField("話者", SET_SLOT_SPEAKER),
        AutoDetectionField("セリフ本文", SET_SLOT_TEXT, "detected"),
    ),
    auto_detection=AutoDetectionStrategy(
        detect=_detect_dialogue_sets,
        resolve_sets=_resolve_dialogue_sets,
    ),
    image_text_fallback=cast(
        ImageTextCorrector,
        RepeatedDotCorrector(field_prefixes=("セリフ", "補足セリフ")),
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
