# テスト

通常のテストは、非公開の検証画像がない環境でも実行できます。GitHub Actionsでも同じコマンドを使用します。

```powershell
uv run python -m unittest discover -s tests
```

`.samples`の検証画像を使うローカルテストは、専用スクリプトから実行します。このスクリプトは通常のテストに加えて、`private_sample_test`で分類された検出・画像補正テストも有効にします。

```powershell
uv run python scripts/run_private_sample_tests.py
```

実際のPaddleOCRモデルを使う精度測定は、テストスイートと分けて実行します。

```powershell
uv run python scripts/measure_speaker_ocr.py
uv run python scripts/measure_dialogue_ocr.py
```
