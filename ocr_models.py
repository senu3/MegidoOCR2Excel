from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPLATE_VERSION = 1
POSTPROCESS_OPTIONS = ["そのまま", "数字のみ", "数値抽出", "英数字のみ"]
OCR_BACKEND_OPTIONS = ["default", "tesseract", "paddle"]
OCR_PREPROCESS_OPTIONS = ["default", "gray", "threshold", "invert-threshold", "outline-threshold", "white-glyph"]
OCR_SCALE_OPTIONS = ["auto", "2", "3", "4"]
OCR_LINE_SPLIT_OPTIONS = ["none", "detected"]
LINE_JOIN_NONE = "none"
LINE_JOIN_FULLWIDTH_SPACE = "fullwidth_space"
LINE_JOIN_NEWLINE = "newline"
LINE_JOIN_OPTIONS = [LINE_JOIN_NONE, LINE_JOIN_FULLWIDTH_SPACE, LINE_JOIN_NEWLINE]
CORRECTION_ALL_TARGET = "すべて"
EXPORT_LAYOUT_IMAGE_ROW = "画像ごとに1行"
EXPORT_LAYOUT_SET = "セットごとに1行"
EXPORT_LAYOUT_OPTIONS = [EXPORT_LAYOUT_IMAGE_ROW, EXPORT_LAYOUT_SET]
COORDINATE_SPACE_IMAGE = "image"
COORDINATE_SPACE_CONTENT = "content"
COORDINATE_SPACE_OPTIONS = [COORDINATE_SPACE_IMAGE, COORDINATE_SPACE_CONTENT]
SET_PRESET_CONVERSATION = "conversation"
SET_PRESET_SINGLE_LINE = "single_line"
SET_PRESET_HEADING_TEXT = "heading_text"
SET_PRESET_OPTIONS = [
    SET_PRESET_CONVERSATION,
    SET_PRESET_SINGLE_LINE,
    SET_PRESET_HEADING_TEXT,
]
SET_PRESET_DISPLAY = {
    SET_PRESET_CONVERSATION: "会話（話者＋セリフ）",
    SET_PRESET_SINGLE_LINE: "1行セリフ",
    SET_PRESET_HEADING_TEXT: "見出し＋本文",
}
SET_SLOT_SPEAKER = "speaker"
SET_SLOT_TEXT = "text"
SET_SLOT_HEADING = "heading"
SET_SLOT_SUPPLEMENT = "supplement"

# Internal migration aliases. Templates are still serialized exclusively with
# set_id / slot_key; these names only keep the specialized conversation detector
# and its callers readable while the generic set model is introduced.
DIALOGUE_ROLE_SPEAKER = SET_SLOT_SPEAKER
DIALOGUE_ROLE_TEXT = SET_SLOT_TEXT
DIALOGUE_ROLE_SUPPLEMENT = SET_SLOT_SUPPLEMENT
EXPORT_LAYOUT_DIALOGUE_PAIR = EXPORT_LAYOUT_SET


@dataclass(frozen=True)
class SetColumn:
    key: str
    label: str
    ocr_line_split: str = "none"

    def normalized(self) -> "SetColumn":
        key = self.key.strip()
        label = self.label.strip()
        return SetColumn(
            key=key,
            label=label,
            ocr_line_split=(
                self.ocr_line_split
                if self.ocr_line_split in OCR_LINE_SPLIT_OPTIONS
                else "none"
            ),
        )

    def to_dict(self) -> dict:
        return asdict(self.normalized())


@dataclass(frozen=True)
class SetDefinition:
    preset: str
    name: str
    order_label: str
    columns: tuple[SetColumn, ...]

    def normalized(self) -> "SetDefinition":
        columns = tuple(column.normalized() for column in self.columns)
        return SetDefinition(
            preset=(
                self.preset
                if self.preset in SET_PRESET_OPTIONS
                else SET_PRESET_CONVERSATION
            ),
            name=self.name.strip() or "セット",
            order_label=self.order_label.strip() or "順序",
            columns=columns,
        )

    @property
    def slot_keys(self) -> tuple[str, ...]:
        return tuple(column.key for column in self.columns)

    def slot_label(self, key: str) -> str:
        if key == SET_SLOT_SUPPLEMENT and self.preset == SET_PRESET_CONVERSATION:
            return "補足セリフ"
        return next(
            (column.label for column in self.columns if column.key == key),
            "未割当",
        )

    def column_for(self, key: str) -> SetColumn | None:
        return next((column for column in self.columns if column.key == key), None)

    def allowed_slot_keys(self) -> tuple[str, ...]:
        if self.preset == SET_PRESET_CONVERSATION:
            return (*self.slot_keys, SET_SLOT_SUPPLEMENT)
        return self.slot_keys

    def to_dict(self) -> dict:
        normalized = self.normalized()
        return {
            "preset": normalized.preset,
            "name": normalized.name,
            "order_label": normalized.order_label,
            "columns": [column.to_dict() for column in normalized.columns],
        }


