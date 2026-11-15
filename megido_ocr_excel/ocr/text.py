from __future__ import annotations

import re
from dataclasses import dataclass

from megido_ocr_excel.models import (
    CORRECTION_ALL_TARGET, LINE_JOIN_FULLWIDTH_SPACE, LINE_JOIN_NEWLINE,
    CorrectionRule, TemplateField, TextFormattingSettings,
)


@dataclass(frozen=True)
class RecognitionResult:
    raw_text: str | None
    text: str | None
    error: str | None = None


def process_text(raw_text: str, field: TemplateField,
                 settings: TextFormattingSettings | None = None,
                 rules: list[CorrectionRule] | None = None) -> str:
    """The single text pipeline used by previews and all export formats."""
    formatted = format_ocr_text(raw_text, settings)
    corrected = apply_correction_rules(formatted, field, rules)
    return apply_postprocess(corrected, field, preserve_whitespace=True)


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return " ".join(line for line in lines if line).strip()


def fullwidth_ascii(text: str) -> str:
    converted: list[str] = []
    for char in text:
        codepoint = ord(char)
        if char == " ":
            converted.append("　")
        elif 0x21 <= codepoint <= 0x7E:
            converted.append(chr(codepoint + 0xFEE0))
        else:
            converted.append(char)
    return "".join(converted)


def format_ocr_text(
    text: str,
    settings: TextFormattingSettings | None,
) -> str:
    normalized = (settings or TextFormattingSettings()).normalized()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    separator = {
        LINE_JOIN_FULLWIDTH_SPACE: "　",
        LINE_JOIN_NEWLINE: "\n",
    }.get(normalized.line_join, "")
    value = separator.join(lines)
    return fullwidth_ascii(value) if normalized.fullwidth_ascii else value


def apply_postprocess(
    text: str,
    field: TemplateField,
    preserve_whitespace: bool = False,
) -> str:
    value = text
    if field.replace_from:
        value = value.replace(field.replace_from, field.replace_to)
    for token in [part.strip() for part in field.remove_text.split(",") if part.strip()]:
        value = value.replace(token, "")
    value = value.strip() if preserve_whitespace else " ".join(value.split()).strip()

    if field.postprocess == "数字のみ":
        return re.sub(r"\D+", "", value)
    if field.postprocess == "数値抽出":
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
        return match.group(0).replace(",", ".") if match else ""
    if field.postprocess == "英数字のみ":
        return re.sub(r"[^0-9A-Za-z]+", "", value)
    return value


def apply_correction_rules(text: str, field: TemplateField, correction_rules: list[CorrectionRule] | None = None) -> str:
    value = text
    for rule in correction_rules or []:
        pattern = rule.pattern
        if not rule.enabled or not pattern:
            continue
        if rule.target not in {CORRECTION_ALL_TARGET, field.name}:
            continue
        value = value.replace(pattern, rule.replacement)
    return value


