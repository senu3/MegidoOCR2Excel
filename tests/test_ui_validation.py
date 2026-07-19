from __future__ import annotations

import unittest
from unittest.mock import patch

from megido_ocr_excel.ocr.environment import (
    OCR_ENV_LOCATION_ERROR,
    OCR_ENV_READY,
    OCR_ENV_SETUP,
    OCR_ENV_UNAVAILABLE,
    OCR_ENV_VERIFY,
)
from scripts.validate_ocr_setup_ui import (
    VALIDATION_STATES,
    ValidationOcrEnvironmentManager,
    status_for_state,
)
from scripts.validate_launcher_ui import (
    VALIDATION_STATES as LAUNCHER_VALIDATION_STATES,
    ValidationService as LauncherValidationService,
    status_for_state as launcher_status_for_state,
)


class OcrSetupUiValidationTests(unittest.TestCase):
    def test_each_validation_state_maps_to_an_ocr_environment_state(self) -> None:
        expected = {
            "setup": OCR_ENV_SETUP,
            "verify": OCR_ENV_VERIFY,
            "check-failed": OCR_ENV_VERIFY,
            "location-error": OCR_ENV_LOCATION_ERROR,
            "unavailable": OCR_ENV_UNAVAILABLE,
            "ready": OCR_ENV_READY,
        }

        self.assertEqual(set(VALIDATION_STATES), set(expected))
        for state, expected_environment_state in expected.items():
            with self.subTest(state=state):
                self.assertEqual(
                    status_for_state(state).state,
                    expected_environment_state,
                )

    def test_validation_manager_keeps_state_in_memory(self) -> None:
        status = status_for_state("setup")
        manager = ValidationOcrEnvironmentManager(status)

        self.assertEqual(manager.apply_to_process(), status.cache_dir)
        self.assertIs(manager.quick_status(), status)
        self.assertEqual(manager.verify(lambda: None), status)

    def test_validation_manager_switches_cache_modes_without_disk_writes(self) -> None:
        status = status_for_state("setup")
        manager = ValidationOcrEnvironmentManager(status)

        manager.use_custom_cache(status.cache_dir / "custom")
        self.assertEqual(manager.quick_status().state, OCR_ENV_VERIFY)
        self.assertEqual(manager.settings.cache_mode, "custom")

        manager.use_automatic_cache()
        self.assertEqual(manager.settings.cache_mode, "auto")


class LauncherUiValidationTests(unittest.TestCase):
    def test_each_launcher_validation_state_has_the_expected_setup_kind(self) -> None:
        expected_first_setup = {
            "first": True,
            "update": False,
            "repair": False,
            "running": True,
            "error": True,
        }

        self.assertEqual(
            set(LAUNCHER_VALIDATION_STATES), set(expected_first_setup)
        )
        for state, first_setup in expected_first_setup.items():
            with self.subTest(state=state):
                status = launcher_status_for_state(state)
                self.assertFalse(status.ready)
                self.assertEqual(status.first_setup, first_setup)
                self.assertIsNotNone(status.uv_path)

    def test_validation_service_matches_launcher_prepare_contract(self) -> None:
        service = LauncherValidationService()
        output: list[str] = []

        with patch("scripts.validate_launcher_ui.time.sleep") as sleep:
            service.prepare(output.append, force_reinstall=True)

        self.assertTrue(service.force_reinstall_requested)
        self.assertEqual(output, ["Resolved application dependencies"])
        sleep.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
