from __future__ import annotations

from ocr_accuracy_common import run_accuracy
from profiles.megido_novel import field_ocr_preset


if __name__ == "__main__":
    preset = field_ocr_preset("セリフ本文")
    raise SystemExit(
        run_accuracy(
            "セリフ本文",
            default_psm=preset["ocr_psm"],
            default_preprocess=preset["ocr_preprocess"],
            default_scale=preset["ocr_scale"],
            default_threshold=preset["ocr_threshold"],
            default_lang=preset["ocr_lang"],
            default_line_split=preset["ocr_line_split"],
            default_line_padding=preset["ocr_line_padding"],
            default_line_detect_threshold=preset["ocr_line_detect_threshold"],
            default_line_detect_min_ratio=preset["ocr_line_detect_min_ratio"],
            default_line_detect_gap=preset["ocr_line_detect_gap"],
            default_match_space_normalized=True,
        )
    )
