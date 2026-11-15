from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from PIL import Image
from megido_ocr_excel.models import (
    DEFAULT_SET_DEFINITION, EXPORT_LAYOUT_IMAGE_ROW, EXPORT_LAYOUT_SET,
    SetDetectionResult, SetDefinition, TemplateField, set_groups, set_validation_error,
)
from megido_ocr_excel.operations import CancelCheck, raise_if_cancelled


@dataclass
class ExportSettings:
    sheet_name: str = "OCR"
    write_mode: str = "上書き"
    start_row: int = 1
    start_col: int = 1
    include_filename: bool = True
    include_header: bool = True
    output_layout: str = EXPORT_LAYOUT_IMAGE_ROW


@dataclass
class ExportError:
    image: str
    field: str
    error: str


@dataclass
class ExportResult:
    total_images: int
    errors: list[ExportError]
    records: list["ImageExportRecord"]
    notices: list["ExportNotice"] = field(default_factory=list)

    @property
    def failed_records(self) -> list["ImageExportRecord"]:
        return [record for record in self.records if record.errors]


@dataclass
class ImageExportRecord:
    image_path: Path
    start_row: int
    row_count: int
    errors: list[ExportError]
    notices: list["ExportNotice"] = field(default_factory=list)


@dataclass
class ExportNotice:
    image: str
    notice: str


OcrCallback = Callable[[Image.Image, TemplateField], tuple[str | None, str | None]]
SetResolver = Callable[
    [Image.Image, list[TemplateField]], SetDetectionResult
]


def resolve_export_set_definition(
    settings: ExportSettings,
    set_definition: SetDefinition | None,
) -> SetDefinition:
    if settings.output_layout == EXPORT_LAYOUT_SET and set_definition is None:
        raise ValueError(
            "セット単位で出力するには、セット定義を指定してください。"
        )
    return (set_definition or DEFAULT_SET_DEFINITION).normalized()


