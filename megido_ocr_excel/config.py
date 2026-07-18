from __future__ import annotations

import re
from pathlib import Path

from megido_ocr_excel.profiles import get_profile


APP_PROFILE = get_profile("megido_novel")
APP_TITLE = APP_PROFILE.app_title
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def natural_image_sort_key(path: Path) -> tuple:
    """Sort numbered screenshot names in the order users expect."""
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name.casefold()))
