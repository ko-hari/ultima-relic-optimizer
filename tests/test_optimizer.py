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
