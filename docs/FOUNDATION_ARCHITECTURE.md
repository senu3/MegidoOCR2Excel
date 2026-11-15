# Python基盤とアプリ固有層

## Processing and editing boundaries (2026-11-15)

- `ocr/text.py` owns the text pipeline: formatting, correction rules, then
  postprocessing. Recognition retains the original line breaks. Preview refreshes
  and exports must call the same pipeline rather than reimplementing its stages.
- `export/rows.py` owns image recognition, set resolution, format-neutral rows,
  errors and notices. CSV does not depend on the Excel writer.
- `export/job.py` snapshots request settings and emits start, image-complete,
  saving and completion events. Excel, CSV and retries use the same execution
  path. It does not read Tk variables or update widgets.
- `export/session.py` owns output fingerprints, structural compatibility and
  image-level retry planning. Each image retains its rows, including an empty
  list on detection failure. Retrying replaces those results and recalculates
  subsequent row offsets; it does not rerun successful images.
- Writers own file-format behavior. Excel writes recognized values as strings,
  validates worksheet bounds and creates uniquely named report sheets. A retry
  removes only report sheets recorded by that export session. Append preserves
  pre-existing report sheets and column widths.
- Output fingerprints are checked both before retry and immediately before
  atomic replacement. Cancellation is also checked after serialization. External
  edits cause a refusal, not a merge based on stale row numbers. Retry metadata
  is currently session-local, as is the existing retry UI; restarting the app
  requires a fresh export.
- Excel retries rewrite only the current batch's output rectangle. Adjacent
  columns and earlier appended batches remain intact. Growth into occupied
  cells is rejected rather than shifting unrelated workbook data or formulas.
- `editing.py` owns field entries, stable session IDs, selection and raw/formatted
  results together. Result values are views of entries, not parallel arrays.
  Add, delete, reorder and undo use this state. IDs are not written into v1
  templates. Background recognition resolves IDs again before applying results.
- `ui/template_view.py`, `ui/review_view.py` and `ui/export_view.py` compose the
  three workflow screens. The application still owns UI event handlers and the
  canvas; the split is intentionally not a new generic UI framework. Recognition
  result updates retain review widgets, and structural rebuilds preserve list
  scroll positions.

Regression coverage lives in `test_processing_foundation.py`,
`test_export_safety.py` and `test_editing.py`, alongside the existing workflow,
GUI, cancellation and private-sample tests. Real-model accuracy measurements are
separate from those tests. Two speaker and two dialogue samples matched exactly
after this refactor; this small smoke check is not a full accuracy benchmark.

この文書は開発者向けです。利用方法は `README.md` と
`docs/USER_GUIDE.md` に集約します。

## 境界

### 共通基盤

- `models.py`
  - 任意の `SetDefinition`、テンプレート項目、座標・文字整形設定
  - `set_id` / `slot_key` だけをセットの標準語彙として扱う
- `application.py`
  - OCR範囲編集、認識テスト、Excel・CSV出力の共通UI
  - 起動時に `OcrProfile` と `ApplicationConfig` を必須で受け取る
- `export/`
  - `SetDefinition` に従った表形式出力
  - 自動検出を使う場合も、`SetResolution` へ変換してから受け取る
- `ui/theme.py`
  - 色、寸法、フォント、アプリを問わない操作文だけを保持する

### 定義例

`set_definitions.py` の `conversation` と `heading_text` は、共通基盤の
固定仕様ではなく `SetDefinition` の同梱例です。Megidoプロファイルは
この2例を採用しています。別アプリは独自のキー、列数、追加行を持つ
定義へ差し替えられます。

### OCRプロファイル

`profiles/` は対象画像に依存する次の情報を持ちます。

- OCR既定値と項目別プリセット
- 座標系と文字補正
- 利用可能なセット定義と既定セット
- 自動検出用の初期項目と検出ストラテジー

Megidoの会話検出規則と画像補正は `profiles/megido_novel.py` および
`ocr/dialogue_detector.py` に閉じています。

### アプリ設定とエントリポイント

`apps/megido.py` が次を組み合わせます。

- `get_profile("megido_novel")`
- ウィンドウ名、AppDataフォルダー名、既定テンプレート名
- 開始方法や自動検出結果などのアプリ固有コピー
- アプリ本体とランチャーの起動

このため、共通の `config.py` や `application.py` は特定プロファイルを
暗黙選択しません。

## 別アプリを追加する手順

1. `profiles/` に対象画像用の `OcrProfile` を追加する。
2. 必要なら独自の `SetDefinition` と自動検出ストラテジーを追加する。
3. `apps/<app_name>.py` で `ApplicationConfig` とプロファイルを組み合わせる。
4. `main.py`、`launcher.py`、コンソールスクリプトをそのエントリポイントへ向ける。
5. 配布名、README、AppData名、リリーススクリプトを新アプリ用に設定する。

## 互換性

- 公開済みテンプレートの `set_id` / `slot_key` とテンプレートversion 1は維持する。
- version 1の `conversation` 定義に追加スロット情報がない場合は、同梱例を
  読み込み時の補完値として使う。
- Python内部だけで使われていた `pair_id`、`dialogue_role`、
  `dialogue_pair_resolver` は廃止する。
- ランチャー・ログ・OCR設定の既定AppData名は既存テストとの互換用であり、
  実アプリのエントリポイントは必ず `ApplicationConfig` の名前を渡す。
