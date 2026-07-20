from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from megido_ocr_excel.models import LINE_JOIN_NEWLINE, SET_SLOT_SPEAKER, CoordinateSettings, TEMPLATE_VERSION, TemplateField, TextFormattingSettings
from megido_ocr_excel.profiles import get_profile, registered_profiles
from megido_ocr_excel.profiles.base import FieldPreset, OcrProfile
from megido_ocr_excel.templates import TemplateValidationError, build_template_data, load_template, profile_options_from_template, save_template, text_formatting_from_template


def valid_template(profile_id: str = "megido_novel") -> dict:
    return build_template_data(
        fields=[TemplateField("本文", 0, 0, 100, 50)],
        lang="jpn",
        tesseract_path="",
        ocr_backend="tesseract",
        output_settings={
            "sheet_name": "OCR",
            "write_mode": "上書き",
            "start_cell": "A1",
            "include_filename": True,
            "include_header": True,
            "output_layout": "画像ごとに1行",
        },
        coordinate_settings=CoordinateSettings(),
        profile_id=profile_id,
    )


class ProfileTests(unittest.TestCase):
    def test_registered_profile_exposes_defaults_and_field_matching(self) -> None:
        profile = get_profile("megido_novel")

        self.assertIn(profile, registered_profiles())
        self.assertEqual(profile.default_backend, "paddle")
        self.assertEqual(profile.field_family("セリフ本文3"), "セリフ本文")
        self.assertEqual(profile.field_ocr_preset("セリフ3")["ocr_line_split"], "detected")
        self.assertEqual(profile.field_ocr_preset("セリフ3")["ocr_preprocess"], "gray")
        self.assertFalse(profile.has_field_ocr_preset("選択肢"))
        self.assertTrue(profile.text_formatting_settings().fullwidth_ascii)
        self.assertIsNotNone(profile.image_text_corrector)

    def test_profile_model_can_define_an_independent_game(self) -> None:
        profile = OcrProfile(
            profile_id="another_game",
            name="Another game",
            app_title="Another OCR",
            default_backend="tesseract",
            default_lang="eng",
            coordinate_defaults={"coordinate_space": "image"},
            default_field_ocr={"ocr_lang": ""},
            field_presets=(FieldPreset("name", ("Name",), {"ocr_lang": "eng"}),),
        )

        self.assertEqual(profile.coordinate_settings().coordinate_space, "image")
        self.assertEqual(profile.field_ocr_preset("Name 1")["ocr_lang"], "eng")
        self.assertEqual(profile.field_ocr_preset("Body")["ocr_lang"], "")
        self.assertIsNone(profile.image_text_corrector)


class TemplateV1Tests(unittest.TestCase):
    def test_build_save_and_load_use_release_version_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "template.json"
            data = valid_template()

            save_template(path, data)
            loaded = load_template(path, expected_profile_id="megido_novel")

            self.assertEqual(TEMPLATE_VERSION, 1)
            self.assertEqual(loaded["version"], 1)
            self.assertEqual(loaded["profile_id"], "megido_novel")

    def test_template_with_unsupported_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unsupported-version.json"
            data = valid_template()
            data["version"] = TEMPLATE_VERSION + 1
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(
                TemplateValidationError, rf"version {TEMPLATE_VERSION}"
            ):
                load_template(path)

    def test_template_for_a_different_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "other.json"
            path.write_text(json.dumps(valid_template("another_game")), encoding="utf-8")

            with self.assertRaisesRegex(TemplateValidationError, "another_game.*megido_novel"):
                load_template(path, expected_profile_id="megido_novel")

    def test_template_missing_required_field_properties_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            for key in ("name", "set_id", "slot_key"):
                with self.subTest(key=key):
                    path = Path(temp_dir) / f"missing-{key}.json"
                    data = valid_template()
                    data["fields"][0].pop(key)
                    path.write_text(json.dumps(data), encoding="utf-8")

                    with self.assertRaisesRegex(TemplateValidationError, key):
                        load_template(path)

    def test_set_assignment_is_preserved_in_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dialogue.json"
            data = valid_template()
            data["fields"][0]["set_id"] = 3
            data["fields"][0]["slot_key"] = SET_SLOT_SPEAKER

            save_template(path, data)
            loaded = load_template(path)

            self.assertEqual(loaded["fields"][0]["set_id"], 3)
            self.assertEqual(loaded["fields"][0]["slot_key"], SET_SLOT_SPEAKER)

    def test_duplicate_set_column_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "duplicate-set-columns.json"
            data = valid_template()
            data["set_definition"]["columns"].append(
                dict(data["set_definition"]["columns"][0])
            )
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(TemplateValidationError, "key が重複"):
                load_template(path)

    def test_shared_text_formatting_is_preserved_in_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "formatting.json"
            data = valid_template()
            data["text_formatting"] = TextFormattingSettings(
                LINE_JOIN_NEWLINE, True
            ).to_dict()

            save_template(path, data)
            settings = text_formatting_from_template(load_template(path))

            self.assertEqual(settings.line_join, LINE_JOIN_NEWLINE)
            self.assertTrue(settings.fullwidth_ascii)

    def test_profile_image_correction_option_is_optional_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile-options.json"
            data = valid_template()
            data["profile_options"] = {"image_text_correction": False}

            save_template(path, data)
            options = profile_options_from_template(load_template(path))

            self.assertFalse(options["image_text_correction"])

            data.pop("profile_options")
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(profile_options_from_template(load_template(path)), {})

    def test_profile_image_correction_option_requires_a_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid-profile-options.json"
            data = valid_template()
            data["profile_options"] = {"image_text_correction": "off"}
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(
                TemplateValidationError,
                "profile_options.image_text_correction",
            ):
                load_template(path)


if __name__ == "__main__":
    unittest.main()
