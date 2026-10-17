from __future__ import annotations

import pygame

from .constants import BOARD_LEFT, BOARD_SIZE, BOARD_TOP, SQUARE_SIZE, WHITE
from .effects import Effects, SoftGlowEffects
from .models import Move, Piece
from .rules import ChessGame

class BoardRenderer:
    def __init__(self, effects: Effects | None = None) -> None:
        self.effects = effects or SoftGlowEffects()
        self.font = pygame.font.SysFont("segoeui", 38, bold=True)
        self.coordinate_font = pygame.font.SysFont("segoeui", 14, bold=True)
        self.light_square = (232, 222, 201)
        self.dark_square = (102, 126, 112)

    def draw(
        self,
        surface: pygame.Surface,
        game: ChessGame,
        selected: tuple[int, int] | None,
        legal_moves: list[Move],
        checked_king: tuple[int, int] | None,
        now: float,
    ) -> None:
        destinations = {move.end for move in legal_moves}
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                rect = pygame.Rect(
                    BOARD_LEFT + col * SQUARE_SIZE,
                    BOARD_TOP + row * SQUARE_SIZE,
                    SQUARE_SIZE,
                    SQUARE_SIZE,
                )
                is_light = (row + col) % 2 == 0
                pygame.draw.rect(
                    surface, self.light_square if is_light else self.dark_square, rect
                )
                piece = game.board[row][col]
                is_selected = selected == (row, col)
                is_checked = checked_king == (row, col)
                self.effects.draw(
                    surface,
                    rect,
                    selected=is_selected,
                    checked=is_checked,
                    time_seconds=now,
                )
                if (row, col) in destinations:
                    self._draw_destination(surface, rect, piece is not None)
                if piece is not None:
                    self._draw_piece(surface, rect, piece)
                if col == 0:
                    label = self.coordinate_font.render(
                        str(8 - row), True, (35, 48, 43)
                    )
                    surface.blit(label, (rect.x + 4, rect.y + 3))
                if row == 7:
                    label = self.coordinate_font.render(
                        chr(ord("a") + col), True, (35, 48, 43)
                    )
                    surface.blit(
                        label,
                        (rect.right - label.get_width() - 4, rect.bottom - 18),
                    )

    def _draw_piece(
        self, surface: pygame.Surface, rect: pygame.Rect, piece: Piece
    ) -> None:
        center = rect.center
        radius = 28
        if piece.color == WHITE:
            fill, ink, border = (250, 247, 237), (41, 52, 48), (67, 79, 71)
        else:
            fill, ink, border = (43, 54, 51), (244, 236, 216), (27, 35, 33)
        pygame.draw.circle(surface, border, center, radius + 3)
        pygame.draw.circle(surface, fill, center, radius)
        glyph = self.font.render(piece.kind, True, ink)
        surface.blit(glyph, glyph.get_rect(center=center))

    @staticmethod
    def _draw_destination(
        surface: pygame.Surface, rect: pygame.Rect, is_capture: bool
    ) -> None:
        if is_capture:
            pygame.draw.circle(surface, (51, 56, 49), rect.center, 34, width=4)
        else:
            pygame.draw.circle(surface, (51, 56, 49), rect.center, 9)
