from __future__ import annotations

from megido_ocr_excel.profiles.base import OcrProfile
from megido_ocr_excel.profiles.megido_novel import PROFILE as MEGIDO_NOVEL_PROFILE


_PROFILES = {
    MEGIDO_NOVEL_PROFILE.profile_id: MEGIDO_NOVEL_PROFILE,
}


def get_profile(profile_id: str) -> OcrProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"未登録のOCRプロファイルです: {profile_id}") from exc


def registered_profiles() -> tuple[OcrProfile, ...]:
    return tuple(_PROFILES.values())
