# Design

## Direction

このツールのUIは、ゲームの世界観を再現する画面ではなく、ノベル画面を正確に切り出すための作業台にする。

採用する方向性は **midnight inspection bench**。黒い余白、紫の鋭い発光、硬い金属感を「スクリーンショット検査のための暗い作業面」として借りる。ロゴ風の装飾やファンサイト的な演出にはしない。

## Visual Policy

- Screenshot first: 画面左のプレビューを主役にする。背景は黒に近い無彩色で、画像の端と選択範囲が読みやすいことを優先する。
- Light control panel: 右側の操作パネルは白系にして、項目名・OCR結果・保存先の確認を長時間読めるようにする。
- Purple as active state: 紫は主操作、選択中、現在の作業状態に限定する。装飾用には使わない。
- Olive as completion action: Excel出力のような最後の実行操作だけに黄緑/オリーブを使う。
- Compact desktop density: これはランディングページではなくWindows作業ツール。余白は控えめにし、ボタンと入力欄は見慣れた密度にする。

## Color Tokens

Conceptual tokens are OKLCH. Tkinter implementation values live in `megido_ui_theme.py` as hex because CustomTkinter expects Tk-compatible colors.

```css
:root {
  --bg: oklch(0.120 0.000 0);
  --surface: oklch(1.000 0.000 0);
  --surface-alt: oklch(0.975 0.006 300);
  --ink: oklch(0.220 0.030 300);
  --muted: oklch(0.480 0.030 300);
  --primary: oklch(0.520 0.180 300);
  --primary-hover: oklch(0.450 0.180 300);
  --accent: oklch(0.520 0.110 110);
  --accent-hover: oklch(0.450 0.110 110);
  --border: oklch(0.875 0.025 300);
  --canvas-bg: oklch(0.060 0.000 0);
  --canvas-panel: oklch(0.150 0.035 300);
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
- Right: fixed-width workflow panel with segmented modes for template, review, and export.

The three modes are the product structure:

- Template: create and edit OCR regions.
- Review: run OCR on the current image and correct results.
- Export: choose source folder/output file and batch export.

## Components

- Toolbar buttons are compact filled controls.
- Segmented mode switch is the main workflow navigation.
- Field rows show enabled state, order, field name, and pixel size.
- OCR review rows pair a field label with an editable text result.
- Export panel keeps folder, output file, summary, and final action close together.

## Implementation Notes

UI direction should be changed in these files first:

- `megido_ui_theme.py`: colors, fonts, dimensions, visible UI copy.
- `DESIGN.md`: rationale and product-level design rules.
- `PRODUCT.md`: audience, purpose, anti-references, and strategic principles.

Keep OCR behavior, template serialization, and Excel export independent from visual choices. Avoid adding new colors directly inside `megido_ocr_excel_app.py`; add a named token to `megido_ui_theme.py` instead.

## Motion

No decorative motion. State changes should be immediate. Future progress feedback should prefer status text and determinate counts over spinners.

## Sample Template

`.sample/megido_novel_template.json` is a coordinate starter for actual novel screenshots. Treat it as a placeholder: users should load a real screenshot, drag exact regions, and save a corrected template.
