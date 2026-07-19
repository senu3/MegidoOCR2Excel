# 開発ドキュメント

## 環境構築と起動

現在は `uv` でPython環境と依存関係を管理します。

```powershell
uv sync
uv run python main.py
```

Windowsでは `run_app.ps1` からも起動できます。

## UI検証モード（一時）

OCRモデルや端末設定を変更せず、OCR準備画面の状態を固定して確認できます。

```powershell
uv run python scripts/validate_ocr_setup_ui.py --state setup
```

`--state` には次を指定できます。

- `setup`: 認識モデルの準備が必要
- `checking`: 起動時の自動確認中
- `check-failed`: 自動確認の失敗
- `location-error`: モデル保存先のエラー
- `unavailable`: PaddleOCRの依存ファイル不足
- `ready`: 準備済み

`--screenshot` を指定すると、表示状態を画像へ保存して終了します。

```powershell
uv run python scripts/validate_ocr_setup_ui.py --state checking --screenshot C:\tmp\ocr-checking.png
```

## OCR準備状態

OCR環境マネージャーは、依存パッケージ、モデル保存先、モデルファイル、PaddleOCR・PaddlePaddleのバージョンを確認します。

「OCRを準備する」は通常認識と行分割認識を実際に初期化し、不足モデルを取得します。成功時は保存先とパッケージバージョンから確認署名を保存します。保存先やパッケージが変わると、次回起動時に再確認します。

## プロファイル

ゲーム固有設定は共通の `OcrProfile` から分離しています。現在の設定は `megido_ocr_excel/profiles/megido_novel.py` にあります。

別ゲームへ対応する場合は、次を定義します。

- ID、表示名、アプリ名
- 既定OCRバックエンドと言語
- 座標変換の既定値
- 項目名の接頭辞と項目別OCRプリセット
- `megido_ocr_excel/profiles/__init__.py` のレジストリ登録
- `megido_ocr_excel/config.py` の有効プロファイル指定

プロファイルには検証用サンプルのパスを含めません。共有しないサンプルは精度測定スクリプトの引数で指定します。

## テンプレート形式

正式形式は `format: image-ocr-to-excel-template`, `version: 1` です。読み込み時に形式、バージョン、必須項目、`profile_id` を検証します。

セット出力は項目の表示順ではなく、テンプレートの `set_id`、`slot_key`、セット定義でExcel列を対応付けます。

開発中の旧形式や旧キー名に対する互換読み込みは行いません。今後変更する場合はバージョンを更新し、必要になった時点で移行処理を設計します。

自動検出の基準範囲とOCRプリセットはプロファイルで管理します。検証用テンプレートは使用しません。特殊な会話・カード形式のサンプルは自動検出ではなく、新規テンプレートで検証します。

## 主な構成

- `main.py`: 起動と配布ビルドのスモークテスト入口
- `megido_ocr_excel/application.py`: CustomTkinter UIと画面遷移
- `megido_ocr_excel/diagnostics.py`: 診断ログ、ローテーション、未処理例外の捕捉
- `megido_ocr_excel/ui/`: テーマ、アイコン、ダイアログ、ツールチップ
- `megido_ocr_excel/ocr/`: OCR実行、画像処理、準備状態、会話検出
- `megido_ocr_excel/export/`: Excel出力と画像キュー
- `megido_ocr_excel/profiles/`: ゲーム固有設定と共通プロファイル
- `megido_ocr_excel/models.py`: テンプレート項目モデル
- `megido_ocr_excel/templates.py`: テンプレートの保存・読み込み
- `megido_ocr_excel/persistence.py`: アトミック保存

## OCR精度測定

`.samples` の画像と同名CSVを正解データとして比較します。アプリと同じ自動検出、黒余白補正、補正ルール、テキスト整形を使用します。

```powershell
uv run python scripts/measure_speaker_ocr.py
uv run python scripts/measure_dialogue_ocr.py
```

調整例:

```powershell
uv run python scripts/measure_speaker_ocr.py --preprocess white-glyph --scale 4 --threshold 190 --psm 6 --lang jpn
uv run python scripts/measure_dialogue_ocr.py --preprocess threshold --scale 3 --threshold 140 --psm 6 --lang jpn --csv-out C:\tmp\dialogue-ocr.csv
uv run python scripts/measure_dialogue_ocr.py --line-split detected --preprocess threshold --scale 3 --threshold 140 --psm 6 --lang jpn
uv run python scripts/measure_dialogue_ocr.py --line-split none
```
