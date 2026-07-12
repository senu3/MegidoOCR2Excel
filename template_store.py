from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from atomic_io import atomic_write_text
from ocr_models import DIALOGUE_ROLE_OPTIONS, LINE_JOIN_OPTIONS, CoordinateSettings, TEMPLATE_VERSION, CorrectionRule, TemplateField, TextFormattingSettings, coordinate_settings_from_dict, correction_rule_from_dict, field_from_dict, text_formatting_settings_from_dict


TEMPLATE_FORMAT = "image-ocr-to-excel-template"


class TemplateValidationError(ValueError):
    pass


def _require_mapping(data: dict, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise TemplateValidationError(f"'{key}' はオブジェクトで指定してください。")
    return value


def validate_template_data(data: object, expected_profile_id: str | None = None) -> dict:
    if not isinstance(data, dict):
        raise TemplateValidationError("テンプレートのルートはJSONオブジェクトで指定してください。")
    if data.get("format") != TEMPLATE_FORMAT:
        raise TemplateValidationError(f"未対応のテンプレート形式です。format は '{TEMPLATE_FORMAT}' が必要です。")
    version = data.get("version")
    if type(version) is not int or version != TEMPLATE_VERSION:
        raise TemplateValidationError(f"未対応のテンプレートバージョンです。version {TEMPLATE_VERSION} が必要です。")

    profile_id = data.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise TemplateValidationError("profile_id を指定してください。")
    if expected_profile_id and profile_id != expected_profile_id:
        raise TemplateValidationError(
            f"このテンプレートはプロファイル '{profile_id}' 用です。現在のプロファイルは '{expected_profile_id}' です。"
        )
    if not isinstance(data.get("template_name"), str) or not data["template_name"].strip():
        raise TemplateValidationError("template_name を指定してください。")
    if not isinstance(data.get("lang"), str) or not data["lang"].strip():
        raise TemplateValidationError("lang を指定してください。")
    if data.get("ocr_backend") not in {"tesseract", "paddle"}:
        raise TemplateValidationError("ocr_backend は 'tesseract' または 'paddle' を指定してください。")

    output_settings = _require_mapping(data, "output_settings")
    for key in ("sheet_name", "write_mode", "start_cell", "include_filename", "include_header"):
        if key not in output_settings:
            raise TemplateValidationError(f"output_settings.{key} がありません。")
    _require_mapping(data, "coordinate_settings")
    text_formatting = data.get("text_formatting")
    if text_formatting is not None:
        if not isinstance(text_formatting, dict):
            raise TemplateValidationError("text_formatting はオブジェクトで指定してください。")
        if text_formatting.get("line_join") not in LINE_JOIN_OPTIONS:
            raise TemplateValidationError("text_formatting.line_join が不正です。")
        if type(text_formatting.get("fullwidth_ascii")) is not bool:
            raise TemplateValidationError("text_formatting.fullwidth_ascii は真偽値で指定してください。")

    correction_rules = data.get("correction_rules", [])
    if not isinstance(correction_rules, list) or any(not isinstance(item, dict) for item in correction_rules):
        raise TemplateValidationError("correction_rules はオブジェクトの配列で指定してください。")
    fields = data.get("fields")
    if not isinstance(fields, list) or not fields:
        raise TemplateValidationError("fields に1件以上の読み取り項目を指定してください。")
    required_field_keys = {"name", "x1", "y1", "x2", "y2"}
    for index, item in enumerate(fields, start=1):
        if not isinstance(item, dict):
            raise TemplateValidationError(f"fields[{index}] はオブジェクトで指定してください。")
        missing = required_field_keys - item.keys()
        if missing:
            raise TemplateValidationError(f"fields[{index}] に必要な項目がありません: {', '.join(sorted(missing))}")
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise TemplateValidationError(f"fields[{index}].name を指定してください。")
        if any(type(item[key]) is not int for key in ("x1", "y1", "x2", "y2")):
            raise TemplateValidationError(f"fields[{index}] の座標は整数で指定してください。")
        if "pair_id" in item and (type(item["pair_id"]) is not int or item["pair_id"] < 0):
            raise TemplateValidationError(f"fields[{index}].pair_id は0以上の整数で指定してください。")
        if "dialogue_role" in item and item["dialogue_role"] not in {"", *DIALOGUE_ROLE_OPTIONS}:
            raise TemplateValidationError(f"fields[{index}].dialogue_role が不正です。")
    return data


def build_template_data(
    fields: list[TemplateField],
    lang: str,
    tesseract_path: str,
    ocr_backend: str,
    output_settings: dict,
    correction_rules: list[CorrectionRule] | None = None,
    coordinate_settings: CoordinateSettings | None = None,
    text_formatting: TextFormattingSettings | None = None,
    template_name: str = "ocr-template",
    profile_id: str = "",
) -> dict:
    return {
        "format": TEMPLATE_FORMAT,
        "version": TEMPLATE_VERSION,
        "template_name": template_name,
        "profile_id": profile_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lang": lang,
        "tesseract_path": tesseract_path,
        "ocr_backend": ocr_backend,
        "output_settings": output_settings,
        "coordinate_settings": (coordinate_settings or CoordinateSettings()).to_dict(),
        "text_formatting": (text_formatting or TextFormattingSettings()).to_dict(),
        "correction_rules": [rule.to_dict() for rule in correction_rules or [] if rule.pattern.strip()],
        "fields": [field.to_dict() for field in fields],
    }


def save_template(path: Path, data: dict) -> None:
    validate_template_data(data)
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_template(path: Path, expected_profile_id: str | None = None) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TemplateValidationError(f"JSONとして読み込めません: {exc.msg}（{exc.lineno}行目）") from exc
    return validate_template_data(data, expected_profile_id)


def fields_from_template(data: dict) -> list[TemplateField]:
    return [field_from_dict(item) for item in data.get("fields", [])]


def correction_rules_from_template(data: dict) -> list[CorrectionRule]:
    return [correction_rule_from_dict(item) for item in data.get("correction_rules", [])]


def coordinate_settings_from_template(data: dict) -> CoordinateSettings:
    return coordinate_settings_from_dict(data.get("coordinate_settings"))


def text_formatting_from_template(
    data: dict,
    fallback: TextFormattingSettings | None = None,
) -> TextFormattingSettings:
    return text_formatting_settings_from_dict(data.get("text_formatting"), fallback)
