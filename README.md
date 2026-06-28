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
2. セリフ、話者名、選択肢などの読み取り範囲をドラッグ作成する
3. 項目名を付ける
4. テンプレートをJSONとして保存する
5. 「画像フォルダ」で同形式のスクリーンショット群を選ぶ
6. 「確認」でOCR結果を見て、必要なら手修正する
7. 「出力」でExcel出力先を選び、「Excelへ一括出力」

## 初期テンプレート

`.sample/megido_novel_template.json` は実スクリーンショットに合わせて座標調整するための仮テンプレートです。ロゴ画像は方向性確認用で、OCR範囲の基準画像としては実際のノベル画面を使ってください。

## ショートカット

- `Ctrl+Left`: 前の画像
- `Ctrl+Right`: 次の画像
- `Ctrl+S`: テンプレート保存
- `Ctrl+O`: テンプレート読み込み
- `Ctrl+Enter`: Excelへ一括出力
