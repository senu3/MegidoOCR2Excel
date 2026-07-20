from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from PIL import Image

from megido_ocr_excel.models import CoordinateSettings, DialogueLogDetectionConfig, SET_SLOT_SPEAKER, SET_SLOT_TEXT, TemplateField, TextFormattingSettings, text_formatting_settings_from_dict


ImageTextCorrector = Callable[[Image.Image, TemplateField, str, int], str]


@dataclass(frozen=True)
class FieldPreset:
    family: str
    prefixes: tuple[str, ...]
    ocr: Mapping[str, object]

    def matches(self, field_name: str) -> bool:
        return any(field_name.startswith(prefix) for prefix in self.prefixes)


@dataclass(frozen=True)
class OcrProfile:
    profile_id: str
    name: str
    app_title: str
    default_backend: str
    default_lang: str
    coordinate_defaults: Mapping[str, object]
    default_field_ocr: Mapping[str, object]
    text_format_defaults: Mapping[str, object] = field(default_factory=dict)
    field_presets: tuple[FieldPreset, ...] = field(default_factory=tuple)
    dialogue_log_detection: DialogueLogDetectionConfig | None = None
    image_text_corrector: ImageTextCorrector | None = None

    def coordinate_settings(self) -> CoordinateSettings:
        return CoordinateSettings(**self.coordinate_defaults).normalized()

    def text_formatting_settings(self) -> TextFormattingSettings:
        return text_formatting_settings_from_dict(dict(self.text_format_defaults))

    def field_family(self, field_name: str) -> str:
        preset = self._matching_preset(field_name)
        return preset.family if preset else field_name

    def has_field_ocr_preset(self, field_name: str) -> bool:
        return self._matching_preset(field_name) is not None

    def field_ocr_preset(self, field_name: str) -> dict:
        values = dict(self.default_field_ocr)
        preset = self._matching_preset(field_name)
        if preset:
            values.update(preset.ocr)
        return values

    def auto_detection_fields(self) -> list[TemplateField]:
        fields = [
            TemplateField(
                "話者", 0, 0, 1, 1, set_id=1, slot_key=SET_SLOT_SPEAKER
            ),
            TemplateField(
                "セリフ本文",
                0,
                0,
                1,
                1,
                set_id=1,
                slot_key=SET_SLOT_TEXT,
                ocr_line_split="detected",
            ),
        ]
        for field in fields:
            for key, value in self.field_ocr_preset(field.name).items():
                setattr(field, key, value)
        return fields

    def _matching_preset(self, field_name: str) -> FieldPreset | None:
        return next((preset for preset in self.field_presets if preset.matches(field_name)), None)
