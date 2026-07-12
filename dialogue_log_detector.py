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
    layout: str = "unknown"
    allow_empty_speaker: bool = False
    allow_empty_dialogue: bool = False
    review_reason: str = ""
    candidate_fields: list[TemplateField] | None = None

    def __post_init__(self) -> None:
        if self.candidate_fields is None:
            object.__setattr__(self, "candidate_fields", [])

    @property
    def notices(self) -> list[str]:
        messages: list[str] = []
        if self.skipped_leading:
            messages.append("画面上端の話者がないセリフ断片を除外しました。")
        if self.skipped_trailing:
            messages.append(
                f"画面下端で途切れている会話 {self.skipped_trailing} 件を除外しました。"
            )
        if self.review_reason:
            messages.append(self.review_reason)
        return messages


def detect_complete_dialogue_pairs(
    image: Image.Image,
    fields: list[TemplateField],
    coordinate_settings: CoordinateSettings,
    config: DialogueLogDetectionConfig,
) -> DialoguePairDetectionResult:
    prototypes = dialogue_pair_groups(fields)
    if prototypes:
        _pair_id, speaker_prototype, dialogue_prototype = prototypes[0]
    else:
        dialogue_prototype = next(
            (
                field
                for field in fields
                if field.ocr_line_split == "detected"
                or field.name.startswith(("セリフ", "本文"))
            ),
            None,
        )
        speaker_prototype = next(
            (field for field in fields if field is not dialogue_prototype), None
        )
    if speaker_prototype is None or dialogue_prototype is None:
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
    log_anchors = _regular_anchor_sequence(anchors, pair_height)
    if len(log_anchors) < 3:
        return _detect_single_screen(
            image,
            speaker_prototype=speaker_prototype,
            dialogue_prototype=dialogue_prototype,
            content_rect=(0, 0, image.width, image.height),
            coordinate_settings=coordinate_settings,
            config=config,
        )

    complete = [band for band in log_anchors if band[0] + pair_height <= log_bottom]
    skipped_trailing = len(log_anchors) - len(complete)
    skipped_leading = int(
        bool(log_anchors) and log_anchors[0][0] - log_top > pair_height * 0.6
    )

    speaker_base = scaled_field(
        speaker_prototype, image, coordinate_settings, content_rect
    )
    dialogue_base = scaled_field(
        dialogue_prototype, image, coordinate_settings, content_rect
    )
    groups: list[tuple[int, TemplateField, TemplateField]] = []
    speaker_padding = max(
        2, round(content_height * config.speaker_vertical_padding_ratio)
    )
    for pair_id, (anchor_top, anchor_bottom) in enumerate(complete, start=1):
        pair_bottom = min(image.height, anchor_top + pair_height)
        speaker = replace(
            speaker_base,
            x1=round(left + content_width * config.log_speaker_x1_ratio),
            x2=round(left + content_width * config.log_speaker_x2_ratio),
            y1=max(0, anchor_top - speaker_padding),
            y2=min(image.height, anchor_bottom + 1 + speaker_padding),
            source_width=0,
            source_height=0,
            pair_id=pair_id,
        )
        dialogue = replace(
            dialogue_base,
            x1=round(left + content_width * config.log_dialogue_x1_ratio),
            x2=round(left + content_width * config.log_dialogue_x2_ratio),
            y1=min(pair_bottom, anchor_bottom + 1),
            y2=pair_bottom,
            source_width=0,
            source_height=0,
            pair_id=pair_id,
        )
        groups.append((pair_id, speaker, dialogue))
    return DialoguePairDetectionResult(
        groups,
        skipped_leading,
        skipped_trailing,
        layout="log",
    )


def _regular_anchor_sequence(
    anchors: list[tuple[int, int]], pair_height: int
) -> list[tuple[int, int]]:
    best: list[tuple[int, int]] = []
    for start_index, anchor in enumerate(anchors):
        sequence = [anchor]
        for candidate in anchors[start_index + 1 :]:
            gap = candidate[0] - sequence[-1][0]
            if pair_height * 0.85 <= gap <= pair_height * 1.5:
                sequence.append(candidate)
        if len(sequence) > len(best):
            best = sequence
    return best


