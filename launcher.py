from __future__ import annotations

from pathlib import Path

from megido_ocr_excel.apps.megido import launcher_main


if __name__ == "__main__":
    raise SystemExit(
        launcher_main(project_root=Path(__file__).resolve().parent)
    )
