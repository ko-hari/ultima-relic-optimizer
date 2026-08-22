import numpy as np
from PIL import Image

from image_analysis import BoardRegion, ScreenshotAnalyzer


def test_sample_detects_all_acquired_items():
    result = ScreenshotAnalyzer().analyze("Sample_Board.png")
    assert result.board.found_rewards == 23
    assert result.board.cell(0, 8).state.value == "reward_found"
    assert result.region.left == 8
    assert result.region.top == 36
    assert result.region.right == 384
    assert result.region.bottom == 411
    assert abs(result.region.cell_height - 25.0) < 0.01
    assert result.board.width == 15
    assert result.board.reward_count == 72
    assert result.inventory == {
        "Boom": 0,
        "Special Boom": 0,
        "Lazer X": 0,
        "Lazer Y": 0,
    }


def test_second_sample_is_detected_as_15_by_15():
    result = ScreenshotAnalyzer().analyze("Sample2.png")
    assert result.board.width == 15
    assert result.board.height == 15
    assert result.region.left == 6
    assert result.region.top == 36
    assert result.region.right == 390
    assert result.region.bottom == 411


def test_third_sample_keeps_the_full_15_by_15_board_region():
    result = ScreenshotAnalyzer().analyze("Sample3.png")
    assert result.board.width == 15
    assert result.board.height == 15
    assert result.region.left < 15
    assert result.region.right > 375


def test_fourth_sample_uses_the_board_frame_below_the_header():
    result = ScreenshotAnalyzer().analyze("Sample4.png")
    assert result.board.width == 15
    assert result.board.height == 15
    assert 30 <= result.region.top <= 36
    assert result.region.left < 15
    assert result.region.right > 375


def test_colored_reward_count_rules_out_small_late_game_boards():
    image = Image.open("Sample4.png").convert("RGB")
    rgb = np.asarray(image)
    region = ScreenshotAnalyzer(15).detect_region(image)
    counts = {
        size: ScreenshotAnalyzer._count_reward_cells(rgb, region, size)
        for size in (5, 10, 15)
    }
    assert counts[5] > 8 + 1
    assert counts[10] > 32 + 4
    assert ScreenshotAnalyzer().detect_region(image).width == 15


def test_colored_reward_layout_aligns_with_15_by_15_cell_centers():
    image = Image.open("Sample_Board.png").convert("RGB")
    rgb = np.asarray(image)
    region = ScreenshotAnalyzer(15).detect_region(image)
    alignment, reliable = ScreenshotAnalyzer._reward_layout_alignment(rgb, region)
    assert reliable is True
    assert min(alignment, key=alignment.get) == 15
    assert alignment[15] + 0.07 < min(alignment[5], alignment[10])


def test_sparse_color_layout_does_not_override_grid_edges():
    image = np.full((300, 300, 3), 120, dtype=np.uint8)
    image[145:155, 145:155] = (40, 80, 220)
    region = BoardRegion(0, 0, 300, 300, 15, 15)
    _alignment, reliable = ScreenshotAnalyzer._reward_layout_alignment(image, region)
    assert reliable is False


def test_grid_periodicity_detects_supported_board_sizes():
    region = BoardRegion(10, 10, 310, 310, 15, 15)
    for size in (5, 10, 15):
        image = np.full((320, 320, 3), 120, dtype=np.uint8)
        for index in range(size + 1):
            coordinate = round(10 + index * 300 / size)
            image[10:310, max(0, coordinate - 1):min(320, coordinate + 1)] = 245
            image[max(0, coordinate - 1):min(320, coordinate + 1), 10:310] = 245
        assert ScreenshotAnalyzer._infer_board_size(image, region) == size
