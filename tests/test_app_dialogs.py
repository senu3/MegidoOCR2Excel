from __future__ import annotations

import unittest

import customtkinter as ctk

from app_dialogs import AppDialogs
from megido_ui_theme import THEME


class AppDialogsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ctk.CTk()
        self.root.geometry("760x520+10000+10000")
        self.root.update()
        self.dialogs = AppDialogs(self.root)

    def tearDown(self) -> None:
        if self.dialogs.active_modal is not None:
            self.dialogs.active_modal.destroy()
        self.root.destroy()

    def _send(self, sequence: str) -> None:
        modal = self.dialogs.active_modal
        self.assertIsNotNone(modal)
        modal.window.event_generate(sequence, when="tail")

    def test_enter_accepts_the_default_action(self) -> None:
        self.root.after(100, lambda: self._send("<Return>"))

        accepted = self.dialogs.askyesno("確認", "この操作を続行しますか。")

        self.assertTrue(accepted)
        self.assertIsNone(self.dialogs.active_modal)

    def test_escape_returns_the_non_destructive_result(self) -> None:
        self.root.after(100, lambda: self._send("<Escape>"))

        accepted = self.dialogs.askyesno(
            "削除確認",
            "この項目を削除しますか。",
            destructive=True,
        )

        self.assertFalse(accepted)

    def test_enter_defaults_to_cancel_for_a_destructive_action(self) -> None:
        self.root.after(100, lambda: self._send("<Return>"))

        accepted = self.dialogs.askyesno(
            "削除確認",
            "この項目を削除しますか。",
            destructive=True,
        )

        self.assertFalse(accepted)

    def test_enter_invokes_the_focused_action_instead_of_the_default(self) -> None:
        self.root.after(100, lambda: self._send("<Tab>"))
        self.root.after(160, lambda: self._send("<Return>"))

        accepted = self.dialogs.askyesno(
            "削除確認",
            "この項目を削除しますか。",
            destructive=True,
        )

        self.assertTrue(accepted)

    def test_dialog_kinds_use_semantic_theme_colors(self) -> None:
        self.assertEqual(
            AppDialogs._appearance("error"),
            ("alert_circle", THEME.palette.danger),
        )
        self.assertEqual(
            AppDialogs._appearance("warning"),
            ("alert_circle", THEME.palette.warning),
        )
        self.assertEqual(
            AppDialogs._appearance("info"),
            ("check_circle", THEME.palette.info),
        )


if __name__ == "__main__":
    unittest.main()
