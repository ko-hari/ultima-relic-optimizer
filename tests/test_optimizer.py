from optimizer.exhaustive import exhaustive_recommendations
from engine.effects import candidate_targets
from models.board import Board


def test_top_five_recommendations_are_sorted():
    result = exhaustive_recommendations(Board.create(5), {"Boom": 1, "Lazer X": 1}, top_n=5)
    assert 0 < len(result) <= 5
    assert all(result[i].score >= result[i + 1].score for i in range(len(result) - 1))


def test_lazer_targets_are_unique_per_effect_axis():
    board = Board.create(5)
    lazer_x = candidate_targets(board, "Lazer X")
    lazer_y = candidate_targets(board, "Lazer Y")
    assert len(lazer_x) == board.height
    assert len({y for _x, y in lazer_x}) == board.height
    assert len(lazer_y) == board.width
    assert len({x for x, _y in lazer_y}) == board.width


def test_automatic_items_are_not_recommendation_candidates():
    result = exhaustive_recommendations(
        Board.create(10),
        {"Boom": 1, "Gunpowder Barrel": 1, "Key": 1},
        top_n=20,
    )
    assert result
    assert {item.item for item in result} == {"Boom"}


def test_area_target_keeps_current_coverage_first_then_preserves_next_lazers():
    board = Board.create(5)
    for x, y in {
        (4, 0),
        (2, 2),
        (0, 4),
        (1, 0),
        (2, 0),
        (2, 3),
        (3, 0),
        (1, 2),
    }:
        board.set_state(x, y, "no_reward")

    results = exhaustive_recommendations(board, {"Boom": 1}, top_n=25)
    top = results[0]

    assert top.target == (3, 3)
    assert top.expected_newly_explored_cells == 7
    assert top.next_lazer_x_cells == 5
    assert top.next_lazer_y_cells == 4
    assert top.next_lazer_average_cells == 4.5

    same_coverage_weaker_future = next(item for item in results if item.target == (3, 2))
    assert same_coverage_weaker_future.expected_newly_explored_cells == 7
    assert same_coverage_weaker_future.next_lazer_average_cells == 4.0
