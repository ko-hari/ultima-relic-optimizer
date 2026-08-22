from engine.probability import evaluate_candidate
from models.board import Board


def test_edge_area_is_smaller_than_center_area():
    board = Board.create(5)
    edge = evaluate_candidate(board, "Boom", (0, 0))
    center = evaluate_candidate(board, "Boom", (2, 2))
    assert edge.expected_newly_explored_cells == 4
    assert center.expected_newly_explored_cells == 9


def test_key_completes_board():
    evaluation = evaluate_candidate(Board.create(5), "Key", None)
    assert evaluation.probability_of_completion == 1.0
    assert evaluation.expected_rewards == 8
