"""UI-independent execution of a frozen batch request."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from megido_ocr_excel.export.csv import CsvExporter
from megido_ocr_excel.export.excel import ExcelExporter
from megido_ocr_excel.export.rows import ExportResult, ExportSettings
from megido_ocr_excel.models import CoordinateSettings, CorrectionRule, SetDefinition, TemplateField, TextFormattingSettings, EXPORT_LAYOUT_SET
from megido_ocr_excel.ocr.engine import OcrEngine
from megido_ocr_excel.operations import CancelCheck, raise_if_cancelled
from megido_ocr_excel.profiles.base import AutoDetectionStrategy


@dataclass(frozen=True)
class BatchProgress:
    phase: str
    completed: int
    total: int
    image_path: Path | None = None


@dataclass
class ExportJob:
    output_path: Path
    image_files: list[Path]
    fields: list[TemplateField]
    settings: ExportSettings
    definition: SetDefinition
    coordinates: CoordinateSettings
    formatting: TextFormattingSettings
    rules: list[CorrectionRule]
    language: str
    backend: str
    detection: AutoDetectionStrategy | None = None
    previous: ExportResult | None = None

    def __post_init__(self) -> None:
        # UI edits after submission must not alter an in-flight operation.
        for name in ('image_files', 'fields', 'settings', 'definition', 'coordinates', 'formatting', 'rules', 'previous'):
            setattr(self, name, deepcopy(getattr(self, name)))

    def run(self, exporter: ExcelExporter | CsvExporter, engine: OcrEngine,
            progress: Callable[[BatchProgress], None], cancel_check: CancelCheck | None = None) -> ExportResult:
        raise_if_cancelled(cancel_check)
        paths = self.image_files
        if self.previous is not None:
            targets = set(paths)
            paths = [r.image_path for r in self.previous.failed_records if r.image_path in targets]
        total = len(paths)
        progress(BatchProgress('started', 0, total, paths[0] if paths else None))

        def completed(count: int, _total: int, path: Path) -> None:
            progress(BatchProgress('image_completed', count, total, path))
            if count < total:
                progress(BatchProgress('started', count, total, paths[count]))
            else:
                progress(BatchProgress('saving', count, total))

        def recognize(image, field):
            raise_if_cancelled(cancel_check)
            return engine.recognize_field(image, field, self.language, '', self.backend,
                                          self.rules, self.coordinates, self.formatting)

        resolver = None
        detection = self.detection
        if detection is not None and self.settings.output_layout == EXPORT_LAYOUT_SET:
            resolver = lambda image, fields: detection.resolve_sets(image, fields, self.coordinates)
        if self.previous is None:
            result = exporter.export(self.output_path, paths, self.fields, self.settings, recognize, progress_callback=completed, set_definition=self.definition,
                                     set_resolver=resolver, cancel_check=cancel_check)
        else:
            result = exporter.retry_failed(self.output_path, self.previous, self.fields, self.settings,
                                           recognize, retry_files=paths, progress_callback=completed, set_definition=self.definition,
                                           set_resolver=resolver, cancel_check=cancel_check)
        progress(BatchProgress('completed', total, total))
        return result
