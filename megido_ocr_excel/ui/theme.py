from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fonts:
    family: str = "Yu Gothic UI"
    launcher_log: tuple[str, int] = ("Consolas", 9)

    @property
    def normal(self) -> tuple[str, int]:
        return self.family, 13

    @property
    def small(self) -> tuple[str, int]:
        return self.family, 12

    @property
    def bold(self) -> tuple[str, int, str]:
        return self.family, 14, "bold"

    @property
    def title(self) -> tuple[str, int, str]:
        return self.family, 16, "bold"

    @property
    def canvas(self) -> tuple[str, int, str]:
        return self.family, 11, "bold"

    @property
    def native_body(self) -> tuple[str, int]:
        return self.family, 10

    @property
    def launcher_primary(self) -> tuple[str, int, str]:
        return self.family, 10, "bold"



@dataclass(frozen=True)
class Palette:
    app_bg: str = "#07060a"
    surface: str = "#121019"
    surface_alt: str = "#191523"
    input_bg: str = "#0d0b12"
    border: str = "#352b43"
    border_subtle: str = "#27212f"
    text: str = "#f3eff8"
    muted: str = "#bfb4cb"
    primary: str = "#8b49df"
    primary_hover: str = "#9250e3"
    primary_pressed: str = "#7f43ce"
    secondary: str = "#211c2b"
    secondary_hover: str = "#2d2639"
    danger: str = "#df6176"
    danger_hover: str = "#c94e64"
    success: str = "#59c98c"
    info: str = "#62c6e8"
    warning: str = "#e5b85c"
    cta: str = "#8b49df"
    cta_hover: str = "#9250e3"
    canvas_bg: str = "#030304"
    canvas_panel: str = "#0b0910"
    canvas_toolbar: str = "#0d0b12"
    canvas_border: str = "#27212f"
    toolbar_divider: str = "#2b2435"
    toolbar_text: str = "#f3eff8"
    toolbar_muted: str = "#bfb4cb"
    utility_hover: str = "#282132"
    segmented_bg: str = "#18141f"
    segmented_hover: str = "#282132"
    selected_row: str = "#241936"
    dragging_row: str = "#302047"
    dragging_border: str = "#b77af5"
    disabled_fill: str = "#5f566a"
    enabled_region: str = "#b77af5"
    inactive_region: str = "#6f5a86"
    line_region: str = "#3fd7e8"
    line_region_selected: str = "#6af5ff"
    inactive_line_region: str = "#2e7f8c"
    line_guide: str = "#8ff8ff"
    line_badge: str = "#145467"
    set_outline: str = "#8a769f"
    set_outline_selected: str = "#b77af5"
    set_handle: str = "#6b3aa3"
    set_handle_hover: str = "#7d45c2"
    empty_title: str = "#f3eff8"
    empty_note: str = "#bfb4cb"
    modal_backdrop: str = "#050407"
    modal_button_hover: str = "#282132"
    on_color: str = "#ffffff"


@dataclass(frozen=True)
class Layout:
    window_size: str = "1220x800"
    min_window_size: tuple[int, int] = (1040, 680)
    side_panel_width: int = 390
    panel_radius: int = 8
    control_radius: int = 6
    button_height: int = 32
    row_button_height: int = 34
    entry_height: int = 32
    primary_button_height: int = 38
    export_button_height: int = 40
    toolbar_height: int = 54
    status_bar_height: int = 34
    settings_size: str = "440x500"
    modal_backdrop_alpha: float = 0.66


@dataclass(frozen=True)
class Copy:
    initial_status: str = "開始方法を選び、画像フォルダを選択してください。"
    saved_template_hint: str = (
        "保存済みテンプレートは右上のメニューから読み込めます。"
    )
    new_template_label: str = "新規テンプレート（未保存）"


@dataclass(frozen=True)
class UiTheme:
    fonts: Fonts = Fonts()
    palette: Palette = Palette()
    layout: Layout = Layout()
    copy: Copy = Copy()


THEME = UiTheme()
