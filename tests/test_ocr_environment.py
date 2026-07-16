from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ocr_engine import OcrEngine
from ocr_environment import (
    OCR_ENV_LOCATION_ERROR,
    OCR_ENV_READY,
    OCR_ENV_SETUP,
    OCR_ENV_UNAVAILABLE,
    OCR_ENV_VERIFY,
    OcrEnvironmentManager,
)


class OcrEnvironmentManagerTests(unittest.TestCase):
    def _manager(
        self,
        root: Path,
        *,
        dependencies: bool = True,
    ) -> OcrEnvironmentManager:
        return OcrEnvironmentManager(
            settings_path=root / "settings.json",
            home=root / "home",
            environ={},
            dependency_checker=lambda _name: dependencies,
            version_provider=lambda name: {"paddleocr": "3.7", "paddlepaddle": "3.3"}[name],
        )

    @staticmethod
    def _add_model(cache_dir: Path) -> None:
        model = cache_dir / "official_models" / "japan_rec"
        model.mkdir(parents=True)
        (model / "inference.pdiparams").write_bytes(b"model")

    def test_missing_dependencies_require_reinstallation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._manager(Path(temp_dir), dependencies=False)

            self.assertEqual(manager.quick_status().state, OCR_ENV_UNAVAILABLE)

    def test_models_progress_from_setup_to_verify_to_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = self._manager(root)

            self.assertEqual(manager.quick_status().state, OCR_ENV_SETUP)
            self._add_model(manager.cache_dir)
            self.assertEqual(manager.quick_status().state, OCR_ENV_VERIFY)

            called = []
            status = manager.verify(lambda: called.append(True))

            self.assertEqual(called, [True])
            self.assertEqual(status.state, OCR_ENV_READY)
            saved = json.loads((root / "settings.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["ocr_verified_signature"])

    def test_failed_full_verification_does_not_mark_environment_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = self._manager(root)
            self._add_model(manager.cache_dir)

            with self.assertRaisesRegex(RuntimeError, "initialization failed"):
                manager.verify(
                    lambda: (_ for _ in ()).throw(
                        RuntimeError("initialization failed")
                    )
                )

            self.assertEqual(manager.quick_status().state, OCR_ENV_VERIFY)

    def test_custom_cache_is_machine_local_and_missing_path_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            custom = root / "models"
            custom.mkdir()
            environment = {}
            manager = OcrEnvironmentManager(
                settings_path=root / "settings.json",
                home=root / "home",
                environ=environment,
                dependency_checker=lambda _name: True,
                version_provider=lambda _name: "1",
            )

            manager.use_custom_cache(custom)

            self.assertEqual(manager.cache_dir, custom.resolve())
            self.assertEqual(environment["PADDLE_PDX_CACHE_HOME"], str(custom.resolve()))
            custom.rmdir()
            self.assertEqual(manager.quick_status().state, OCR_ENV_LOCATION_ERROR)

    def test_automatic_cache_clears_custom_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            custom = root / "models"
            custom.mkdir()
            manager = self._manager(root)
            manager.use_custom_cache(custom)

            manager.use_automatic_cache()

            self.assertEqual(manager.cache_dir, root / "home" / ".paddlex")
            self.assertEqual(manager.settings.cache_mode, "auto")


class OcrEnvironmentProbeTests(unittest.TestCase):
    def test_full_probe_initializes_normal_and_line_recognition_paths(self) -> None:
        backend = MagicMock()
        with patch("ocr_engine.PaddleBackend", return_value=backend):
            engine = OcrEngine()

            engine.verify_paddle_environment("jpn+eng")

        backend.recognize.assert_called_once()
        backend.recognize_lines.assert_called_once()
        self.assertIs(engine.paddle_backend, backend)


if __name__ == "__main__":
    unittest.main()
