from __future__ import annotations

from typing import Iterable

from models.board import Board
from models.cell import CellState
from models.item import ITEM_DEFINITIONS, ItemDefinition


def affected_positions(board: Board, item_name: str, target: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    """Return eligible unknown cells affected by an item."""
    item = ITEM_DEFINITIONS[item_name]
    if item.effect_type == "global_reward_scan":
        return {(c.x, c.y) for c in board.unknown_cells}
    if item.selection == "random_unknown_cell":
        if target is None:
            raise ValueError("Gunpowder Barrel needs a center for a concrete effect")
    elif item.target_required and target is None:
        raise ValueError(f"{item_name} requires a target")
    if target is None:
        return set()
    x, y = target
    if not board.in_bounds(x, y) or board.cell(x, y).state is not CellState.UNKNOWN:
        return set()
    if item.effect_type == "area":
        candidates = {
            (xx, yy)
            for yy in range(y - 1, y + 2)
            for xx in range(x - 1, x + 2)
            if board.in_bounds(xx, yy)
        }
    elif item.effect_type == "line" and item.axis == "x":
        candidates = {(xx, y) for xx in range(board.width)}
    elif item.effect_type == "line" and item.axis == "y":
        candidates = {(x, yy) for yy in range(board.height)}
    else:
        candidates = set()
    return {pos for pos in candidates if board.cell(*pos).state is CellState.UNKNOWN}


def candidate_targets(board: Board, item_name: str) -> list[tuple[int, int] | None]:
    item = ITEM_DEFINITIONS[item_name]
    if item.selection == "none":
        return [None]
    if item.selection == "random_unknown_cell":
        return [None]
    if item.effect_type == "line" and item.axis == "x":
        # Every target in the same row has an identical effect. Keep the
        # unknown cell nearest the horizontal center as the representative.
        center_x = (board.width - 1) / 2
        targets = []
        for y in range(board.height):
            row = [cell for cell in board.unknown_cells if cell.y == y]
            if row:
                cell = min(row, key=lambda candidate: (abs(candidate.x - center_x), candidate.x))
                targets.append((cell.x, cell.y))
        return targets
    if item.effect_type == "line" and item.axis == "y":
        # Every target in the same column has an identical effect. Keep the
        # unknown cell nearest the vertical center as the representative.
        center_y = (board.height - 1) / 2
        targets = []
        for x in range(board.width):
            column = [cell for cell in board.unknown_cells if cell.x == x]
            if column:
                cell = min(column, key=lambda candidate: (abs(candidate.y - center_y), candidate.y))
                targets.append((cell.x, cell.y))
        return targets
    return [(c.x, c.y) for c in board.unknown_cells]


def resolve_item(board: Board, item_name: str, target: tuple[int, int] | None, rng) -> tuple[int, int, int, tuple[int, int] | None]:
    """Resolve an item on a sampled board; returns explored, rewards, value, actual center."""
    item = ITEM_DEFINITIONS[item_name]
    actual_target = target
    if item.selection == "random_unknown_cell":
        eligible = board.unknown_cells
        if not eligible:
            return 0, 0, 0, None
        chosen = rng.choice(eligible)
        actual_target = (chosen.x, chosen.y)
    positions = affected_positions(board, item_name, actual_target)
    if item.effect_type == "global_reward_scan":
        positions = {(c.x, c.y) for c in board.unknown_cells}
    explored, rewards = board.reveal(positions)
    return explored, rewards, rewards * item.multiplier, actual_target
