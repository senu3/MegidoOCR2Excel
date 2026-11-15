from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, cast

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.worksheet.worksheet import Worksheet
from PIL import Image

from megido_ocr_excel.persistence import atomic_save_workbook
from megido_ocr_excel.models import (
    DEFAULT_SET_DEFINITION,
    EXPORT_LAYOUT_IMAGE_ROW,
    EXPORT_LAYOUT_OPTIONS,
    EXPORT_LAYOUT_SET,
    SetDetectionResult,
    SetDefinition,
    TemplateField,
    set_groups,
    set_validation_error,
)
from megido_ocr_excel.operations import CancelCheck, raise_if_cancelled


from megido_ocr_excel.export.rows import (
    RowRecognizer, ExportSettings, ExportError, ExportResult, ImageExportRecord,
    ExportNotice, OcrCallback, SetResolver, resolve_export_set_definition,
)


def validate_export_settings(
    sheet_name: str,
    write_mode: str,
    start_cell: str,
    include_filename: bool,
    include_header: bool,
    output_layout: str = EXPORT_LAYOUT_IMAGE_ROW,
) -> tuple[ExportSettings | None, str | None]:
    sheet_name = sheet_name.strip() or "OCR"
    if len(sheet_name) > 31 or any(char in sheet_name for char in "[]:*?/\\"):
        return None, "シート名は31文字以内で、次の文字は使えません: []:*?/\\"

    start_cell = start_cell.strip().upper() or "A1"
    try:
        start_row, start_col = coordinate_to_tuple(start_cell)
    except ValueError:
        return None, "開始セルは A1 形式で入力してください。"

    if write_mode not in {"上書き", "追記"}:
        write_mode = "上書き"
    if output_layout not in EXPORT_LAYOUT_OPTIONS:
        output_layout = EXPORT_LAYOUT_IMAGE_ROW

    return (
        ExportSettings(
            sheet_name=sheet_name,
            write_mode=write_mode,
            start_row=start_row,
            start_col=start_col,
            include_filename=include_filename,
            include_header=include_header,
            output_layout=output_layout,
        ),
        None,
    )


