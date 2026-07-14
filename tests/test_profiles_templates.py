from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ocr_models import LINE_JOIN_NEWLINE, SET_SLOT_SPEAKER, CoordinateSettings, TEMPLATE_VERSION, TemplateField, TextFormattingSettings
from profiles import get_profile, registered_profiles
from profiles.base import FieldPreset, OcrProfile
from template_store import TemplateValidationError, build_template_data, load_template, save_template, text_formatting_from_template


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

    def test_old_template_versions_are_rejected_without_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "old.json"
            data = valid_template()
            data["version"] = 5
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(TemplateValidationError, "version 1"):
                load_template(path)

    def test_template_for_a_different_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "other.json"
            path.write_text(json.dumps(valid_template("another_game")), encoding="utf-8")

            with self.assertRaisesRegex(TemplateValidationError, "another_game.*megido_novel"):
                load_template(path, expected_profile_id="megido_novel")

    def test_legacy_field_alias_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy-field.json"
            data = valid_template()
            data["fields"][0].pop("name")
            data["fields"][0]["cell"] = "A1"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(TemplateValidationError, "name"):
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

    def test_pre_set_schema_is_rejected_without_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "old-pair-schema.json"
            data = valid_template()
            field = data["fields"][0]
            field["pair_id"] = field.pop("set_id")
            field["dialogue_role"] = field.pop("slot_key")
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(TemplateValidationError, "set_id"):
                load_template(path)

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


if __name__ == "__main__":
    unittest.main()
