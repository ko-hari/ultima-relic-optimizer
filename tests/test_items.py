from engine.effects import affected_positions
from models.board import Board


def test_area_and_line_effects_ignore_revealed_cells():
    board = Board.create(5)
    board.set_state(0, 1, "no_reward")
    assert len(affected_positions(board, "Boom", (1, 1))) == 8
    assert len(affected_positions(board, "Lazer X", (1, 1))) == 4
    board.set_state(1, 0, "no_reward")
    assert len(affected_positions(board, "Lazer Y", (1, 1))) == 4


def test_key_targets_all_unknown_cells():
    board = Board.create(5)
    assert len(affected_positions(board, "Key")) == 25
