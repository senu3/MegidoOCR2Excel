from __future__ import annotations

import sys


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--packaging-smoke-test":
        from megido_ocr_excel.packaging_smoke import run_packaging_smoke_test

        raise SystemExit(run_packaging_smoke_test(sys.argv[2]))

    from megido_ocr_excel.application import main

    main()