def set_definition_for_preset(preset: str) -> SetDefinition:
    if preset == SET_PRESET_SINGLE_LINE:
        return SetDefinition(
            preset,
            "1行セリフ",
            "順序",
            (SetColumn(SET_SLOT_TEXT, "セリフ", "none"),),
        )
    if preset == SET_PRESET_HEADING_TEXT:
        return SetDefinition(
            preset,
            "見出し＋本文",
            "順序",
            (
                SetColumn(SET_SLOT_HEADING, "見出し", "none"),
                SetColumn(SET_SLOT_TEXT, "本文", "detected"),
            ),
        )
    return SetDefinition(
        SET_PRESET_CONVERSATION,
        "会話",
        "順序",
        (
            SetColumn(SET_SLOT_SPEAKER, "話者", "none"),
            SetColumn(SET_SLOT_TEXT, "セリフ", "detected"),
        ),
    )


def set_definition_from_dict(item: dict | None) -> SetDefinition:
    data = item or {}
    preset = str(data.get("preset") or SET_PRESET_CONVERSATION)
    fallback = set_definition_for_preset(preset)
    columns_data = data.get("columns")
    if not isinstance(columns_data, list) or not columns_data:
        return fallback
    columns = tuple(
        SetColumn(
            str(column.get("key") or ""),
            str(column.get("label") or ""),
            str(column.get("ocr_line_split") or "none"),
        )
        for column in columns_data
        if isinstance(column, dict)
    )
    return SetDefinition(
        preset,
        str(data.get("name") or fallback.name),
        str(data.get("order_label") or fallback.order_label),
        columns or fallback.columns,
    ).normalized()


@dataclass(frozen=True)
class DialogueLogDetectionConfig:
    """Profile-specific visual rules for locating repeated dialogue cards."""

    anchor_x1_ratio: float
    anchor_x2_ratio: float
    log_top_ratio: float
    log_bottom_ratio: float
    pair_height_ratio: float
    min_bar_height_ratio: float = 0.015
    max_bar_height_ratio: float = 0.03
    row_match_ratio: float = 0.5
    max_band_gap: int = 4
    normal_anchor_top_ratio: float = 0.62
    normal_anchor_bottom_ratio: float = 0.82
    normal_speaker_x1_ratio: float = 0.05
    normal_speaker_x2_ratio: float = 0.72
    normal_dialogue_x1_ratio: float = 0.04
    normal_dialogue_x2_ratio: float = 0.96
    log_speaker_x1_ratio: float = 0.10
    log_speaker_x2_ratio: float = 0.38
    log_dialogue_x1_ratio: float = 0.10
    log_dialogue_x2_ratio: float = 0.86
    speaker_vertical_padding_ratio: float = 0.006


