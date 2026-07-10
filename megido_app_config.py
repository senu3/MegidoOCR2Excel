from __future__ import annotations

import re
from pathlib import Path

from profiles.megido_novel import DEFAULT_BACKEND, DEFAULT_LANG, PROFILE_ID, PROFILE_NAME


APP_TITLE = "Megido OCR to Excel"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def natural_image_sort_key(path: Path) -> tuple:
    """Sort numbered screenshot names in the order users expect."""
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name.casefold()))
