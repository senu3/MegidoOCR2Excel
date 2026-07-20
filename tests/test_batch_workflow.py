from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from openpyxl import Workbook, load_workbook
from PIL import Image

from megido_ocr_excel.export.queue import (
    STATUS_EXCLUDED,
    STATUS_FAILED,
    STATUS_SUCCESS,
    ImageQueue,
)
from megido_ocr_excel.ocr.dialogue_detector import (
    DialoguePairDetectionResult,
    detect_complete_dialogue_pairs,
    include_supplement_candidates,
)
from megido_ocr_excel.export.excel import ExcelExporter, ExportSettings
from megido_ocr_excel.operations import OperationCancelled
from megido_ocr_excel.config import natural_image_sort_key
from megido_ocr_excel.ocr.engine import (
    apply_postprocess,
    detect_content_rect,
    format_detected_text,
    scaled_field,
)
from megido_ocr_excel.models import (
    COORDINATE_SPACE_CONTENT,
    COORDINATE_SPACE_IMAGE,
    EXPORT_LAYOUT_SET,
    LINE_JOIN_FULLWIDTH_SPACE,
    LINE_JOIN_NEWLINE,
    LINE_JOIN_NONE,
    SET_PRESET_HEADING_TEXT,
    SET_SLOT_HEADING,
    SET_SLOT_SPEAKER,
    SET_SLOT_SUPPLEMENT,
    SET_SLOT_TEXT,
    CoordinateSettings,
    TemplateField,
    TextFormattingSettings,
    set_definition_for_preset,
    set_validation_error,
)
from scripts.ocr_accuracy_common import (
    build_accuracy_row,
    expected_values_for_field,
    measurement_fields,
    read_expected_sets,
    recognize_image,
    recognize_with_engine,
)
from megido_ocr_excel.templates import coordinate_settings_from_template
from megido_ocr_excel.profiles.megido_novel import PROFILE


def auto_detection_context() -> tuple[list[TemplateField], CoordinateSettings]:
    return PROFILE.auto_detection_fields(), PROFILE.coordinate_settings()


