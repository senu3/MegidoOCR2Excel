from __future__ import annotations

from pathlib import Path

from megido_ocr_excel.launcher.ui import main


if __name__ == "__main__":
    raise SystemExit(main(project_root=Path(__file__).resolve().parent))
