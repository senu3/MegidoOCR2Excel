from __future__ import annotations

import unittest

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


class OcrSetupUiValidationTests(unittest.TestCase):
    def test_each_validation_state_maps_to_an_ocr_environment_state(self) -> None:
        expected = {
            "setup": OCR_ENV_SETUP,
            "checking": OCR_ENV_VERIFY,
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


if __name__ == "__main__":
    unittest.main()