class RowRecognizer:
    """Image recognition and tabular layout, independent of file format."""

    def recognize_rows(
        self,
        image_files: list[Path],
        fields: list[TemplateField],
        settings: ExportSettings,
        ocr_callback: OcrCallback,
        *,
        start_row: int = 1,
        progress_callback: Callable[[int, int, Path], None] | None = None,
        set_definition: SetDefinition | None = None,
        set_resolver: SetResolver | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[list[list[str]], ExportResult]:
        """Recognize images into format-neutral rows for spreadsheet exporters."""
        raise_if_cancelled(cancel_check)
        definition = resolve_export_set_definition(settings, set_definition)
        if settings.output_layout == EXPORT_LAYOUT_SET and set_resolver is None:
            set_error = set_validation_error(fields, definition)
            if set_error:
                raise ValueError(set_error)

        output_rows: list[list[str]] = []
        errors: list[ExportError] = []
        notices: list[ExportNotice] = []
        records: list[ImageExportRecord] = []
        row_cursor = start_row
        total = len(image_files)

        for row_index, image_path in enumerate(image_files, start=1):
            raise_if_cancelled(cancel_check)
            rows, image_errors, image_notices = self.recognize_image_rows(
                image_path,
                fields,
                settings,
                ocr_callback,
                definition,
                set_resolver,
                cancel_check,
            )
            records.append(
                ImageExportRecord(
                    image_path,
                    row_cursor,
                    len(rows),
                    image_errors,
                    image_notices,
                )
            )
            output_rows.extend(rows)
            row_cursor += len(rows)
            errors.extend(image_errors)
            notices.extend(image_notices)
            if progress_callback:
                progress_callback(row_index, total, image_path)

        raise_if_cancelled(cancel_check)
        return output_rows, ExportResult(total, errors, records, notices)

    def recognize_image_rows(
        self,
        image_path: Path,
        fields: list[TemplateField],
        settings: ExportSettings,
        ocr_callback: OcrCallback,
        set_definition: SetDefinition | None = None,
        set_resolver: SetResolver | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[list[list[str]], list[ExportError], list[ExportNotice]]:
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as exc:
            error = ExportError(image_path.name, "", f"画像を開けませんでした: {exc}")
            return self._blank_rows(
                image_path,
                fields,
                settings,
                set_definition or DEFAULT_SET_DEFINITION,
            ), [error], []

        if settings.output_layout == EXPORT_LAYOUT_SET:
            return self._recognize_set_rows(
                image_path,
                image,
                fields,
                settings,
                ocr_callback,
                set_definition or DEFAULT_SET_DEFINITION,
                set_resolver,
                cancel_check,
            )

        errors: list[ExportError] = []
        row = [image_path.name] if settings.include_filename else []
        for field in fields:
            raise_if_cancelled(cancel_check)
            text, error = ocr_callback(image, field)
            raise_if_cancelled(cancel_check)
            if text is None:
                errors.append(ExportError(image_path.name, field.name, error or "OCRに失敗しました。"))
                row.append("")
                continue
            if not text.strip():
                errors.append(ExportError(image_path.name, field.name, "OCR結果が空です。読み取り範囲または認識設定を確認してください。"))
            row.append(text)
        return [row], errors, []

    def _recognize_set_rows(
        self,
        image_path: Path,
        image: Image.Image,
        fields: list[TemplateField],
        settings: ExportSettings,
        ocr_callback: OcrCallback,
        set_definition: SetDefinition,
        set_resolver: SetResolver | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[list[list[str]], list[ExportError], list[ExportNotice]]:
        errors: list[ExportError] = []
        notices: list[ExportNotice] = []
        rows: list[list[str]] = []
        allow_empty_slots: set[str] = set()
        if set_resolver is None:
            groups = set_groups(fields, set_definition)
        else:
            raise_if_cancelled(cancel_check)
            detection = set_resolver(image, fields)
            raise_if_cancelled(cancel_check)
            groups = detection.groups
            allow_empty_slots.update(detection.allow_empty_slots)
            notices.extend(
                ExportNotice(image_path.name, message)
                for message in detection.notices
            )
            if detection.review_reason:
                errors.append(
                    ExportError(image_path.name, "セット確認", detection.review_reason)
                )
                return [], errors, notices
            if not groups:
                errors.append(
                    ExportError(
                        image_path.name,
                        "セット検出",
                        detection.review_reason
                        or "完全なセットを検出できませんでした。",
                    )
                )
        for order, slots in groups:
            missing_keys = [
                column.key
                for column in set_definition.columns
                if column.key not in slots
            ]
            if missing_keys:
                labels = [
                    set_definition.slot_label(key)
                    for key in missing_keys
                ]
                errors.append(
                    ExportError(
                        image_path.name,
                        "セット検出",
                        "自動検出結果に必要な項目がありません: "
                        + "、".join(labels),
                    )
                )
                continue
            values: list[str] = []
            for column in set_definition.columns:
                raise_if_cancelled(cancel_check)
                field = slots[column.key]
                text, error = ocr_callback(image, field)
                raise_if_cancelled(cancel_check)
                failed = text is None
                if text is None:
                    errors.append(ExportError(image_path.name, field.name, error or "OCRに失敗しました。"))
                    text = ""
                if not failed and not text.strip() and column.key not in allow_empty_slots:
                    errors.append(ExportError(image_path.name, field.name, "OCR結果が空です。読み取り範囲または認識設定を確認してください。"))
                values.append(text)
            row = [str(order), *values]
            if settings.include_filename:
                row.insert(0, image_path.name)
            rows.append(row)
        return rows, errors, notices

    def _blank_rows(
        self,
        image_path: Path,
        fields: list[TemplateField],
        settings: ExportSettings,
        set_definition: SetDefinition,
    ) -> list[list[str]]:
        if settings.output_layout == EXPORT_LAYOUT_SET:
            rows = []
            for order, _slots in set_groups(fields, set_definition):
                row = [str(order), *([""] * len(set_definition.columns))]
                if settings.include_filename:
                    row.insert(0, image_path.name)
                rows.append(row)
            return rows
        return [[*([image_path.name] if settings.include_filename else []), *([""] * len(fields))]]

    def headers(
        self,
        fields: list[TemplateField],
        settings: ExportSettings,
        set_definition: SetDefinition,
    ) -> list[str]:
        if settings.output_layout == EXPORT_LAYOUT_SET:
            return self._set_headers(settings.include_filename, set_definition)
        return self._export_headers(fields, settings.include_filename)

    def _export_headers(self, fields: list[TemplateField], include_filename: bool) -> list[str]:
        headers = [field.name for field in fields]
        if include_filename:
            return ["画像名", *headers]
        return headers

    def _set_headers(self, include_filename: bool, definition: SetDefinition) -> list[str]:
        headers = [definition.order_label, *(column.label for column in definition.columns)]
        if include_filename:
            return ["画像名", *headers]
        return headers
