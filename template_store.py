from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ocr_models import CoordinateSettings, TEMPLATE_VERSION, CorrectionRule, TemplateField, coordinate_settings_from_dict, correction_rule_from_dict, field_from_dict


def build_template_data(
    fields: list[TemplateField],
    lang: str,
    tesseract_path: str,
    ocr_backend: str,
    output_settings: dict,
    correction_rules: list[CorrectionRule] | None = None,
    coordinate_settings: CoordinateSettings | None = None,
    template_name: str = "ocr-template",
    profile_id: str = "",
) -> dict:
    return {
        "format": "image-ocr-to-excel-template",
        "version": TEMPLATE_VERSION,
        "template_name": template_name,
        "profile_id": profile_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lang": lang,
        "tesseract_path": tesseract_path,
        "ocr_backend": ocr_backend,
        "output_settings": output_settings,
        "coordinate_settings": (coordinate_settings or CoordinateSettings()).to_dict(),
        "correction_rules": [rule.to_dict() for rule in correction_rules or [] if rule.pattern.strip()],
        "fields": [field.to_dict() for field in fields],
    }


def save_template(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_template(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fields_from_template(data: dict) -> list[TemplateField]:
    return [field_from_dict(item) for item in data.get("fields", [])]


def correction_rules_from_template(data: dict) -> list[CorrectionRule]:
    return [correction_rule_from_dict(item) for item in data.get("correction_rules", [])]


def coordinate_settings_from_template(data: dict) -> CoordinateSettings:
    return coordinate_settings_from_dict(data.get("coordinate_settings"))
