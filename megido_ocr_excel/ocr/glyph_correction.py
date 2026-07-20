from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps

from megido_ocr_excel.models import TemplateField
from megido_ocr_excel.ocr.engine import detect_line_bands


@dataclass(frozen=True)
class HorizontalGlyphCorrector:
    """Resolve two isolated horizontal glyphs using profile-specific widths."""

    field_prefixes: tuple[str, ...]
    short_glyph: str
    long_glyph: str
    short_max_width_ratio: float
    long_min_width_ratio: float
    dark_threshold: int = 100
    min_aspect_ratio: float = 5.0
    min_width_to_line_height: float = 0.65
    max_height_to_line_height: float = 0.22
    min_center_y_ratio: float = 0.35
    max_center_y_ratio: float = 0.65
    min_area_to_line_height_squared: float = 0.03

    def __call__(
        self,
        crop: Image.Image,
        field: TemplateField,
        text: str,
        reference_width: int,
    ) -> str:
        if (
            not text
            or reference_width <= 0
            or field.ocr_line_split != "detected"
            or not field.name.startswith(self.field_prefixes)
        ):
            return text

        ambiguous_positions = [
            index
            for index, char in enumerate(text)
            if char in {self.short_glyph, self.long_glyph}
        ]
        if not ambiguous_positions:
            return text

        candidates = self._horizontal_candidates(crop)
        if len(candidates) != len(ambiguous_positions):
            return text

        corrected = list(text)
        for text_index, component_width in zip(ambiguous_positions, candidates):
            width_ratio = component_width / reference_width
            if width_ratio <= self.short_max_width_ratio:
                corrected[text_index] = self.short_glyph
            elif width_ratio >= self.long_min_width_ratio:
                corrected[text_index] = self.long_glyph
        return "".join(corrected)

    def _horizontal_candidates(self, crop: Image.Image) -> list[int]:
        bands = detect_line_bands(
            crop,
            threshold=self.dark_threshold,
            min_ratio=0.015,
            gap=max(2, round(crop.width * 0.01)),
            padding=0,
        )
        candidates: list[tuple[int, int, int]] = []
        for band_top, band_bottom in bands:
            line = ImageOps.grayscale(crop.crop((0, band_top, crop.width, band_bottom)))
            line_height = line.height
            if line_height <= 0:
                continue
            for x1, y1, x2, y2, area in _dark_components(
                line, self.dark_threshold
            ):
                width = x2 - x1
                height = y2 - y1
                center_y_ratio = (y1 + y2) / 2 / line_height
                if (
                    width / max(1, height) < self.min_aspect_ratio
                    or width < line_height * self.min_width_to_line_height
                    or height > line_height * self.max_height_to_line_height
                    or not self.min_center_y_ratio
                    <= center_y_ratio
                    <= self.max_center_y_ratio
                    or area
                    < line_height
                    * line_height
                    * self.min_area_to_line_height_squared
                ):
                    continue
                candidates.append((band_top, x1, width))
        candidates.sort(key=lambda item: (item[0], item[1]))
        return [width for _y, _x, width in candidates]


def _dark_components(
    gray: Image.Image,
    threshold: int,
) -> list[tuple[int, int, int, int, int]]:
    """Return 8-connected dark components as half-open boxes plus their area."""
    width, height = gray.size
    pixels = list(gray.get_flattened_data())
    remaining = bytearray(value < threshold for value in pixels)
    components: list[tuple[int, int, int, int, int]] = []

    for start in range(len(remaining)):
        if not remaining[start]:
            continue
        remaining[start] = 0
        stack = [start]
        start_y, start_x = divmod(start, width)
        min_x = max_x = start_x
        min_y = max_y = start_y
        area = 0
        while stack:
            index = stack.pop()
            y, x = divmod(index, width)
            area += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
                row_start = neighbor_y * width
                for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row_start + neighbor_x
                    if remaining[neighbor]:
                        remaining[neighbor] = 0
                        stack.append(neighbor)
        components.append((min_x, min_y, max_x + 1, max_y + 1, area))
    return components
