from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from pathlib import Path

from megido_ocr_excel.launcher.core import (
    DEFAULT_PYTHON_VERSION,
    LauncherBusy,
    LauncherError,
    LauncherService,
    SingleInstanceLock,
    launcher_paths,
    load_state,
    project_signature,
    save_state,
)


class FakeRunner:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.commands: list[list[str]] = []
        self.cancelled = False
        self.fail_at = fail_at

    def reset_cancellation(self) -> None:
        self.cancelled = False

    def run(self, command, *, cwd, env, on_output=None) -> None:
        self.commands.append(list(command))
        if on_output is not None:
            on_output(f"fake command {len(self.commands)}")
        if self.fail_at == len(self.commands):
            raise LauncherError("fake failure")

    def cancel(self) -> None:
        self.cancelled = True


class LauncherCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()
        (self.root / "pyproject.toml").write_text("[project]\nname='test'\n")
        (self.root / "uv.lock").write_text("version = 1\n")
        (self.root / ".python-version").write_text("3.12\n")
        self.local_app_data = Path(self.temp_dir.name) / "local"
        self.paths = launcher_paths(
            self.root,
            environ={"LOCALAPPDATA": str(self.local_app_data)},
            home=Path(self.temp_dir.name) / "home",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _logger() -> logging.Logger:
        logger = logging.getLogger("test.launcher")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        return logger

    def _service(self, runner=None) -> LauncherService:
        return LauncherService(
            self.paths,
            environ={"PATH": ""},
            uv_path="C:/tools/uv.exe",
            logger=self._logger(),
            runner=runner,
        )

    def _add_runtime_python(self) -> None:
        self.paths.python_executable.parent.mkdir(parents=True, exist_ok=True)
        self.paths.python_executable.write_bytes(b"")

    def test_paths_use_user_local_app_data(self) -> None:
        self.assertEqual(
            self.paths.app_data_dir,
            self.local_app_data / "MegidoOCR2Excel",
        )
        self.assertEqual(
            self.paths.runtime_dir,
            self.local_app_data / "MegidoOCR2Excel" / "runtime" / "v1",
        )

    def test_project_signature_changes_with_locked_inputs(self) -> None:
        original = project_signature(self.root)
        (self.root / "uv.lock").write_text("version = 2\n")
        self.assertNotEqual(project_signature(self.root), original)

    def test_state_is_atomic_and_round_trips(self) -> None:
        signature = project_signature(self.root)
        save_state(self.paths.state_path, signature)

        state = load_state(self.paths.state_path)

        self.assertIsNotNone(state)
        self.assertEqual(state["project_signature"], signature)
        self.assertEqual(state["python_version"], DEFAULT_PYTHON_VERSION)
        self.assertEqual(list(self.paths.state_path.parent.glob("*.tmp")), [])

    def test_status_requires_setup_before_state_exists(self) -> None:
        status = self._service().status()

        self.assertFalse(status.ready)
        self.assertTrue(status.first_setup)
        self.assertIn("初回", status.reason)

    def test_status_is_ready_only_with_matching_state_and_runtime(self) -> None:
        self._add_runtime_python()
        save_state(self.paths.state_path, project_signature(self.root))

        status = self._service().status()

        self.assertTrue(status.ready)
        self.assertFalse(status.first_setup)

    def test_changed_lock_file_requires_update(self) -> None:
        self._add_runtime_python()
        save_state(self.paths.state_path, project_signature(self.root))
        (self.root / "uv.lock").write_text("version = 2\n")

        status = self._service().status()

        self.assertFalse(status.ready)
        self.assertFalse(status.first_setup)
        self.assertIn("更新", status.reason)

    def test_prepare_syncs_probes_then_marks_ready(self) -> None:
        runner = FakeRunner()
        service = self._service(runner)
        output: list[str] = []

        service.prepare(output.append)

        self.assertEqual(len(runner.commands), 2)
        self.assertEqual(runner.commands[0][1], "sync")
        self.assertEqual(runner.commands[1][1], "run")
        self.assertEqual(len(output), 2)
        state = load_state(self.paths.state_path)
        self.assertEqual(state["project_signature"], project_signature(self.root))

    def test_failed_probe_does_not_mark_environment_ready(self) -> None:
        runner = FakeRunner(fail_at=2)
        service = self._service(runner)

        with self.assertRaisesRegex(LauncherError, "fake failure"):
            service.prepare()

        self.assertFalse(self.paths.state_path.exists())

    def test_cancel_is_forwarded_to_running_command(self) -> None:
        runner = FakeRunner()
        service = self._service(runner)

        service.cancel()

        self.assertTrue(runner.cancelled)

    def test_commands_use_locked_user_environment(self) -> None:
        service = LauncherService(
            self.paths,
            environ={"PATH": "", "VIRTUAL_ENV": "C:/wrong-environment"},
            uv_path="C:/tools/uv.exe",
            logger=self._logger(),
            runner=FakeRunner(),
        )

        sync = service.sync_command()
        probe = service.probe_command()
        application = service.application_command()

        self.assertIn("--locked", sync)
        self.assertIn("--no-dev", sync)
        self.assertIn("--no-sync", probe)
        self.assertIn("--no-sync", application)
        self.assertEqual(
            service.environment()["UV_PROJECT_ENVIRONMENT"],
            str(self.paths.runtime_dir),
        )
        self.assertNotIn("VIRTUAL_ENV", service.environment())

    def test_missing_uv_is_actionable(self) -> None:
        service = LauncherService(
            self.paths,
            environ={"PATH": ""},
            logger=self._logger(),
            runner=FakeRunner(),
        )

        status = service.status()

        self.assertFalse(status.ready)
        self.assertIsNone(status.uv_path)
        with self.assertRaisesRegex(LauncherError, "uvが見つかりません"):
            service.sync_command()

    @unittest.skipUnless(os.name == "nt", "Windows file-lock behavior")
    def test_only_one_launcher_can_hold_the_lock(self) -> None:
        first = SingleInstanceLock(self.paths.lock_path)
        second = SingleInstanceLock(self.paths.lock_path)
        first.acquire()
        try:
            with self.assertRaises(LauncherBusy):
                second.acquire()
        finally:
            first.release()

    def test_state_file_is_plain_json_for_diagnostics(self) -> None:
        save_state(self.paths.state_path, project_signature(self.root))

        data = json.loads(self.paths.state_path.read_text(encoding="utf-8"))

        self.assertEqual(data["version"], 1)
        self.assertIn("completed_at", data)

    def test_cmd_bootstrap_is_ascii_safe_and_forwards_arguments(self) -> None:
        command_path = Path(__file__).resolve().parents[1] / "MegidoOCR2Excel.cmd"

        text = command_path.read_bytes().decode("ascii")

        self.assertIn("python launcher.py %*", text)
        self.assertNotIn("chcp", text.casefold())


if __name__ == "__main__":
    unittest.main()
