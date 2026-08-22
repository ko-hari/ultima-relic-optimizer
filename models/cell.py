from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CellState(str, Enum):
    UNKNOWN = "unknown"
    REWARD_FOUND = "reward_found"
    NO_REWARD = "no_reward"


@dataclass
class Cell:
    """A board cell. Coordinates are zero-based (x=column, y=row)."""

    x: int
    y: int
    state: CellState = CellState.UNKNOWN

    @property
    def can_be_selected(self) -> bool:
        return self.state is CellState.UNKNOWN

    @property
    def affected_by_items(self) -> bool:
        return self.state is CellState.UNKNOWN
