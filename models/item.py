from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ItemDefinition:
    name: str
    target_required: bool
    selection: Literal["manual", "random_unknown_cell", "none"]
    effect_type: Literal["area", "line", "global_reward_scan"]
    available_sizes: tuple[int, ...] = (5, 10, 15)
    multiplier: int = 1
    axis: str | None = None
    auto_activates: bool = False


ITEM_DEFINITIONS: dict[str, ItemDefinition] = {
    "Boom": ItemDefinition("Boom", True, "manual", "area"),
    "Special Boom": ItemDefinition("Special Boom", True, "manual", "area", multiplier=2),
    "Lazer X": ItemDefinition("Lazer X", True, "manual", "line", axis="x"),
    "Lazer Y": ItemDefinition("Lazer Y", True, "manual", "line", axis="y"),
    "Gunpowder Barrel": ItemDefinition("Gunpowder Barrel", False, "random_unknown_cell", "area", (10, 15), auto_activates=True),
    "Key": ItemDefinition("Key", False, "none", "global_reward_scan", auto_activates=True),
}

MANUAL_ITEM_NAMES = tuple(name for name, item in ITEM_DEFINITIONS.items() if not item.auto_activates)
