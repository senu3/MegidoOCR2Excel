from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image

from excel_exporter import ExcelExporter, ExportSettings
from megido_app_config import natural_image_sort_key
from ocr_engine import detect_content_rect, scaled_field
from ocr_models import COORDINATE_SPACE_CONTENT, COORDINATE_SPACE_IMAGE, EXPORT_LAYOUT_DIALOGUE_PAIR, CoordinateSettings, TemplateField
from template_store import coordinate_settings_from_template, load_template


class BatchWorkflowTests(unittest.TestCase):
    def test_black_letterbox_content_rect_is_detected(self) -> None:
        image = Image.new("RGB", (100, 120), "black")
        image.paste(Image.new("RGB", (100, 80), "#303030"), (0, 20))

        rect = detect_content_rect(
            image,
            CoordinateSettings(coordinate_space=COORDINATE_SPACE_CONTENT, stable_run=3),
        )

        self.assertEqual(rect, (0, 20, 100, 100))

    def test_field_is_mapped_between_detected_content_rects(self) -> None:
        image = Image.new("RGB", (100, 120), "black")
        field = TemplateField("本文", 10, 30, 90, 50, True, 100, 100)
        settings = CoordinateSettings(
            coordinate_space=COORDINATE_SPACE_CONTENT,
            source_content_rect=(0, 10, 100, 90),
        )

        mapped = scaled_field(field, image, settings, target_content_rect=(0, 20, 100, 100))

        self.assertEqual((mapped.x1, mapped.y1, mapped.x2, mapped.y2), (10, 40, 90, 60))

    def test_sample_template_enables_content_coordinates(self) -> None:
        template = load_template(Path(".samples/megido_novel_template.json"))

        settings = coordinate_settings_from_template(template)

        self.assertEqual(settings.coordinate_space, COORDINATE_SPACE_CONTENT)
        self.assertEqual(settings.source_content_rect, (0, 219, 1080, 2087))

    def test_legacy_template_keeps_full_image_coordinates(self) -> None:
        settings = coordinate_settings_from_template({"version": 4})

        self.assertEqual(settings.coordinate_space, COORDINATE_SPACE_IMAGE)
        self.assertIsNone(settings.source_content_rect)

    def test_screenshot_names_are_sorted_naturally(self) -> None:
        paths = [Path("10.png"), Path("2.png"), Path("1.png"), Path("scene11.png"), Path("scene3.png")]

        result = [path.name for path in sorted(paths, key=natural_image_sort_key)]

        self.assertEqual(result, ["1.png", "2.png", "10.png", "scene3.png", "scene11.png"])

    def test_empty_image_row_result_is_written_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "1.png"
            output_path = root / "output.xlsx"
            Image.new("RGB", (20, 20), "white").save(image_path)

            result = ExcelExporter().export(
                output_path,
                [image_path],
                [TemplateField("セリフ", 0, 0, 20, 20)],
                ExportSettings(),
                lambda _image, _field: ("", None),
            )

            self.assertEqual(len(result.errors), 1)
            self.assertIn("空です", result.errors[0].error)
            workbook = load_workbook(output_path)
            self.assertIn("Errors", workbook.sheetnames)

    def test_empty_dialogue_pair_results_are_each_written_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "1.png"
            output_path = root / "output.xlsx"
            Image.new("RGB", (20, 20), "white").save(image_path)
            fields = [
                TemplateField("話者", 0, 0, 20, 10),
                TemplateField("セリフ", 0, 10, 20, 20),
            ]

            result = ExcelExporter().export(
                output_path,
                [image_path],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_DIALOGUE_PAIR),
                lambda _image, _field: ("", None),
            )

            self.assertEqual(len(result.errors), 2)
            self.assertTrue(all("空です" in error.error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