class BatchWorkflowTests(unittest.TestCase):
    def test_detection_results_own_their_candidate_field_lists(self) -> None:
        first = DialoguePairDetectionResult([])
        second = DialoguePairDetectionResult([])

        first.candidate_fields.append(TemplateField("候補", 0, 0, 1, 1))

        self.assertEqual(len(first.candidate_fields), 1)
        self.assertEqual(second.candidate_fields, [])

    def test_cancelled_export_does_not_replace_existing_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "1.png"
            output = root / "output.xlsx"
            Image.new("RGB", (10, 10), "white").save(image_path)
            workbook = Workbook()
            workbook.active["A1"] = "変更前"
            workbook.save(output)
            original_bytes = output.read_bytes()
            cancelled = False

            def recognize(_image, _field):
                nonlocal cancelled
                cancelled = True
                return "未保存", None

            with self.assertRaises(OperationCancelled):
                ExcelExporter().export(
                    output,
                    [image_path],
                    [TemplateField("本文", 0, 0, 10, 10)],
                    ExportSettings(write_mode="追記"),
                    recognize,
                    cancel_check=lambda: cancelled,
                )

            self.assertEqual(output.read_bytes(), original_bytes)

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
        fields, settings = auto_detection_context()
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
        fields, coordinate_settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "log.xlsx"
            result = ExcelExporter().export(
                output,
                [Path(".samples/b1.png"), Path(".samples/b2.png")],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_SET),
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
                "話者", 0, 0, 1, 1, set_id=1, slot_key=SET_SLOT_SPEAKER
            ),
            TemplateField(
                "セリフ本文",
                0,
                0,
                1,
                1,
                ocr_line_split="detected",
                set_id=1,
                slot_key=SET_SLOT_TEXT,
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
                ExportSettings(output_layout=EXPORT_LAYOUT_SET),
                lambda _image, field: (
                    (
                        ""
                        if field.slot_key == SET_SLOT_SPEAKER
                        and field.x2 - field.x1 <= 1
                        else "話者"
                        if field.slot_key == SET_SLOT_SPEAKER
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
        fields, settings = auto_detection_context()
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
        self.assertEqual(supplement.candidate_fields[0].name, "補足セリフ候補")
        self.assertEqual(
            supplement.candidate_fields[0].slot_key,
            SET_SLOT_SUPPLEMENT,
        )
        self.assertIn("補足セリフ", supplement.review_reason)

    def test_supplement_fallback_ignores_the_surrounding_scene_color(self) -> None:
        fields, settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None
        image = Image.open(".samples/e-2.png").convert("RGB")

        result = detect_complete_dialogue_pairs(
            image,
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(result.layout, "supplement_candidate")
        self.assertEqual(len(result.candidate_fields), 1)
        candidate = result.candidate_fields[0]
        self.assertLess(candidate.x1, 270)
        self.assertGreater(candidate.x2, 750)
        self.assertLess(candidate.y1, 1105)
        self.assertGreater(candidate.y2, 1186)
        self.assertLess(candidate.x2 - candidate.x1, image.width * 0.65)

        scene_mask = Image.new("L", image.size)
        scene_mask.putdata(
            [
                255 if green > 240 and red < 30 and blue < 80 else 0
                for red, green, blue in image.get_flattened_data()
            ]
        )
        bright_scene = Image.composite(
            Image.new("RGB", image.size, (235, 235, 235)),
            image,
            scene_mask,
        )
        bright_result = detect_complete_dialogue_pairs(
            bright_scene,
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )
        self.assertEqual(bright_result.layout, "supplement_candidate")
        self.assertEqual(len(bright_result.candidate_fields), 1)

    def test_supplement_fallback_supports_four_text_lines(self) -> None:
        fields, settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None
        image = Image.open(".samples/e-2.png").convert("RGB")
        line = image.crop((225, 1135, 798, 1205))
        image.paste(Image.new("RGB", (720, 300), (0, 255, 20)), (150, 930))
        for line_index in range(4):
            image.paste(line, (225, 970 + line_index * 52))

        result = detect_complete_dialogue_pairs(
            image,
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(result.layout, "supplement_candidate")
        self.assertEqual(len(result.candidate_fields), 1)
        candidate = result.candidate_fields[0]
        self.assertLessEqual(candidate.y1, 970)
        self.assertGreaterEqual(candidate.y2, 1190)
        self.assertGreater(candidate.y2 - candidate.y1, image.height * 0.12)

    def test_supplement_candidate_requires_text_like_content(self) -> None:
        fields, settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None

        result = detect_complete_dialogue_pairs(
            Image.open(".samples/12.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(result.layout, "normal")
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.candidate_fields, [])

    def test_log_detection_requires_speaker_text_in_repeated_blue_bands(self) -> None:
        fields, settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None

        result = detect_complete_dialogue_pairs(
            Image.open(".samples/14.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(result.layout, "normal")
        self.assertEqual(len(result.groups), 1)

    def test_shifted_log_reuses_recorded_content_rect_when_black_edge_detection_is_ambiguous(self) -> None:
        fields = [
            TemplateField("話者", 0, 0, 1, 1, set_id=1, slot_key=SET_SLOT_SPEAKER),
            TemplateField("セリフ本文", 0, 0, 1, 1, ocr_line_split="detected", set_id=1, slot_key=SET_SLOT_TEXT),
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
            TemplateField("話者", 0, 0, 1, 1, set_id=1, slot_key=SET_SLOT_SPEAKER),
            TemplateField("セリフ本文", 0, 0, 1, 1, ocr_line_split="detected", set_id=1, slot_key=SET_SLOT_TEXT),
        ]
        settings = PROFILE.coordinate_settings()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "supplement.xlsx"
            result = ExcelExporter().export(
                output,
                [Path(".samples/e.png")],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_SET),
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
                ["2", "話者", "補足セリフ候補"],
            )

    def test_existing_novel_samples_are_not_misclassified_as_logs_or_supplements(self) -> None:
        fields, settings = auto_detection_context()
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

    def test_normal_speaker_crop_keeps_left_text_margin(self) -> None:
        fields, settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None

        result = detect_complete_dialogue_pairs(
            Image.open(".samples/1.png"),
            fields,
            settings,
            PROFILE.dialogue_log_detection,
        )

        self.assertEqual(result.layout, "normal")
        self.assertLessEqual(result.groups[0][1].x1, 40)

    def test_special_conversation_samples_are_outside_auto_detection(self) -> None:
        fields, settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None

        results = [
            detect_complete_dialogue_pairs(
                Image.open(Path(".samples") / filename),
                fields,
                settings,
                PROFILE.dialogue_log_detection,
            )
            for filename in ("f.jpg", "g.png")
        ]

        self.assertEqual([result.layout for result in results], ["unknown", "unknown"])
        self.assertEqual([len(result.groups) for result in results], [0, 0])

    def test_accuracy_samples_preserve_repeated_dialogues_and_expand_supplements(self) -> None:
        b1 = read_expected_sets(Path(".samples/b1.csv"))
        b2 = read_expected_sets(Path(".samples/b2.csv"))
        supplement = read_expected_sets(Path(".samples/e.csv"))

        self.assertEqual(len(b1), 5)
        self.assertEqual(len(b2), 5)
        self.assertEqual(b1[0].speaker, "タナトス")
        self.assertEqual(b1[-1].text, "死体だからいいんだろ　いいから案内してくれよ")
        self.assertEqual(len(supplement), 2)
        self.assertEqual(
            [row.speaker for row in supplement],
            ["ドン引きする治療猫たち", "ドン引きする治療猫たち"],
        )
        self.assertIn("意訳", supplement[1].text)

    def test_accuracy_measurement_uses_the_same_dynamic_groups_as_export(self) -> None:
        fields, settings = auto_detection_context()
        speaker = next(field for field in fields if field.slot_key == SET_SLOT_SPEAKER)
        dialogue = next(field for field in fields if field.slot_key == SET_SLOT_TEXT)

        b2_dialogues, b2_error = measurement_fields(
            Image.open(".samples/b2.png"), fields, dialogue, settings
        )
        e_speakers, e_error = measurement_fields(
            Image.open(".samples/e.png"), fields, speaker, settings
        )
        e_dialogues, _ = measurement_fields(
            Image.open(".samples/e.png"), fields, dialogue, settings
        )

        self.assertEqual(b2_error, "")
        self.assertEqual(len(b2_dialogues), 5)
        self.assertEqual(e_error, "")
        self.assertEqual(len(e_speakers), 2)
        self.assertEqual(len(e_dialogues), 2)
        self.assertEqual(
            expected_values_for_field(read_expected_sets(Path(".samples/e.csv")), speaker),
            ["ドン引きする治療猫たち", "ドン引きする治療猫たち"],
        )

    def test_accuracy_measurement_passes_the_apps_text_formatting_to_ocr(self) -> None:
        formatting = TextFormattingSettings(
            line_join=LINE_JOIN_FULLWIDTH_SPACE,
            fullwidth_ascii=True,
        )
        args = Namespace(
            backend="paddle",
            preprocess="default",
            scale="auto",
            threshold=180,
            psm=6,
            lang="jpn",
            line_split="detected",
            line_padding=12,
            line_detect_threshold=90,
            line_detect_min_ratio=0.015,
            line_detect_gap=10,
            tesseract="",
            correction_rules=[],
            coordinate_settings=CoordinateSettings(),
            text_formatting=formatting,
        )
        engine = MagicMock()
        engine.recognize_field_detail.return_value = (
            "ABC!?",
            "ＡＢＣ！？",
            None,
        )

        value, error = recognize_with_engine(
            Image.new("RGB", (20, 20), "white"),
            TemplateField("セリフ本文", 0, 0, 20, 20),
            args,
            engine,
        )

        self.assertEqual(value, "ＡＢＣ！？")
        self.assertEqual(error, "")
        self.assertEqual(
            engine.recognize_field_detail.call_args.kwargs["text_formatting"],
            formatting,
        )
        failed = build_accuracy_row("missing.png", "", "", "検出失敗")
        self.assertFalse(failed.exact)
        self.assertFalse(failed.normalized_match)

    def test_paddle_accuracy_measurement_saves_the_source_crop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            save_crops = Path(temp_dir)
            args = Namespace(
                backend="paddle",
                preprocess="default",
                scale="auto",
                threshold=180,
                psm=6,
                lang="jpn",
                line_split="none",
                line_padding=12,
                line_detect_threshold=90,
                line_detect_min_ratio=0.015,
                line_detect_gap=10,
                tesseract="",
                correction_rules=[],
                coordinate_settings=CoordinateSettings(),
                text_formatting=TextFormattingSettings(),
                save_crops=save_crops,
            )
            engine = MagicMock()
            engine.recognize_field_detail.return_value = ("test", "test", None)

            value, error = recognize_image(
                Image.new("RGB", (20, 20), "white"),
                TemplateField("dialogue", 2, 3, 12, 13),
                args,
                engine,
                output_stem="sample",
            )

            self.assertEqual(value, "test")
            self.assertEqual(error, "")
            with Image.open(save_crops / "sample_dialogue.png") as crop:
                self.assertEqual(crop.size, (10, 10))

    def test_intentionally_blank_speakerless_frame_is_not_an_ocr_error(self) -> None:
        fields, coordinate_settings = auto_detection_context()
        assert PROFILE.dialogue_log_detection is not None
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "blank.xlsx"
            result = ExcelExporter().export(
                output,
                [Path(".samples/c.png")],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_SET),
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

    def test_profile_enables_content_coordinates_and_field_presets(self) -> None:
        fields, settings = auto_detection_context()

        self.assertEqual(settings.coordinate_space, COORDINATE_SPACE_CONTENT)
        self.assertEqual(settings.source_content_rect, (0, 219, 1080, 2087))
        self.assertEqual(
            next(field for field in fields if field.slot_key == SET_SLOT_SPEAKER).ocr_preprocess,
            "default",
        )
        self.assertEqual(
            next(field for field in fields if field.slot_key == SET_SLOT_TEXT).ocr_preprocess,
            "gray",
        )

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
                TemplateField("話者", 0, 0, 20, 10, set_id=1, slot_key=SET_SLOT_SPEAKER),
                TemplateField("セリフ", 0, 10, 20, 20, set_id=1, slot_key=SET_SLOT_TEXT),
            ]

            result = ExcelExporter().export(
                output_path,
                [image_path],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_SET),
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
                TemplateField("話者1", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER),
                TemplateField("セリフ1", 10, 0, 20, 10, set_id=1, slot_key=SET_SLOT_TEXT),
                TemplateField("話者2", 0, 10, 10, 20, set_id=2, slot_key=SET_SLOT_SPEAKER),
                TemplateField("セリフ2", 10, 10, 20, 20, set_id=2, slot_key=SET_SLOT_TEXT),
            ]
            settings = ExportSettings(output_layout=EXPORT_LAYOUT_SET)
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
                TemplateField("セリフ2", 10, 10, 20, 20, set_id=2, slot_key=SET_SLOT_TEXT),
                TemplateField("話者1", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER),
                TemplateField("セリフ1", 10, 0, 20, 10, set_id=1, slot_key=SET_SLOT_TEXT),
                TemplateField("話者2", 0, 10, 10, 20, set_id=2, slot_key=SET_SLOT_SPEAKER),
            ]
            recognized = {field.name: field.name for field in fields}

            ExcelExporter().export(
                output,
                [image_path],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_SET),
                lambda _image, field: (recognized[field.name], None),
            )
            sheet = load_workbook(output)["OCR"]

            self.assertEqual([sheet.cell(2, column).value for column in range(2, 5)], ["1", "話者1", "セリフ1"])
            self.assertEqual([sheet.cell(3, column).value for column in range(2, 5)], ["2", "話者2", "セリフ2"])

    def test_conversation_set_validation_reports_missing_and_duplicate_slots(self) -> None:
        missing = [TemplateField("話者", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER)]
        duplicate = [
            TemplateField("話者A", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER),
            TemplateField("話者B", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_SPEAKER),
            TemplateField("本文", 0, 0, 10, 10, set_id=1, slot_key=SET_SLOT_TEXT),
        ]

        definition = set_definition_for_preset("conversation")
        self.assertIn("セリフ", set_validation_error(missing, definition) or "")
        self.assertIn("複数", set_validation_error(duplicate, definition) or "")

    def test_heading_text_set_uses_definition_for_headers_and_slot_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "missions.png"
            output = root / "heading-text.xlsx"
            Image.new("RGB", (20, 20), "white").save(image_path)
            definition = set_definition_for_preset(SET_PRESET_HEADING_TEXT)
            fields = [
                TemplateField("本文", 0, 10, 20, 20, set_id=1, slot_key=SET_SLOT_TEXT),
                TemplateField("見出し", 0, 0, 20, 10, set_id=1, slot_key=SET_SLOT_HEADING),
            ]

            ExcelExporter().export(
                output,
                [image_path],
                fields,
                ExportSettings(output_layout=EXPORT_LAYOUT_SET),
                lambda _image, field: (field.name, None),
                set_definition=definition,
            )
            sheet = load_workbook(output)["OCR"]

            self.assertEqual(
                [sheet.cell(1, column).value for column in range(1, 5)],
                ["画像名", "順序", "見出し", "本文"],
            )
            self.assertEqual(
                [sheet.cell(2, column).value for column in range(2, 5)],
                ["1", "見出し", "本文"],
            )


if __name__ == "__main__":
    unittest.main()
