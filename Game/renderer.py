from __future__ import annotations

import math
from functools import lru_cache

import pygame

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "Game"

from .constants import (
    BOARD_VIEW_PIXELS,
    BOARD_LEFT,
    BOARD_TOP,
    SQUARE_SIZE,
    VIEW_SIZE,
    WHITE,
)
from .effects import Effects, SoftGlowEffects
from .localization import translate
from .models import Move, Piece
from .rules import ChessGame
from .textures import SceneTextures


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont("consolas", size, bold=bold)


class BoardRenderer:
    PIECE_PIXELS = {
        "K": (
            "0000000110000000", "0000000110000000", "0000111111110000",
            "0000111111110000", "0000000110000000", "0000000110000000",
            "0000000110000000", "0000000110000000", "0000011111100000",
            "0000111111110000", "0001111111111000", "0011111111111100",
            "0000001111000000", "0000011111100000", "0000111111110000",
            "0001111111111000",
        ),
        "Q": (
            "0000100000100000", "0000110001100000", "1000111111100001",
            "1100011111000011", "0110001110000110", "0011001110001100",
            "0001111111111000", "0000111111110000", "0000011111100000",
            "0000011111100000", "0000111111110000", "0001111111111000",
            "0011111111111100", "0111111111111110", "0111111111111110",
            "0011111111111100",
        ),
        "R": (
            "0011000110001100", "0011000110001100", "1111111111111111",
            "1111111111111111", "0001111111111000", "0001111111111000",
            "0001111111111000", "0001111111111000", "0001111111111000",
            "0001111111111000", "0001111111111000", "0001111111111000",
            "0011111111111100", "0111111111111110", "0111111111111110",
            "0011111111111100",
        ),
        "B": (
            "0000000110000000", "0000001111000000", "0000011111100000",
            "0000111111110000", "0001111111111000", "0001111211111000",
            "0000111121110000", "0000011221100000", "0000002221000000",
            "0000011111100000", "0000111111110000", "0001111111111000",
            "0011111111111100", "0111111111111110", "0111111111111110",
            "0011111111111100",
        ),
        "N": (
            "0000001000000000", "0000011100000000", "0000111111000000",
            "0001111111110000", "0011111111111100", "0011222111111110",
            "0001111111111100", "0000011111110000", "0000011111100000",
            "0000111111000000", "0001111111000000", "0011111111000000",
            "0111111111100000", "1111111111110000", "1111111111111000",
            "1111111111111100",
        ),
        "P": (
            "0000001111000000", "0000011221100000", "0000112221110000",
            "0000112221110000", "0000011221100000", "0000001111000000",
            "0000011111100000", "0000111111110000", "0001111111111000",
            "0000001111000000", "0000001111000000", "0000011111100000",
            "0000111111110000", "0001111111111000", "0011111111111100",
            "0111111111111110",
        ),
    }

    def __init__(
        self,
        effects: Effects | None = None,
        textures: SceneTextures | None = None,
    ) -> None:
        self.effects = effects or SoftGlowEffects()
        self.textures = textures or SceneTextures()
        self.coordinate_font = pygame.font.SysFont("consolas", 9, bold=True)
        self.piece_sprite_cache: dict[
            tuple[str, str, int, int], pygame.Surface
        ] = {}

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
        board_origin: tuple[float, float] = (BOARD_LEFT, BOARD_TOP),
        loot: dict[tuple[int, int], int] | None = None,
        shop_tiles: dict[tuple[int, int], str] | None = None,
        buildings: dict[
            tuple[int, int], tuple[str, str, bool, int, int]
        ] | None = None,
        viewport_rect: pygame.Rect | None = None,
        boss_chest_tiles: set[tuple[int, int]] | None = None,
        piece_animation: tuple[Piece, tuple[int, int], tuple[int, int], float] | None = None,
        raiders: list[tuple[float, float]] | None = None,
        potions: set[tuple[int, int]] | None = None,
        king_attack_progress: float | None = None,
        language: str = "cs",
        piece_opacity: float = 1.0,
        king_scale: float = 1.0,
        king_health_ratio: float | None = None,
        hidden_piece_square: tuple[int, int] | None = None,
    ) -> None:
        destinations = {move.end for move in legal_moves}
        mines = mines or {}
        loot = loot or {}
        shop_tiles = shop_tiles or {}
        buildings = buildings or {}
        boss_chest_tiles = boss_chest_tiles or set()
        raiders = raiders or []
        potions = potions or set()
        health_animations = health_animations or {}
        damage_popups = damage_popups or []
        health_scale = game.piece_health_multiplier
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
                if (row, col) in potions:
                    self._draw_potion(surface, rect)
                if (row, col) in mines:
                    self._draw_mine(surface, rect)
                if (row, col) in loot:
                    self._draw_loot(surface, rect, loot[(row, col)])
                if (row, col) in shop_tiles:
                    self._draw_shop_tile(surface, rect, shop_tiles[(row, col)])
                is_animated_destination = (
                    piece_animation is not None
                    and (row, col) == piece_animation[2]
                )
                if (
                    piece is not None
                    and not is_animated_destination
                    and (row, col) != hidden_piece_square
                ):
                    self._draw_piece_with_opacity(
                        surface,
                        rect,
                        piece,
                        health_animations.get((row, col)),
                        now,
                        (
                            king_attack_progress
                            if piece.color == WHITE and piece.kind == "K"
                            else None
                        ),
                        piece_opacity,
                        king_scale
                        if piece.color == WHITE and piece.kind == "K"
                        else 1.0,
                        health_scale,
                        king_health_ratio
                        if piece.color == WHITE and piece.kind == "K"
                        else None,
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
        self._draw_buildings(
            surface, buildings, camera, square_size, board_origin, language
        )
        for row in range(
            max(0, math.floor(camera_row)),
            min(board_size, math.ceil(camera_row + VIEW_SIZE)),
        ):
            for col in range(
                max(0, math.floor(camera_col)),
                min(board_size, math.ceil(camera_col + VIEW_SIZE)),
            ):
                piece = game.board[row][col]
                if (
                    piece is None
                    or piece.color != WHITE
                    or piece.kind != "K"
                    or (piece_animation is not None and (row, col) == piece_animation[2])
                ):
                    continue
                rect = pygame.Rect(
                    round(origin_x + (col - camera_col) * square_size),
                    round(origin_y + (row - camera_row) * square_size),
                    square_size,
                    square_size,
                )
                self._draw_piece_with_opacity(
                    surface,
                    rect,
                    piece,
                    health_animations.get((row, col)),
                    now,
                    king_attack_progress,
                    piece_opacity,
                    king_scale,
                    health_scale,
                    king_health_ratio,
                )
        if boss_chest_tiles:
            self._draw_boss_chest(
                surface, boss_chest_tiles, camera, square_size, board_origin
            )
        if piece_animation is not None:
            piece, start, end, started_at = piece_animation
            progress = min(1.0, max(0.0, (now - started_at) / 0.18))
            eased = progress * progress * (3 - 2 * progress)
            row = start[0] + (end[0] - start[0]) * eased
            col = start[1] + (end[1] - start[1]) * eased
            animated_rect = pygame.Rect(
                round(board_origin[0] + (col - camera[1]) * square_size),
                round(board_origin[1] + (row - camera[0]) * square_size),
                square_size,
                square_size,
            )
            self._draw_piece_with_opacity(
                surface,
                animated_rect,
                piece,
                None,
                now,
                (
                    king_attack_progress
                    if piece.color == WHITE and piece.kind == "K"
                    else None
                ),
                piece_opacity,
                king_scale
                if piece.color == WHITE and piece.kind == "K"
                else 1.0,
                health_scale,
                king_health_ratio
                if piece.color == WHITE and piece.kind == "K"
                else None,
            )
        self._draw_raiders(surface, raiders, camera, square_size, board_origin)
        self._draw_damage_popups(
            surface, damage_popups, now, camera, square_size, board_origin
        )
        surface.set_clip(previous_clip)

    def _draw_raiders(
        self,
        surface: pygame.Surface,
        raiders: list[tuple[float, float]],
        camera: tuple[float, float],
        square_size: int,
        board_origin: tuple[float, float],
    ) -> None:
        for row, col in raiders:
            center = (
                round(board_origin[0] + (col + 0.5 - camera[1]) * square_size),
                round(board_origin[1] + (row + 0.5 - camera[0]) * square_size),
            )
            pygame.draw.ellipse(
                surface,
                (37, 25, 25),
                pygame.Rect(
                    center[0] - square_size // 3,
                    center[1] + square_size // 4,
                    square_size * 2 // 3,
                    max(3, square_size // 5),
                ),
            )
            pawn_rect = pygame.Rect(
                0,
                0,
                max(16, round(square_size * 0.9)),
                max(16, round(square_size * 0.9)),
            )
            pawn_rect.center = center
            self.draw_piece_sprite(surface, pawn_rect, "P", "black")

    @staticmethod
    def _draw_cooldown_bar(
        surface: pygame.Surface, rect: pygame.Rect, progress: float
    ) -> None:
        width = max(6, rect.width - 8)
        height = max(2, rect.height // 22)
        bar = pygame.Rect(
            rect.centerx - width // 2,
            rect.bottom - height - 1,
            width,
            height,
        )
        pygame.draw.rect(surface, (37, 40, 38), bar)
        fill = bar.copy()
        fill.width = round(width * max(0.0, min(1.0, progress)))
        if fill.width:
            pygame.draw.rect(surface, (255, 255, 255), fill)

    @staticmethod
    def _draw_boss_chest(
        surface: pygame.Surface,
        squares: set[tuple[int, int]],
        camera: tuple[float, float],
        square_size: int,
        board_origin: tuple[float, float],
    ) -> None:
        rows = [row for row, _ in squares]
        cols = [col for _, col in squares]
        for row, col in squares:
            rect = pygame.Rect(
                round(board_origin[0] + (col - camera[1]) * square_size),
                round(board_origin[1] + (row - camera[0]) * square_size),
                square_size,
                square_size,
            )
            pygame.draw.rect(surface, (202, 154, 58), rect, width=2)
        bounds = pygame.Rect(
            round(board_origin[0] + (min(cols) - camera[1]) * square_size),
            round(board_origin[1] + (min(rows) - camera[0]) * square_size),
            (max(cols) - min(cols) + 1) * square_size,
            (max(rows) - min(rows) + 1) * square_size,
        )
        chest = pygame.Rect(
            0,
            0,
            max(18, bounds.width * 3 // 5),
            max(14, bounds.height // 2),
        )
        chest.center = bounds.center
        pygame.draw.rect(surface, (49, 35, 19), chest.inflate(4, 4), border_radius=4)
        pygame.draw.rect(surface, (139, 81, 31), chest, border_radius=3)
        lid = pygame.Rect(chest.x, chest.y, chest.width, max(5, chest.height // 3))
        pygame.draw.rect(surface, (224, 170, 55), lid, border_radius=3)
        lock = pygame.Rect(
            chest.centerx - max(2, square_size // 12),
            chest.centery - max(2, square_size // 16),
            max(4, square_size // 6),
            max(5, square_size // 4),
        )
        pygame.draw.rect(surface, (255, 224, 112), lock, border_radius=2)

    @staticmethod
    def _draw_loot(surface: pygame.Surface, rect: pygame.Rect, value: int) -> None:
        center = (rect.centerx, rect.centery)
        radius = max(4, rect.width // 4)
        pygame.draw.circle(surface, (71, 54, 22), center, radius + 1)
        pygame.draw.circle(surface, (231, 185, 70), center, radius)
        label = _font(max(8, rect.width // 3), bold=True)
        image = label.render(str(value), True, (58, 45, 22))
        surface.blit(image, image.get_rect(center=center))

    @staticmethod
    def _draw_potion(surface: pygame.Surface, rect: pygame.Rect) -> None:
        center_x, center_y = rect.center
        width = max(6, rect.width // 3)
        height = max(9, rect.height // 2)
        bottle = pygame.Rect(
            center_x - width // 2,
            center_y - height // 2 + 2,
            width,
            height,
        )
        pygame.draw.rect(surface, (245, 234, 204), bottle, border_radius=3)
        pygame.draw.rect(surface, (198, 57, 70), bottle.inflate(-3, -4), border_radius=2)
        neck = pygame.Rect(center_x - width // 4, bottle.top - 3, width // 2, 4)
        pygame.draw.rect(surface, (245, 234, 204), neck, border_radius=1)

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
        font = _font(max(9, rect.width // 2), bold=True)
        label = font.render(abbreviations.get(kind, "?"), True, (255, 247, 220))
        surface.blit(label, label.get_rect(center=rect.center))

    @staticmethod
    def _draw_buildings(
        surface: pygame.Surface,
        buildings: dict[tuple[int, int], tuple[str, str, bool, int, int]],
        camera: tuple[float, float],
        square_size: int,
        board_origin: tuple[float, float],
        language: str = "cs",
    ) -> None:
        groups: dict[
            tuple[str, str, bool, int, int], list[tuple[int, int]]
        ] = {}
        for square, building in buildings.items():
            groups.setdefault(building, []).append(square)

        names = {"farm": "FARMA", "city": "MESTO", "armory": "ZBROJNICE"}
        palettes = {
            "farm": ((57, 92, 54), (113, 164, 86)),
            "city": ((55, 76, 96), (103, 147, 172)),
            "armory": ((103, 58, 50), (174, 98, 76)),
        }
        for (kind, owner, owned, progress, level), squares in groups.items():
            rows = [square[0] for square in squares]
            cols = [square[1] for square in squares]
            top, left = min(rows), min(cols)
            unowned_color, owned_color = palettes[kind]
            color = owned_color if owned else unowned_color
            if owner == "black":
                color = tuple(max(0, channel - 18) for channel in color)
            for index, (row, col) in enumerate(
                sorted(squares, key=lambda square: (square[0], square[1]))
            ):
                rect = pygame.Rect(
                    round(board_origin[0] + (col - camera[1]) * square_size),
                    round(board_origin[1] + (row - camera[0]) * square_size),
                    square_size,
                    square_size,
                )
                active = owned and (
                    index < progress or (kind == "city" and index == 0)
                )
                improved = (
                    active
                    and level > 0
                    and (index + 1) // 2 <= level
                    and index % 2 == 1
                )
                BoardRenderer._draw_building_tile(
                    surface, rect, kind, color, active, improved
                )

            bounds = pygame.Rect(
                round(board_origin[0] + (left - camera[1]) * square_size),
                round(board_origin[1] + (top - camera[0]) * square_size),
                (max(cols) - left + 1) * square_size,
                (max(rows) - top + 1) * square_size,
            )
            label = f"{translate(names[kind], language)} {progress}"
            if kind == "farm":
                label += "/12"
            badge = pygame.Rect(bounds.x + 2, bounds.y + 2, bounds.width - 4, max(10, square_size // 2))
            pygame.draw.rect(surface, (25, 31, 28), badge, border_radius=3)
            font = _font(max(7, square_size // 3), bold=True)
            image = font.render(label, True, (255, 246, 222))
            image.set_alpha(255 if owned else 145)
            surface.blit(image, image.get_rect(center=badge.center))

    @staticmethod
    def _draw_building_tile(
        surface: pygame.Surface,
        rect: pygame.Rect,
        kind: str,
        base_color: tuple[int, int, int],
        active: bool,
        improved: bool = False,
    ) -> None:
        pygame.draw.rect(surface, (25, 31, 28), rect)
        tile = rect.inflate(-3, -3)
        color = base_color if active else tuple(max(25, channel - 48) for channel in base_color)
        pygame.draw.rect(surface, color, tile)
        if not active:
            return

        scale = min(rect.width, rect.height)
        if kind == "farm":
            for row in range(3):
                y = tile.y + tile.height * (row + 1) // 4
                pygame.draw.line(
                    surface,
                    (49, 67, 39),
                    (tile.x + 3, y),
                    (tile.right - 3, y),
                    max(1, scale // 14),
                )
                for col in range(2):
                    x = tile.x + tile.width * (col + 1) // 3
                    plant_y = y - max(2, scale // 8)
                    pygame.draw.line(
                        surface,
                        (215, 205, 105),
                        (x, y),
                        (x, plant_y),
                        max(1, scale // 16),
                    )
            if improved:
                shed = pygame.Rect(
                    tile.x + tile.width // 2,
                    tile.y + 3,
                    max(5, tile.width // 3),
                    max(4, tile.height // 4),
                )
                pygame.draw.rect(surface, (102, 59, 39), shed)
                pygame.draw.polygon(
                    surface,
                    (226, 186, 96),
                    (
                        (shed.left - 2, shed.top + 2),
                        (shed.centerx, shed.top - 2),
                        (shed.right + 2, shed.top + 2),
                    ),
                )
        elif kind == "city":
            house = pygame.Rect(
                tile.x + tile.width // 4,
                tile.y + tile.height // 3,
                tile.width // 2,
                tile.height // 2,
            )
            pygame.draw.rect(surface, (205, 190, 151), house)
            pygame.draw.polygon(
                surface,
                (139, 71, 58) if not improved else (224, 180, 82),
                (
                    (house.left - 2, house.top + 2),
                    (house.centerx, house.top - max(2, scale // 8)),
                    (house.right + 2, house.top + 2),
                ),
            )
            door = pygame.Rect(
                house.centerx - max(1, scale // 16),
                house.bottom - max(3, house.height // 3),
                max(2, scale // 8),
                max(3, house.height // 3),
            )
            pygame.draw.rect(surface, (65, 54, 43), door)
            if improved:
                tower = pygame.Rect(
                    house.right - max(3, house.width // 4),
                    house.top - max(3, scale // 5),
                    max(3, house.width // 4),
                    max(4, scale // 3),
                )
                pygame.draw.rect(surface, (227, 193, 105), tower)
        elif kind == "armory":
            forge = pygame.Rect(
                tile.x + tile.width // 4,
                tile.y + tile.height // 3,
                tile.width // 2,
                tile.height // 2,
            )
            pygame.draw.rect(surface, (194, 164, 128), forge)
            pygame.draw.polygon(
                surface,
                (84, 45, 39),
                (
                    (forge.left - 2, forge.top + 2),
                    (forge.centerx, forge.top - max(2, scale // 8)),
                    (forge.right + 2, forge.top + 2),
                ),
            )
            pygame.draw.rect(
                surface,
                (241, 174, 70),
                (
                    forge.centerx - max(2, scale // 10),
                    forge.bottom - max(5, forge.height // 2),
                    max(4, scale // 5),
                    max(5, forge.height // 2),
                ),
            )

    def _draw_piece(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        piece: Piece,
        health_animation: tuple[int, int, float] | None,
        now: float,
        cooldown_progress: float | None = None,
        health_scale: float = 1.0,
        health_ratio_override: float | None = None,
    ) -> None:
        self.draw_piece_sprite(surface, rect, piece.kind, piece.color)
        cooldown_height = (
            max(2, rect.height // 22) + 2
            if cooldown_progress is not None
            else 0
        )
        health_width = max(6, rect.width - 4)
        health_height = max(1, rect.height // 8)
        health_rect = pygame.Rect(
            rect.centerx - health_width // 2,
            rect.bottom - health_height - cooldown_height - 1,
            health_width,
            health_height,
        )
        pygame.draw.rect(surface, (31, 37, 34), health_rect)
        ratio = (
            max(0.0, min(1.0, health_ratio_override))
            if health_ratio_override is not None
            else self._health_ratio(piece, health_animation, now, health_scale)
        )
        if ratio > 0:
            health_color = (
                int(224 * (1 - ratio) + 72 * ratio),
                int(65 * (1 - ratio) + 190 * ratio),
                70,
            )
            fill_rect = health_rect.copy()
            fill_rect.width = max(1, int(health_width * ratio))
            pygame.draw.rect(surface, health_color, fill_rect)
        if cooldown_progress is not None:
            self._draw_cooldown_bar(surface, rect, cooldown_progress)
        if piece.upgrades:
            pygame.draw.circle(
                surface,
                (245, 194, 75),
                (rect.right - 4, rect.y + 4),
                max(1, rect.width // 12),
            )

    def _draw_piece_with_opacity(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        piece: Piece,
        health_animation: tuple[int, int, float] | None,
        now: float,
        cooldown_progress: float | None,
        opacity: float,
        scale: float = 1.0,
        health_scale: float = 1.0,
        health_ratio_override: float | None = None,
    ) -> None:
        opacity = min(1.0, max(0.0, opacity))
        scale = max(0.1, scale)
        if opacity >= 1.0 and scale == 1.0:
            self._draw_piece(
                surface,
                rect,
                piece,
                health_animation,
                now,
                cooldown_progress,
                health_scale,
                health_ratio_override,
            )
            return
        piece_size = (
            max(1, round(rect.width * scale)),
            max(1, round(rect.height * scale)),
        )
        piece_surface = pygame.Surface(piece_size, pygame.SRCALPHA)
        self._draw_piece(
            piece_surface,
            piece_surface.get_rect(),
            piece,
            health_animation,
            now,
            cooldown_progress,
            health_scale,
            health_ratio_override,
        )
        piece_surface.set_alpha(round(opacity * 255))
        surface.blit(piece_surface, piece_surface.get_rect(center=rect.center))

    def draw_piece_sprite(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        kind: str,
        color: str,
    ) -> None:
        mask = self.PIECE_PIXELS[kind]
        sprite_width = max(16, round(rect.width * 0.9))
        sprite_height = max(16, round(rect.height * 0.9))
        cache_key = (kind, color, sprite_width, sprite_height)
        sprite = self.piece_sprite_cache.get(cache_key)
        if sprite is not None:
            surface.blit(sprite, sprite.get_rect(center=rect.center))
            return
        if color == WHITE:
            outline, fill, highlight = (65, 48, 37), (239, 222, 176), (255, 246, 207)
        else:
            outline, fill, highlight = (24, 31, 35), (79, 113, 143), (144, 185, 204)
        sprite = pygame.Surface((16, 16), pygame.SRCALPHA)
        for row, pixel_row in enumerate(mask):
            for col, value in enumerate(pixel_row):
                if value == "0":
                    continue
                boundary = any(
                    next_row < 0
                    or next_row >= len(mask)
                    or next_col < 0
                    or next_col >= len(pixel_row)
                    or mask[next_row][next_col] == "0"
                    for next_row, next_col in (
                        (row - 1, col),
                        (row + 1, col),
                        (row, col - 1),
                        (row, col + 1),
                    )
                )
                pixel_color = outline if boundary else (
                    highlight
                    if value == "2" or (row + col) % 7 == 0
                    else fill
                )
                sprite.set_at((col, row), pixel_color)
        sprite = pygame.transform.scale(sprite, (sprite_width, sprite_height))
        self.piece_sprite_cache[cache_key] = sprite
        surface.blit(sprite, sprite.get_rect(center=rect.center))

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
        health_scale: float = 1.0,
    ) -> float:
        displayed_max_health = max(1, round(piece.max_health * health_scale))
        if animation is None:
            return max(0.0, min(1.0, (piece.health or 0) / displayed_max_health))
        start, end, started_at = animation
        progress = min(1.0, max(0.0, (now - started_at) / 0.45))
        eased = progress * progress * (3 - 2 * progress)
        health = start + (end - start) * eased
        return max(0.0, min(1.0, health / displayed_max_health))

    @staticmethod
    def _draw_damage_popups(
        surface: pygame.Surface,
        popups: list[tuple[tuple[int, int], int, float]],
        now: float,
        camera: tuple[float, float],
        square_size: int,
        board_origin: tuple[float, float],
    ) -> None:
        font = _font(max(9, square_size // 2), bold=True)
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


if __name__ == "__main__":
    from .app import run_game

    run_game()
