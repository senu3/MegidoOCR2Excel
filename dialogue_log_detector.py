from __future__ import annotations

from dataclasses import dataclass, replace

from PIL import Image

from ocr_engine import detect_content_rect, scaled_field
from ocr_models import (
    CoordinateSettings,
    DialogueLogDetectionConfig,
    TemplateField,
    dialogue_pair_groups,
)


@dataclass(frozen=True)
class DialoguePairDetectionResult:
    groups: list[tuple[int, TemplateField, TemplateField]]
    skipped_leading: int = 0
    skipped_trailing: int = 0

    @property
    def notices(self) -> list[str]:
        messages: list[str] = []
        if self.skipped_leading:
            messages.append("画面上端の話者がないセリフ断片を除外しました。")
        if self.skipped_trailing:
            messages.append(
                f"画面下端で途切れている会話 {self.skipped_trailing} 件を除外しました。"
            )
        return messages


def detect_complete_dialogue_pairs(
    image: Image.Image,
    fields: list[TemplateField],
    coordinate_settings: CoordinateSettings,
    config: DialogueLogDetectionConfig,
) -> DialoguePairDetectionResult:
    prototypes = dialogue_pair_groups(fields)
    if not prototypes:
        return DialoguePairDetectionResult([])

    content_rect = _target_content_rect(image, fields, coordinate_settings)
    left, top, right, bottom = content_rect
    content_width = right - left
    content_height = bottom - top
    scan_x1 = round(left + content_width * config.anchor_x1_ratio)
    scan_x2 = round(left + content_width * config.anchor_x2_ratio)
    log_top = round(top + content_height * config.log_top_ratio)
    log_bottom = round(top + content_height * config.log_bottom_ratio)
    min_height = max(8, round(content_height * config.min_bar_height_ratio))
    max_height = max(min_height, round(content_height * config.max_bar_height_ratio))

    anchors = _speaker_bar_bands(
        image,
        scan_x1,
        scan_x2,
        log_top,
        log_bottom,
        config.row_match_ratio,
        config.max_band_gap,
        min_height,
        max_height,
    )
    pair_height = max(1, round(content_height * config.pair_height_ratio))
    complete = [band for band in anchors if band[0] + pair_height <= log_bottom]
    skipped_trailing = len(anchors) - len(complete)
    skipped_leading = int(
        bool(anchors) and anchors[0][0] - log_top > pair_height * 0.6
    )

    _pair_id, speaker_prototype, dialogue_prototype = prototypes[0]
    speaker_base = scaled_field(
        speaker_prototype, image, coordinate_settings, content_rect
    )
    dialogue_base = scaled_field(
        dialogue_prototype, image, coordinate_settings, content_rect
    )
    groups: list[tuple[int, TemplateField, TemplateField]] = []
    for pair_id, (anchor_top, anchor_bottom) in enumerate(complete, start=1):
        pair_bottom = min(image.height, anchor_top + pair_height)
        speaker = replace(
            speaker_base,
            y1=max(0, anchor_top),
            y2=min(image.height, anchor_bottom + 1),
            source_width=0,
            source_height=0,
            pair_id=pair_id,
        )
        dialogue = replace(
            dialogue_base,
            y1=min(pair_bottom, anchor_bottom + 1),
            y2=pair_bottom,
            source_width=0,
            source_height=0,
            pair_id=pair_id,
        )
        groups.append((pair_id, speaker, dialogue))
    return DialoguePairDetectionResult(groups, skipped_leading, skipped_trailing)


def _target_content_rect(
    image: Image.Image,
    fields: list[TemplateField],
    settings: CoordinateSettings,
) -> tuple[int, int, int, int]:
    detected = detect_content_rect(image, settings)
    if detected is not None:
        return detected
    source = settings.normalized().source_content_rect
    source_width = next((field.source_width for field in fields if field.source_width), 0)
    source_height = next((field.source_height for field in fields if field.source_height), 0)
    if source and source_width and source_height:
        scale_x = image.width / source_width
        scale_y = image.height / source_height
        return (
            round(source[0] * scale_x),
            round(source[1] * scale_y),
            round(source[2] * scale_x),
            round(source[3] * scale_y),
        )
    return (0, 0, image.width, image.height)


def _speaker_bar_bands(
    image: Image.Image,
    x1: int,
    x2: int,
    y1: int,
    y2: int,
    row_match_ratio: float,
    max_gap: int,
    min_height: int,
    max_height: int,
) -> list[tuple[int, int]]:
    rgb = image.convert("RGB")
    sample_step = max(1, (x2 - x1) // 90)
    matching_rows: list[int] = []
    for y in range(max(0, y1), min(rgb.height, y2)):
        pixels = [rgb.getpixel((x, y)) for x in range(max(0, x1), min(rgb.width, x2), sample_step)]
        if not pixels:
            continue
        matching = sum(
            blue > red * 1.25 and blue > green * 1.05 and blue < 170
            for red, green, blue in pixels
        )
        if matching / len(pixels) >= row_match_ratio:
            matching_rows.append(y)

    bands: list[list[int]] = []
    for y in matching_rows:
        if not bands or y - bands[-1][1] > max_gap + 1:
            bands.append([y, y])
        else:
            bands[-1][1] = y
    return [
        (start, end)
        for start, end in bands
        if min_height <= end - start + 1 <= max_height
    ]
