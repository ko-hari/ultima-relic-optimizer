from __future__ import annotations

from engine.probability import Evaluation
from models.board import Board
from .exhaustive import exhaustive_recommendations


def greedy_recommendations(board: Board, inventory: dict[str, int], objective: str = "balanced", top_n: int = 5) -> list[Evaluation]:
    """Greedy one-action baseline; inventory quantities gate availability."""
    return exhaustive_recommendations(board, inventory, objective, top_n)
