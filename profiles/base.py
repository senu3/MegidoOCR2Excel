from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ocr_models import CoordinateSettings


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
    field_presets: tuple[FieldPreset, ...] = field(default_factory=tuple)

    def coordinate_settings(self) -> CoordinateSettings:
        return CoordinateSettings(**self.coordinate_defaults).normalized()

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

    def _matching_preset(self, field_name: str) -> FieldPreset | None:
        return next((preset for preset in self.field_presets if preset.matches(field_name)), None)
