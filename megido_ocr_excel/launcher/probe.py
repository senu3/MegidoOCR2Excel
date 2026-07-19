from __future__ import annotations

import importlib
import json
import platform


REQUIRED_IMPORTS = (
    "customtkinter",
    "openpyxl",
    "PIL",
    "paddle",
    "paddleocr",
)


def probe() -> dict[str, object]:
    versions: dict[str, str] = {}
    for name in REQUIRED_IMPORTS:
        module = importlib.import_module(name)
        versions[name] = str(getattr(module, "__version__", "available"))
    return {
        "ok": True,
        "python": platform.python_version(),
        "packages": versions,
    }


def main() -> int:
    print(json.dumps(probe(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
