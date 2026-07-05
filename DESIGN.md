# Design

## Direction

このツールのUIは、ゲームの世界観を再現する画面ではなく、ノベル画面を正確に切り出すための作業台にする。

採用する方向性は **midnight violet workbench**。黒い余白、紫の鋭い発光、硬い金属感を、スクリーンショット検査とOCR修正のための暗い作業環境として使う。ロゴ風の装飾やファンサイト的な演出にはしない。

## Visual Policy

- Screenshot first: 画面左のプレビューを主役にする。背景は黒に近い無彩色で、画像の端と選択範囲が読みやすいことを優先する。
- Dark control panel: 右側の操作パネルも黒紫に統一する。ただし本文・OCR結果・保存先の可読性を落とさないよう、面の明度差を十分に取る。
- Purple as structure: 紫は主操作、選択中、現在の作業状態、最終実行に使う。装飾ではなく状態の語彙として扱う。
- Layered dark surfaces: 背景、キャンバス、パネル、入力欄、行はそれぞれ少しずつ明度を変え、黒一色に潰さない。
- Compact desktop density: これはランディングページではなくWindows作業ツール。余白は控えめにし、ボタンと入力欄は見慣れた密度にする。

## Color Tokens

Conceptual tokens are OKLCH. Tkinter implementation values live in `megido_ui_theme.py` as hex because CustomTkinter expects Tk-compatible colors.

```css
:root {
  --bg: oklch(0.070 0.015 300);
  --surface: oklch(0.150 0.035 300);
  --surface-alt: oklch(0.200 0.050 300);
  --ink: oklch(0.960 0.020 300);
  --muted: oklch(0.780 0.045 300);
  --primary: oklch(0.560 0.200 300);
  --primary-hover: oklch(0.500 0.190 300);
  --accent: oklch(0.510 0.195 300);
  --accent-hover: oklch(0.450 0.180 300);
  --border: oklch(0.330 0.080 300);
  --canvas-bg: oklch(0.060 0.000 0);
  --canvas-panel: oklch(0.120 0.035 300);
}
```

## Typography

Use `Meiryo` for the desktop app. Japanese OCR workflows benefit from familiar Windows rendering more than expressive display type.

- Support text: 12px
- Controls: 13px
- Row labels and primary actions: 14px bold
- Panel titles: 16px bold
- Canvas labels: 11px bold

Do not use display fonts or fluid type in the application UI.

## Layout

Primary layout is two-pane:

- Left: screenshot canvas, toolbar, scrollbars, and status bar.
- Right: fixed-width workflow panel with segmented modes for range/column design, OCR review, and export.

The three modes are the product structure:

- 1. 範囲・列: create and edit OCR regions, name fields, order Excel columns, and load/save templates.
- 2. OCR確認: run OCR on the current image, compare raw/postprocessed text, and tune field-level processing.
- 3. Excel出力: choose source folder/output file, configure Excel writing, and batch export.

## Components

- Toolbar buttons are compact filled controls for global image navigation and OCR settings only.
- Segmented mode switch is the main workflow navigation.
- Field rows show enabled state, order, field name, and pixel size.
- Line-split OCR is a mode of a normal field, not a separate region type. Show it with a cyan field outline, a compact row badge, and light horizontal guides inside the existing rectangle.
- Canvas region editing prioritizes movement in the center of a rectangle and resizing only near the edges. Dragging a canvas label moves its field unless the pointer is on a resize edge/corner. The selected field is drawn and hit-tested in front of other fields; non-selected fields are visually muted, and their labels are hidden while a field is selected.
- Selecting a field should update existing row chrome and the active detail panel only. Avoid rebuilding the whole side panel or resizing the preview image for selection-only changes.
- OCR review rows pair a field label with an editable text result.
- Export panel keeps folder, output file, summary, and final action close together.
- Template load/save lives with range and column design, not in the global toolbar.
- OCR run actions live at the top of OCR確認 so they remain visible while field detail settings are edited.

## Implementation Notes

UI direction should be changed in these files first:

- `megido_ui_theme.py`: colors, fonts, dimensions, visible UI copy.
- `DESIGN.md`: rationale and product-level design rules.
- `PRODUCT.md`: audience, purpose, anti-references, and strategic principles.

Keep OCR behavior, template serialization, and Excel export independent from visual choices. Avoid adding new colors directly inside `megido_ocr_excel_app.py`; add a named token to `megido_ui_theme.py` instead.

## Motion

No decorative motion. State changes should be immediate. Future progress feedback should prefer status text and determinate counts over spinners.

## Sample Template

`.samples/megido_novel_template.json` is a coordinate starter for actual novel screenshots. Treat it as a placeholder: users should load a real screenshot, drag exact regions, and save a corrected template.