class ExcelExporter(RowRecognizer):
    def export(
        self,
        output_path: Path,
        image_files: list[Path],
        fields: list[TemplateField],
        settings: ExportSettings,
        ocr_callback: OcrCallback,
        progress_callback: Callable[[int, int, Path], None] | None = None,
        set_definition: SetDefinition | None = None,
        set_resolver: SetResolver | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ExportResult:
        raise_if_cancelled(cancel_check)
        definition = resolve_export_set_definition(settings, set_definition)
        workbook, sheet, row_cursor = self._prepare_output_sheet(output_path, settings)
        headers = self.headers(fields, settings, definition)
        if settings.include_header and row_cursor == settings.start_row:
            self._write_excel_row(sheet, row_cursor, settings.start_col, headers)
            row_cursor += 1

        rows, result = self.recognize_rows(
            image_files,
            fields,
            settings,
            ocr_callback,
            start_row=row_cursor,
            progress_callback=progress_callback,
            set_definition=definition,
            set_resolver=set_resolver,
            cancel_check=cancel_check,
        )
        for row in rows:
            self._write_excel_row(sheet, row_cursor, settings.start_col, row)
            row_cursor += 1

        raise_if_cancelled(cancel_check)
        self._fit_output_columns(sheet)
        self._write_error_sheet(workbook, result.errors)
        self._write_notice_sheet(workbook, result.notices)

        raise_if_cancelled(cancel_check)
        atomic_save_workbook(workbook, output_path)
        return result


    def retry_failed(
        self,
        output_path: Path,
        previous_result: ExportResult,
        fields: list[TemplateField],
        settings: ExportSettings,
        ocr_callback: OcrCallback,
        retry_files: list[Path] | None = None,
        progress_callback: Callable[[int, int, Path], None] | None = None,
        set_definition: SetDefinition | None = None,
        set_resolver: SetResolver | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ExportResult:
        raise_if_cancelled(cancel_check)
        definition = resolve_export_set_definition(settings, set_definition)
        if settings.output_layout == EXPORT_LAYOUT_SET and set_resolver is None:
            set_error = set_validation_error(fields, definition)
            if set_error:
                raise ValueError(set_error)
        if not output_path.exists():
            raise FileNotFoundError(f"再実行するExcelファイルがありません: {output_path}")
        workbook = load_workbook(output_path)
        if settings.sheet_name not in workbook.sheetnames:
            raise ValueError(f"再実行先のシートがありません: {settings.sheet_name}")
        sheet = workbook[settings.sheet_name]
        retry_targets = set(retry_files) if retry_files is not None else None
        retry_records = [
            record for record in previous_result.failed_records
            if retry_targets is None or record.image_path in retry_targets
        ]
        retry_paths = {record.image_path for record in retry_records}
        errors = [error for record in previous_result.records if record.image_path not in retry_paths for error in record.errors]
        notices = [notice for record in previous_result.records if record.image_path not in retry_paths for notice in record.notices]
        updated_by_path: dict[Path, ImageExportRecord] = {}
        total = len(retry_records)

        for row_index, record in enumerate(retry_records, start=1):
            raise_if_cancelled(cancel_check)
            rows, image_errors, image_notices = self.recognize_image_rows(
                record.image_path,
                fields,
                settings,
                ocr_callback,
                definition,
                set_resolver,
                cancel_check,
            )
            if len(rows) != record.row_count:
                raise ValueError("出力レイアウトが前回の一括出力から変更されています。全画像を再出力してください。")
            self._clear_record_rows(
                sheet,
                record,
                settings.start_col,
                len(self.headers(fields, settings, definition)),
            )
            for offset, row in enumerate(rows):
                self._write_excel_row(sheet, record.start_row + offset, settings.start_col, row)
            errors.extend(image_errors)
            notices.extend(image_notices)
            updated_by_path[record.image_path] = ImageExportRecord(
                record.image_path,
                record.start_row,
                record.row_count,
                image_errors,
                image_notices,
            )
            if progress_callback:
                progress_callback(row_index, total, record.image_path)

        raise_if_cancelled(cancel_check)
        self._fit_output_columns(sheet)
        self._write_error_sheet(workbook, errors)
        self._write_notice_sheet(workbook, notices)
        raise_if_cancelled(cancel_check)
        atomic_save_workbook(workbook, output_path)
        records = [updated_by_path.get(record.image_path, record) for record in previous_result.records]
        return ExportResult(previous_result.total_images, errors, records, notices)





    def _clear_record_rows(self, sheet, record: ImageExportRecord, start_col: int, column_count: int) -> None:
        for row in range(record.start_row, record.start_row + record.row_count):
            for column in range(start_col, start_col + column_count):
                sheet.cell(row=row, column=column).value = None

    def _prepare_output_sheet(self, output_path: Path, settings: ExportSettings):
        if settings.write_mode == "追記" and output_path.exists():
            workbook = load_workbook(output_path)
            sheet = cast(
                Worksheet,
                workbook[settings.sheet_name]
                if settings.sheet_name in workbook.sheetnames
                else workbook.create_sheet(settings.sheet_name),
            )
            row_cursor = max(settings.start_row, sheet.max_row + 1) if self._sheet_has_values(sheet) else settings.start_row
            return workbook, sheet, row_cursor

        workbook = Workbook()
        sheet = workbook.active
        if sheet is None:
            sheet = workbook.create_sheet()
        sheet.title = settings.sheet_name
        return workbook, sheet, settings.start_row

    def _sheet_has_values(self, sheet) -> bool:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value not in (None, ""):
                    return True
        return False



    def _write_excel_row(self, sheet, row_index: int, start_col: int, values: list[str]) -> None:
        max_lines = 1
        for offset, value in enumerate(values):
            cell = sheet.cell(row=row_index, column=start_col + offset, value=value)
            line_count = str(value).count("\n") + 1
            max_lines = max(max_lines, line_count)
            if line_count > 1:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        if max_lines > 1:
            sheet.row_dimensions[row_index].height = max(15, 15 * max_lines)

    def _fit_output_columns(self, sheet) -> None:
        for column_cells in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 42)

    def _write_error_sheet(self, workbook, errors: list[ExportError]) -> None:
        if "Errors" in workbook.sheetnames:
            workbook.remove(workbook["Errors"])
        if not errors:
            return
        sheet = workbook.create_sheet("Errors")
        sheet.append(["画像ファイル", "項目", "エラー"])
        for error in errors:
            sheet.append([error.image, error.field, error.error])
        self._fit_output_columns(sheet)

    def _write_notice_sheet(self, workbook, notices: list[ExportNotice]) -> None:
        if "Notices" in workbook.sheetnames:
            workbook.remove(workbook["Notices"])
        if not notices:
            return
        sheet = workbook.create_sheet("Notices")
        sheet.append(["画像ファイル", "処理通知"])
        for notice in notices:
            sheet.append([notice.image, notice.notice])
        self._fit_output_columns(sheet)