def _detect_single_screen(
    image: Image.Image,
    speaker_prototype: TemplateField,
    dialogue_prototype: TemplateField,
    content_rect: tuple[int, int, int, int],
    coordinate_settings: CoordinateSettings,
    config: DialogueLogDetectionConfig,
) -> DialoguePairDetectionResult:
    left, top, right, bottom = content_rect
    width = right - left
    height = bottom - top
    all_bands = _speaker_bar_bands(
        image,
        round(left + width * config.anchor_x1_ratio),
        round(left + width * config.anchor_x2_ratio),
        round(top + height * config.normal_anchor_top_ratio),
        round(top + height * config.normal_anchor_bottom_ratio),
        config.row_match_ratio,
        config.max_band_gap,
        max(8, round(height * 0.01)),
        max(12, round(height * 0.05)),
    )
    if all_bands:
        anchor_top, anchor_bottom = all_bands[-1]
        supplement_region = _supplement_candidate_region(image, content_rect, anchor_top)
        supplement_candidate = supplement_region is not None
        panel_bottom = _light_panel_bottom(image, content_rect, anchor_bottom + 1)
        speaker_base = scaled_field(
            speaker_prototype, image, coordinate_settings, content_rect
        )
        dialogue_base = scaled_field(
            dialogue_prototype, image, coordinate_settings, content_rect
        )
        speaker = replace(
            speaker_base,
            x1=round(left + width * config.normal_speaker_x1_ratio),
            x2=round(left + width * config.normal_speaker_x2_ratio),
            y1=max(
                0,
                anchor_top
                - max(2, round(height * config.speaker_vertical_padding_ratio)),
            ),
            y2=min(
                image.height,
                anchor_bottom
                + 1
                + max(2, round(height * config.speaker_vertical_padding_ratio)),
            ),
            source_width=0,
            source_height=0,
            pair_id=1,
        )
        dialogue = replace(
            dialogue_base,
            x1=round(left + width * config.normal_dialogue_x1_ratio),
            x2=round(left + width * config.normal_dialogue_x2_ratio),
            y1=anchor_bottom + 1,
            y2=panel_bottom,
            source_width=0,
            source_height=0,
            pair_id=1,
        )
        speakerless = not _bar_has_text(
            image,
            replace(speaker, y1=anchor_top, y2=anchor_bottom + 1),
        )
        blank_dialogue = not _region_has_bright_or_dark_text(image, dialogue)
        if speakerless and blank_dialogue:
            dialogue = replace(dialogue, known_empty=True)
        candidate_fields = []
        if supplement_region is not None:
            candidate_fields.append(
                replace(
                    dialogue_prototype,
                    name="補助テキスト候補",
                    x1=supplement_region[0],
                    y1=supplement_region[1],
                    x2=supplement_region[2],
                    y2=supplement_region[3],
                    source_width=0,
                    source_height=0,
                    pair_id=0,
                    dialogue_role="",
                    ocr_line_split="detected",
                )
            )
        return DialoguePairDetectionResult(
            [(1, speaker, dialogue)],
            candidate_fields=candidate_fields,
            layout="needs_review" if supplement_candidate else ("speakerless" if speakerless else "normal"),
            allow_empty_speaker=speakerless,
            allow_empty_dialogue=speakerless and blank_dialogue,
            review_reason=(
                "補助テキスト候補を検出しました。候補項目を選択して読み取り結果を確認してください。"
                if supplement_candidate
                else ""
            ),
        )

    narrator = _narrator_region(image, content_rect)
    if narrator is not None:
        speaker = replace(
            speaker_prototype,
            x1=narrator[0],
            y1=narrator[1],
            x2=narrator[0] + 1,
            y2=narrator[1] + 1,
            source_width=0,
            source_height=0,
            pair_id=1,
        )
        dialogue = replace(
            dialogue_prototype,
            x1=narrator[0],
            y1=narrator[1],
            x2=narrator[2],
            y2=narrator[3],
            source_width=0,
            source_height=0,
            pair_id=1,
            ocr_line_split="detected",
        )
        return DialoguePairDetectionResult(
            [(1, speaker, dialogue)],
            layout="narration",
            allow_empty_speaker=True,
        )
    return DialoguePairDetectionResult([])


def _target_content_rect(
    image: Image.Image,
    fields: list[TemplateField],
    settings: CoordinateSettings,
) -> tuple[int, int, int, int]:
    normalized = settings.normalized()
    if normalized.coordinate_space != "content":
        return (0, 0, image.width, image.height)
    detected = detect_content_rect(image, normalized)
    if detected is not None:
        return detected
    source = normalized.source_content_rect
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
    if source and source[2] <= image.width and source[3] <= image.height:
        return source
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


