from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image

from batch_queue import STATUS_EXCLUDED, STATUS_FAILED, STATUS_SUCCESS, ImageQueue
from dialogue_log_detector import detect_complete_dialogue_pairs, include_supplement_candidates
from excel_exporter import ExcelExporter, ExportSettings
from megido_app_config import natural_image_sort_key
from ocr_engine import apply_postprocess, detect_content_rect, format_detected_text, scaled_field
from ocr_models import COORDINATE_SPACE_CONTENT, COORDINATE_SPACE_IMAGE, DIALOGUE_ROLE_SPEAKER, DIALOGUE_ROLE_SUPPLEMENT, DIALOGUE_ROLE_TEXT, EXPORT_LAYOUT_DIALOGUE_PAIR, LINE_JOIN_FULLWIDTH_SPACE, LINE_JOIN_NEWLINE, LINE_JOIN_NONE, CoordinateSettings, TemplateField, TextFormattingSettings, dialogue_pair_validation_error
from template_store import coordinate_settings_from_template, load_template
from template_store import fields_from_template
from profiles.megido_novel import PROFILE


class BatchWorkflowTests(unittest.TestCase):
    def test_detected_lines_support_shared_join_and_fullwidth_settings(self) -> None:
        source = "ABC!? ()\n次の行"

        self.assertEqual(
            format_detected_text(
                source, TextFormattingSettings(LINE_JOIN_NONE, False)
            ),
            "ABC!? ()次の行",
        )
        self.assertEqual(
            format_detected_text(
                source, TextFormattingSettings(LINE_JOIN_FULLWIDTH_SPACE, True)
            ),
            "ＡＢＣ！？　（）　次の行",
        )
        self.assertEqual(
            format_detected_text(
                source, TextFormattingSettings(LINE_JOIN_NEWLINE, True)
            ),
            "ＡＢＣ！？　（）\n次の行",
        )
        field = TemplateField("本文", 0, 0, 10, 10, ocr_line_split="detected")
        self.assertEqual(
            apply_postprocess("一行目\n二行目", field, preserve_whitespace=True),
            "一行目\n二行目",
        )

    def test_excel_wraps_and_expands_multiline_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            Image.new("RGB", (20, 20), "white").save(image_path)
            output = Path(temp_dir) / "multiline.xlsx"
            ExcelExporter().export(
                output,
                [image_path],
                [TemplateField("本文", 0, 0, 20, 20)],
                ExportSettings(),
                lambda _image, _field: ("一行目\n二行目", None),
            )
            sheet = load_workbook(output)["OCR"]

            self.assertTrue(sheet.cell(2, 2).alignment.wrap_text)
            self.assertGreaterEqual(sheet.row_dimensions[2].height or 0, 30)

    def test_log_detector_tracks_shifted_complete_pairs_and_skips_fragments(self) -> None:
        template = load_template(
            Path(".samples/megido_novellog_template.json"),
            expected_profile_id="megido_novel",
        )
        fields = fields_from_template(template)
        settings = coordinate_settings_from_template(template)
        assert PROFILE.dialogue_log_detection is not None

        b1 = detect_complete_dialogue_pairs(
            Image.open(".samples/b1.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )
        b2 = detect_complete_dialogue_pairs(
            Image.open(".samples/b2.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(len(b1.groups), 5)
        self.assertEqual(b1.skipped_trailing, 1)
        self.assertEqual(b1.skipped_leading, 0)
        self.assertEqual(len(b2.groups), 5)
        self.assertEqual(b2.skipped_leading, 1)
        self.assertEqual(b2.skipped_trailing, 0)
        self.assertGreater(b2.groups[0][1].y1, b1.groups[0][1].y1)
        self.assertLess(b1.groups[0][1].y1, 375)
        self.assertGreater(b1.groups[0][1].y2, 409)
        self.assertGreater(b1.groups[0][1].x2 - b1.groups[0][1].x1, 200)
        self.assertGreater(b1.groups[0][2].x2 - b1.groups[0][2].x1, 700)

    def test_dynamic_log_export_writes_only_complete_pairs_and_notices(self) -> None:
        template = load_template(
            Path(".samples/megido_novellog_template.json"),
            expected_profile_id="megido_novel",
        )
        fields = fields_from_template(template)
        coordinate_settings = coordinate_settings_from_template(template)
        assert PROFILE.dialogue_log_detection is not None
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "log.xlsx"
            result = ExcelExporter().export(
                output,
                [Path(".samples/b1.png"), Path(".samples/b2.png")],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_DIALOGUE_PAIR),
                lambda _image, field: (field.name, None),
                dialogue_pair_resolver=lambda image, detection_fields: detect_complete_dialogue_pairs(
                    image,
                    detection_fields,
                    coordinate_settings,
                    PROFILE.dialogue_log_detection,
                ),
            )

            sheet = load_workbook(output)["OCR"]
            self.assertEqual(sheet.max_row, 11)
            self.assertEqual([record.row_count for record in result.records], [5, 5])
            self.assertEqual(len(result.notices), 2)
            self.assertIn("Notices", load_workbook(output).sheetnames)

    def test_mixed_normal_speakerless_narration_and_log_images_export_together(self) -> None:
        fields = [
            TemplateField(
                "話者", 0, 0, 1, 1, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER
            ),
            TemplateField(
                "セリフ本文",
                0,
                0,
                1,
                1,
                ocr_line_split="detected",
                pair_id=1,
                dialogue_role=DIALOGUE_ROLE_TEXT,
            ),
        ]
        coordinate_settings = PROFILE.coordinate_settings()
        assert PROFILE.dialogue_log_detection is not None
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "mixed.xlsx"
            result = ExcelExporter().export(
                output,
                [
                    Path(".samples/9.png"),
                    Path(".samples/c.png"),
                    Path(".samples/d.png"),
                    Path(".samples/b1.png"),
                ],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_DIALOGUE_PAIR),
                lambda _image, field: (
                    (
                        ""
                        if field.dialogue_role == DIALOGUE_ROLE_SPEAKER
                        and field.x2 - field.x1 <= 1
                        else "話者"
                        if field.dialogue_role == DIALOGUE_ROLE_SPEAKER
                        else "本文"
                    ),
                    None,
                ),
                dialogue_pair_resolver=lambda image, detection_fields: detect_complete_dialogue_pairs(
                    image,
                    detection_fields,
                    coordinate_settings,
                    PROFILE.dialogue_log_detection,
                ),
            )

            self.assertEqual([record.row_count for record in result.records], [1, 1, 1, 5])
            self.assertEqual(result.errors, [])

    def test_single_screen_patterns_are_classified_safely(self) -> None:
        template = load_template(
            Path(".samples/megido_novel_template.json"),
            expected_profile_id="megido_novel",
        )
        fields = fields_from_template(template)
        settings = coordinate_settings_from_template(template)
        assert PROFILE.dialogue_log_detection is not None

        normal = detect_complete_dialogue_pairs(
            Image.open(".samples/9.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )
        speakerless = detect_complete_dialogue_pairs(
            Image.open(".samples/c.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )
        narration = detect_complete_dialogue_pairs(
            Image.open(".samples/d.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )
        supplement = detect_complete_dialogue_pairs(
            Image.open(".samples/e.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(normal.layout, "normal")
        self.assertEqual(len(normal.groups), 1)
        self.assertEqual(speakerless.layout, "speakerless")
        self.assertTrue(speakerless.allow_empty_speaker)
        self.assertTrue(speakerless.allow_empty_dialogue)
        self.assertTrue(speakerless.groups[0][2].known_empty)
        self.assertEqual(narration.layout, "narration")
        self.assertTrue(narration.allow_empty_speaker)
        self.assertEqual(supplement.layout, "supplement_candidate")
        self.assertEqual(len(supplement.groups), 1)
        self.assertEqual(len(supplement.candidate_fields), 1)
        self.assertEqual(supplement.candidate_fields[0].name, "補助テキスト候補")
        self.assertEqual(
            supplement.candidate_fields[0].dialogue_role,
            DIALOGUE_ROLE_SUPPLEMENT,
        )
        self.assertIn("補助テキスト", supplement.review_reason)

    def test_shifted_log_reuses_recorded_content_rect_when_black_edge_detection_is_ambiguous(self) -> None:
        fields = [
            TemplateField("話者", 0, 0, 1, 1, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER),
            TemplateField("セリフ本文", 0, 0, 1, 1, ocr_line_split="detected", pair_id=1, dialogue_role=DIALOGUE_ROLE_TEXT),
        ]
        settings = PROFILE.coordinate_settings()
        settings = replace(settings, source_content_rect=(0, 219, 1080, 2087))
        result = detect_complete_dialogue_pairs(
            Image.open(".samples/b2.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(result.layout, "log")
        self.assertEqual(len(result.groups), 5)

    def test_supplement_is_automatically_written_as_the_same_speakers_next_dialogue(self) -> None:
        fields = [
            TemplateField("話者", 0, 0, 1, 1, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER),
            TemplateField("セリフ本文", 0, 0, 1, 1, ocr_line_split="detected", pair_id=1, dialogue_role=DIALOGUE_ROLE_TEXT),
        ]
        settings = PROFILE.coordinate_settings()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "supplement.xlsx"
            result = ExcelExporter().export(
                output,
                [Path(".samples/e.png")],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_DIALOGUE_PAIR),
                lambda _image, field: (field.name, None),
                dialogue_pair_resolver=lambda image, detection_fields: include_supplement_candidates(
                    detect_complete_dialogue_pairs(
                        image,
                        detection_fields,
                        settings,
                        PROFILE.dialogue_log_detection,
                    )
                ),
            )
            sheet = load_workbook(output)["OCR"]

            self.assertEqual(result.errors, [])
            self.assertEqual(result.records[0].row_count, 2)
            self.assertEqual(
                [sheet.cell(2, column).value for column in range(2, 5)],
                ["1", "話者", "セリフ本文"],
            )
            self.assertEqual(
                [sheet.cell(3, column).value for column in range(2, 5)],
                ["2", "話者", "補助テキスト候補"],
            )

    def test_existing_novel_samples_are_not_misclassified_as_logs_or_supplements(self) -> None:
        template = load_template(
            Path(".samples/megido_novel_template.json"),
            expected_profile_id="megido_novel",
        )
        fields = fields_from_template(template)
        settings = coordinate_settings_from_template(template)
        assert PROFILE.dialogue_log_detection is not None

        layouts = [
            detect_complete_dialogue_pairs(
                Image.open(f".samples/{index}.png"),
                fields,
                settings,
                PROFILE.dialogue_log_detection,
            ).layout
            for index in range(1, 10)
        ]

        self.assertEqual(layouts, ["normal"] * 9)

    def test_intentionally_blank_speakerless_frame_is_not_an_ocr_error(self) -> None:
        template = load_template(
            Path(".samples/megido_novellog_template.json"),
            expected_profile_id="megido_novel",
        )
        fields = fields_from_template(template)
        coordinate_settings = coordinate_settings_from_template(template)
        assert PROFILE.dialogue_log_detection is not None
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "blank.xlsx"
            result = ExcelExporter().export(
                output,
                [Path(".samples/c.png")],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_DIALOGUE_PAIR),
                lambda _image, _field: ("", None),
                dialogue_pair_resolver=lambda image, detection_fields: detect_complete_dialogue_pairs(
                    image,
                    detection_fields,
                    coordinate_settings,
                    PROFILE.dialogue_log_detection,
                ),
            )

            self.assertEqual(result.errors, [])
            self.assertEqual(result.records[0].row_count, 1)

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
        template = load_template(Path(".samples/megido_novel_template.json"), expected_profile_id="megido_novel")

        settings = coordinate_settings_from_template(template)

        self.assertEqual(settings.coordinate_space, COORDINATE_SPACE_CONTENT)
        self.assertEqual(settings.source_content_rect, (0, 219, 1080, 2087))

    def test_missing_coordinate_settings_use_full_image_default(self) -> None:
        settings = coordinate_settings_from_template({})

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
                TemplateField("話者", 0, 0, 20, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER),
                TemplateField("セリフ", 0, 10, 20, 20, pair_id=1, dialogue_role=DIALOGUE_ROLE_TEXT),
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

    def test_queue_preserves_failed_state_across_exclusion(self) -> None:
        first = Path("1.png")
        second = Path("2.png")
        queue = ImageQueue()
        queue.reset([first, second])

        queue.items[0].status = STATUS_FAILED
        queue.items[0].resume_status = STATUS_FAILED
        queue.items[1].status = STATUS_SUCCESS
        queue.items[1].resume_status = STATUS_SUCCESS
        queue.set_included(first, False)

        self.assertEqual(queue.items[0].status, STATUS_EXCLUDED)
        self.assertEqual(queue.failed_files(), [])

        queue.set_included(first, True)

        self.assertEqual(queue.failed_files(), [first])
        self.assertEqual(queue.items[0].status, STATUS_FAILED)

    def test_failed_image_retry_overwrites_original_row_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            good = root / "1.png"
            failed = root / "2.png"
            output = root / "output.xlsx"
            Image.new("RGB", (10, 10), "white").save(good)
            Image.new("RGB", (10, 10), "black").save(failed)
            exporter = ExcelExporter()
            settings = ExportSettings()
            fields = [TemplateField("本文", 0, 0, 10, 10)]

            first_result = exporter.export(
                output,
                [good, failed],
                fields,
                settings,
                lambda image, _field: ("成功", None) if image.getpixel((0, 0)) == (255, 255, 255) else (None, "一時的な失敗"),
            )

            self.assertEqual(first_result.failed_records[0].start_row, 3)
            retry_result = exporter.retry_failed(
                output,
                first_result,
                fields,
                settings,
                lambda _image, _field: ("再認識", None),
            )
            workbook = load_workbook(output)
            sheet = workbook["OCR"]

            self.assertEqual(sheet.max_row, 3)
            self.assertEqual(sheet.cell(3, 1).value, "2.png")
            self.assertEqual(sheet.cell(3, 2).value, "再認識")
            self.assertEqual(retry_result.errors, [])
            self.assertNotIn("Errors", workbook.sheetnames)

    def test_unreadable_image_reserves_a_row_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "broken.png"
            output = root / "output.xlsx"
            image_path.write_text("not an image", encoding="utf-8")
            exporter = ExcelExporter()
            settings = ExportSettings()
            fields = [TemplateField("本文", 0, 0, 10, 10)]

            first_result = exporter.export(output, [image_path], fields, settings, lambda _image, _field: ("未使用", None))
            first_sheet = load_workbook(output)["OCR"]

            self.assertEqual(first_result.records[0].row_count, 1)
            self.assertEqual(first_sheet.cell(2, 1).value, "broken.png")
            self.assertIsNone(first_sheet.cell(2, 2).value)

            Image.new("RGB", (10, 10), "white").save(image_path)
            exporter.retry_failed(output, first_result, fields, settings, lambda _image, _field: ("復旧", None))
            retried_sheet = load_workbook(output)["OCR"]

            self.assertEqual(retried_sheet.max_row, 2)
            self.assertEqual(retried_sheet.cell(2, 2).value, "復旧")

    def test_dialogue_pair_retry_keeps_recorded_row_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "scene.png"
            output = root / "output.xlsx"
            Image.new("RGB", (20, 20), "white").save(image_path)
            fields = [
                TemplateField("話者1", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER),
                TemplateField("セリフ1", 10, 0, 20, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_TEXT),
                TemplateField("話者2", 0, 10, 10, 20, pair_id=2, dialogue_role=DIALOGUE_ROLE_SPEAKER),
                TemplateField("セリフ2", 10, 10, 20, 20, pair_id=2, dialogue_role=DIALOGUE_ROLE_TEXT),
            ]
            settings = ExportSettings(output_layout=EXPORT_LAYOUT_DIALOGUE_PAIR)
            exporter = ExcelExporter()
            first_result = exporter.export(
                output,
                [image_path],
                fields,
                settings,
                lambda _image, _field: (None, "失敗"),
            )

            self.assertEqual(first_result.records[0].row_count, 2)
            values = iter(["A", "一行目", "B", "二行目"])
            exporter.retry_failed(output, first_result, fields, settings, lambda _image, _field: (next(values), None))
            sheet = load_workbook(output)["OCR"]

            self.assertEqual(sheet.max_row, 3)
            self.assertEqual([sheet.cell(2, column).value for column in range(1, 5)], ["scene.png", "1", "A", "一行目"])
            self.assertEqual([sheet.cell(3, column).value for column in range(1, 5)], ["scene.png", "2", "B", "二行目"])

    def test_dialogue_pairs_ignore_field_list_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "scene.png"
            output = root / "output.xlsx"
            Image.new("RGB", (20, 20), "white").save(image_path)
            fields = [
                TemplateField("セリフ2", 10, 10, 20, 20, pair_id=2, dialogue_role=DIALOGUE_ROLE_TEXT),
                TemplateField("話者1", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER),
                TemplateField("セリフ1", 10, 0, 20, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_TEXT),
                TemplateField("話者2", 0, 10, 10, 20, pair_id=2, dialogue_role=DIALOGUE_ROLE_SPEAKER),
            ]
            recognized = {field.name: field.name for field in fields}

            ExcelExporter().export(
                output,
                [image_path],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_DIALOGUE_PAIR),
                lambda _image, field: (recognized[field.name], None),
            )
            sheet = load_workbook(output)["OCR"]

            self.assertEqual([sheet.cell(2, column).value for column in range(2, 5)], ["1", "話者1", "セリフ1"])
            self.assertEqual([sheet.cell(3, column).value for column in range(2, 5)], ["2", "話者2", "セリフ2"])

    def test_dialogue_pair_validation_reports_missing_and_duplicate_roles(self) -> None:
        missing = [TemplateField("話者", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER)]
        duplicate = [
            TemplateField("話者A", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER),
            TemplateField("話者B", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_SPEAKER),
            TemplateField("本文", 0, 0, 10, 10, pair_id=1, dialogue_role=DIALOGUE_ROLE_TEXT),
        ]

        self.assertIn("セリフ", dialogue_pair_validation_error(missing) or "")
        self.assertIn("複数", dialogue_pair_validation_error(duplicate) or "")


if __name__ == "__main__":
    unittest.main()
