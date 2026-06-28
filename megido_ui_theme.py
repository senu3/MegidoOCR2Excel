from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fonts:
    family: str = "Meiryo"
    normal: tuple[str, int] = ("Meiryo", 13)
    small: tuple[str, int] = ("Meiryo", 12)
    bold: tuple[str, int, str] = ("Meiryo", 14, "bold")
    title: tuple[str, int, str] = ("Meiryo", 16, "bold")
    canvas: tuple[str, int, str] = ("Meiryo", 11, "bold")


@dataclass(frozen=True)
class Palette:
    app_bg: str = "#101015"
    surface: str = "#ffffff"
    surface_alt: str = "#f7f7fb"
    border: str = "#d7d4e8"
    text: str = "#20182f"
    muted: str = "#655d76"
    primary: str = "#7b1fc7"
    primary_hover: str = "#6515a8"
    secondary: str = "#2d2740"
    secondary_hover: str = "#1c172c"
    danger: str = "#dc2626"
    danger_hover: str = "#b91c1c"
    cta: str = "#6d7b18"
    cta_hover: str = "#596612"
    canvas_bg: str = "#050506"
    canvas_panel: str = "#14111f"
    canvas_toolbar: str = "#0b0911"
    canvas_border: str = "#34224f"
    toolbar_divider: str = "#403158"
    toolbar_text: str = "#efe7ff"
    toolbar_muted: str = "#d8c9ef"
    toolbar_button: str = "#252033"
    toolbar_button_hover: str = "#382c52"
    segmented_bg: str = "#e2e8f0"
    segmented_hover: str = "#cbd5e1"
    selected_row: str = "#f4efff"
    disabled_fill: str = "#94a3b8"
    enabled_region: str = "#2dd4bf"
    empty_title: str = "#cbd5e1"
    empty_note: str = "#94a3b8"
    modal_button_hover: str = "#e2e8f0"
    on_color: str = "#ffffff"


@dataclass(frozen=True)
class Layout:
    window_size: str = "1220x800"
    min_window_size: tuple[int, int] = (1040, 680)
    side_panel_width: int = 390
    panel_radius: int = 8
    button_height: int = 30
    row_button_height: int = 34
    entry_height: int = 32
    primary_button_height: int = 36
    export_button_height: int = 42
    toolbar_height: int = 50
    status_bar_height: int = 34
    settings_size: str = "420x300"


@dataclass(frozen=True)
class Copy:
    header: str = "ノベル画面をExcel化"
    initial_status: str = "ノベル画面のスクリーンショットを開き、読み取りたいセリフ範囲をドラッグしてください。"
    empty_canvas_title: str = "サンプル画像を開いてください"
    empty_canvas_note: str = "テンプレート作成では、読み取りたい場所をドラッグして項目名を付けます。"
    default_template_name: str = "megido-novel-template.json"


@dataclass(frozen=True)
class UiTheme:
    fonts: Fonts = Fonts()
    palette: Palette = Palette()
    layout: Layout = Layout()
    copy: Copy = Copy()


THEME = UiTheme()

