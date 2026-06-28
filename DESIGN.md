# Design

## Intent

Megido OCR to Excel is a task-first desktop utility. The visual direction comes from the supplied logo image: black negative space, sharp violet light, and metallic precision. The UI should feel like a quiet inspection bench for screenshots, not a fan page.

## Color

Use restrained product color. The application code currently uses Tk-compatible hex colors; conceptual tokens are expressed here in OKLCH for future UI work.

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

Use `Meiryo` for the current Windows desktop UI because Japanese OCR workflows benefit from familiar, dense system rendering. Keep type sizes fixed: 12px for support text, 13px for controls, 14px bold for row labels and primary actions, 16px bold for panel titles.

## Layout

Primary layout is two-pane:

- Left: screenshot canvas, toolbar, scrollbars, and status bar.
- Right: 390px workflow panel with segmented modes for template, review, and export.

The screenshot area remains dark so image edges and selection rectangles are visible. The side panel remains light for form readability and fatigue reduction.

## Components

- Toolbar buttons use compact filled controls.
- Segmented mode switch separates the three workflow phases.
- Field rows show enabled state, order, field name, and pixel size.
- OCR review rows pair field label with editable text result.
- Export panel keeps folder, output file, and summary close to the action.

## Motion

No decorative motion. State changes should be immediate. Future progress feedback should prefer status text and determinate counts over spinners.

## Sample Template

`.sample/megido_novel_template.json` is a coordinate starter for actual novel screenshots. Treat it as a placeholder: users should load a real screenshot, drag exact regions, and save a corrected template.
