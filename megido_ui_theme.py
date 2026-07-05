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
    app_bg: str = "#050409"
    surface: str = "#14101f"
    surface_alt: str = "#1d1730"
    border: str = "#3b2b5e"
    text: str = "#f5efff"
    muted: str = "#c3afd9"
    primary: str = "#8a3fe0"
    primary_hover: str = "#7830c6"
    secondary: str = "#2b223e"
    secondary_hover: str = "#392d54"
    danger: str = "#d64a65"
    danger_hover: str = "#b63a52"
    cta: str = "#7a31c8"
    cta_hover: str = "#6b27b4"
    canvas_bg: str = "#050506"
    canvas_panel: str = "#100b19"
    canvas_toolbar: str = "#09060f"
    canvas_border: str = "#4a2c75"
    toolbar_divider: str = "#432d63"
    toolbar_text: str = "#f5efff"
    toolbar_muted: str = "#cdb9e8"
    toolbar_button: str = "#211936"
    toolbar_button_hover: str = "#32264e"
    segmented_bg: str = "#241b36"
    segmented_hover: str = "#302348"
    selected_row: str = "#26173d"
    disabled_fill: str = "#726184"
    enabled_region: str = "#c08cff"
    inactive_region: str = "#7f5ca6"
    line_region: str = "#3fd7e8"
    line_region_selected: str = "#6af5ff"
    inactive_line_region: str = "#2e7f8c"
    line_guide: str = "#8ff8ff"
    line_badge: str = "#145467"
    empty_title: str = "#eadfff"
    empty_note: str = "#bda8d9"
    modal_button_hover: str = "#251c38"
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
    initial_status: str = "ノベル画面の画像フォルダを選び、先頭画像で読み取りたい範囲をドラッグしてください。"
    empty_canvas_title: str = "画像フォルダを選択してください"
    empty_canvas_note: str = "フォルダ内の先頭画像を基準に、読み取りたい場所をドラッグして項目名を付けます。"
    default_template_name: str = "megido-novel-template.json"


@dataclass(frozen=True)
class UiTheme:
    fonts: Fonts = Fonts()
    palette: Palette = Palette()
    layout: Layout = Layout()
    copy: Copy = Copy()


THEME = UiTheme()
