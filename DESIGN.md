# Design

## Direction

このツールのUIは、ゲームの世界観を再現する画面ではなく、ノベル画面を正確に切り出すための作業台にする。

採用する方向性は **midnight violet workbench**。黒い余白、紫の鋭い発光、硬い金属感を、スクリーンショット検査と認識設定の検証に集中する暗い作業環境として使う。ロゴ風の装飾やファンサイト的な演出にはしない。

## Visual Policy

- Screenshot first: 画面左のプレビューを主役にする。背景は黒に近い無彩色で、画像の端と選択範囲が読みやすいことを優先する。
- Content-relative coordinates: 黒余白を除いたゲーム画面領域を検出し、その領域を基準にCanvas表示とOCR範囲を変換する。検出状態は認識テストに短く表示する。
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

Use `Yu Gothic UI` with `Meiryo` as the Windows fallback. Japanese OCR workflows benefit from familiar system rendering more than expressive display type.

- Support text: 12px
- Controls: 13px
- Row labels and primary actions: 14px bold
- Panel titles: 16px bold
- Canvas labels: 11px bold

Do not use display fonts or fluid type in the application UI.

## Layout

Primary layout is two-pane:

- Left: screenshot canvas, toolbar, scrollbars, and status bar.
- Right: fixed-width workflow panel with segmented modes for range/column design, recognition testing, and export.

The three modes are the product structure:

- 1. 範囲・列: create and edit OCR regions, name fields, order Excel columns or dialogue-pair order, and load/save templates.
- 2. 認識テスト: use representative images to inspect the selected crop and full OCR result, then tune the OCR mode before batch export. This is a preflight test; Excel export runs OCR again for every target image.
- 3. Excel出力: review the naturally sorted image queue, exclude non-target captures, choose the output file/settings, and batch export.

## Components

