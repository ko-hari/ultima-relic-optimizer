from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Iterable, Iterator, Optional

from .cell import Cell, CellState


SUPPORTED_SIZES = {(5, 5): 8, (10, 10): 32, (15, 15): 72}


@dataclass
class Board:
    """Known board state plus the conditional reward distribution.

    The board does not need to know the location of undiscovered rewards. For
    simulations, ``hidden_rewards`` is populated on a clone using the uniform
    conditional distribution described in the specification.
    """

    width: int
    height: int
    reward_count: int
    cells: list[Cell] = field(default_factory=list)
    hidden_rewards: set[tuple[int, int]] | None = None

    def __post_init__(self) -> None:
        if (self.width, self.height) not in SUPPORTED_SIZES:
            raise ValueError("Supported board sizes are 5x5, 10x10, and 15x15")
        if not self.cells:
            self.cells = [
                Cell(x, y)
                for y in range(self.height)
                for x in range(self.width)
            ]
        if len(self.cells) != self.width * self.height:
            raise ValueError("cells must contain width * height cells")
        if not 0 <= self.reward_count <= self.width * self.height:
            raise ValueError("reward_count is outside the board")
        if self.remaining_rewards < 0:
            raise ValueError("revealed rewards exceed reward_count")

    @classmethod
    def create(cls, size: int, reward_count: int | None = None) -> "Board":
        if (size, size) not in SUPPORTED_SIZES:
            raise ValueError("size must be 5, 10, or 15")
        if reward_count is None:
            reward_count = SUPPORTED_SIZES[(size, size)]
        return cls(size, size, reward_count)

    def clone(self) -> "Board":
        return Board(
            self.width,
            self.height,
            self.reward_count,
            [Cell(c.x, c.y, c.state) for c in self.cells],
            None if self.hidden_rewards is None else set(self.hidden_rewards),
        )

    def cell(self, x: int, y: int) -> Cell:
        if not self.in_bounds(x, y):
            raise IndexError(f"({x}, {y}) is outside the board")
        return self.cells[y * self.width + x]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def iter_cells(self) -> Iterator[Cell]:
        return iter(self.cells)

    @property
    def unknown_cells(self) -> list[Cell]:
        return [c for c in self.cells if c.state is CellState.UNKNOWN]

    @property
    def unknown_count(self) -> int:
        return len(self.unknown_cells)

    @property
    def found_rewards(self) -> int:
        return sum(c.state is CellState.REWARD_FOUND for c in self.cells)

    @property
    def remaining_rewards(self) -> int:
        return self.reward_count - self.found_rewards

    @property
    def is_complete(self) -> bool:
        return self.remaining_rewards == 0

    def set_state(self, x: int, y: int, state: CellState) -> None:
        self.cell(x, y).state = state if isinstance(state, CellState) else CellState(state)

    def reveal(self, positions: Iterable[tuple[int, int]]) -> tuple[int, int]:
        """Reveal eligible positions using a sampled hidden reward layout.

        Returns ``(newly_explored_cells, newly_found_rewards)``.
        """
        if self.hidden_rewards is None:
            raise RuntimeError("Call sample_hidden_rewards before reveal")
        explored = found = 0
        for x, y in positions:
            if not self.in_bounds(x, y):
                continue
            cell = self.cell(x, y)
            if cell.state is not CellState.UNKNOWN:
                continue
            explored += 1
            if (x, y) in self.hidden_rewards:
                cell.state = CellState.REWARD_FOUND
                found += 1
            else:
                cell.state = CellState.NO_REWARD
        return explored, found

    def sample_hidden_rewards(self, rng: random.Random) -> "Board":
        """Clone the state and place remaining rewards uniformly among unknowns."""
        clone = self.clone()
        if clone.remaining_rewards > clone.unknown_count:
            raise ValueError("The known board is inconsistent with reward_count")
        candidates = [(c.x, c.y) for c in clone.unknown_cells]
        clone.hidden_rewards = set(rng.sample(candidates, clone.remaining_rewards))
        return clone

    def apply_known_reward_layout(self, rewards: Iterable[tuple[int, int]]) -> None:
        """Attach a full hidden layout, useful for deterministic tests."""
        layout = set(rewards)
        if len(layout) != self.remaining_rewards:
            raise ValueError("layout must contain exactly the remaining reward count")
        if not all(self.in_bounds(*pos) and self.cell(*pos).can_be_selected for pos in layout):
            raise ValueError("layout contains an already revealed or invalid cell")
        self.hidden_rewards = layout

    def probability_of_reward(self) -> float:
        if self.unknown_count == 0:
            return 0.0
        return self.remaining_rewards / self.unknown_count


def hypergeometric_at_least_one(population: int, successes: int, draws: int) -> float:
    if draws <= 0 or successes <= 0 or population <= 0:
        return 0.0
    draws = min(draws, population)
    if draws >= population or successes >= population:
        return 1.0
    if population - successes < draws:
        return 1.0
    no_success = math.comb(population - successes, draws) / math.comb(population, draws)
    return 1.0 - no_success


def hypergeometric_all_successes(population: int, successes: int, draws: int) -> float:
    if successes <= 0:
        return 1.0
    if draws < successes or population <= 0:
        return 0.0
    if draws >= population:
        return 1.0
    return math.comb(draws, successes) / math.comb(population, successes)
