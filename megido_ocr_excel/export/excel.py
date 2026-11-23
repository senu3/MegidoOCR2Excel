from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, cast

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.worksheet.worksheet import Worksheet

from megido_ocr_excel.persistence import atomic_save_workbook
from megido_ocr_excel.export.session import (file_digest, verify_commit, structure_signature, seal_result, validate_retry, recognize_retry)
from megido_ocr_excel.models import (
    EXPORT_LAYOUT_IMAGE_ROW,
    EXPORT_LAYOUT_OPTIONS,
    SetDefinition,
    TemplateField,
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
    if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]*", start_cell):
        return None, "開始セルは A1 形式で入力してください。"
    try:
        start_row, start_col = coordinate_to_tuple(start_cell)
    except ValueError:
        return None, "開始セルは A1 形式で入力してください。"

    if not (1 <= start_row <= 1048576 and 1 <= start_col <= 16384):
        return None, "開始セルがExcelの有効範囲外です。"

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
        *, save_completed: bool = False,
    ) -> ExportResult:
        raise_if_cancelled(cancel_check)
        definition = resolve_export_set_definition(settings, set_definition)
        original_digest = file_digest(output_path)
        signature = structure_signature(settings, fields, definition)
        self._validate_bounds(settings.start_row, settings.start_col, len(self.headers(fields, settings, definition)))
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
            cancel_check=cancel_check, save_completed=save_completed,
        )
        commit_cancel = None if save_completed and result.records else cancel_check
        for row in rows:
            self._write_excel_row(sheet, row_cursor, settings.start_col, row)
            row_cursor += 1

        raise_if_cancelled(commit_cancel)
        if settings.write_mode != "追記" or not original_digest:
            self._fit_output_columns(sheet, settings.start_col, len(headers), settings.start_row)
        result.report_sheets = self._write_reports(workbook, result)

        raise_if_cancelled(commit_cancel)
        atomic_save_workbook(workbook, output_path, before_replace=lambda: verify_commit(output_path, original_digest, commit_cancel))
        return seal_result(result, output_path, signature)


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
        *, save_completed: bool = False,
    ) -> ExportResult:
        raise_if_cancelled(cancel_check)
        definition = resolve_export_set_definition(settings, set_definition)
        signature = structure_signature(settings, fields, definition)
        validate_retry(previous_result, output_path, signature)
        result = recognize_retry(self, previous_result, fields, settings, ocr_callback,
                                 definition, set_resolver, retry_files, progress_callback, cancel_check, save_completed)
        commit_cancel = None if save_completed else cancel_check
        workbook = load_workbook(output_path)
        sheet = workbook[settings.sheet_name]
        start_row = previous_result.records[0].start_row if previous_result.records else settings.start_row
        old_count = sum(r.row_count for r in previous_result.records)
        rows = [row for record in result.records for row in record.rows]
        width = len(self.headers(fields, settings, definition))
        self._validate_bounds(start_row + max(len(rows), 1) - 1, settings.start_col, width)
        # Only our output rectangle is rewritten; adjacent user columns stay intact.
        for row_index in range(start_row, start_row + max(old_count, len(rows))):
            for column in range(settings.start_col, settings.start_col + width):
                cell = sheet.cell(row_index, column)
                if row_index >= start_row + old_count and cell.value is not None:
                    raise ValueError("再実行結果の書き込み先に既存データがあります。別のファイルへ出力してください。")
                cell.value = None
        for offset, row in enumerate(rows):
            self._write_excel_row(sheet, start_row + offset, settings.start_col, row)
        # Names belong to this export session; the digest verifies ownership.
        for name in previous_result.report_sheets:
            if name in workbook.sheetnames:
                workbook.remove(workbook[name])
        result.report_sheets = self._write_reports(workbook, result)
        raise_if_cancelled(commit_cancel)
        atomic_save_workbook(workbook, output_path,
                             before_replace=lambda: verify_commit(output_path, previous_result.output_digest, commit_cancel))
        return seal_result(result, output_path, signature)

    @staticmethod
    def _validate_bounds(row: int, column: int, width: int) -> None:
        if not (1 <= row <= 1048576 and 1 <= column and column + width - 1 <= 16384):
            raise ValueError("出力範囲がExcelの有効範囲外です。")

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
        self._validate_bounds(row_index, start_col, len(values))
        max_lines = 1
        for offset, value in enumerate(values):
            cell = sheet.cell(row=row_index, column=start_col + offset, value=value)
            cell.data_type = "s"
            cell.alignment = Alignment(wrap_text="\n" in value, vertical="top")
            line_count = str(value).count("\n") + 1
            max_lines = max(max_lines, line_count)
            if line_count > 1:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[row_index].height = max(15, 15 * max_lines)

    def _fit_output_columns(self, sheet, start_col: int = 1, width: int | None = None, start_row: int = 1) -> None:
        end_col = start_col + width - 1 if width is not None else sheet.max_column
        for column_cells in sheet.iter_cols(min_col=start_col, max_col=end_col, min_row=start_row):
            max_length = max((len(str(cell.value or "")) for cell in column_cells), default=0)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 42)

    def _write_reports(self, workbook, result: ExportResult) -> list[str]:
        names = []
        reports = [
            ("Errors", ["画像ファイル", "項目", "エラー"],
             [[e.image, e.field, e.error] for e in result.errors]),
            ("Notices", ["画像ファイル", "処理通知"],
             [[n.image, n.notice] for n in result.notices]),
        ]
        for title, headers, rows in reports:
            if not rows:
                continue
            # openpyxl allocates a unique name, including case-insensitive collisions.
            sheet = workbook.create_sheet(title)
            names.append(sheet.title)
            for index, row in enumerate([headers, *rows], 1):
                self._write_excel_row(sheet, index, 1, row)
            self._fit_output_columns(sheet)
        return names
