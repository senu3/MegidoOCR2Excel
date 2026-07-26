from __future__ import annotations

from io import BytesIO
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from megido_ocr_excel.ocr.dialogue_detector import detect_complete_dialogue_pairs
from megido_ocr_excel.models import SET_SLOT_SUPPLEMENT, TemplateField
from megido_ocr_excel.ocr.engine import OcrEngine
from megido_ocr_excel.profiles.megido_novel import PROFILE
from tests.private_samples import private_sample_test


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
    @private_sample_test
    def test_repeated_dots_are_recovered_for_all_dialogue_preprocessing(self) -> None:
        image = Image.open(".samples/b3.png").convert("RGB")
        result = detect_complete_dialogue_pairs(
            image,
            PROFILE.auto_detection_fields(),
            PROFILE.coordinate_settings(),
            PROFILE.dialogue_log_detection,
        )
        field = result.groups[-1][2]
        crop = image.crop((field.x1, field.y1, field.x2, field.y2))
        fallback = PROFILE.image_text_fallback
        assert fallback is not None

        self.assertEqual(field.ocr_preprocess, "threshold")
        self.assertEqual(fallback(crop, field, "", image.width), "…………")
        field.ocr_preprocess = "gray"
        self.assertEqual(fallback(crop, field, "", image.width), "…………")

    def test_short_repeated_dots_can_recover_two_ellipsis_characters(self) -> None:
        image = Image.new("RGB", (1080, 100), "white")
        draw = ImageDraw.Draw(image)
        for center_x in (40, 54, 68, 82, 96, 110):
            draw.ellipse(
                (center_x - 3, 47, center_x + 3, 53),
                fill="black",
            )
        field = TemplateField(
            "セリフ本文",
            0,
            0,
            image.width,
            image.height,
            ocr_preprocess="gray",
            ocr_line_split="detected",
        )
        fallback = PROFILE.image_text_fallback
        assert fallback is not None

        self.assertEqual(fallback(image, field, "", image.width), "……")
        self.assertEqual(fallback(image, field, "認識済み", image.width), "認識済み")

        field.name = "任意項目"
        self.assertEqual(fallback(image, field, "", image.width), "")
        field.slot_key = SET_SLOT_SUPPLEMENT
        self.assertEqual(fallback(image, field, "", image.width), "……")

    def test_empty_dialogue_is_not_filled_with_punctuation(self) -> None:
        image = Image.new("RGB", (1080, 100), "white")
        field = TemplateField(
            "セリフ本文",
            0,
            0,
            image.width,
            image.height,
            ocr_preprocess="threshold",
            ocr_line_split="detected",
        )
        fallback = PROFILE.image_text_fallback
        assert fallback is not None

        self.assertEqual(fallback(image, field, "", image.width), "")

    @private_sample_test
    def test_megido_samples_resolve_one_and_prolonged_sound_marks(self) -> None:
        for filename, (misrecognized, expected) in SAMPLE_TEXT.items():
            with self.subTest(filename=filename):
                image = Image.open(Path(".samples") / filename).convert("RGB")
                self.assertEqual(correct_sample(image, misrecognized), expected)

    @private_sample_test
    def test_double_bar_is_recovered_at_dialogue_line_start(self) -> None:
        image = Image.open(".samples/b6.png").convert("RGB")
        suffix = (
            "被害については見当もつかん\n"
            "なにしろ、空間の繋ぎ目から\n"
            "別の場所へ行ったが最後…"
        )

        for recognized in ("一", "ー", "―"):
            with self.subTest(recognized=recognized):
                self.assertEqual(
                    correct_sample(image, recognized + suffix),
                    "――" + suffix,
                )

    def test_double_bar_is_recovered_at_line_end_but_not_in_the_middle(self) -> None:
        image = Image.new("RGB", (1080, 100), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 25, 70, 75), fill="black")
        draw.rectangle((100, 49, 180, 50), fill="black")
        field = TemplateField(
            "セリフ本文",
            0,
            0,
            image.width,
            image.height,
            ocr_preprocess="gray",
            ocr_line_split="detected",
        )
        corrector = PROFILE.image_text_corrector
        assert corrector is not None

        self.assertEqual(corrector(image, field, "本文ー", image.width), "本文――")
        self.assertNotIn("――", corrector(image, field, "本ー文", image.width))

    @private_sample_test
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

    @private_sample_test
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

    @private_sample_test
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

    @private_sample_test
    def test_engine_without_profile_correction_keeps_the_ocr_result(self) -> None:
        image = Image.open(".samples/5.png").convert("RGB")
        field = detected_dialogue(image)
        engine = OcrEngine()
        misrecognized, _expected = SAMPLE_TEXT["5.png"]

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
        self.assertEqual(raw, misrecognized)
        self.assertIn("ああ一、", value or "")


if __name__ == "__main__":
    unittest.main()
