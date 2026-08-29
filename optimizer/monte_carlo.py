from __future__ import annotations

from engine.probability import Evaluation
from engine.simulator import simulate
from models.board import Board
from optimizer.exhaustive import exhaustive_recommendations


def monte_carlo_recommendations(board: Board, inventory: dict[str, int], objective: str = "balanced", top_n: int = 5, iterations: int = 10000, seed: int = 42) -> list[Evaluation]:
    """Rank analytically promising candidates, then validate them by simulation."""
    candidates = exhaustive_recommendations(board, inventory, objective, top_n=max(top_n * 3, 10))
    output: list[Evaluation] = []
    for index, candidate in enumerate(candidates):
        result = simulate(board, candidate.item, candidate.target, iterations, seed + index)
        output.append(Evaluation(
            candidate.item, candidate.target,
            result.expected_newly_explored_cells,
            result.expected_rewards * __import__("models.item", fromlist=["ITEM_DEFINITIONS"]).ITEM_DEFINITIONS[candidate.item].multiplier,
            result.probability_of_at_least_one_reward,
            result.probability_of_completion,
            candidate.score,
            candidate.reason + f" Monte Carlo {iterations:,}회로 검증했습니다.",
            candidate.next_lazer_x_cells,
            candidate.next_lazer_y_cells,
            candidate.next_lazer_average_cells,
        ))
    output.sort(
        key=lambda e: (
            e.score,
            e.expected_rewards,
            e.expected_newly_explored_cells,
            e.next_lazer_average_cells,
        ),
        reverse=True,
    )
    return output[:top_n]
