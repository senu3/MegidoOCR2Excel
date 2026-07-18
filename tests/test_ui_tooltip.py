from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from megido_ocr_excel.ui.tooltip import UiTooltip, add_tooltip


class UiTooltipTests(unittest.TestCase):
    def _widget(self) -> MagicMock:
        widget = MagicMock()
        widget.after.return_value = "tooltip-job"
        widget.winfo_rootx.return_value = 100
        widget.winfo_rooty.return_value = 100
        widget.winfo_width.return_value = 32
        widget.winfo_height.return_value = 32
        widget.winfo_vrootx.return_value = 0
        widget.winfo_vrooty.return_value = 0
        widget.winfo_vrootwidth.return_value = 800
        widget.winfo_vrootheight.return_value = 600
        return widget

    def test_pointer_and_keyboard_use_expected_delays(self) -> None:
        widget = self._widget()
        tooltip = UiTooltip(widget, "基本設定")

        tooltip._schedule()
        widget.after.assert_called_with(500, tooltip.show)

        tooltip._show_from_focus()
        widget.after.assert_called_with(0, tooltip.show)

    def test_position_flips_above_near_the_bottom_edge(self) -> None:
        widget = self._widget()
        widget.winfo_rooty.return_value = 570
        tooltip = UiTooltip(widget, "次の画像")

        x, y = tooltip._position(100, 28)

        self.assertEqual(x, 66)
        self.assertEqual(y, 536)

    def test_add_tooltip_keeps_the_instance_with_the_widget(self) -> None:
        widget = self._widget()

        tooltip = add_tooltip(widget, "前の画像")

        self.assertIs(widget._ui_tooltip, tooltip)
        events = [call.args[0] for call in widget.bind.call_args_list]
        self.assertIn("<Enter>", events)
        self.assertIn("<FocusIn>", events)


if __name__ == "__main__":
    unittest.main()
