from __future__ import annotations

from io import BytesIO
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from megido_ocr_excel.ocr.dialogue_detector import detect_complete_dialogue_pairs
from megido_ocr_excel.ocr.engine import OcrEngine
from megido_ocr_excel.profiles.megido_novel import PROFILE


SAMPLE_TEXT = {
    "5.png": (
        "ああ一、\nここは説明が必要かな\n"
        "ヴァイガルドでさえ、騎士の定義が\n古いものとは変わってきてる",
        "ああー、\nここは説明が必要かな\n"
        "ヴァイガルドでさえ、騎士の定義が\n古いものとは変わってきてる",
    ),
    "10.png": (
        "私もー緒に行くわ\nー応、なにかあったときのために\n"
        "ソロモンに伝えとこうと思ったの",
        "私も一緒に行くわ\n一応、なにかあったときのために\n"
        "ソロモンに伝えとこうと思ったの",
    ),
    "11.png": (
        "ひゃっほ一！\n皆殺しだぜ一！",
        "ひゃっほー！\n皆殺しだぜー！",
    ),
    "12.png": (
        "生まれる前のヴィ一タに魂が入れば\n"
        "生まれた後のヴィ一タに魂を入れる\n"
        "ことだって、できるはずだろ",
        "生まれる前のヴィータに魂が入れば\n"
        "生まれた後のヴィータに魂を入れる\n"
        "ことだって、できるはずだろ",
    ),
}


def jpeg_copy(image: Image.Image, quality: int) -> Image.Image:
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality)
    output.seek(0)
    return Image.open(output).convert("RGB")


def detected_dialogue(image: Image.Image):
    result = detect_complete_dialogue_pairs(
        image,
        PROFILE.auto_detection_fields(),
        PROFILE.coordinate_settings(),
        PROFILE.dialogue_log_detection,
    )
    return result.groups[0][2]


def correct_sample(image: Image.Image, text: str) -> str:
    corrector = PROFILE.image_text_corrector
    assert corrector is not None
    field = detected_dialogue(image)
    crop = image.crop((field.x1, field.y1, field.x2, field.y2))
    return corrector(crop, field, text, image.width)


class HorizontalGlyphCorrectionTests(unittest.TestCase):
    def test_megido_samples_resolve_one_and_prolonged_sound_marks(self) -> None:
        for filename, (misrecognized, expected) in SAMPLE_TEXT.items():
            with self.subTest(filename=filename):
                image = Image.open(Path(".samples") / filename).convert("RGB")
                self.assertEqual(correct_sample(image, misrecognized), expected)

    def test_degraded_sample_keeps_the_prolonged_sound_shape(self) -> None:
        image = Image.open(".samples/5.png").convert("RGB")
        half = image.resize(
            (image.width // 2, image.height // 2),
            Image.Resampling.LANCZOS,
        )
        misrecognized, expected = SAMPLE_TEXT["5.png"]

        for variant in (jpeg_copy(image, 40), half, jpeg_copy(half, 40)):
            with self.subTest(size=variant.size):
                self.assertEqual(correct_sample(variant, misrecognized), expected)

    def test_candidate_count_mismatch_and_unrelated_fields_are_not_changed(self) -> None:
        image = Image.open(".samples/5.png").convert("RGB")
        corrector = PROFILE.image_text_corrector
        assert corrector is not None
        field = detected_dialogue(image)
        crop = image.crop((field.x1, field.y1, field.x2, field.y2))
        mismatch = "ああ一、一"

        self.assertEqual(corrector(crop, field, mismatch, image.width), mismatch)
        field.name = "任意項目"
        self.assertEqual(
            corrector(crop, field, SAMPLE_TEXT["5.png"][0], image.width),
            SAMPLE_TEXT["5.png"][0],
        )

    def test_engine_applies_profile_correction_before_formatting(self) -> None:
        image = Image.open(".samples/5.png").convert("RGB")
        field = detected_dialogue(image)
        engine = OcrEngine(PROFILE.image_text_corrector)
        misrecognized, expected = SAMPLE_TEXT["5.png"]

        with patch.object(
            engine,
            "recognize_detected_lines",
            return_value=misrecognized,
        ):
            raw, value, error = engine.recognize_field_detail(
                image,
                field,
                lang="jpn",
                backend="paddle",
                coordinate_settings=PROFILE.coordinate_settings(),
                text_formatting=PROFILE.text_formatting_settings(),
            )

        self.assertIsNone(error)
        self.assertEqual(raw, expected)
        self.assertIn("ああー、", value or "")
        self.assertNotIn("ああ一、", value or "")


if __name__ == "__main__":
    unittest.main()
