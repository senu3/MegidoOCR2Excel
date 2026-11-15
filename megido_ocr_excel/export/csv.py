from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Callable

from megido_ocr_excel.export.rows import (
    RowRecognizer,
    ExportError,
    ExportNotice,
    ExportResult,
    ExportSettings,
    ImageExportRecord,
    OcrCallback,
    SetResolver,
    resolve_export_set_definition,
)
from megido_ocr_excel.models import (
    SetDefinition,
    TemplateField,
)
from megido_ocr_excel.operations import CancelCheck, raise_if_cancelled
from megido_ocr_excel.persistence import atomic_write_text
from megido_ocr_excel.export.session import (file_digest, verify_commit, structure_signature, seal_result, validate_retry, recognize_retry)


class CsvExporter:
    """Write the same recognized rows as Excel export to a UTF-8 BOM CSV."""

    def __init__(self, row_exporter: RowRecognizer | None = None) -> None:
        self.row_exporter = row_exporter or RowRecognizer()

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
        original_digest = file_digest(output_path)
        signature = structure_signature(settings, fields, definition)
        first_data_row = 2 if settings.include_header else 1
        rows, result = self.row_exporter.recognize_rows(
            image_files,
            fields,
            settings,
            ocr_callback,
            start_row=first_data_row,
            progress_callback=progress_callback,
            set_definition=definition,
            set_resolver=set_resolver,
            cancel_check=cancel_check,
        )

        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        if settings.include_header:
            writer.writerow(
                self.row_exporter.headers(
                    fields,
                    settings,
                    definition,
                )
            )
        writer.writerows(rows)

        raise_if_cancelled(cancel_check)
        atomic_write_text(output_path, output.getvalue(), encoding="utf-8-sig", before_replace=lambda: verify_commit(output_path, original_digest, cancel_check))
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
    ) -> ExportResult:
        raise_if_cancelled(cancel_check)
        definition = resolve_export_set_definition(settings, set_definition)
        signature = structure_signature(settings, fields, definition)
        validate_retry(previous_result, output_path, signature)
        result = recognize_retry(self.row_exporter, previous_result, fields, settings, ocr_callback,
                                 definition, set_resolver, retry_files, progress_callback, cancel_check)
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        if settings.include_header:
            writer.writerow(self.row_exporter.headers(fields, settings, definition))
        writer.writerows(row for record in result.records for row in record.rows)
        raise_if_cancelled(cancel_check)
        atomic_write_text(output_path, output.getvalue(), encoding="utf-8-sig",
                          before_replace=lambda: verify_commit(output_path, previous_result.output_digest, cancel_check))
        return seal_result(result, output_path, signature)