- Toolbar buttons are compact controls for global image navigation and OCR settings only. Only `画像を開く` uses the primary fill; navigation and settings use neutral icon buttons.
- Segmented mode switch is the main workflow navigation.
- Tabs carry the section label; do not repeat tab headings or explanatory text inside the tab body.
- Tab changes build the next side-panel surface offscreen and swap it in atomically. They do not clear the visible panel first or redraw the unchanged screenshot Canvas.
- Persistent path displays should use compact names, not full filesystem paths. Keep full paths for dialogs and transient status messages only.
- Use icon-plus-short-label buttons for frequent actions, and icon-only buttons for compact global controls when the icon is familiar. Icons come from the local monochrome outline system in `megido_icons.py`: 1.75px-equivalent stroke, gently rounded joins, 16/18/20px sizes, and no emoji or Unicode-symbol mixing.
- Buttons use three roles: purple Primary for one main action per surface, bordered dark Secondary for supporting actions, and neutral icon-only controls for navigation. Standard controls are 32–34px high with 6px corners; final actions are 40px high.
- Queue status combines a monochrome state icon, semantic color, and a text label. Color is never the only status channel.
- Field rows show enabled state, order, field name, and pixel size.
- Field-name editing is never dependent on hidden gestures. Every row shows a pencil action and an overflow menu; double-click, right-click, and F2 remain accelerators. Newly drawn ordinary fields enter inline name editing immediately.
- Inline naming uses Enter to commit and Esc to restore the previous name. Duplicate names stay in edit mode with a local error instead of being silently renamed. The overflow menu exposes select, duplicate, and undoable delete actions.
- Dialogue-pair export is a template/output mode, not a positional convention. Every field stores an explicit `pair_id` and `dialogue_role`; Excel groups by pair ID and folds each complete pair into `ログ順 / 話者 / セリフ` rows. Field names and raw list order never determine meaning.
- Range design groups fields under `会話 n`, exposes role/pair assignment inline, and reorders the whole pair with one action. Adding a pair guides the user through speaker range and then dialogue range on the Canvas.
- In dialogue-pair mode, Canvas shows an amber pair outline and a compact numeric handle for each complete enabled pair. Inner field rectangles stay hidden by default to avoid double outlines; selecting an individual field shows only that field's rectangle for precise move/resize. Dragging the pair handle moves both regions together.
- Line-split OCR is a mode of a normal field, not a separate region type. Show it with a cyan field outline, a compact row badge, and light horizontal guides inside the existing rectangle.
- Line-split text formatting is one shared basic setting, not a per-field control. Templates store the line join mode (none, full-width space, or newline) and whether ASCII letters, digits, spaces, and punctuation are normalized to full-width forms. Recognition tests and Excel export use the same formatting path; multiline Excel cells enable wrapping and receive a readable row height.
- Canvas region editing prioritizes movement in the center of a rectangle and resizing only near the edges. Dragging a canvas label moves its field unless the pointer is on a resize edge/corner. The selected field is drawn and hit-tested in front of other fields; non-selected fields are visually muted, and their labels are hidden while a field is selected.
- Selecting a field should update existing row chrome and the active detail panel only. Avoid rebuilding the whole side panel or resizing the preview image for selection-only changes.
- Recognition-test rows are selection controls. The detail panel shows the selected crop, the full processed result, raw OCR when it differs, and the OCR mode.
- Recognition testing is sample-based rather than a per-image correction queue. Users switch representative images with the global previous/next controls and can test either one field or every enabled field.
- Recognition testing reports whether content-relative coordinate correction is active or whether the app fell back to full-image scaling.
- Empty OCR output is a batch warning and is written to the Errors sheet even when the OCR backend itself did not raise an error.
- Correction-rule UI is currently hidden because per-image editing is outside the batch-first workflow. Keep the underlying `CorrectionRule` model, template serialization, and OCR application path as future foundation for a bulk-correction workflow.
- Export panel keeps folder, output file, queue, summary, and final action close together. Queue rows use explicit text states (`待機 / 処理中 / 完了 / 要再実行 / 除外`) so status never depends on color alone.
- Failed-image retry overwrites the exact row range reserved by the preceding export. It is session-scoped and disabled when the output path or structural Excel settings no longer match.
- Unsaved template state is visible as `*` in both the window title and template filename. Loading another template or closing offers save, discard, and cancel. During OCR/export, a subdued close icon in the progress panel offers cooperative cancellation after confirmation; closing the app uses the same safe cancellation path before continuing to the unsaved-changes check.
- Template and Excel writes use same-directory temporary files followed by atomic replacement so a failed save does not damage the previous file.
- The app receives an `OcrProfile`; game identity, OCR defaults, coordinate defaults, and field-name preset matching stay outside the UI and OCR engine.
- Release templates use schema version 1 and are validated at the file boundary. Format, version, required structure, and profile ID must match; prerelease legacy formats are intentionally rejected instead of guessed or silently normalized.
- Template load/save lives with range and column design, not in the global toolbar.
- OCR run actions live at the bottom of the selected field detail panel, close to the raw OCR preview and OCR mode.

## Implementation Notes

UI direction should be changed in these files first:

- `megido_ui_theme.py`: colors, fonts, dimensions, visible UI copy.
- `megido_icons.py`: the local, dependency-free outline icon renderer and icon cache.
- `profiles/base.py`: profile interface shared by every game.
- `profiles/<game>.py`: game-specific defaults and field preset rules.
- `DESIGN.md`: rationale and product-level design rules.
- `PRODUCT.md`: audience, purpose, anti-references, and strategic principles.

Keep OCR behavior, template serialization, and Excel export independent from visual choices. Avoid adding new colors directly inside `megido_ocr_excel_app.py`; add a named token to `megido_ui_theme.py` instead.

## Motion

No decorative motion. State changes should be immediate. Future progress feedback should prefer status text and determinate counts over spinners.

## Sample Template

`.samples/megido_novel_template.json` is a coordinate starter for actual novel screenshots. Treat it as a placeholder: users should load a real screenshot, drag exact regions, and save a corrected template.
