import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook
from PIL import Image

from megido_ocr_excel.export.csv import CsvExporter
from megido_ocr_excel.export.excel import ExcelExporter, ExportSettings, validate_export_settings
from megido_ocr_excel.models import TemplateField, SetDetectionResult, EXPORT_LAYOUT_SET
from megido_ocr_excel.set_definitions import CONVERSATION_SET_DEFINITION


class ExportSafetyTests(unittest.TestCase):
    def test_batch_job_freezes_settings_and_reports_phases(self):
        from unittest.mock import Mock
        from megido_ocr_excel.export.job import ExportJob
        from megido_ocr_excel.models import CoordinateSettings, TextFormattingSettings
        from megido_ocr_excel.operations import OperationCancelled
        settings = ExportSettings()
        job = ExportJob(self.root / 'job.csv', self.images, self.fields, settings,
                        CONVERSATION_SET_DEFINITION, CoordinateSettings(), TextFormattingSettings(), [], 'eng', 'paddle')
        self.fields[0].name = 'changed'
        settings.include_header = False
        engine = Mock()
        engine.recognize_field.return_value = ('ok', None)
        events = []
        job.run(CsvExporter(), engine, events.append)
        self.assertEqual([e.phase for e in events],
                         ['started', 'image_completed', 'started', 'image_completed', 'saving', 'completed'])
        self.assertEqual(job.fields[0].name, 'text')
        self.assertTrue(job.settings.include_header)
        with self.assertRaises(OperationCancelled):
            job.run(CsvExporter(), engine, events.append, lambda: True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = [self.root / 'a.png', self.root / 'b.png']
        for image in self.images:
            Image.new('RGB', (20, 20)).save(image)
        self.fields = [TemplateField('text', 0, 0, 10, 10)]

    def test_existing_reports_and_formula_like_text_are_preserved(self):
        output = self.root / 'out.xlsx'
        wb = Workbook()
        wb.active.title = 'Errors'
        wb.active['A1'] = 'user data'
        wb.create_sheet('Notices')['A1'] = 'user notice'
        wb.save(output)
        result = ExcelExporter().export(output, self.images, self.fields,
                                        ExportSettings(write_mode='追記'), lambda *_: ('=1+1', None))
        wb = load_workbook(output)
        self.assertEqual(wb['Errors']['A1'].value, 'user data')
        self.assertEqual(wb['Notices']['A1'].value, 'user notice')
        self.assertEqual(wb['OCR']['B2'].data_type, 's')
        self.assertEqual(wb['OCR']['B2'].value, '=1+1')
        self.assertEqual(result.report_sheets, [])

    def test_output_sheet_named_errors_does_not_collide(self):
        output = self.root / 'out.xlsx'
        exporter = ExcelExporter()
        settings = ExportSettings(sheet_name='Errors')
        result = exporter.export(output, self.images, self.fields, settings, lambda *_: (None, 'error'))
        self.assertNotIn('Errors', result.report_sheets)
        exporter.retry_failed(output, result, self.fields, settings, lambda *_: ('fixed', None))
        self.assertEqual(load_workbook(output)['Errors']['B2'].value, 'fixed')

    def test_external_edit_blocks_retry_in_both_formats(self):
        for exporter, suffix in [(ExcelExporter(), '.xlsx'), (CsvExporter(), '.csv')]:
            output = self.root / ('out' + suffix)
            settings = ExportSettings()
            result = exporter.export(output, self.images, self.fields, settings, lambda *_: (None, 'error'))
            if suffix == '.xlsx':
                wb = load_workbook(output)
                wb['OCR'].insert_rows(2)
                wb['OCR']['A2'] = 'keep'
                wb.save(output)
            else:
                output.write_text(output.read_text(encoding='utf-8-sig') + 'keep\n', encoding='utf-8-sig')
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                exporter.retry_failed(output, result, self.fields, settings, lambda *_: ('fixed', None))
            self.assertEqual(output.read_bytes(), before)

    def test_zero_rows_can_recover_and_shift_following_records(self):
        definition = CONVERSATION_SET_DEFINITION
        fields = [TemplateField(c.label, 0, 0, 10, 10, set_id=1, slot_key=c.key) for c in definition.columns]
        groups = [(1, {f.slot_key: f for f in fields})]
        for exporter, suffix in [(ExcelExporter(), '.xlsx'), (CsvExporter(), '.csv')]:
            output = self.root / ('recover' + suffix)
            calls = iter([SetDetectionResult([], review_reason='review'), SetDetectionResult(groups)])
            settings = ExportSettings(output_layout=EXPORT_LAYOUT_SET)
            first = exporter.export(output, self.images, fields, settings, lambda *_: ('ok', None),
                                    set_definition=definition, set_resolver=lambda *_: next(calls))
            result = exporter.retry_failed(output, first, fields, settings, lambda *_: ('fixed', None),
                                           set_definition=definition, set_resolver=lambda *_: SetDetectionResult(groups))
            self.assertEqual([r.start_row for r in result.records], [2, 3])
            self.assertEqual([r.row_count for r in result.records], [1, 1])
            self.assertEqual(result.errors, [])
            self.assertEqual(result.records[1].rows[0][-1], 'ok')

    def test_change_during_recognition_is_not_overwritten(self):
        for exporter, suffix in [(ExcelExporter(), '.xlsx'), (CsvExporter(), '.csv')]:
            output = self.root / ('concurrent' + suffix)
            def recognize(*_):
                output.write_bytes(b'external edit')
                return 'ok', None
            with self.assertRaises(ValueError):
                exporter.export(output, self.images, self.fields, ExportSettings(), recognize)
            self.assertEqual(output.read_bytes(), b'external edit')

    def test_invalid_excel_bounds_are_rejected(self):
        for cell in ('A0', 'XFE1', 'A1048577', 'A-1', '1A'):
            settings, error = validate_export_settings('OCR', '上書き', cell, True, True)
            self.assertIsNone(settings)
            self.assertTrue(error)
        output = self.root / 'bounds.xlsx'
        with self.assertRaises(ValueError):
            ExcelExporter().export(output, self.images, self.fields,
                                   ExportSettings(start_col=16384), lambda *_: ('ok', None))
        self.assertFalse(output.exists())
