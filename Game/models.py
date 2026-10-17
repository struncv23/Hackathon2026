from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Piece:
    color: str
    kind: str
    level: int = 1
    experience: int = 0


@dataclass(frozen=True)
class Move:
    start: tuple[int, int]
    end: tuple[int, int]
    promotion: str | None = None
    en_passant: bool = False
    castle: bool = False
