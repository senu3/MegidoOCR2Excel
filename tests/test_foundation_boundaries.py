from __future__ import annotations

import inspect
import unittest

import megido_ocr_excel.config as shared_config
from megido_ocr_excel.app_config import ApplicationConfig
from megido_ocr_excel.application import ImageOcrExcelApp
from megido_ocr_excel.apps.megido import CONFIG, PROFILE
from megido_ocr_excel.models import (
    SetColumn,
    SetDefinition,
    TemplateField,
    set_definition_from_dict,
    set_groups,
)
from megido_ocr_excel.set_definitions import SET_PRESET_CONVERSATION
from megido_ocr_excel.ui.theme import THEME


class FoundationBoundaryTests(unittest.TestCase):
    def test_application_entry_point_must_select_profile_and_app_config(self) -> None:
        parameters = inspect.signature(ImageOcrExcelApp.__init__).parameters

        self.assertIs(parameters["profile"].default, inspect.Parameter.empty)
        self.assertIs(parameters["app_config"].default, inspect.Parameter.empty)
        self.assertFalse(hasattr(shared_config, "APP_PROFILE"))
        self.assertFalse(hasattr(shared_config, "APP_TITLE"))
        self.assertIsInstance(CONFIG, ApplicationConfig)

    def test_conversation_is_one_profile_owned_set_definition(self) -> None:
        self.assertEqual(PROFILE.default_set_preset, SET_PRESET_CONVERSATION)
        self.assertIn(
            SET_PRESET_CONVERSATION,
            {definition.preset for definition in PROFILE.set_definitions},
        )

        custom = SetDefinition(
            "metadata",
            "見出し情報",
            "表示順",
            (
                SetColumn("title", "題名"),
                SetColumn("author", "著者"),
            ),
        )
        restored = set_definition_from_dict(custom.to_dict())
        self.assertEqual(restored, custom)

    def test_generic_set_grouping_uses_only_set_definition(self) -> None:
        definition = SetDefinition(
            "contact",
            "連絡先",
            "順序",
            (
                SetColumn("name", "氏名"),
                SetColumn("email", "メール"),
            ),
            extra_slots=(SetColumn("alternate_email", "予備メール"),),
            additional_rows=(("name", "alternate_email"),),
        )
        fields = [
            TemplateField("氏名", 0, 0, 10, 10, set_id=1, slot_key="name"),
            TemplateField("メール", 0, 10, 10, 20, set_id=1, slot_key="email"),
            TemplateField(
                "予備メール",
                0,
                20,
                10,
                30,
                set_id=1,
                slot_key="alternate_email",
            ),
        ]

        groups = set_groups(fields, definition)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0][1]["email"].name, "メール")
        self.assertEqual(groups[1][1]["email"].name, "予備メール")

    def test_removed_dialogue_compatibility_keywords_are_rejected(self) -> None:
        with self.assertRaises(TypeError):
            TemplateField("項目", 0, 0, 10, 10, pair_id=1)
        with self.assertRaises(TypeError):
            TemplateField("項目", 0, 0, 10, 10, dialogue_role="text")

    def test_app_specific_copy_is_not_stored_in_visual_theme(self) -> None:
        self.assertFalse(hasattr(THEME.copy, "workflow_choice_note"))
        self.assertFalse(hasattr(THEME.copy, "default_template_name"))
        self.assertIn("会話", CONFIG.copy.workflow_choice_note)
        self.assertEqual(CONFIG.default_template_name, "megido-novel-template.json")


if __name__ == "__main__":
    unittest.main()
