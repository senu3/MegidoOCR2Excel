from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image

from excel_exporter import ExcelExporter, ExportSettings
from megido_app_config import natural_image_sort_key
from ocr_models import EXPORT_LAYOUT_DIALOGUE_PAIR, TemplateField


class BatchWorkflowTests(unittest.TestCase):
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
