from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:  # OpenCV is available in the recommended `travel` conda environment.
    import cv2
except ImportError:  # Keep the application usable with the base Python too.
    cv2 = None

from models.board import Board
from models.cell import CellState
from models.item import MANUAL_ITEM_NAMES


_DIGIT_TEMPLATES: dict[int, list[np.ndarray]] | None = None


@dataclass(frozen=True)
class BoardRegion:
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int

    @property
    def cell_width(self) -> float:
        return (self.right - self.left) / self.width

    @property
    def cell_height(self) -> float:
        return (self.bottom - self.top) / self.height


@dataclass
class ImageBoard:
    board: Board
    region: BoardRegion
    image: Image.Image
    reward_centers: list[tuple[int, int]]
    inventory: dict[str, int]


class ScreenshotAnalyzer:
    """Lightweight geometric/color analyzer for the provided game screenshot.

    It deliberately avoids a hard OpenCV dependency. Brown revealed cells,
    tan stone cells, and blue/purple reward glyphs are separated by robust
    color statistics at each cell center and its neighborhood.
    """

    def __init__(self, expected_size: int | None = None):
        if expected_size not in (None, 5, 10, 15):
            raise ValueError("expected_size must be 5, 10, 15, or None")
        self.expected_size = expected_size

    def detect_region(self, image: Image.Image) -> BoardRegion:
        width, height = image.size
        arr = np.asarray(image.convert("RGB"))
        cv_region = self._detect_region_opencv(arr)
        if cv_region is not None:
            refined = self._refine_grid_region(arr, cv_region)
            return self._apply_detected_size(arr, refined)
        red, green, blue = [arr[:, :, i] for i in range(3)]
        board_like = (green < 165) & (blue < 140) & (red < 215)
        row_score = board_like.mean(axis=1)
        col_score = board_like.mean(axis=0)

        def longest_run(values: np.ndarray, threshold: float, start: int, end: int) -> tuple[int, int] | None:
            best = None
            run_start = None
            for index in range(start, min(end, len(values))):
                if values[index] > threshold:
                    run_start = index if run_start is None else run_start
                elif run_start is not None:
                    if best is None or index - run_start > best[1] - best[0]:
                        best = (run_start, index)
                    run_start = None
            if run_start is not None and (best is None or len(values) - run_start > best[1] - best[0]):
                best = (run_start, len(values))
            return best

        xrun = longest_run(col_score, 0.62, 0, width)
        yrun = longest_run(row_score, 0.62, max(0, height // 20), int(height * 0.92))
        # The fallback also keeps the analyzer useful for resized versions of
        # the sample where anti-aliasing makes the scan less certain.
        # The game board spans almost the full screenshot width. A dense run
        # inside the board can look valid when icons and revealed cells split
        # the color mask near one side, but using that partial run crops whole
        # columns and makes a 15x15 board resemble 5x5.
        if (
            xrun is None
            or xrun[1] - xrun[0] < width * 0.85
            or xrun[0] > width * 0.08
            or xrun[1] < width * 0.92
        ):
            xrun = (round(width * 0.018), round(width * 0.982))
        if yrun is None or yrun[1] - yrun[0] < height * 0.5:
            yrun = (round(height * 0.085), round(height * 0.87))
        provisional_size = self.expected_size or 15
        coarse = BoardRegion(xrun[0], yrun[0], xrun[1], yrun[1], provisional_size, provisional_size)
        refined = self._refine_grid_region(arr, coarse)
        return self._apply_detected_size(arr, refined)

    def _apply_detected_size(self, rgb: np.ndarray, region: BoardRegion) -> BoardRegion:
        size = self.expected_size or self._infer_board_size(rgb, region)
        return BoardRegion(region.left, region.top, region.right, region.bottom, size, size)

    @classmethod
    def _infer_board_size(cls, rgb: np.ndarray, region: BoardRegion) -> int:
        """Choose 5, 10, or 15 from the periodic grid-edge response."""
        gray = (
            rgb[:, :, 0].astype(float) * 0.299
            + rgb[:, :, 1].astype(float) * 0.587
            + rgb[:, :, 2].astype(float) * 0.114
        )
        vertical = np.abs(gray[region.top:region.bottom, 1:] - gray[region.top:region.bottom, :-1]).mean(axis=0)
        horizontal = np.abs(gray[1:, region.left:region.right] - gray[:-1, region.left:region.right]).mean(axis=1)

        def boundary_mean(profile: np.ndarray, positions: list[int]) -> float:
            values = []
            for position in positions:
                window = profile[max(0, position - 2):min(len(profile), position + 2)]
                if len(window):
                    values.append(float(window.max()))
            return float(np.mean(values)) if values else 0.0

        scores: dict[int, float] = {}
        for size in (5, 10, 15):
            xs = [round(region.left + index * (region.right - region.left) / size) for index in range(size + 1)]
            ys = [round(region.top + index * (region.bottom - region.top) / size) for index in range(size + 1)]
            contrast = (
                boundary_mean(vertical, xs) - float(vertical.mean())
                + boundary_mean(horizontal, ys) - float(horizontal.mean())
            )
            scores[size] = contrast
        reward_cell_counts = {
            size: cls._count_reward_cells(rgb, region, size)
            for size in (5, 10, 15)
        }
        # Colorful item/reward cells provide a useful lower bound late in a
        # board. A 5x5 board cannot contain more than 8 rewards and a 10x10
        # board cannot contain more than 32. Small tolerances account for a
        # slightly misplaced grid splitting one icon across adjacent cells.
        reward_limits = {5: 8, 10: 32, 15: 72}
        split_tolerance = {5: 1, 10: 4, 15: 9}
        compatible_sizes = [
            size
            for size in (5, 10, 15)
            if size == 15
            or reward_cell_counts[size] <= reward_limits[size] + split_tolerance[size]
        ]
        strongest = max(scores[size] for size in compatible_sizes)
        # A 10x10 grid contains every second 5x5 boundary and a 15x15 grid
        # contains every third one. Prefer the denser candidate when its full
        # boundary evidence remains close to the strongest subset response.
        # Real boards do not draw every cell edge with identical contrast:
        # adjacent revealed cells can make many interior lines faint, while
        # every third edge remains strong and resembles a 5x5 subset. Keep a
        # wider tolerance so the full 15x15 periodic signal wins in that case.
        plausible = [
            size
            for size in compatible_sizes
            if scores[size] >= strongest * 0.77
        ]
        alignment, layout_reliable = cls._reward_layout_alignment(rgb, region)
        if layout_reliable:
            ranked_layouts = sorted(
                compatible_sizes,
                key=lambda size: alignment[size],
            )
            best_layout = ranked_layouts[0]
            second_error = alignment[ranked_layouts[1]] if len(ranked_layouts) > 1 else 1.0
            # A unique, tightly aligned item pattern can correct weak or
            # partially obscured grid edges. Retain a minimum edge signal so
            # arbitrary colorful artwork cannot decide the board size alone.
            if (
                alignment[best_layout] <= 0.30
                and second_error - alignment[best_layout] >= 0.07
                and scores[best_layout] >= strongest * 0.45
            ):
                plausible = [best_layout]
            else:
                layout_supported = {
                    size
                    for size in compatible_sizes
                    if alignment[size] <= min(alignment.values()) + 0.06
                }
                overlap = [size for size in plausible if size in layout_supported]
                if overlap:
                    plausible = overlap
        return max(plausible)

    @classmethod
    def _count_reward_cells(cls, rgb: np.ndarray, region: BoardRegion, size: int) -> int:
        """Count grid cells containing colorful reward/item artwork."""
        found = 0
        for y in range(size):
            for x in range(size):
                x0 = round(region.left + x * (region.right - region.left) / size)
                x1 = round(region.left + (x + 1) * (region.right - region.left) / size)
                y0 = round(region.top + y * (region.bottom - region.top) / size)
                y1 = round(region.top + (y + 1) * (region.bottom - region.top) / size)
                if cls.classify_patch(rgb[y0:y1, x0:x1]) is CellState.REWARD_FOUND:
                    found += 1
        return found

    @staticmethod
    def _reward_color_mask(patch: np.ndarray) -> np.ndarray:
        """Return blue/purple/yellow pixels belonging to reward artwork."""
        red, green, blue = [patch[:, :, i].astype(float) for i in range(3)]
        colorful = (
            ((blue > red + 25) & (blue > green + 5) & (blue > 80))
            | ((red > 100) & (blue > green + 15) & (blue > 80))
        )
        rgb = patch.astype(float) / 255.0
        maximum = rgb.max(axis=2)
        minimum = rgb.min(axis=2)
        delta = maximum - minimum
        saturation = np.divide(
            delta,
            maximum,
            out=np.zeros_like(delta),
            where=maximum > 0,
        )
        hue = np.zeros_like(maximum)
        nonzero = delta > 0
        red_max = nonzero & (rgb[:, :, 0] == maximum)
        green_max = nonzero & (rgb[:, :, 1] == maximum)
        blue_max = nonzero & (rgb[:, :, 2] == maximum)
        hue[red_max] = 60 * np.mod(
            (rgb[:, :, 1][red_max] - rgb[:, :, 2][red_max]) / delta[red_max],
            6,
        )
        hue[green_max] = 60 * (
            (rgb[:, :, 2][green_max] - rgb[:, :, 0][green_max]) / delta[green_max]
            + 2
        )
        hue[blue_max] = 60 * (
            (rgb[:, :, 0][blue_max] - rgb[:, :, 1][blue_max]) / delta[blue_max]
            + 4
        )
        yellow = (
            (saturation > (110 / 255))
            & (maximum > (125 / 255))
            & (hue >= 40)
            & (hue <= 100)
        )
        return colorful | yellow

    @classmethod
    def _reward_layout_alignment(
        cls,
        rgb: np.ndarray,
        region: BoardRegion,
    ) -> tuple[dict[int, float], bool]:
        """Measure how reward pixels align with candidate grid-cell centers.

        Distances are normalized to each candidate's cell width and height.
        A layout is considered informative only when colored pixels are both
        numerous and spread across a meaningful portion of both board axes.
        """
        patch = rgb[region.top:region.bottom, region.left:region.right]
        ys, xs = np.where(cls._reward_color_mask(patch))
        if len(xs) == 0:
            return {5: 1.0, 10: 1.0, 15: 1.0}, False
        scores: dict[int, float] = {}
        for size in (5, 10, 15):
            cell_width = max(1.0, patch.shape[1] / size)
            cell_height = max(1.0, patch.shape[0] / size)
            dx = np.abs(np.mod((xs + 0.5) / cell_width, 1.0) - 0.5)
            dy = np.abs(np.mod((ys + 0.5) / cell_height, 1.0) - 0.5)
            scores[size] = float(np.mean(np.hypot(dx, dy)))
        enough_pixels = len(xs) >= max(64, round(patch.shape[0] * patch.shape[1] * 0.002))
        spread_x = int(xs.max()) - int(xs.min()) >= patch.shape[1] * 0.30
        spread_y = int(ys.max()) - int(ys.min()) >= patch.shape[0] * 0.30
        return scores, bool(enough_pixels and spread_x and spread_y)

    def _refine_grid_region(self, rgb: np.ndarray, coarse: BoardRegion) -> BoardRegion:
        """Move a coarse board box from content edges onto the true cell grid.

        Reward icons can interrupt the top contour, causing a contour box to
        begin several pixels below the first row. The outer frame is much more
        stable, so find its four strongest nearby edges and inset to the inner
        grid. Insets scale with the estimated cell size for resized captures.
        """
        gray = (
            rgb[:, :, 0].astype(float) * 0.299
            + rgb[:, :, 1].astype(float) * 0.587
            + rgb[:, :, 2].astype(float) * 0.114
        )
        horizontal_delta = np.abs(gray[1:, :] - gray[:-1, :])
        vertical_delta = np.abs(gray[:, 1:] - gray[:, :-1])
        image_height, image_width = gray.shape
        cell_size = max(4.0, (coarse.right - coarse.left) / coarse.width)
        search_margin = max(4, round(cell_size * 0.45))

        x0 = max(0, coarse.left)
        x1 = min(image_width, coarse.right + 1)
        y0 = max(0, coarse.top - search_margin)
        y1 = min(image_height, coarse.bottom + search_margin)
        horizontal_profile = horizontal_delta[:, x0:x1].mean(axis=1)
        vertical_profile = vertical_delta[y0:y1, :].mean(axis=0)

        def strongest_edge(profile: np.ndarray, low: int, high: int) -> int:
            low = max(1, low)
            high = min(len(profile), high)
            if high <= low:
                return low
            # A delta at index n lies between pixels n and n+1, so expose the
            # boundary in image coordinates as n+1.
            return int(low + np.argmax(profile[low - 1:high - 1]))

        # The color run can start either below the frame (when icons interrupt
        # it) or above it (when the dark header resembles board colors). Search
        # both directions around the coarse edge so the actual frame wins.
        outer_top = strongest_edge(
            horizontal_profile,
            coarse.top - search_margin,
            coarse.top + search_margin,
        )
        outer_bottom = strongest_edge(horizontal_profile, coarse.bottom - 3, coarse.bottom + 4)
        # Avoid selecting the screenshot's own border only when the color run
        # actually touches it. Otherwise retain the narrow local search that
        # is more accurate for captures with a normal outer margin.
        if coarse.left <= 3:
            outer_left = strongest_edge(
                vertical_profile,
                coarse.left,
                coarse.left + search_margin,
            )
        else:
            outer_left = strongest_edge(vertical_profile, coarse.left - 3, coarse.left + 2)
        if coarse.right >= image_width - 1:
            outer_right = strongest_edge(
                vertical_profile,
                coarse.right - search_margin,
                coarse.right,
            )
        else:
            outer_right = strongest_edge(vertical_profile, coarse.right - 1, coarse.right + 4)

        side_inset = max(1, round(cell_size * 0.08))
        top_inset = max(2, round(cell_size * 0.12))
        left = outer_left + side_inset
        right = outer_right - side_inset
        top = outer_top + top_inset
        bottom = outer_bottom - side_inset

        if right - left < image_width * 0.5 or bottom - top < image_height * 0.5:
            return coarse
        return BoardRegion(left, top, right, bottom, coarse.width, coarse.height)

    def _detect_region_opencv(self, rgb: np.ndarray) -> BoardRegion | None:
        """Find the large near-square board frame using Canny + contours.

        The contour path is intentionally optional: deployments without
        OpenCV fall back to the same color-scan detector used by the tests.
        """
        if cv2 is None:
            return None
        height, width = rgb.shape[:2]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 45, 130)
        edges = cv2.dilate(edges, np.ones((3, 3), dtype=np.uint8), iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[tuple[float, int, int, int, int]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            ratio = w / max(1, h)
            if area > width * height * 0.35 and 0.88 <= ratio <= 1.12 and y > height * 0.03 and y + h < height * 0.94:
                candidates.append((area, x, y, w, h))
        if not candidates:
            return None
        _, x, y, w, h = max(candidates)
        provisional_size = self.expected_size or 15
        return BoardRegion(x, y, x + w, y + h, provisional_size, provisional_size)

    def analyze(self, path: str | Path, reward_count: int | None = None) -> ImageBoard:
        return self.analyze_image(Image.open(path).convert("RGB"), reward_count)

    def analyze_image(self, image: Image.Image, reward_count: int | None = None) -> ImageBoard:
        image = image.convert("RGB")
        region = self.detect_region(image)
        board = Board.create(region.width, reward_count)
        arr = np.asarray(image)
        reward_centers: list[tuple[int, int]] = []
        for y in range(region.height):
            for x in range(region.width):
                x0 = round(region.left + x * region.cell_width)
                x1 = round(region.left + (x + 1) * region.cell_width)
                y0 = round(region.top + y * region.cell_height)
                y1 = round(region.top + (y + 1) * region.cell_height)
                patch = arr[max(0, y0):min(arr.shape[0], y1), max(0, x0):min(arr.shape[1], x1)]
                state = self.classify_patch(patch)
                board.set_state(x, y, state)
                if state is CellState.REWARD_FOUND:
                    reward_centers.append((x, y))
        return ImageBoard(board, region, image, reward_centers, self.detect_inventory(image))

    def detect_inventory(self, image: Image.Image) -> dict[str, int]:
        """Read the four bright quantity glyphs from the bottom item slots."""
        rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]
        counts: list[int] = []
        for index in range(4):
            slot_left = round(width * (10 / 390 + index * 94 / 390))
            slot_right = round(width * (99 / 390 + index * 94 / 390))
            top = round(height * (423 / 474))
            bottom = round(height * (466 / 474))
            slot_width = slot_right - slot_left
            roi_left = slot_left + round(slot_width * 0.48)
            roi_right = slot_left + round(slot_width * 0.88)
            patch = rgb[top:bottom, roi_left:roi_right]
            red, green, blue = [patch[:, :, channel] for channel in range(3)]
            mask = ((red > 235) & (green > 210) & (blue > 145)).astype(np.uint8)
            glyphs = self._connected_glyphs(mask)
            digits = [self._recognize_digit(glyph) for glyph in glyphs]
            counts.append(int("".join(str(digit) for digit in digits)) if digits else 0)
        return dict(zip(MANUAL_ITEM_NAMES, counts))

    @staticmethod
    def _connected_glyphs(mask: np.ndarray) -> list[np.ndarray]:
        if cv2 is not None:
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            boxes = []
            for label in range(1, count):
                x, y, width, height, area = stats[label]
                if height >= max(7, round(mask.shape[0] * 0.25)) and width >= 2 and area >= 12:
                    boxes.append((x, mask[y:y + height, x:x + width]))
            return [glyph for _x, glyph in sorted(boxes, key=lambda item: item[0])]

        visited = np.zeros_like(mask, dtype=bool)
        boxes = []
        for start_y, start_x in zip(*np.where(mask > 0)):
            if visited[start_y, start_x]:
                continue
            stack = [(int(start_x), int(start_y))]
            visited[start_y, start_x] = True
            points = []
            while stack:
                x, y = stack.pop()
                points.append((x, y))
                for yy in range(max(0, y - 1), min(mask.shape[0], y + 2)):
                    for xx in range(max(0, x - 1), min(mask.shape[1], x + 2)):
                        if mask[yy, xx] and not visited[yy, xx]:
                            visited[yy, xx] = True
                            stack.append((xx, yy))
            xs, ys = zip(*points)
            x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
            if y1 - y0 >= max(7, round(mask.shape[0] * 0.25)) and x1 - x0 >= 2 and len(points) >= 12:
                boxes.append((x0, mask[y0:y1, x0:x1]))
        return [glyph for _x, glyph in sorted(boxes, key=lambda item: item[0])]

    @staticmethod
    def _normalize_glyph(mask: np.ndarray) -> np.ndarray:
        target_size = (16, 24)
        image = Image.fromarray((mask > 0).astype(np.uint8) * 255)
        return (np.asarray(image.resize(target_size, Image.Resampling.NEAREST)) > 0).astype(np.uint8)

    @classmethod
    def _recognize_digit(cls, glyph: np.ndarray) -> int:
        global _DIGIT_TEMPLATES
        if _DIGIT_TEMPLATES is None:
            _DIGIT_TEMPLATES = {digit: [] for digit in range(10)}
            font_paths = [
                Path("C:/Windows/Fonts/segoeuib.ttf"),
                Path("C:/Windows/Fonts/arialbd.ttf"),
                Path("C:/Windows/Fonts/calibrib.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
            ]
            fonts = []
            for font_path in font_paths:
                if font_path.exists():
                    fonts.append(ImageFont.truetype(str(font_path), 28))
            if not fonts:
                fonts.append(ImageFont.load_default())
            for digit in range(10):
                for font in fonts:
                    canvas = Image.new("L", (40, 50), 0)
                    ImageDraw.Draw(canvas).text((2, -2), str(digit), font=font, fill=255)
                    rendered = (np.asarray(canvas) > 100).astype(np.uint8)
                    ys, xs = np.where(rendered > 0)
                    if len(xs):
                        cropped = rendered[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                        _DIGIT_TEMPLATES[digit].append(cls._normalize_glyph(cropped))
        normalized = cls._normalize_glyph(glyph)
        scores = {
            digit: max(float((normalized == template).mean()) for template in templates)
            for digit, templates in _DIGIT_TEMPLATES.items()
        }
        return max(scores, key=scores.get)

    @staticmethod
    def classify_patch(patch: np.ndarray) -> CellState:
        if patch.size == 0:
            return CellState.UNKNOWN
        if cv2 is not None:
            hsv = cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_RGB2HSV)
            # Blue/purple reward glyphs have high saturation and a bright
            # enough value compared with the brown/tan board tiles. The
            # yellow acquisition icon uses a separate narrow hue range.
            hue = hsv[:, :, 0]
            colorful_mask = (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 80) & (hue >= 100) & (hue <= 175)
            yellow_icon_mask = (hsv[:, :, 1] > 110) & (hsv[:, :, 2] > 125) & (hue >= 20) & (hue <= 50)
            if float(colorful_mask.mean()) > 0.025 or float(yellow_icon_mask.mean()) > 0.20:
                return CellState.REWARD_FOUND
        red, green, blue = [patch[:, :, i].astype(int) for i in range(3)]
        # Reward glyphs in Sample_Board.png are high-saturation blue/purple
        # pixels. This catches both the crystal and the EXP-style icon.
        colorful = ((blue > red + 25) & (blue > green + 5) & (blue > 80)) | ((red > 100) & (blue > green + 15) & (blue > 80))
        if colorful.mean() > 0.025:
            return CellState.REWARD_FOUND
        # NumPy-only HSV equivalent for environments without OpenCV. Tan
        # stone tiles have a hue below this range, while the missed yellow
        # acquisition icon occupies more than 20% of its cell patch.
        rgb = patch.astype(float) / 255.0
        maximum = rgb.max(axis=2)
        minimum = rgb.min(axis=2)
        delta = maximum - minimum
        saturation = np.divide(delta, maximum, out=np.zeros_like(delta), where=maximum > 0)
        hue_degrees = np.zeros_like(maximum)
        nonzero = delta > 0
        red_max = nonzero & (rgb[:, :, 0] == maximum)
        green_max = nonzero & (rgb[:, :, 1] == maximum)
        blue_max = nonzero & (rgb[:, :, 2] == maximum)
        hue_degrees[red_max] = 60 * np.mod((rgb[:, :, 1][red_max] - rgb[:, :, 2][red_max]) / delta[red_max], 6)
        hue_degrees[green_max] = 60 * (((rgb[:, :, 2][green_max] - rgb[:, :, 0][green_max]) / delta[green_max]) + 2)
        hue_degrees[blue_max] = 60 * (((rgb[:, :, 0][blue_max] - rgb[:, :, 1][blue_max]) / delta[blue_max]) + 4)
        yellow_icon = (saturation > (110 / 255)) & (maximum > (125 / 255)) & (hue_degrees >= 40) & (hue_degrees <= 100)
        if float(yellow_icon.mean()) > 0.20:
            return CellState.REWARD_FOUND
        center = patch[patch.shape[0] // 2, patch.shape[1] // 2].astype(int)
        # Open brown cells have a significantly lower green channel than the
        # tan stone tiles used for unrevealed cells.
        if center[1] < 112 and center[0] < 175:
            return CellState.NO_REWARD
        return CellState.UNKNOWN
