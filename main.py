from __future__ import annotations

import sys


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--packaging-smoke-test":
        from packaging_smoke import run_packaging_smoke_test

        raise SystemExit(run_packaging_smoke_test(sys.argv[2]))

    from megido_ocr_excel_app import main

    main()
