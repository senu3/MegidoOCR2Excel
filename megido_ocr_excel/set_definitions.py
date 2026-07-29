from __future__ import annotations

from megido_ocr_excel.models import (
    SetColumn,
    SetDefinition,
    find_set_definition,
)


SET_PRESET_CONVERSATION = "conversation"
SET_PRESET_HEADING_TEXT = "heading_text"
SET_SLOT_SPEAKER = "speaker"
SET_SLOT_TEXT = "text"
SET_SLOT_HEADING = "heading"
SET_SLOT_SUPPLEMENT = "supplement"

CONVERSATION_SET_DEFINITION = SetDefinition(
    SET_PRESET_CONVERSATION,
    "話者＋セリフ",
    "順序",
    (
        SetColumn(SET_SLOT_SPEAKER, "話者", "none"),
        SetColumn(SET_SLOT_TEXT, "セリフ", "detected"),
    ),
    extra_slots=(
        SetColumn(SET_SLOT_SUPPLEMENT, "補足セリフ", "detected"),
    ),
    additional_rows=((SET_SLOT_SPEAKER, SET_SLOT_SUPPLEMENT),),
)

HEADING_TEXT_SET_DEFINITION = SetDefinition(
    SET_PRESET_HEADING_TEXT,
    "見出し＋本文",
    "順序",
    (
        SetColumn(SET_SLOT_HEADING, "見出し", "none"),
        SetColumn(SET_SLOT_TEXT, "本文", "detected"),
    ),
)

EXAMPLE_SET_DEFINITIONS = (
    CONVERSATION_SET_DEFINITION,
    HEADING_TEXT_SET_DEFINITION,
)
def example_set_definition(preset: str) -> SetDefinition:
    """Return a bundled example, also used to read version-1 templates."""

    return find_set_definition(EXAMPLE_SET_DEFINITIONS, preset)
