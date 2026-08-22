from __future__ import annotations

from dataclasses import dataclass
import random

from engine.effects import resolve_item
from models.board import Board


@dataclass(frozen=True)
class SimulationResult:
    iterations: int
    expected_newly_explored_cells: float
    expected_rewards: float
    probability_of_at_least_one_reward: float
    probability_of_completion: float


def simulate(board: Board, item_name: str, target, iterations: int = 10000, seed: int = 42) -> SimulationResult:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    rng = random.Random(seed)
    total_explored = total_rewards = 0
    any_reward = completed = 0
    for _ in range(iterations):
        sampled = board.sample_hidden_rewards(rng)
        explored, rewards, _value, _actual_target = resolve_item(sampled, item_name, target, rng)
        total_explored += explored
        total_rewards += rewards
        any_reward += rewards > 0
        completed += sampled.is_complete
    return SimulationResult(
        iterations,
        total_explored / iterations,
        total_rewards / iterations,
        any_reward / iterations,
        completed / iterations,
    )
