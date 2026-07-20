# 開発ドキュメント

## 環境構築と起動

現在は `uv` でPython環境と依存関係を管理します。

```powershell
uv sync
uv run python main.py
```

Windowsでは `MegidoOCR2Excel.cmd` または `run_app.ps1` から専用ランチャーを起動できます。

```powershell
.\MegidoOCR2Excel.cmd --repair
.\run_app.ps1 --repair
```

`--repair` は通常の同期と異なり `uv sync --reinstall` を実行し、依存パッケージを入れ直してから非モデル取得型のプローブを実行します。アプリ内の「ランチャーで修復」は、現在の実行環境に依存しないuvブートストラップでこの処理へ引き渡します。

### ランチャーの実行環境

ユーザーにはuvの事前導入を求めます。ランチャー自体は `uv run --no-project --python 3.12` で起動し、アプリ用環境はアプリデータ配下の `runtime/v1` で管理します。プロジェクト直下の仮想環境は使用しません。

`pyproject.toml`、`uv.lock`、`.python-version` の内容が変わると更新を必要と判定します。`uv sync --locked --no-dev` とプローブの両方が成功した後だけ状態ファイルを更新し、次回起動から準備を省略します。ランチャーは多重起動をロックし、ログをアプリデータ配下に保存します。

## UI検証モード（一時）

OCRモデルや端末設定を変更せず、OCR準備画面の状態を固定して確認できます。

```powershell
uv run python scripts/validate_ocr_setup_ui.py --state setup
```

`--state` には次を指定できます。

- `setup`: 認識モデルの準備が必要
- `verify`: 既存モデルまたは実行環境の明示確認が必要
- `check-failed`: モデル準備・確認の失敗
- `location-error`: モデル保存先のエラー
- `unavailable`: PaddleOCRの依存ファイル不足
- `ready`: 準備済み

`--screenshot` を指定すると、表示状態を画像へ保存して終了します。

```powershell
uv run python scripts/validate_ocr_setup_ui.py --state verify --screenshot C:\tmp\ocr-verify.png
```

## OCR準備状態

OCR環境マネージャーは、依存パッケージ、モデル保存先、検証済みモデルファイルの一覧とサイズ、PaddleOCR・PaddlePaddleのバージョンを確認します。

「ダウンロードして準備」または「確認して更新」は専用の子プロセスで通常認識と行分割認識を実際に初期化し、不足モデルを取得します。子プロセスの成功後だけ、保存先・パッケージバージョンの確認署名とモデル一覧を保存します。保存先やパッケージが変わると次回起動時に明示確認を求め、自動初期化は行いません。

モデルは既定で `%USERPROFILE%\.paddlex` に保存します。保存先は端末設定であり、テンプレートには含めません。準備中のキャンセルは子プロセスを終了し、フルプローブに成功していない環境を準備済みとして記録しません。

保存先の変更後はランチャー経由でアプリを再起動します。OCR実行環境が不足している場合は修復へ引き渡し、依存パッケージだけを再構築します。認識モデル、テンプレート、端末設定は修復対象外です。

## 出力と保存の保護

- 空の認識結果や処理失敗は `Errors` シートへ記録する
- 不完全な会話の除外理由は `Notices` シートへ記録する
- 失敗分の再実行は、対象画像の前回行だけを置き換える
- テンプレートとExcelは一時ファイルへ書き切った後に置き換える
- 新規テンプレートの座標はゲーム画面領域を基準に正規化し、黒余白の差を補正する

診断ログは一定サイズでローテーションし、OCRの認識結果は記録しません。

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

- `main.py`: アプリの起動エントリーポイント
- `launcher.py`: 専用ランチャーの起動エントリーポイント
- `megido_ocr_excel/launcher/`: 実行環境の準備、修復、起動UI
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

## リリース前の確認

Windowsでの初回準備、OCRモデル取得、実Excel出力、修復保持を含む手順と実施結果は [Phase 6 リリーステスト](PHASE6_TEST_CHECKLIST.md) を参照してください。

```powershell
uv run python -m py_compile main.py launcher.py
uv run python -m unittest discover -s tests
```

ランチャーは `scripts/validate_launcher_ui.py`、OCR準備画面は `scripts/validate_ocr_setup_ui.py` で主要状態を確認します。初回準備は、新しいユーザー環境で `MegidoOCR2Excel.cmd` から起動し、ランチャーの環境構築からOCRモデルの明示取得、アプリ再起動までを通して検証します。
