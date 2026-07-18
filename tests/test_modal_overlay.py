from __future__ import annotations

import sys
import unittest

import customtkinter as ctk

from megido_ocr_excel.ui.modal import ModalOverlay


class ModalOverlayTests(unittest.TestCase):
    def test_geometry_supports_negative_monitor_coordinates(self) -> None:
        self.assertEqual(
            ModalOverlay._geometry(470, 260, -1920, 40),
            "470x260-1920+40",
        )

    def test_backdrop_alpha_is_clamped(self) -> None:
        root = ctk.CTk()
        root.withdraw()
        modal = ModalOverlay(
            root,
            width=320,
            backdrop_color="#050407",
            backdrop_alpha=1.5,
            surface_color="#121019",
            border_color="#352b43",
            corner_radius=8,
        )
        try:
            self.assertEqual(modal.backdrop_alpha, 1.0)
            self.assertAlmostEqual(float(modal.backdrop.attributes("-alpha")), 1.0)
        finally:
            modal.destroy()
            root.destroy()

    def test_show_covers_the_root_without_blocking_windows_title_bar(self) -> None:
        root = ctk.CTk()
        root.geometry("800x600+10000+10000")
        modal = ModalOverlay(
            root,
            width=360,
            backdrop_color="#050407",
            backdrop_alpha=0.66,
            surface_color="#121019",
            border_color="#352b43",
            corner_radius=8,
        )
        try:
            modal.show()
            root.update()
            self.assertEqual(modal.backdrop.state(), "normal")
            self.assertEqual(modal.window.state(), "normal")
            if sys.platform.startswith("win"):
                self.assertIsNone(root.grab_current())
            else:
                self.assertEqual(modal.window.grab_current(), modal.window)
            self.assertTrue(modal.backdrop.geometry().startswith("800x600"))

            modal.hide()
            self.assertEqual(modal.backdrop.state(), "withdrawn")
            self.assertEqual(modal.window.state(), "withdrawn")
        finally:
            modal.destroy()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
