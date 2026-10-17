from __future__ import annotations

from dataclasses import dataclass

from .constants import PIECE_VALUES


@dataclass(frozen=True)
class Piece:
    color: str
    kind: str
    level: int = 1
    experience: int = 0
    health: int | None = None
    upgrades: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.health is None:
            object.__setattr__(self, "health", PIECE_VALUES[self.kind])

    @property
    def max_health(self) -> int:
        return PIECE_VALUES[self.kind]

    @property
    def value(self) -> int:
        return PIECE_VALUES[self.kind]


@dataclass(frozen=True)
class Move:
    start: tuple[int, int]
    end: tuple[int, int]
    promotion: str | None = None
    en_passant: bool = False
    castle: bool = False
