from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from megido_icons import _DRAWERS


class IconDrawingTests(unittest.TestCase):
    @staticmethod
    def _render(name: str, scale: int = 4) -> Image.Image:
        image = Image.new("RGBA", (18 * scale, 18 * scale), (0, 0, 0, 0))
        _DRAWERS[name](ImageDraw.Draw(image), 18 * scale, scale)
        return image

    def test_every_registered_icon_draws_visible_pixels(self) -> None:
        for name in _DRAWERS:
            with self.subTest(name=name):
                self.assertIsNotNone(self._render(name).getbbox())

    def test_scan_rows_are_not_joined_by_a_diagonal(self) -> None:
        image = self._render("scan")

        self.assertEqual(image.getpixel((36, 34))[3], 0)

    def test_table_rows_are_not_joined_by_a_diagonal(self) -> None:
        image = self._render("table")

        self.assertEqual(image.getpixel((36, 36))[3], 0)

    def test_refresh_arrows_connect_to_opposite_arc_ends(self) -> None:
        image = self._render("refresh")

        for point in ((12, 32), (28, 32), (44, 40), (60, 56)):
            with self.subTest(point=point):
                self.assertGreater(image.getpixel(point)[3], 0)


if __name__ == "__main__":
    unittest.main()