@dataclass(frozen=True)
class CoordinateSettings:
    coordinate_space: str = COORDINATE_SPACE_IMAGE
    source_content_rect: tuple[int, int, int, int] | None = None
    black_threshold: int = 8
    min_nonblack_ratio: float = 0.01
    stable_run: int = 6
    aspect_ratio_tolerance: float = 0.08

    def normalized(self) -> "CoordinateSettings":
        coordinate_space = self.coordinate_space if self.coordinate_space in COORDINATE_SPACE_OPTIONS else COORDINATE_SPACE_IMAGE
        rect = self.source_content_rect
        if rect is not None:
            x1, y1, x2, y2 = (int(value) for value in rect)
            rect = (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None
        return CoordinateSettings(
            coordinate_space=coordinate_space,
            source_content_rect=rect,
            black_threshold=max(0, min(254, int(self.black_threshold))),
            min_nonblack_ratio=max(0.001, min(0.5, float(self.min_nonblack_ratio))),
            stable_run=max(1, min(50, int(self.stable_run))),
            aspect_ratio_tolerance=max(0.0, min(1.0, float(self.aspect_ratio_tolerance))),
        )

    def to_dict(self) -> dict:
        normalized = self.normalized()
        return {
            "coordinate_space": normalized.coordinate_space,
            "source_content_rect": list(normalized.source_content_rect) if normalized.source_content_rect else None,
            "black_threshold": normalized.black_threshold,
            "min_nonblack_ratio": normalized.min_nonblack_ratio,
            "stable_run": normalized.stable_run,
            "aspect_ratio_tolerance": normalized.aspect_ratio_tolerance,
        }


@dataclass(frozen=True)
class TextFormattingSettings:
    line_join: str = LINE_JOIN_FULLWIDTH_SPACE
    fullwidth_ascii: bool = False

    def normalized(self) -> "TextFormattingSettings":
        return TextFormattingSettings(
            line_join=(
                self.line_join
                if self.line_join in LINE_JOIN_OPTIONS
                else LINE_JOIN_FULLWIDTH_SPACE
            ),
            fullwidth_ascii=bool(self.fullwidth_ascii),
        )

    def to_dict(self) -> dict:
        normalized = self.normalized()
        return {
            "line_join": normalized.line_join,
            "fullwidth_ascii": normalized.fullwidth_ascii,
        }


def text_formatting_settings_from_dict(
    item: dict | None,
    fallback: TextFormattingSettings | None = None,
) -> TextFormattingSettings:
    default = (fallback or TextFormattingSettings()).normalized()
    data = item or {}
    return TextFormattingSettings(
        line_join=str(data.get("line_join") or default.line_join),
        fullwidth_ascii=bool(
            data.get("fullwidth_ascii", default.fullwidth_ascii)
        ),
    ).normalized()


def coordinate_settings_from_dict(item: dict | None) -> CoordinateSettings:
    data = item or {}
    rect_data = data.get("source_content_rect")
    rect = tuple(rect_data) if isinstance(rect_data, (list, tuple)) and len(rect_data) == 4 else None
    return CoordinateSettings(
        coordinate_space=str(data.get("coordinate_space") or COORDINATE_SPACE_IMAGE),
        source_content_rect=rect,
        black_threshold=int(data.get("black_threshold", 8)),
        min_nonblack_ratio=float(data.get("min_nonblack_ratio", 0.01)),
        stable_run=int(data.get("stable_run", 6)),
        aspect_ratio_tolerance=float(data.get("aspect_ratio_tolerance", 0.08)),
    ).normalized()


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


@dataclass(init=False)
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
    set_id: int = 0
    slot_key: str = ""
    known_empty: bool = False

    def __init__(
        self,
        name: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        enabled: bool = True,
        source_width: int = 0,
        source_height: int = 0,
        postprocess: str = "そのまま",
        replace_from: str = "",
        replace_to: str = "",
        remove_text: str = "",
        ocr_backend: str = "default",
        ocr_preprocess: str = "default",
        ocr_scale: str = "auto",
        ocr_threshold: int = 180,
        ocr_psm: int = 6,
        ocr_lang: str = "",
        ocr_line_split: str = "none",
        ocr_line_padding: int = 12,
        ocr_line_detect_threshold: int = 90,
        ocr_line_detect_min_ratio: float = 0.015,
        ocr_line_detect_gap: int = 10,
        set_id: int = 0,
        slot_key: str = "",
        known_empty: bool = False,
        **migration_aliases,
    ) -> None:
        # Accepted only by Python callers during the internal migration. JSON
        # templates still require set_id / slot_key and reject the old schema.
        if "pair_id" in migration_aliases:
            set_id = migration_aliases.pop("pair_id")
        if "dialogue_role" in migration_aliases:
            slot_key = migration_aliases.pop("dialogue_role")
        if migration_aliases:
            unexpected = next(iter(migration_aliases))
            raise TypeError(f"TemplateField.__init__() got an unexpected keyword argument '{unexpected}'")
        self.name = name
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.enabled = enabled
        self.source_width = source_width
        self.source_height = source_height
        self.postprocess = postprocess
        self.replace_from = replace_from
        self.replace_to = replace_to
        self.remove_text = remove_text
        self.ocr_backend = ocr_backend
        self.ocr_preprocess = ocr_preprocess
        self.ocr_scale = ocr_scale
        self.ocr_threshold = ocr_threshold
        self.ocr_psm = ocr_psm
        self.ocr_lang = ocr_lang
        self.ocr_line_split = ocr_line_split
        self.ocr_line_padding = ocr_line_padding
        self.ocr_line_detect_threshold = ocr_line_detect_threshold
        self.ocr_line_detect_min_ratio = ocr_line_detect_min_ratio
        self.ocr_line_detect_gap = ocr_line_detect_gap
        self.set_id = set_id
        self.slot_key = slot_key
        self.known_empty = known_empty

    @property
    def pair_id(self) -> int:
        return self.set_id

    @pair_id.setter
    def pair_id(self, value: int) -> None:
        self.set_id = value

    @property
    def dialogue_role(self) -> str:
        return self.slot_key

    @dialogue_role.setter
    def dialogue_role(self, value: str) -> None:
        self.slot_key = value

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
            max(0, int(self.set_id)),
            self.slot_key.strip(),
            bool(self.known_empty),
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
        int(item.get("set_id") or 0),
        str(item.get("slot_key") or ""),
        bool(item.get("known_empty", False)),
    ).normalized()