def _light_panel_bottom(
    image: Image.Image,
    content_rect: tuple[int, int, int, int],
    start_y: int,
) -> int:
    left, _top, right, bottom = content_rect
    rgb = image.convert("RGB")
    x1 = round(left + (right - left) * 0.04)
    x2 = round(left + (right - left) * 0.96)
    step = max(1, (x2 - x1) // 120)
    last_light = start_y
    dark_run = 0
    for y in range(start_y, min(image.height, bottom)):
        pixels = [rgb.getpixel((x, y)) for x in range(x1, x2, step)]
        light_ratio = sum(sum(pixel) / 3 > 125 for pixel in pixels) / max(
            1, len(pixels)
        )
        if light_ratio >= 0.35:
            last_light = y
            dark_run = 0
        else:
            dark_run += 1
            if dark_run >= max(8, round(image.height * 0.008)):
                break
    return max(start_y + 1, last_light + 1)


def _bar_has_text(image: Image.Image, field: TemplateField) -> bool:
    text_right = field.x1 + max(1, round((field.x2 - field.x1) * 0.45))
    crop = image.crop((field.x1, field.y1, text_right, field.y2)).convert("RGB")
    pixels = list(crop.get_flattened_data())
    bright = sum(min(pixel) > 175 for pixel in pixels)
    return bright / max(1, len(pixels)) > 0.008


def _region_has_bright_or_dark_text(
    image: Image.Image, field: TemplateField
) -> bool:
    crop = image.crop((field.x1, field.y1, field.x2, field.y2)).convert("L")
    pixels = list(crop.get_flattened_data())
    dark = sum(value < 70 for value in pixels)
    return dark / max(1, len(pixels)) > 0.004


def _supplement_candidate_region(
    image: Image.Image,
    content_rect: tuple[int, int, int, int],
    anchor_top: int,
) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = content_rect
    width = right - left
    height = bottom - top
    x1 = round(left + width * 0.15)
    x2 = round(left + width * 0.85)
    y1 = max(top, round(anchor_top - height * 0.18))
    y2 = max(y1, round(anchor_top - height * 0.03))
    rgb = image.convert("RGB")
    step = max(1, (x2 - x1) // 140)
    candidate_rows: list[int] = []
    for y in range(y1, y2):
        pixels = [rgb.getpixel((x, y)) for x in range(x1, x2, step)]
        blue_ratio = sum(
            blue > red * 1.18 and blue > green * 1.03 and 40 < blue < 190
            for red, green, blue in pixels
        ) / max(1, len(pixels))
        white_ratio = sum(min(pixel) > 180 for pixel in pixels) / max(
            1, len(pixels)
        )
        if blue_ratio > 0.48 and white_ratio > 0.06:
            candidate_rows.append(y)
    clusters: list[list[int]] = []
    for y in candidate_rows:
        if not clusters or y - clusters[-1][-1] > 10:
            clusters.append([y])
        else:
            clusters[-1].append(y)
    valid = [
        cluster
        for cluster in clusters
        if cluster[-1] - cluster[0] + 1 >= max(18, round(height * 0.03))
        and len(cluster) / (cluster[-1] - cluster[0] + 1) >= 0.45
    ]
    if not valid:
        return None
    cluster = max(valid, key=lambda item: item[-1] - item[0])
    padding = max(8, round(height * 0.012))
    return (x1, max(top, cluster[0] - padding), x2, min(anchor_top, cluster[-1] + 1 + padding))


def _narrator_region(
    image: Image.Image,
    content_rect: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = content_rect
    width = right - left
    height = bottom - top
    rgb = image.convert("RGB")
    sample_step = max(1, min(width, height) // 180)
    samples = [
        rgb.getpixel((x, y))
        for y in range(top, bottom, sample_step)
        for x in range(left, right, sample_step)
    ]
    black_ratio = sum(max(pixel) < 28 for pixel in samples) / max(1, len(samples))
    if black_ratio < 0.82:
        return None

    search_x1 = round(left + width * 0.15)
    search_x2 = round(left + width * 0.85)
    search_y1 = round(top + height * 0.22)
    search_y2 = round(top + height * 0.78)
    points: list[tuple[int, int]] = []
    point_step = max(1, width // 540)
    for y in range(search_y1, search_y2, point_step):
        for x in range(search_x1, search_x2, point_step):
            red, green, blue = rgb.getpixel((x, y))
            if min(red, green, blue) > 165 and max(red, green, blue) - min(
                red, green, blue
            ) < 55:
                points.append((x, y))
    if len(points) < 30:
        return None
    padding_x = max(12, round(width * 0.025))
    padding_y = max(12, round(height * 0.015))
    return (
        max(left, min(x for x, _y in points) - padding_x),
        max(top, min(y for _x, y in points) - padding_y),
        min(right, max(x for x, _y in points) + padding_x),
        min(bottom, max(y for _x, y in points) + padding_y),
    )
