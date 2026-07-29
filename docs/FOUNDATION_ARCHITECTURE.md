# Python基盤とアプリ固有層

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
