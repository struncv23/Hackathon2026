from __future__ import annotations

import math

import pygame

from .constants import (
    BOARD_VIEW_PIXELS,
    BOARD_LEFT,
    BOARD_TOP,
    SQUARE_SIZE,
    VIEW_SIZE,
    WHITE,
)
from .effects import Effects, SoftGlowEffects
from .models import Move, Piece
from .rules import ChessGame
from .textures import SceneTextures

class BoardRenderer:
    def __init__(
        self,
        effects: Effects | None = None,
        textures: SceneTextures | None = None,
    ) -> None:
        self.effects = effects or SoftGlowEffects()
        self.textures = textures or SceneTextures()
        self.coordinate_font = pygame.font.SysFont("segoeui", 9, bold=True)
        self.glyph_font = pygame.font.SysFont("segoeuisymbol", 32)

    def draw(
        self,
        surface: pygame.Surface,
        game: ChessGame,
        selected: tuple[int, int] | None,
        legal_moves: list[Move],
        checked_king: tuple[int, int] | None,
        now: float,
        mines: dict[tuple[int, int], str] | None = None,
        health_animations: dict[
            tuple[int, int], tuple[int, int, float]
        ] | None = None,
        damage_popups: list[tuple[tuple[int, int], int, float]] | None = None,
        camera: tuple[float, float] = (0, 0),
        *,
        square_size: int = SQUARE_SIZE,
        board_origin: tuple[int, int] = (BOARD_LEFT, BOARD_TOP),
        loot: dict[tuple[int, int], int] | None = None,
        shop_tiles: dict[tuple[int, int], str] | None = None,
        buildings: dict[tuple[int, int], tuple[str, str, bool]] | None = None,
        viewport_rect: pygame.Rect | None = None,
    ) -> None:
        destinations = {move.end for move in legal_moves}
        mines = mines or {}
        loot = loot or {}
        shop_tiles = shop_tiles or {}
        buildings = buildings or {}
        health_animations = health_animations or {}
        damage_popups = damage_popups or []
        camera_row, camera_col = camera
        origin_x, origin_y = board_origin
        board_size = game.board_size
        self.textures.draw_background(surface)
        previous_clip = surface.get_clip()
        surface.set_clip(
            viewport_rect
            or pygame.Rect(
                BOARD_LEFT,
                BOARD_TOP,
                BOARD_VIEW_PIXELS,
                BOARD_VIEW_PIXELS,
            )
        )
        for row in range(
            max(0, math.floor(camera_row)),
            min(board_size, math.ceil(camera_row + VIEW_SIZE)),
        ):
            for col in range(
                max(0, math.floor(camera_col)),
                min(board_size, math.ceil(camera_col + VIEW_SIZE)),
            ):
                rect = pygame.Rect(
                    round(origin_x + (col - camera_col) * square_size),
                    round(origin_y + (row - camera_row) * square_size),
                    square_size,
                    square_size,
                )
                is_light = (row + col) % 2 == 0
                self.textures.draw_board_square(surface, rect, light=is_light)
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
                if (row, col) in mines:
                    self._draw_mine(surface, rect)
                if (row, col) in loot:
                    self._draw_loot(surface, rect, loot[(row, col)])
                if (row, col) in shop_tiles:
                    self._draw_shop_tile(surface, rect, shop_tiles[(row, col)])
                if piece is not None:
                    self._draw_piece(
                        surface,
                        rect,
                        piece,
                        health_animations.get((row, col)),
                        now,
                    )
                if col == 0:
                    label = self.coordinate_font.render(
                        str(board_size - row), True, (35, 48, 43)
                    )
                    surface.blit(label, (rect.x + 4, rect.y + 3))
                if row == board_size - 1:
                    label = self.coordinate_font.render(
                        str(col + 1), True, (35, 48, 43)
                    )
                    surface.blit(
                        label,
                        (rect.right - label.get_width() - 4, rect.bottom - 18),
                    )
        self._draw_buildings(surface, buildings, camera, square_size, board_origin)
        self._draw_damage_popups(
            surface, damage_popups, now, camera, square_size, board_origin
        )
        surface.set_clip(previous_clip)

    @staticmethod
    def _draw_loot(surface: pygame.Surface, rect: pygame.Rect, value: int) -> None:
        center = (rect.centerx, rect.centery)
        radius = max(4, rect.width // 4)
        pygame.draw.circle(surface, (71, 54, 22), center, radius + 1)
        pygame.draw.circle(surface, (231, 185, 70), center, radius)
        label = pygame.font.SysFont("segoeui", max(8, rect.width // 3), bold=True)
        image = label.render(str(value // 100), True, (58, 45, 22))
        surface.blit(image, image.get_rect(center=center))

    @staticmethod
    def _draw_shop_tile(surface: pygame.Surface, rect: pygame.Rect, kind: str) -> None:
        colors = {
            "farm": (89, 137, 79),
            "city": (87, 125, 145),
            "armory": (163, 93, 73),
            "recruit": (164, 137, 74),
            "upgrade": (133, 107, 158),
            "war": (151, 71, 67),
        }
        pygame.draw.rect(surface, (31, 37, 34), rect)
        inset = rect.inflate(-4, -4)
        pygame.draw.rect(surface, colors.get(kind, (110, 110, 110)), inset)
        abbreviations = {
            "farm": "F",
            "city": "M",
            "armory": "Z",
            "recruit": "+",
            "upgrade": "^",
            "war": "!",
        }
        font = pygame.font.SysFont("segoeui", max(9, rect.width // 2), bold=True)
        label = font.render(abbreviations.get(kind, "?"), True, (255, 247, 220))
        surface.blit(label, label.get_rect(center=rect.center))

    @staticmethod
    def _draw_buildings(
        surface: pygame.Surface,
        buildings: dict[tuple[int, int], tuple[str, str, bool]],
        camera: tuple[float, float],
        square_size: int,
        board_origin: tuple[int, int],
    ) -> None:
        groups: dict[tuple[str, str, bool], list[tuple[int, int]]] = {}
        for square, building in buildings.items():
            groups.setdefault(building, []).append(square)

        names = {"farm": "FARMA", "city": "MESTO", "armory": "ZBROJNICE"}
        palettes = {
            "farm": ((57, 92, 54), (113, 164, 86)),
            "city": ((55, 76, 96), (103, 147, 172)),
            "armory": ((103, 58, 50), (174, 98, 76)),
        }
        for (kind, owner, owned), squares in groups.items():
            rows = [square[0] for square in squares]
            cols = [square[1] for square in squares]
            top, left = min(rows), min(cols)
            rect = pygame.Rect(
                round(board_origin[0] + (left - camera[1]) * square_size),
                round(board_origin[1] + (top - camera[0]) * square_size),
                (max(cols) - left + 1) * square_size,
                (max(rows) - top + 1) * square_size,
            )
            unowned_color, owned_color = palettes[kind]
            color = owned_color if owned else unowned_color
            if owner == "black":
                color = tuple(max(0, channel - 18) for channel in color)
            pygame.draw.rect(surface, (25, 31, 28), rect)
            pygame.draw.rect(surface, color, rect.inflate(-3, -3))
            for row in range(1, 4):
                y = rect.y + row * square_size
                pygame.draw.line(surface, (34, 42, 37), (rect.x, y), (rect.right, y), 2)
            for col in range(1, 3):
                x = rect.x + col * square_size
                pygame.draw.line(surface, (34, 42, 37), (x, rect.y), (x, rect.bottom), 2)
            font = pygame.font.SysFont("segoeui", max(8, square_size // 2), bold=True)
            label = font.render(names[kind], True, (255, 246, 222))
            label.set_alpha(255 if owned else 145)
            surface.blit(label, label.get_rect(center=rect.center))

    def _draw_piece(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        piece: Piece,
        health_animation: tuple[int, int, float] | None,
        now: float,
    ) -> None:
        center = rect.center
        radius = max(3, rect.width // 3)
        if piece.color == WHITE:
            fill, highlight, ink = (226, 217, 193), (255, 250, 228), (41, 52, 48)
        else:
            fill, highlight, ink = (43, 54, 51), (91, 108, 98), (244, 236, 216)
        pygame.draw.circle(surface, (22, 29, 27), (center[0], center[1] + 1), radius + 1)
        pygame.draw.circle(surface, (166, 132, 73), center, radius + 1)
        pygame.draw.circle(surface, fill, center, radius)
        pygame.draw.circle(
            surface,
            highlight,
            (center[0] - radius // 3, center[1] - radius // 3),
            max(2, radius // 2),
            1,
        )
        glyphs = {
            WHITE: {
                "K": "\u2654", "Q": "\u2655", "R": "\u2656",
                "B": "\u2657", "N": "\u2658", "P": "\u2659",
            },
            "black": {
                "K": "\u265a", "Q": "\u265b", "R": "\u265c",
                "B": "\u265d", "N": "\u265e", "P": "\u265f",
            },
        }
        glyph = self.glyph_font.render(glyphs[piece.color][piece.kind], True, ink)
        glyph_size = max(8, rect.width - 2)
        glyph = pygame.transform.smoothscale(glyph, (glyph_size, glyph_size))
        surface.blit(glyph, glyph.get_rect(center=center))
        health_width = max(6, rect.width - 4)
        health_height = max(1, rect.height // 8)
        health_rect = pygame.Rect(
            rect.centerx - health_width // 2,
            rect.bottom - health_height - 1,
            health_width,
            health_height,
        )
        pygame.draw.rect(surface, (31, 37, 34), health_rect)
        ratio = self._health_ratio(piece, health_animation, now)
        if ratio > 0:
            health_color = (
                int(224 * (1 - ratio) + 72 * ratio),
                int(65 * (1 - ratio) + 190 * ratio),
                70,
            )
            fill_rect = health_rect.copy()
            fill_rect.width = max(1, int(health_width * ratio))
            pygame.draw.rect(surface, health_color, fill_rect)
        if piece.upgrades:
            pygame.draw.circle(
                surface,
                (245, 194, 75),
                (rect.right - 4, rect.y + 4),
                max(1, rect.width // 12),
            )

    @staticmethod
    def _draw_destination(
        surface: pygame.Surface, rect: pygame.Rect, is_capture: bool
    ) -> None:
        if is_capture:
            pygame.draw.circle(
                surface,
                (51, 56, 49),
                rect.center,
                max(2, rect.width // 2 - 2),
                width=2,
            )
        else:
            pygame.draw.circle(
                surface, (51, 56, 49), rect.center, max(2, rect.width // 8)
            )

    @staticmethod
    def _draw_mine(surface: pygame.Surface, rect: pygame.Rect) -> None:
        center = (rect.right - 5, rect.y + 5)
        pygame.draw.circle(surface, (35, 24, 24), center, 4)
        pygame.draw.circle(surface, (210, 70, 57), center, 3)
        pygame.draw.circle(surface, (255, 219, 125), center, 1)

    @staticmethod
    def _health_ratio(
        piece: Piece,
        animation: tuple[int, int, float] | None,
        now: float,
    ) -> float:
        if animation is None:
            return max(0.0, min(1.0, (piece.health or 0) / piece.max_health))
        start, end, started_at = animation
        progress = min(1.0, max(0.0, (now - started_at) / 0.45))
        eased = progress * progress * (3 - 2 * progress)
        health = start + (end - start) * eased
        return max(0.0, min(1.0, health / piece.max_health))

    @staticmethod
    def _draw_damage_popups(
        surface: pygame.Surface,
        popups: list[tuple[tuple[int, int], int, float]],
        now: float,
        camera: tuple[float, float],
        square_size: int,
        board_origin: tuple[int, int],
    ) -> None:
        font = pygame.font.SysFont("segoeui", max(9, square_size // 2), bold=True)
        origin_x, origin_y = board_origin
        for (row, col), damage, started_at in popups:
            progress = (now - started_at) / 0.65
            if not 0 <= progress < 1:
                continue
            label = font.render(f"-{damage}", True, (255, 110, 95))
            label.set_alpha(round(255 * (1 - progress)))
            position = (
                round(origin_x + (col - camera[1]) * square_size)
                + (square_size - label.get_width()) // 2,
                round(origin_y + (row - camera[0]) * square_size)
                - int(progress * square_size),
            )
            surface.blit(label, position)
