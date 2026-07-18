from __future__ import annotations

import json
import sys
import traceback
from importlib.metadata import version
from pathlib import Path

from megido_ocr_excel.persistence import atomic_write_text


def run_packaging_smoke_test(report_path: str | Path) -> int:
    """Verify imports that commonly fail only inside a frozen application."""
    report: dict[str, object] = {
        "ok": False,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "python": sys.version,
    }
    try:
        import customtkinter
        import paddle
        import paddleocr
        from paddleocr import PaddleOCR, TextRecognition

        report.update(
            {
                "ok": True,
                "customtkinter": customtkinter.__version__,
                "paddle": paddle.__version__,
                "paddleocr": paddleocr.__version__,
                "paddlepaddle_metadata": version("paddlepaddle"),
                "paddleocr_metadata": version("paddleocr"),
                "paddlex_metadata": version("paddlex"),
                "ocr_class": PaddleOCR.__name__,
                "recognition_class": TextRecognition.__name__,
            }
        )
    except Exception as error:
        report.update(
            {
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(),
            }
        )

    atomic_write_text(
        Path(report_path),
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    return 0 if report["ok"] else 1
