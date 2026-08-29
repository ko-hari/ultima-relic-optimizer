from __future__ import annotations

from dataclasses import dataclass

from models.board import Board, hypergeometric_all_successes, hypergeometric_at_least_one
from models.item import ITEM_DEFINITIONS
from .effects import affected_positions, candidate_targets


@dataclass(frozen=True)
class Evaluation:
    item: str
    target: tuple[int, int] | None
    expected_newly_explored_cells: float
    expected_rewards: float
    probability_of_at_least_one_reward: float
    probability_of_completion: float
    score: float
    reason: str
    next_lazer_x_cells: float = 0.0
    next_lazer_y_cells: float = 0.0
    next_lazer_average_cells: float = 0.0

    def as_dict(self) -> dict:
        return {
            "item": self.item,
            "target_x": None if self.target is None else self.target[0],
            "target_y": None if self.target is None else self.target[1],
            "expected_newly_explored_cells": self.expected_newly_explored_cells,
            "expected_rewards": self.expected_rewards,
            "probability_of_at_least_one_reward": self.probability_of_at_least_one_reward,
            "probability_of_completion": self.probability_of_completion,
            "score": self.score,
            "reason": self.reason,
            "next_lazer_x_cells": self.next_lazer_x_cells,
            "next_lazer_y_cells": self.next_lazer_y_cells,
            "next_lazer_average_cells": self.next_lazer_average_cells,
        }


OBJECTIVE_WEIGHTS = {
    "maximize_expected_rewards": (1.0, 0.0, 0.0),
    "maximize_explored_cells": (0.0, 1.0, 0.0),
    "maximize_completion_probability": (0.0, 0.0, 1.0),
    "balanced": (0.5, 0.2, 0.3),
}


def next_lazer_potential(board: Board, newly_revealed: set[tuple[int, int]]) -> tuple[int, int, float]:
    """Return the best X/Y line sizes after the current action is applied.

    The next item is assumed to be Lazer X or Lazer Y with equal probability,
    so their average is used only as a tie-breaker between otherwise equal
    current actions.
    """
    remaining_unknown = {
        (cell.x, cell.y)
        for cell in board.unknown_cells
        if (cell.x, cell.y) not in newly_revealed
    }
    best_x = max(
        (sum(y == row for _x, y in remaining_unknown) for row in range(board.height)),
        default=0,
    )
    best_y = max(
        (sum(x == column for x, _y in remaining_unknown) for column in range(board.width)),
        default=0,
    )
    return best_x, best_y, (best_x + best_y) / 2


def evaluate_candidate(board: Board, item_name: str, target: tuple[int, int] | None, objective: str = "balanced") -> Evaluation:
    item = ITEM_DEFINITIONS[item_name]
    unknown = board.unknown_count
    remaining = board.remaining_rewards
    next_lazer_x_cells = 0.0
    next_lazer_y_cells = 0.0
    next_lazer_average_cells = 0.0
    if item.effect_type == "global_reward_scan":
        affected_count = unknown
        at_least_one = 1.0 if remaining > 0 else 0.0
        completion = 1.0
        expected_rewards = float(remaining * item.multiplier)
        reason = "모든 미확인 칸에서 보상을 즉시 탐색하므로 보드가 종료됩니다."
    elif item.selection == "random_unknown_cell":
        centers = candidate_targets(board, item_name)
        # The random center is uniform over every eligible unknown cell.
        # Compute the expectation over concrete 3x3 effects.
        all_positions = [affected_positions(board, item_name, (c.x, c.y)) for c in board.unknown_cells]
        counts = [len(p) for p in all_positions]
        affected_count = sum(counts) / len(counts) if counts else 0.0
        expected_rewards = affected_count * board.probability_of_reward() * item.multiplier
        at_least_one = sum(
            hypergeometric_at_least_one(unknown, remaining, count) for count in counts
        ) / len(counts) if counts else 0.0
        completion = sum(
            hypergeometric_all_successes(unknown, remaining, count) for count in counts
        ) / len(counts) if counts else 0.0
        reason = "중심이 무작위이므로 가능한 모든 중심의 기대값으로 계산했습니다."
    else:
        positions = affected_positions(board, item_name, target)
        affected_count = len(positions)
        expected_rewards = affected_count * board.probability_of_reward() * item.multiplier
        at_least_one = hypergeometric_at_least_one(unknown, remaining, affected_count)
        completion = hypergeometric_all_successes(unknown, remaining, affected_count)
        label = "3×3 영역" if item.effect_type == "area" else "전체 행" if item.axis == "x" else "전체 열"
        reason = f"{label}에서 {affected_count}개의 미확인 칸을 새로 탐색할 기대값이 가장 높습니다."
        if item.effect_type == "area":
            next_lazer_x_cells, next_lazer_y_cells, next_lazer_average_cells = next_lazer_potential(board, positions)
            reason += (
                f" 이후 최적 Lazer X는 {next_lazer_x_cells}칸, "
                f"Lazer Y는 {next_lazer_y_cells}칸을 탐색할 수 있습니다."
            )
        if item.multiplier > 1:
            reason += " 새로 발견한 보상은 2배로 계산했습니다."
    reward_norm = expected_rewards / max(1.0, remaining * max(1, item.multiplier))
    explored_norm = affected_count / max(1, unknown)
    weights = OBJECTIVE_WEIGHTS.get(objective, OBJECTIVE_WEIGHTS["balanced"])
    score = weights[0] * reward_norm + weights[1] * explored_norm + weights[2] * completion
    return Evaluation(
        item_name,
        target,
        affected_count,
        expected_rewards,
        at_least_one,
        completion,
        score,
        reason,
        next_lazer_x_cells,
        next_lazer_y_cells,
        next_lazer_average_cells,
    )


def evaluate_item(board: Board, item_name: str, objective: str = "balanced") -> list[Evaluation]:
    return [evaluate_candidate(board, item_name, target, objective) for target in candidate_targets(board, item_name)]
