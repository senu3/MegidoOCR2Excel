from megido_ocr_excel.ui.theme import THEME
from megido_ocr_excel.models import (LINE_JOIN_NONE, LINE_JOIN_FULLWIDTH_SPACE, LINE_JOIN_NEWLINE, EXPORT_LAYOUT_IMAGE_ROW, EXPORT_LAYOUT_SET)

UI_FONT_FAMILY = THEME.fonts.family
UI_FONT = THEME.fonts.normal
UI_FONT_SMALL = THEME.fonts.small
UI_FONT_BOLD = THEME.fonts.bold
UI_FONT_TITLE = THEME.fonts.title
UI_FONT_CANVAS = THEME.fonts.canvas

COLOR_BG = THEME.palette.app_bg
COLOR_SURFACE = THEME.palette.surface
COLOR_SURFACE_ALT = THEME.palette.surface_alt
COLOR_INPUT = THEME.palette.input_bg
COLOR_BORDER = THEME.palette.border
COLOR_TEXT = THEME.palette.text
COLOR_MUTED = THEME.palette.muted
COLOR_PRIMARY = THEME.palette.primary
COLOR_PRIMARY_HOVER = THEME.palette.primary_hover
COLOR_SECONDARY = THEME.palette.secondary
COLOR_SECONDARY_HOVER = THEME.palette.secondary_hover
COLOR_UTILITY_HOVER = THEME.palette.utility_hover
COLOR_DANGER = THEME.palette.danger
COLOR_DANGER_HOVER = THEME.palette.danger_hover
COLOR_CTA = THEME.palette.cta
COLOR_CTA_HOVER = THEME.palette.cta_hover
COLOR_CANVAS_BG = THEME.palette.canvas_bg
COLOR_CANVAS_PANEL = THEME.palette.canvas_panel
COLOR_CANVAS_TOOLBAR = THEME.palette.canvas_toolbar

OCR_MODE_OPTIONS = ["範囲全体", "行切り出し"]
LINE_JOIN_DISPLAY = {
    LINE_JOIN_NONE: "スペースなし",
    LINE_JOIN_FULLWIDTH_SPACE: "全角スペース",
    LINE_JOIN_NEWLINE: "改行",
}
EXPORT_LAYOUT_DISPLAY = {
    EXPORT_LAYOUT_IMAGE_ROW: "画像単位（1画像につき1行）",
    EXPORT_LAYOUT_SET: "セット単位（1セットにつき1行）",
}
EXPORT_LAYOUT_BY_DISPLAY = {
    display: value for value, display in EXPORT_LAYOUT_DISPLAY.items()
}
MODE_TEMPLATE = "1. 範囲・列"
MODE_REVIEW = "2. 認識テスト"
MODE_EXPORT = "3. Excel出力"


def native_font(widget, font=UI_FONT_SMALL):
    """Resolve a theme font to scaled Tk pixels for native controls in a CTk frame."""
    return widget._apply_font_scaling(font)
