import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from megido_ocr_excel.application import ImageOcrExcelApp
from megido_ocr_excel.models import CorrectionRule, TemplateField, TextFormattingSettings
from megido_ocr_excel.ocr.engine import OcrEngine
from megido_ocr_excel.ocr.text import process_text


class TextPipelineTests(unittest.TestCase):
    def test_missing_content_rect_is_cached_for_all_fields(self):
        from megido_ocr_excel.models import CoordinateSettings, COORDINATE_SPACE_CONTENT
        image = Image.new('RGB', (20, 20))
        field = TemplateField('text', 0, 0, 10, 10, source_width=20, source_height=20)
        settings = CoordinateSettings(coordinate_space=COORDINATE_SPACE_CONTENT,
                                      source_content_rect=(0, 0, 20, 20))
        engine = OcrEngine()
        with patch('megido_ocr_excel.ocr.engine.detect_content_rect', return_value=None) as detect:
            with patch.object(engine, 'recognize_prepared', return_value='text'):
                for _ in range(3):
                    engine.recognize_field_detail(image, field, backend='paddle', coordinate_settings=settings)
        self.assertEqual(detect.call_count, 1)

    def test_rule_refresh_matches_export_for_every_format(self):
        field = TemplateField('text', 0, 0, 20, 20)
        for line_join in ('none', 'newline', 'fullwidth_space'):
            for fullwidth in (False, True):
                settings = TextFormattingSettings(line_join, fullwidth)
                engine = OcrEngine()
                with patch.object(engine, 'recognize_prepared', return_value='A\nB'):
                    raw, text, error = engine.recognize_field_detail(
                        Image.new('RGB', (20, 20)), field, backend='paddle',
                        text_formatting=settings,
                    )
                self.assertEqual(raw, 'A\nB')
                self.assertIsNone(error)
                app = SimpleNamespace(
                    fields=[field], current_raw_results=[raw], current_results=[text],
                    text_formatting=settings, correction_rules=[],
                    _ensure_result_buffers=lambda: None,
                    _refresh_review_row=lambda index: None,
                    _update_review_detail_values=lambda: None,
                )
                ImageOcrExcelApp._apply_correction_rules_to_current_results(app)
                self.assertEqual(app.current_results, [text])
                app.correction_rules = [CorrectionRule(pattern='B', replacement='C')]
                ImageOcrExcelApp._apply_correction_rules_to_current_results(app)
                self.assertEqual(app.current_results[0], process_text(raw, field, settings, app.correction_rules))

