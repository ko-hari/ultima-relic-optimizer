from models.board import Board
from models.cell import CellState


def test_supported_board_sizes_and_defaults():
    assert Board.create(5).reward_count == 8
    assert Board.create(10).reward_count == 32
    assert Board.create(15).reward_count == 72


def test_revealed_cells_update_remaining_rewards():
    board = Board.create(5)
    board.set_state(0, 0, CellState.REWARD_FOUND)
    board.set_state(1, 0, CellState.NO_REWARD)
    assert board.found_rewards == 1
    assert board.remaining_rewards == 7
    assert board.unknown_count == 23
