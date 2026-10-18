from __future__ import annotations

from pathlib import Path
import random

import pygame


class SceneTextures:
    """Shared, replaceable board and background textures for every level."""

    def __init__(self, texture_directory: Path | None = None) -> None:
        self.texture_directory = texture_directory or (
            Path(__file__).resolve().parent.parent / "assets" / "textures"
        )
        self._background = self._load_or_create(
            "background.png", (160, 160), (38, 48, 44), 1
        )
        self._board = self._load_or_create(
            "board.png", (96, 96), (173, 156, 119), 2
        )
        self._background_scaled: dict[tuple[int, int], pygame.Surface] = {}
        self._board_tiles: dict[tuple[int, bool], pygame.Surface] = {}

    def draw_background(self, surface: pygame.Surface) -> None:
        size = surface.get_size()
        background = self._background_scaled.get(size)
        if background is None:
            background = pygame.transform.scale(self._background, size)
            self._background_scaled[size] = background
        surface.blit(background, (0, 0))

    def draw_board_square(
        self, surface: pygame.Surface, rect: pygame.Rect, *, light: bool
    ) -> None:
        key = (rect.width, light)
        tile = self._board_tiles.get(key)
        if tile is None:
            tile = pygame.transform.scale(self._board, (rect.width, rect.height))
            tint = (224, 201, 153) if light else (92, 119, 104)
            tile.fill((*tint, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self._board_tiles[key] = tile
        surface.blit(tile, rect)
        edge = (152, 119, 75) if light else (54, 76, 68)
        pygame.draw.line(surface, edge, rect.bottomleft, rect.bottomright, 1)
        pygame.draw.line(surface, edge, rect.topright, rect.bottomright, 1)

    def _load_or_create(
        self,
        filename: str,
        size: tuple[int, int],
        base_color: tuple[int, int, int],
        seed: int,
    ) -> pygame.Surface:
        path = self.texture_directory / filename
        if path.is_file():
            return pygame.image.load(str(path)).convert()

        texture = pygame.Surface(size)
        texture.fill(base_color)
        rng = random.Random(seed)
        for _ in range(size[0] * size[1] // 3):
            offset = rng.randint(-18, 18)
            color = tuple(max(0, min(255, channel + offset)) for channel in base_color)
            block = rng.choice((2, 3, 4))
            pygame.draw.rect(
                texture,
                color,
                (
                    rng.randrange(size[0]) // block * block,
                    rng.randrange(size[1]) // block * block,
                    block,
                    block,
                ),
            )
        return texture
