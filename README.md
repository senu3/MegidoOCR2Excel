# Megido OCR to Excel

特定のノベルゲーム画面に寄せた、定型スクリーンショット用のOCRテンプレート作成ツールです。

ベースの作業は汎用版と同じです。画像フォルダの先頭画像で読み取り範囲を作り、同じ画面形式の画像フォルダをまとめてOCRし、Excelへ出力します。

## セットアップ

```powershell
uv sync
```

OCRバックエンドはPaddleOCRを標準で使用します。初回OCR時にPaddleOCRのモデルが自動ダウンロードされるため、初回だけ時間がかかります。モデルはユーザーディレクトリにキャッシュされます。

Tesseract OCRを比較用または退避用に使う場合のみ、追加依存とTesseract OCR本体をインストールしてください。

```powershell
uv sync --extra tesseract
```

- Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
- インストール時にJapanese language dataを選択

Tesseractのパスが自動検出されない場合は、アプリ内の「設定」でバックエンドを `tesseract` にしたうえで、実行ファイルのパスを指定してください。

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

## 起動

```powershell
uv run python main.py
```

または:

```powershell
uv run megido_ocr_excel_app.py
```

## 基本フロー

1. 「画像フォルダ」で同形式のスクリーンショット群を選び、先頭画像を表示する
2. セリフ、話者名、選択肢などの読み取り範囲をドラッグ作成し、必要ならCanvas上で調整する
3. 自動作成された項目名を必要に応じてダブルクリックで編集する
4. 項目カード右端のドラッグハンドルでExcel列順を整える
5. 「範囲・列」でテンプレートをJSONとして保存する
6. 必要に応じてフォルダ内の画像を切り替える
7. 「認識テスト」で代表画像の読み取り範囲とOCR結果をチェックする
8. 「Excel出力」でExcel出力先と出力設定を選び、「Excelへ一括出力」

画像はファイル名中の数字を考慮した自然順で処理します。たとえば `1.png, 2.png, 10.png` の順になります。

会話ログ画面のように複数の話者とセリフが縦に並ぶ画像では、「Excel出力」の出力形式を `会話ペアごとに1行` にします。この形式では、有効項目を `話者1, セリフ本文1, 話者2, セリフ本文2...` の順に並べると、Excelでは `ログ順 / 話者 / セリフ` の行として出力されます。

## 初期テンプレート

`.samples/megido_novel_template.json` は実スクリーンショットに合わせて座標調整するための仮テンプレートです。OCR範囲の基準画像としては実際のノベル画面を使ってください。

## 黒余白と座標補正

新規テンプレートは、画像全体ではなく黒余白を除いたゲーム画面領域を基準に座標を補正します。画像サイズや上下の黒余白が異なっても、ゲーム画面の配置が同じなら同じ読み取り範囲を利用できます。

- テンプレート保存時に基準画像のコンテンツ領域を保存
- 各画像で黒余白を検出し、コンテンツ領域間で座標を変換
- 認識テスト画面に黒余白補正の適用状態を表示
- 黒余白を安定して検出できない画像は、従来の画像全体スケーリングへフォールバック
- 旧テンプレートは互換性のため画像全体基準のまま読み込み

会話ログなど画面レイアウト自体が異なる画像には、黒余白補正ではなく別テンプレートを使用してください。

## 保存と終了の保護

- 座標、項目、OCR設定、出力設定を変更すると、ウィンドウタイトルとテンプレート名に `*` が付きます。
- 未保存のまま別テンプレートを読み込む場合や終了する場合は、保存・破棄・キャンセルを選べます。
- OCRまたはExcel出力の処理中は、ファイル書き込みの中断を防ぐためアプリを終了できません。
- テンプレートとExcelは同じフォルダの一時ファイルへ書き切ってから置換します。保存に失敗した場合、既存ファイルは変更されません。

## 特化設定

このアプリのゲーム特化設定は `profiles/megido_novel.py` に集約しています。通常UIでは範囲、項目名、項目順、後処理、Excel出力を調整し、OCR前処理や行分割などの詳細値はテンプレートJSONまたはプロファイル側で調整します。

プロファイルにはサンプル画像や `.samples` のパスは含めていません。共有しない検証用サンプルは、精度測定スクリプトの `--samples-dir` と `--template` で指定してください。

## 構成

- `megido_ocr_excel_app.py`: CustomTkinter UI
- `megido_ui_theme.py`: 黒紫ダークテーマ、寸法、主要文言
- `profiles/megido_novel.py`: このゲーム向けの既定OCRバックエンド、言語、項目別OCRプリセット
- `ocr_models.py`: テンプレート項目モデル
- `ocr_engine.py`: OCR、画像前処理、後処理、範囲スケーリング
- `excel_exporter.py`: Excel出力、エラーシート生成
- `template_store.py`: テンプレートJSON保存・読み込み
- `atomic_io.py`: テンプレートとExcelのアトミック保存

## ショートカット

- `Ctrl+Left`: 前の画像
- `Ctrl+Right`: 次の画像
- `Ctrl+S`: テンプレート保存
- `Ctrl+O`: テンプレート読み込み
- `Ctrl+Enter`: Excelへ一括出力
- `Alt+Up`: 選択項目を上へ
- `Alt+Down`: 選択項目を下へ
- `Esc` / `Ctrl+Z`: 直前の項目追加、削除、範囲変更を取り消し

## 項目カード操作

- 項目名をダブルクリック: その場で名前を編集
- 項目カードを右クリック: 編集/削除メニュー
- 項目カード右端の `☰` をドラッグ: Excel列順を変更

## Canvas操作

- 空いている場所をドラッグ: 新しい読み取り範囲を作成
- 既存の矩形内をドラッグ: 読み取り範囲を移動
- 既存の矩形の辺または角をドラッグ: 読み取り範囲をリサイズ
- 会話ペア出力時の `#n` ハンドルをドラッグ: 話者とセリフの範囲を同時に移動
- 会話ペア出力時の中枠: 通常は非表示、項目を選択したときだけ個別調整用に表示
- 既存の矩形を右クリック: 項目名編集、削除、直前操作の取り消し
- 作成や範囲変更を誤った直後: `Esc` / `Ctrl+Z` で取り消し
- チェックを外した項目: Canvas上ではグレー表示

## 認識テスト

- 現在の画像について、選択項目または全項目をテスト
- 選択中の項目について、読み取り範囲の拡大プレビューと認識結果全文を確認
- 生OCRと後処理後の結果が異なる場合は両方を表示
- 上部の前後ボタンで先頭・中央・末尾などの代表画像へ移動して再テスト
- 選択項目ごとにOCR方式を調整し、設定変更後に再テスト
- 認識テストの結果はプレビューであり、Excel出力時には対象画像を改めて一括OCR

## Excel出力タブ

- シート名、上書き/追記、開始セルを設定
- 画像ファイル名列とヘッダー行の出力有無を設定
- 出力形式を `画像ごとに1行` または `会話ペアごとに1行` から選択
- 出力設定はテンプレートJSONに保存
- OCR結果が空だった項目や認識に失敗した項目は `Errors` シートに記録

## OCR精度測定

`.samples` の `*.png` と同名の `*.csv` を正解データとして比較します。
話者、セリフ本文ともに、OCR結果をそのままCSVの正解値と完全一致で比較します。
セリフ本文はCSV内の全角スペースを改行相当として扱うため、空白正規化後の一致数も併記します。

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
uv run python scripts/measure_dialogue_ocr.py --backend tesseract --tessdata-dir C:\tessdata_best --oem 1
```