def set_groups(
    fields: list[TemplateField], definition: SetDefinition
) -> list[tuple[int, dict[str, TemplateField]]]:
    grouped: dict[int, dict[str, TemplateField]] = {}
    for field in fields:
        if not field.enabled or field.set_id <= 0:
            continue
        grouped.setdefault(field.set_id, {})[field.slot_key] = field

    output: list[tuple[int, dict[str, TemplateField]]] = []
    output_order = 1
    for _set_id, slots in sorted(grouped.items()):
        if all(key in slots for key in definition.slot_keys):
            output.append(
                (output_order, {key: slots[key] for key in definition.slot_keys})
            )
            output_order += 1
        if (
            definition.preset == SET_PRESET_CONVERSATION
            and SET_SLOT_SPEAKER in slots
            and SET_SLOT_SUPPLEMENT in slots
        ):
            output.append(
                (
                    output_order,
                    {
                        SET_SLOT_SPEAKER: slots[SET_SLOT_SPEAKER],
                        SET_SLOT_TEXT: slots[SET_SLOT_SUPPLEMENT],
                    },
                )
            )
            output_order += 1
    return output


def set_validation_error(
    fields: list[TemplateField], definition: SetDefinition
) -> str | None:
    if not fields:
        labels = "・".join(column.label for column in definition.columns)
        return f"セット出力には、{labels}の範囲が必要です。"
    allowed = set(definition.allowed_slot_keys())
    unassigned = [
        field.name
        for field in fields
        if field.set_id <= 0 or field.slot_key not in allowed
    ]
    if unassigned:
        return f"セットが未設定の項目があります: {', '.join(unassigned)}"
    grouped: dict[int, dict[str, list[str]]] = {}
    for field in fields:
        slots = grouped.setdefault(field.set_id, {})
        slots.setdefault(field.slot_key, []).append(field.name)
    for set_id, slots in sorted(grouped.items()):
        for column in definition.columns:
            names = slots.get(column.key, [])
            if not names:
                return f"セット {set_id} に{column.label}の範囲がありません。"
            if len(names) > 1:
                return f"セット {set_id} に{column.label}の範囲が複数あります: {', '.join(names)}"
        supplement_names = slots.get(SET_SLOT_SUPPLEMENT, [])
        if len(supplement_names) > 1:
            return f"セット {set_id} に補足セリフの範囲が複数あります: {', '.join(supplement_names)}"
    return None


def dialogue_pair_validation_error(fields: list[TemplateField]) -> str | None:
    """Compatibility wrapper for the conversation detector adapter."""

    return set_validation_error(fields, set_definition_for_preset(SET_PRESET_CONVERSATION))


def correction_rule_from_dict(item: dict) -> CorrectionRule:
    return CorrectionRule(
        str(item.get("pattern") or ""),
        str(item.get("replacement") or ""),
        str(item.get("target") or CORRECTION_ALL_TARGET),
        bool(item.get("enabled", True)),
    ).normalized()
