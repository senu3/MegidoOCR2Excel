# Megido OCR to Excel

特定のノベルゲーム画面に寄せた、定型スクリーンショット用のOCRテンプレート作成ツールです。

ベースの作業は汎用版と同じです。サンプル画像上で読み取り範囲を作り、同じ画面形式の画像フォルダをまとめてOCRし、Excelへ出力します。

## セットアップ

```powershell
uv sync
```

OCRにはTesseract OCR本体が必要です。Windowsでは以下をインストールし、日本語データを含めてください。

- Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
- インストール時にJapanese language dataを選択

Tesseractのパスが自動検出されない場合は、アプリ内の「設定」から実行ファイルのパスを指定してください。

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

1. 「サンプル画像」で基準になるノベル画面のスクリーンショットを開く
2. セリフ、話者名、選択肢などの読み取り範囲をドラッグ作成し、必要ならCanvas上で調整する
3. 自動作成された項目名を必要に応じてダブルクリックで編集する
4. 項目カード右端のドラッグハンドルでExcel列順を整える
5. テンプレートをJSONとして保存する
6. 「画像フォルダ」で同形式のスクリーンショット群を選ぶ
7. 「確認」でOCR結果と後処理設定をチェックする
8. 「出力」でExcel出力先と出力設定を選び、「Excelへ一括出力」

## 初期テンプレート

`.samples/megido_novel_template.json` は実スクリーンショットに合わせて座標調整するための仮テンプレートです。OCR範囲の基準画像としては実際のノベル画面を使ってください。

## 構成

- `megido_ocr_excel_app.py`: CustomTkinter UI
- `megido_ui_theme.py`: 黒紫ダークテーマ、寸法、主要文言
- `ocr_models.py`: テンプレート項目モデル
- `ocr_engine.py`: OCR、画像前処理、後処理、範囲スケーリング
- `excel_exporter.py`: Excel出力、エラーシート生成
- `template_store.py`: テンプレートJSON保存・読み込み

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
- 既存の矩形を右クリック: 項目名編集、削除、直前操作の取り消し
- 作成や範囲変更を誤った直後: `Esc` / `Ctrl+Z` で取り消し
- チェックを外した項目: Canvas上ではグレー表示

## 確認タブ

- 選択項目または全項目をOCR
- 選択中の項目について、生OCR結果と後処理後の結果を確認
- 選択項目ごとに抽出方式、置換、削除文字を設定
- 設定変更後はOCRし直して確認

## 出力タブ

- シート名、上書き/追記、開始セルを設定
- 画像ファイル名列とヘッダー行の出力有無を設定
- 出力設定はテンプレートJSONに保存
