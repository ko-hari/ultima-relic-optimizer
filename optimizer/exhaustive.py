from __future__ import annotations

from engine.probability import Evaluation, evaluate_item
from models.board import Board
from models.item import ITEM_DEFINITIONS


def exhaustive_recommendations(board: Board, inventory: dict[str, int], objective: str = "balanced", top_n: int = 5) -> list[Evaluation]:
    """Enumerate every valid item/target pair and return the best candidates."""
    evaluations: list[Evaluation] = []
    for item_name, quantity in inventory.items():
        if quantity <= 0 or item_name not in ITEM_DEFINITIONS:
            continue
        definition = ITEM_DEFINITIONS[item_name]
        if definition.auto_activates or board.width not in definition.available_sizes:
            continue
        evaluations.extend(evaluate_item(board, item_name, objective))
    evaluations.sort(
        key=lambda e: (
            e.score,
            e.expected_rewards,
            e.expected_newly_explored_cells,
            e.next_lazer_average_cells,
        ),
        reverse=True,
    )
    return evaluations[:top_n]
