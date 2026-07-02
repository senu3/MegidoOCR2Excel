from __future__ import annotations

from ocr_accuracy_common import run_accuracy


if __name__ == "__main__":
    raise SystemExit(
        run_accuracy(
            "話者",
            default_psm=6,
            default_preprocess="white-glyph",
            default_scale="4",
            default_threshold=190,
            default_lang="jpn",
        )
    )
