from __future__ import annotations

from ocr_accuracy_common import run_accuracy


if __name__ == "__main__":
    raise SystemExit(
        run_accuracy(
            "セリフ本文",
            default_psm=6,
            default_preprocess="threshold",
            default_scale="3",
            default_threshold=140,
            default_lang="jpn",
        )
    )
