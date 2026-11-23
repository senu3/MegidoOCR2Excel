"""Default destinations for user-facing exports."""
from datetime import date
import os
from pathlib import Path


def downloads_folder() -> Path:
    if os.name == "nt":
        import winreg

        # The Downloads known folder can be redirected away from the user profile.
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                path, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                folder = Path(os.path.expandvars(path))
                if folder.is_absolute():
                    return folder
        except OSError:
            pass
    return Path.home() / "Downloads"


def suggested_output(source: Path | None, extension: str) -> Path:
    name = source.name.strip(". ")[:80] if source else ""
    stem = f"{name or '画像'}_OCR_{date.today():%Y%m%d}"
    folder = downloads_folder()
    candidate = folder / f"{stem}{extension}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{number}{extension}"
        number += 1
    return candidate
