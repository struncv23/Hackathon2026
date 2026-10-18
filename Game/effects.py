from __future__ import annotations

from functools import lru_cache
from math import sin
from typing import Protocol

import pygame


@lru_cache(maxsize=128)
def _selection_overlay(
    width: int,
    height: int,
    color: tuple[int, int, int, int],
) -> pygame.Surface:
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay.fill(color)
    return overlay


class Effects(Protocol):
    def draw(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        selected: bool,
        checked: bool,
        time_seconds: float,
    ) -> None: ...


class SoftGlowEffects:
    """Replace this class with custom animations or a GPU/OpenGL renderer."""

    def draw(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        selected: bool,
        checked: bool,
        time_seconds: float,
    ) -> None:
        if not selected and not checked:
            return
        pulse = pygame.time.get_ticks() / 1100
        alpha = 70 + int(35 * sin(pulse * 2 * 3.14159))
        color = (236, 181, 67, alpha) if selected else (219, 72, 72, alpha)
        overlay = _selection_overlay(rect.width, rect.height, color)
        surface.blit(overlay, rect.topleft)
        pygame.draw.rect(
            surface,
            (247, 205, 99) if selected else (244, 100, 100),
            rect,
            width=3,
        )
