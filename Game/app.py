from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from collections import OrderedDict
import math
import random

import pygame

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "Game"

from .constants import (
    BOT_DIFFICULTIES,
    BLACK,
    BOARD_VIEW_PIXELS,
    BOARD_LEFT,
    BOARD_SIZE,
    BOARD_TOP,
    CAMPAIGN_BOARD_SIZE,
    CLASSIC_BOARD_SIZE,
    CLASSIC_SQUARE_SIZE,
    FARM_INCOME_PER_SECOND,
    SQUARE_SIZE,
    WHITE,
    WINDOW_SIZE,
)
from .bot import choose_move
from .campaign import (
    ARMY_KINDS,
    ARMORY_COST,
    ARMY_UPGRADE_COSTS,
    CITY_COST,
    FARM_LIMIT,
    PICKUP_RESPAWN_DELAY,
    POTION_HEAL,
    POTION_LIMIT,
    RECRUIT_COSTS,
    UPGRADE_SOURCES,
    Campaign,
)
from .effects import Effects
from .models import Move, Piece
from .renderer import BoardRenderer
from .progress import (
    load_campaign,
    load_hardcore_enabled,
    load_language,
    load_tutorials_enabled,
    load_unlocked_level,
    save_campaign,
    save_hardcore_enabled,
    save_language,
    save_tutorials_enabled,
    save_unlocked_level,
)
from .localization import translate
from .rules import ChessGame
from .textures import SceneTextures

CAMPAIGN_INTRO_ZOOM_DURATION_MS = 4500
CAMPAIGN_INTRO_START_ZOOM = 2.0
CAMERA_FOLLOW_SPEED = 14.0


class ChessApp:
    def __init__(self, effects: Effects | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("Šachy — základ")
        self.windowed_size = WINDOW_SIZE
        self.fullscreen = False
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        desktop_sizes = pygame.display.get_desktop_sizes()
        if desktop_sizes:
            desktop_width, desktop_height = desktop_sizes[0]
            window_x = max(0, (desktop_width - WINDOW_SIZE[0]) // 2)
            window_y = max(0, (desktop_height - WINDOW_SIZE[1]) // 2)
            pygame.display.set_window_position((window_x, window_y))
        self.clock = pygame.time.Clock()
        self._campaign_save_dirty = False
        self._last_campaign_save_at = pygame.time.get_ticks()
        self._campaign_save_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="campaign-save"
        )
        self._campaign_save_future: Future[None] | None = None
        self._rendered_text_cache: OrderedDict[
            tuple[int, str, tuple[int, int, int]], pygame.Surface
        ] = OrderedDict()
        self.language = load_language()
        self.tutorial_enabled = load_tutorials_enabled()
        self.hardcore_enabled = load_hardcore_enabled()
        pygame.display.set_caption(translate("Šachy — základ", self.language))
        self.tutorial_seen: set[str] = set()
        self.tutorial_queue: list[tuple[str, str]] = []
        self.tutorial_active: tuple[str, str] | None = None
        self.tutorial_until = 0
        self.tutorial_panel = pygame.Rect(
            WINDOW_SIZE[0] - 328, WINDOW_SIZE[1] - 146, 312, 128
        )
        self.tutorial_close_button = pygame.Rect(
            self.tutorial_panel.right - 30,
            self.tutorial_panel.y + 8,
            22,
            22,
        )
        self.unlocked_level = load_unlocked_level()
        self.campaign = load_campaign()
        self.selected_level = 1
        self.active_level = 1
        self.game = self._create_level_game(self.active_level)
        self.textures = SceneTextures()
        self.renderer = BoardRenderer(effects, self.textures)
        self.font = pygame.font.SysFont("consolas", 22)
        self.small_font = pygame.font.SysFont("consolas", 16)
        self.title_font = pygame.font.SysFont("consolas", 30, bold=True)
        self.selected: tuple[int, int] | None = None
        self.legal_moves: list[Move] = []
        self.pending_promotion: list[Move] = []
        self.status = self.game.status()
        self.running = True
        self.screen = "menu"
        self.has_started_game = False
        self.bot_difficulty = "medium"
        self.zoom = 1.0
        self.camera_offset = (0, 0)
        self.camera_target_offset = (0, 0)
        self.pan_start: tuple[int, int] | None = None
        self.pan_start_offset = (0, 0)
        self.pan_moved = False
        self.level_buttons = {
            1: pygame.Rect(245, 372, 250, 58),
            2: pygame.Rect(545, 372, 250, 58),
        }
        self.difficulty_buttons = {
            "easy": pygame.Rect(210, 278, 190, 46),
            "medium": pygame.Rect(425, 278, 190, 46),
            "hard": pygame.Rect(640, 278, 190, 46),
        }
        self.menu_play_button = pygame.Rect(380, 455, 280, 54)
        self.menu_new_game_button = pygame.Rect(380, 522, 280, 54)
        self.menu_quit_button = pygame.Rect(380, 589, 280, 54)
        self.tutorial_toggle_button = pygame.Rect(790, 20, 210, 40)
        self.language_toggle_button = pygame.Rect(790, 68, 210, 40)
        self.hardcore_toggle_button = pygame.Rect(790, 116, 210, 40)
        self.death_retry_button = pygame.Rect(370, 480, 300, 52)
        self.death_menu_button = pygame.Rect(370, 546, 300, 52)
        self.undo_button = pygame.Rect(720, 650, 280, 32)
        self.reset_button = pygame.Rect(720, 688, 280, 32)
        self.in_game_menu_button = pygame.Rect(720, 726, 280, 30)
        self.last_action_was_bot = False
        self.bot_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="chess-bot"
        )
        self.bot_future: Future[Move | None] | None = None
        self.bot_due_at: int | None = None
        self.team_health_animations: dict[str, tuple[int, int, float]] = {}
        self.piece_move_animation: tuple[
            Piece, tuple[int, int], tuple[int, int], float
        ] | None = None
        self.piece_health_animations: dict[
            tuple[int, int], tuple[int, int, float]
        ] = {}
        self.damage_popups: list[tuple[tuple[int, int], int, float]] = []
        self.campaign_tab = "farms"
        self.kingdom_game: ChessGame | None = None
        self.campaign_battle_active = False
        self.boss_deployment_active = False
        self.boss_battle_active = False
        self.campaign_intro_zoom_started_at: int | None = None
        self.banter_started_at = pygame.time.get_ticks()
        self.boss_deployment: dict[str, int] = {
            kind: 0 for kind in ARMY_KINDS
        }
        self.boss_deployment_buttons = {
            kind: {
                "minus": pygame.Rect(840, 164 + index * 66, 48, 42),
                "plus": pygame.Rect(932, 164 + index * 66, 48, 42),
            }
            for index, kind in enumerate(ARMY_KINDS)
        }
        self.boss_start_button = pygame.Rect(510, 535, 450, 58)
        self.boss_cancel_button = pygame.Rect(510, 610, 450, 48)
        self.boss_deployed_army: dict[str, int] = {}
        self.deployment_limit = 3
        self.deployed_armies: dict[str, dict[str, int]] = {}
        self.shop_menu: str | None = None
        self.shop_confirmation: str | None = None
        self.shop_confirmation_buttons: dict[str, pygame.Rect] = {}
        self.shop_screen_buttons: dict[str, pygame.Rect] = {}
        self.shop_screen_back_button = pygame.Rect(44, 675, 200, 52)
        self.drag_start: tuple[int, int] | None = None
        shop_names = ("farm", "city", "armory", "recruit", "upgrade", "war")
        self.shop_cards = {
            name: pygame.Rect(
                40 + (index % 3) * 198,
                610 + (index // 3) * 56,
                190,
                50,
            )
            for index, name in enumerate(shop_names)
        }
        self.campaign_tab_buttons = {
            "farms": pygame.Rect(720, 210, 90, 34),
            "city": pygame.Rect(815, 210, 90, 34),
            "armory": pygame.Rect(910, 210, 90, 34),
        }
        self.farm_button = pygame.Rect(720, 302, 280, 42)
        self.city_button = pygame.Rect(720, 352, 280, 42)
        self.city_unlock_button = pygame.Rect(720, 302, 280, 34)
        self.armory_button = pygame.Rect(720, 302, 280, 42)
        self.recruit_buttons = {
            kind: pygame.Rect(720, 340 + index * 38, 280, 32)
            for index, kind in enumerate(ARMY_KINDS)
        }
        self.upgrade_buttons = {
            kind: pygame.Rect(720, 530 + index * 29, 280, 25)
            for index, kind in enumerate(("N", "B", "R", "Q"))
        }
        self.deployment_minus_button = pygame.Rect(720, 500, 48, 38)
        self.deployment_plus_button = pygame.Rect(952, 500, 48, 38)
        self.declare_war_button = pygame.Rect(720, 600, 280, 44)
        self.campaign_hud_surface = pygame.Surface(
            (WINDOW_SIZE[0], 68), pygame.SRCALPHA
        )
        self.campaign_hud_surface.fill((20, 27, 24, 228))

    @staticmethod
    def _create_level_game(level: int) -> ChessGame:
        if level == 1:
            return ChessGame(
                board_size=CLASSIC_BOARD_SIZE,
                random_armies=False,
                capture_majority=True,
                piece_health_multiplier=0.5,
            )
        if level == 2:
            return ChessGame(
                board_size=CAMPAIGN_BOARD_SIZE,
                random_armies=False,
                king_only=True,
                campaign_map=True,
            )
        raise ValueError(f"Unknown game level: {level}")

    def run(self) -> None:
        try:
            while self.running:
                elapsed_seconds = self.clock.tick(120) / 1000
                self._handle_events()
                self._update_bot_turn()
                self._advance_campaign_intro_zoom()
                self._update_camera_follow(elapsed_seconds)
                self._draw()
                pygame.display.flip()
                self._advance_realtime_campaign(elapsed_seconds)
                self._flush_campaign_save()
        finally:
            try:
                self._flush_campaign_save(force=True)
            finally:
                self._campaign_save_executor.shutdown(wait=True)
                self.bot_executor.shutdown(wait=False, cancel_futures=True)

    def _advance_realtime_campaign(self, elapsed_seconds: float) -> None:
        if (
            self.active_level != 2
            or self.campaign_battle_active
            or self.campaign.king_dead
        ):
            return

        zombies_were_active = self.campaign.raiders_started_at is not None
        blocked_raider_squares = (
            set(self.game.building_tiles)
            | set(self.game.shop_tiles)
            | set(self.game.loot)
            | self.game.loot_reserved_squares
            | set(self.campaign.potions)
        )
        blocked_raider_squares.update(
            (row, col)
            for row, board_row in enumerate(self.game.board)
            for col, piece in enumerate(board_row)
            if piece is not None
        )
        self.campaign.advance_realtime(
            elapsed_seconds,
            self.game.board_size,
            blocked_raider_squares,
        )
        changed = elapsed_seconds > 0
        earned = self.campaign.accrue_income(elapsed_seconds)
        if (
            not zombies_were_active
            and self.campaign.raiders_started_at is not None
        ):
            self.campaign.potions_active = True
            self._ensure_campaign_potions()
            self._show_tutorial(
                "campaign.zombies",
                "Pesaci zustanou stat na miste. Poraz je kralem a za jednu "
                "sekundu se vrati jeden pesec na nahodne volne policko.",
            )
            self._show_tutorial(
                "campaign.potions",
                "Cervene lektvary se objevi, jakmile zacnou zombici. Kralem "
                "je seberes a kazdy ti vrati az 150 HP.",
            )
        due_loot = [
            spawn_at
            for spawn_at in self.campaign.loot_respawns
            if spawn_at <= self.campaign.realtime_seconds
        ]
        self.campaign.loot_respawns = [
            spawn_at
            for spawn_at in self.campaign.loot_respawns
            if spawn_at > self.campaign.realtime_seconds
        ]
        for _ in due_loot:
            previous_count = len(self.game.loot)
            self.game._spawn_loot(
                previous_count + 1,
                blocked_squares={
                    (int(raider.row), int(raider.col))
                    for raider in self.campaign.raiders
                }
                | set(self.campaign.potions),
            )
            if len(self.game.loot) == previous_count:
                self.campaign.loot_respawns.append(
                    self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
                )
            changed = True
        if self.campaign.raiders_started_at is not None:
            self.campaign.potions_active = True
            if not self.campaign.potions and not self.campaign.potion_respawns:
                self._ensure_campaign_potions()
                changed = True
        while any(
            spawn_at <= self.campaign.realtime_seconds
            for spawn_at in self.campaign.potion_respawns
        ):
            due_index = next(
                index
                for index, spawn_at in enumerate(self.campaign.potion_respawns)
                if spawn_at <= self.campaign.realtime_seconds
            )
            self.campaign.potion_respawns.pop(due_index)
            previous_count = len(self.campaign.potions)
            self._ensure_campaign_potions()
            if len(self.campaign.potions) == previous_count:
                self.campaign.potion_respawns.append(
                    self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
                )
            changed = True
        if changed or earned:
            self._mark_campaign_dirty()

    def _king_square(
        self, color: str, game: ChessGame | None = None
    ) -> tuple[int, int] | None:
        board = (game or self.game).board
        for row_index, row in enumerate(board):
            for col_index, piece in enumerate(row):
                if piece is not None and piece.color == color and piece.kind == "K":
                    return row_index, col_index
        return None

    def _mark_campaign_dirty(self) -> None:
        self._campaign_save_dirty = True

    def _flush_campaign_save(self, *, force: bool = False) -> None:
        now = pygame.time.get_ticks()
        if self._campaign_save_future is not None:
            if force:
                self._campaign_save_future.result()
                self._campaign_save_future = None
            elif self._campaign_save_future.done():
                self._campaign_save_future.result()
                self._campaign_save_future = None
        if self._campaign_save_future is not None:
            return
        if not self._campaign_save_dirty or (
            not force and now - self._last_campaign_save_at < 3000
        ):
            return
        snapshot = deepcopy(self.campaign)
        self._campaign_save_future = self._campaign_save_executor.submit(
            save_campaign, snapshot
        )
        self._campaign_save_dirty = False
        self._last_campaign_save_at = now
        if force:
            self._campaign_save_future.result()
            self._campaign_save_future = None

    def _ensure_boss_chest_position(self) -> bool:
        if (
            self.campaign.boss_chest_claimed
            or self.campaign.player.army_size < 2
        ):
            return False
        created = self.campaign.boss_chest_position is None
        if created:
            board_size = self.game.board_size
            candidates = [
                (row, col)
                for row in range(
                    max(0, board_size - 14), min(board_size - 1, board_size - 6)
                )
                for col in range(6, min(14, board_size - 1))
                if all(
                    self.game.board[tile_row][tile_col] is None
                    and (tile_row, tile_col) not in self.game.shop_tiles
                    and (tile_row, tile_col) not in self.game.building_tiles
                    and (tile_row, tile_col) not in self.game.loot
                    for tile_row in (row, row + 1)
                    for tile_col in (col, col + 1)
                )
            ]
            if not candidates:
                raise RuntimeError("Unable to place the boss chest on the campaign map.")
            self.campaign.boss_chest_position = random.choice(candidates)
        chest_row, chest_col = self.campaign.boss_chest_position
        self.game.loot_reserved_squares = {
            (chest_row, chest_col),
            (chest_row, chest_col + 1),
            (chest_row + 1, chest_col),
            (chest_row + 1, chest_col + 1),
        }
        self.game.loot = {
            square: value
            for square, value in self.game.loot.items()
            if square not in self.game.loot_reserved_squares
        }
        if self.game.king_only:
            self._ensure_campaign_loot()
        return created

    def _ensure_campaign_loot(self) -> None:
        target_count = max(0, 3 - len(self.campaign.loot_respawns))
        while len(self.game.loot) > target_count:
            self.game.loot.pop(next(iter(self.game.loot)))
        self.game._spawn_loot(target_count)

    def _ensure_campaign_potions(self) -> bool:
        previous = list(self.campaign.potions)
        if not self.campaign.potions_active:
            self.campaign.potions.clear()
            self.game.loot_reserved_squares = (
                self._boss_chest_square_set() | set(self.campaign.potions)
            )
            return False
        saved_potion_squares = set(self.campaign.potions)
        if saved_potion_squares:
            self.game.loot = {
                square: value
                for square, value in self.game.loot.items()
                if square not in saved_potion_squares
            }
        occupied_raider_squares = {
            (int(raider.row), int(raider.col)) for raider in self.campaign.raiders
        }
        valid_potions = []
        for square in self.campaign.potions:
            row, col = square
            if (
                0 <= row < self.game.board_size
                and 0 <= col < self.game.board_size
                and self.game.board[row][col] is None
                and square not in self.game.building_tiles
                and square not in self.game.shop_tiles
                and square not in self.game.loot
                and square not in self.game.loot_reserved_squares
                and square not in occupied_raider_squares
                and square not in valid_potions
            ):
                valid_potions.append(square)
        self.campaign.potions = valid_potions[:POTION_LIMIT]
        candidates = [
            (row, col)
            for row in range(
                max(0, self.game.board_size - 14),
                min(self.game.board_size, self.game.board_size - 6),
            )
            for col in range(self.game.board_size)
            if self.game.board[row][col] is None
            and (row, col) not in self.game.building_tiles
            and (row, col) not in self.game.shop_tiles
            and (row, col) not in self.game.loot
            and (row, col) not in self.game.loot_reserved_squares
            and (row, col) not in occupied_raider_squares
            and (row, col) not in self.campaign.potions
        ]
        needed = max(
            0,
            POTION_LIMIT
            - len(self.campaign.potions)
            - len(self.campaign.potion_respawns),
        )
        if needed > 0 and candidates:
            self.campaign.potions.extend(
                random.sample(candidates, min(needed, len(candidates)))
            )
        chest_squares = self._boss_chest_square_set()
        self.game.loot_reserved_squares = chest_squares | set(self.campaign.potions)
        self._ensure_campaign_loot()
        return self.campaign.potions != previous

    def _boss_chest_square_set(self) -> set[tuple[int, int]]:
        chest_squares: set[tuple[int, int]] = set()
        if (
            not self.campaign.boss_chest_claimed
            and self.campaign.player.army_size >= 2
            and self.campaign.boss_chest_position is not None
        ):
            chest_row, chest_col = self.campaign.boss_chest_position
            chest_squares = {
                (chest_row, chest_col),
                (chest_row, chest_col + 1),
                (chest_row + 1, chest_col),
                (chest_row + 1, chest_col + 1),
            }
        return chest_squares

    def _collect_campaign_potion(self, square: tuple[int, int]) -> int:
        if square not in self.campaign.potions:
            return 0
        king = self.game.piece_at(square)
        if king is None or king.kind != "K" or king.color != WHITE:
            return 0
        old_health = king.health or 0
        new_health = min(king.max_health, old_health + POTION_HEAL)
        if new_health == old_health:
            return 0
        self.campaign.potions.remove(square)
        self.game.board[square[0]][square[1]] = Piece(
            king.color,
            king.kind,
            king.level,
            king.experience,
            new_health,
            king.upgrades,
        )
        self.piece_health_animations[square] = (
            old_health,
            new_health,
            pygame.time.get_ticks() / 1000,
        )
        self.campaign.potion_respawns.append(
            self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
        )
        self._show_tutorial(
            "campaign.potion-pickup",
            "Lektvar obnovil zdravi krale. Ztracene zdravi doplnis sbiranim "
            "dalsich lektvaru, maximum zdravi se neprekroci.",
        )
        self._mark_campaign_dirty()
        return new_health - old_health

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif self.campaign_intro_zoom_started_at is not None:
                continue
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key, event.mod)
            elif (
                event.type == pygame.MOUSEWHEEL
                and self.screen == "game"
                and self.active_level == 2
            ):
                self.zoom = min(2.0, max(0.5, self.zoom * (1.1 ** event.y)))
                self._follow_king_camera()
            elif event.type == pygame.MOUSEMOTION and self.pan_start is not None:
                if event.buttons[0]:
                    delta = (
                        event.pos[0] - self.pan_start[0],
                        event.pos[1] - self.pan_start[1],
                    )
                    if abs(delta[0]) + abs(delta[1]) > 6:
                        self.pan_moved = True
                    if self.pan_moved:
                        self.camera_offset = (
                            self.pan_start_offset[0] + delta[0],
                            self.pan_start_offset[1] + delta[1],
                        )
                        self._clamp_camera_offset()
                        self.camera_target_offset = self.camera_offset
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.drag_start = None
                if self.boss_deployment_active:
                    self._handle_click(event.pos)
                elif (
                    self.screen == "game"
                    and self.shop_menu is None
                    and (
                        not self._bot_is_thinking()
                        or self._is_realtime_campaign()
                    )
                ):
                    square = self._board_square_at(event.pos)
                    piece = self.game.piece_at(square) if square is not None else None
                    if piece is not None and piece.color == self.game.turn:
                        self.drag_start = square
                    if (
                        self.active_level == 2
                        and not self.campaign_battle_active
                        and piece is None
                    ):
                        self.pan_start = event.pos
                        self.pan_start_offset = self.camera_offset
                        self.pan_moved = False
                    else:
                        self._handle_click(event.pos)
                else:
                    self._handle_click(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.pan_start is not None:
                    if not self.pan_moved:
                        self._handle_click(event.pos)
                    self.pan_start = None
                    self.pan_moved = False
                else:
                    self._handle_drag_release(event.pos)

    def _handle_key(self, key: int, modifiers: int = 0) -> None:
        if key == pygame.K_F11:
            self._toggle_fullscreen()
            return

        if self.boss_deployment_active:
            if key == pygame.K_ESCAPE:
                self._cancel_boss_deployment()
            return

        if self.screen == "death":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.hardcore_enabled:
                    self.screen = "menu"
                else:
                    self._retry_after_death()
            elif key == pygame.K_ESCAPE:
                self.screen = "menu"
            return

        if self.screen == "menu":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self._start_or_continue()
            return

        if (
            self.active_level == 2
            and not self.campaign_battle_active
            and self.shop_menu is None
        ):
            directions = {
                pygame.K_w: (-1, 0),
                pygame.K_s: (1, 0),
                pygame.K_a: (0, -1),
                pygame.K_d: (0, 1),
            }
            direction = directions.get(key)
            if direction is not None:
                self._move_king_with_wasd(*direction)
                return

        if key == pygame.K_ESCAPE:
            if self.shop_menu is not None:
                self.shop_menu = None
                self.shop_confirmation = None
            elif self.selected is not None or self.pending_promotion:
                self._clear_selection()
            else:
                self.screen = "menu"
        elif key == pygame.K_z and modifiers & pygame.KMOD_CTRL:
            self._undo()
        elif key == pygame.K_p:
            if self.game.pass_turn():
                self.status = self.game.status()
                self._clear_selection()
                self.last_action_was_bot = False
                self._schedule_bot_turn()
        elif key == pygame.K_r and not self.pending_promotion:
            if self.active_level == 2 and self.campaign_battle_active:
                self.status = "Bitvu nelze prerusit resetem."
            else:
                self._cancel_bot_turn()
                self.game.reset()
                self.status = self.game.status()
                self.last_action_was_bot = False
                self._clear_selection()
        elif self._bot_is_thinking():
            return
        elif self.pending_promotion:
            choices = {
                pygame.K_q: "Q",
                pygame.K_r: "R",
                pygame.K_b: "B",
                pygame.K_n: "N",
            }
            selected_piece = choices.get(key)
            if selected_piece is not None:
                move = next(
                    move
                    for move in self.pending_promotion
                    if move.promotion == selected_piece
                )
                self._play_move(move)

    def _toggle_fullscreen(self) -> None:
        if self.fullscreen:
            self.surface = pygame.display.set_mode(self.windowed_size)
            self.fullscreen = False
            return

        self.windowed_size = self.surface.get_size()
        self.surface = pygame.display.set_mode(
            WINDOW_SIZE,
            pygame.FULLSCREEN | pygame.SCALED,
        )
        self.fullscreen = True

    def _handle_click(self, position: tuple[int, int]) -> None:
        if self.boss_deployment_active and self.screen != "menu":
            self._handle_boss_deployment_click(position)
            return
        if self.screen == "death":
            if (
                not self.hardcore_enabled
                and self.death_retry_button.collidepoint(position)
            ):
                self._retry_after_death()
            elif self.death_menu_button.collidepoint(position):
                self.screen = "menu"
            return
        if (
            self.tutorial_active is not None
            and self.tutorial_panel.collidepoint(position)
        ):
            if self.tutorial_close_button.collidepoint(position):
                self.tutorial_until = 0
            return
        if self.screen == "menu":
            level_choice = next(
                (
                    level
                    for level, rect in self.level_buttons.items()
                    if rect.collidepoint(position)
                    and (level <= self.unlocked_level or level == 2)
                ),
                None,
            )
            difficulty_choice = next(
                (
                    difficulty
                    for difficulty, rect in self.difficulty_buttons.items()
                    if rect.collidepoint(position)
                ),
                None,
            )
            if level_choice is not None:
                self.selected_level = level_choice
            elif difficulty_choice is not None:
                self.bot_difficulty = difficulty_choice
            elif self.tutorial_toggle_button.collidepoint(position):
                self._toggle_tutorials()
            elif self.language_toggle_button.collidepoint(position):
                self._toggle_language()
            elif self.hardcore_toggle_button.collidepoint(position):
                self._toggle_hardcore()
            elif self.menu_play_button.collidepoint(position):
                self._start_or_continue()
            elif self.menu_new_game_button.collidepoint(position):
                if not (
                    self.hardcore_enabled
                    and self.campaign.king_dead
                    and self.selected_level == 2
                ):
                    self._start_new_game(abandon_current=True)
                    self.screen = "game"
            elif self.menu_quit_button.collidepoint(position):
                self.running = False
            return

        if self.shop_menu is not None and self.active_level == 2 and not self.campaign_battle_active:
            self._handle_shop_screen_click(position)
            return

        if self.active_level == 2:
            self._handle_campaign_board_click(position)
            return

        if self.pending_promotion:
            return
        if self.in_game_menu_button.collidepoint(position):
            self._clear_selection()
            self.screen = "menu"
            return
        if self.active_level == 2 and self.undo_button.collidepoint(position):
            self._undo()
            return
        if self.reset_button.collidepoint(position):
            if self.campaign_battle_active:
                self.status = "Bitvu nelze prerusit resetem."
            else:
                self._start_new_game()
            return
        if self._bot_is_thinking():
            return
        if self.active_level == 2 and not self.campaign_battle_active:
            card = next(
                (
                    kind
                    for kind, rect in self.shop_cards.items()
                    if rect.collidepoint(position)
                ),
                None,
            )
            if card is not None:
                self._activate_shop_card(card)
                return
            if self._handle_campaign_click(position):
                return
        square = self._board_square_at(position)
        if square is None:
            return

        if self.selected is not None:
            candidates = [move for move in self.legal_moves if move.end == square]
            if candidates:
                if len(candidates) > 1 and candidates[0].promotion is not None:
                    self.pending_promotion = candidates
                else:
                    self._play_move(candidates[0])
                return

        piece = self.game.piece_at(square)
        if piece is not None and piece.color == self.game.turn == WHITE:
            self.selected = square
            self.legal_moves = self.game.legal_moves_from(square)
        else:
            self._clear_selection()

    def _handle_campaign_board_click(self, position: tuple[int, int]) -> None:
        if self.pending_promotion or (
            self._bot_is_thinking() and not self._is_realtime_campaign()
        ):
            return
        square = self._board_square_at(position)
        if square is None:
            return
        if self.selected is not None:
            selected_piece = self.game.piece_at(self.selected)
            building = self.game.building_tiles.get(square)
            if (
                selected_piece is not None
                and selected_piece.kind == "K"
                and building is not None
                and building[0] == WHITE
            ):
                self._open_campaign_building(building[1])
                self._clear_selection()
                return
            candidates = [move for move in self.legal_moves if move.end == square]
            if candidates:
                self._play_move(candidates[0])
                return
        piece = self.game.piece_at(square)
        if piece is not None and piece.color == self.game.turn == WHITE:
            self.selected = square
            self.legal_moves = self.game.legal_moves_from(square)
        else:
            self._clear_selection()

    def _move_king_with_wasd(self, row_step: int, col_step: int) -> None:
        if self.game.turn != WHITE or (
            self._bot_is_thinking() and not self._is_realtime_campaign()
        ):
            return
        king_square = next(
            (
                (row, col)
                for row, board_row in enumerate(self.game.board)
                for col, piece in enumerate(board_row)
                if piece is not None and piece.color == WHITE and piece.kind == "K"
            ),
            None,
        )
        if king_square is None:
            return
        destination = (king_square[0] + row_step, king_square[1] + col_step)
        if not self.game._inside(*destination):
            return
        building = self.game.building_tiles.get(destination)
        if building is not None and building[0] == WHITE:
            self._open_campaign_building(building[1])
            return
        move = next(
            (
                candidate
                for candidate in self.game.legal_moves_from(king_square)
                if candidate.end == destination
            ),
            None,
        )
        if move is not None:
            self._play_move(move)

    def _open_campaign_building(self, kind: str) -> None:
        self.shop_menu = kind
        self.shop_confirmation = None
        self.status = f"Vstoupil jsi do: {self._shop_name(kind)}."
        self._show_farm_purchase_tutorial(kind)

    def _show_farm_purchase_tutorial(self, kind: str) -> None:
        if kind == "farm" and self.campaign.player.farms == 0:
            self._show_tutorial(
                "campaign.first-farm",
                "Kup svou prvni farmu za 250 minci. Farma ti bude automaticky "
                "vydelavat 3 mince za sekundu.",
            )

    def _campaign_shop_owner(self, square: tuple[int, int]) -> str:
        return BLACK if square[0] < self.game.board_size // 2 else WHITE

    def _board_layout(self) -> tuple[int, tuple[float, float]]:
        if self.active_level == 2:
            square_size = max(24, round(32 * self.zoom))
            board_width = self.game.board_size * square_size
            board_height = self.game.board_size * square_size
            view_top = 68
            view_height = WINDOW_SIZE[1] - view_top
            base_x = max(0, (WINDOW_SIZE[0] - board_width) // 2)
            base_y = view_top + max(0, (view_height - board_height) // 2)
            return square_size, (
                base_x + self.camera_offset[0],
                base_y + self.camera_offset[1],
            )
        base_square_size = (
            CLASSIC_SQUARE_SIZE
            if self.game.board_size == CLASSIC_BOARD_SIZE
            else SQUARE_SIZE
        )
        square_size = max(12, round(base_square_size * self.zoom))
        board_offset = (
            BOARD_VIEW_PIXELS - self.game.board_size * square_size
        ) // 2
        return square_size, (BOARD_LEFT + board_offset, BOARD_TOP + board_offset)

    def _clamp_camera_offset(self) -> None:
        self.camera_offset = self._clamped_camera_offset(
            self.camera_offset, keep_king_visible=False
        )

    def _clamped_camera_offset(
        self,
        offset: tuple[float, float],
        *,
        keep_king_visible: bool = True,
    ) -> tuple[float, float]:
        if self.active_level != 2:
            return (0, 0)
        square_size = max(24, round(32 * self.zoom))
        board_width = self.game.board_size * square_size
        board_height = board_width
        view_top = 68
        view_height = WINDOW_SIZE[1] - view_top
        base_x = max(0, (WINDOW_SIZE[0] - board_width) // 2)
        base_y = view_top + max(0, (view_height - board_height) // 2)
        min_x = min(0, WINDOW_SIZE[0] - board_width) - base_x
        max_x = max(0, WINDOW_SIZE[0] - board_width) - base_x
        min_y = min(0, view_height - board_height) - (base_y - view_top)
        max_y = max(0, view_height - board_height) - (base_y - view_top)
        king_square = self._king_square(WHITE)
        if keep_king_visible and self.zoom > 1.0 and king_square is not None:
            king_row, king_col = king_square
            min_x = max(
                -base_x - board_width + square_size,
                -base_x - king_col * square_size,
            )
            max_x = min(
                WINDOW_SIZE[0] - base_x - square_size,
                WINDOW_SIZE[0] - base_x - (king_col + 1) * square_size,
            )
            min_y = max(
                view_top - base_y - board_height + square_size,
                view_top - base_y - king_row * square_size,
            )
            max_y = min(
                view_top + view_height - base_y - (king_row + 1) * square_size,
                view_top + view_height - base_y - square_size,
            )
        return (
            min(max_x, max(min_x, offset[0])),
            min(max_y, max(min_y, offset[1])),
        )

    def _follow_king_camera(self) -> None:
        if self.active_level != 2 or self.zoom <= 1.0:
            self.camera_target_offset = self._clamped_camera_offset((0, 0))
            return
        king_square = self._king_square(WHITE)
        if king_square is None:
            self.camera_target_offset = self._clamped_camera_offset(
                self.camera_target_offset
            )
            return

        square_size = max(24, round(32 * self.zoom))
        board_width = self.game.board_size * square_size
        view_top = 68
        view_height = WINDOW_SIZE[1] - view_top
        base_x = max(0, (WINDOW_SIZE[0] - board_width) // 2)
        base_y = view_top + max(0, (view_height - board_width) // 2)
        row, col = king_square
        target = (
            WINDOW_SIZE[0] // 2 - base_x - (col * square_size + square_size // 2),
            view_top + view_height // 2 - base_y - (row * square_size + square_size // 2),
        )
        self.camera_target_offset = self._clamped_camera_offset(target)

    def _update_camera_follow(self, elapsed_seconds: float) -> None:
        self.camera_target_offset = self._clamped_camera_offset(
            self.camera_target_offset
        )
        blend = 1 - math.exp(-CAMERA_FOLLOW_SPEED * min(elapsed_seconds, 0.1))
        self.camera_offset = tuple(
            current + (target - current) * blend
            for current, target in zip(
                self.camera_offset, self.camera_target_offset
            )
        )
        if all(
            abs(current - target) < 0.1
            for current, target in zip(
                self.camera_offset, self.camera_target_offset
            )
        ):
            self.camera_offset = self.camera_target_offset
        self._clamp_camera_offset()

    def _board_square_at(
        self, position: tuple[int, int]
    ) -> tuple[int, int] | None:
        viewport = (
            pygame.Rect((0, 0), WINDOW_SIZE)
            if self.active_level == 2
            else pygame.Rect(
                BOARD_LEFT, BOARD_TOP, BOARD_VIEW_PIXELS, BOARD_VIEW_PIXELS
            )
        )
        if not viewport.collidepoint(position):
            return None
        square_size, (origin_x, origin_y) = self._board_layout()
        col = math.floor((position[0] - origin_x) / square_size)
        row = math.floor((position[1] - origin_y) / square_size)
        return (row, col) if self.game._inside(row, col) else None

    def _handle_drag_release(self, position: tuple[int, int]) -> None:
        start = self.drag_start
        self.drag_start = None
        if (
            start is None
            or self.screen != "game"
            or self.shop_menu is not None
            or (
                self._bot_is_thinking()
                and not self._is_realtime_campaign()
            )
        ):
            return
        destination = self._board_square_at(position)
        if destination is None or destination == start:
            return
        if self.selected != start:
            self.selected = start
            self.legal_moves = self.game.legal_moves_from(start)
        square_size, (origin_x, origin_y) = self._board_layout()
        destination_position = (
            round(origin_x + destination[1] * square_size + square_size // 2),
            round(origin_y + destination[0] * square_size + square_size // 2),
        )
        self._handle_click(destination_position)

    def _start_or_continue(self) -> None:
        if not self.has_started_game or self.active_level != self.selected_level:
            self._start_new_game(reset_campaign=self.selected_level != 2)
        self.screen = (
            "death"
            if self.active_level == 2 and self.campaign.king_dead
            else "game"
        )

    def _retry_after_death(self) -> None:
        if self.hardcore_enabled:
            self.screen = "menu"
            return
        self.campaign.king_dead = False
        self.campaign.king_death_reason = None
        self._start_new_game(reset_campaign=False)
        self._mark_campaign_dirty()
        self.screen = "game"

    def _start_new_game(
        self, *, reset_campaign: bool = True, abandon_current: bool = False
    ) -> None:
        if (
            not abandon_current
            and (self.campaign_battle_active or self.boss_deployment_active)
        ):
            self.status = "Bitvu nelze prerusit resetem."
            return
        self._cancel_bot_turn()
        self.active_level = self.selected_level
        self.campaign_intro_zoom_started_at = None
        if self.active_level == 2 and reset_campaign:
            self.campaign = Campaign()
        self.game = self._create_level_game(self.active_level)
        if self.active_level == 2:
            changed = self._ensure_boss_chest_position()
            changed = self._ensure_campaign_potions() or changed
            if changed or reset_campaign:
                self._mark_campaign_dirty()
                self._flush_campaign_save(force=True)
        self.campaign_battle_active = False
        self.boss_battle_active = False
        self.boss_deployment_active = False
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.boss_deployed_army = {}
        self.deployed_armies = {}
        self.piece_move_animation = None
        self.kingdom_game = None
        self.zoom = 1.0
        self.camera_offset = (0, 0)
        self.camera_target_offset = (0, 0)
        self.shop_menu = None
        self.shop_confirmation = None
        self.status = self.game.status()
        self.has_started_game = True
        self.last_action_was_bot = False
        self.banter_started_at = pygame.time.get_ticks()
        self._clear_selection()
        if self.active_level == 1:
            self._show_tutorial(
                "classic.start",
                "Pohyb: klikni na svoji figurku a potom na cilove pole. "
                "Vyhrat muzes JEN zabitim cerneho krale. Zasahy poskozuji "
                "figurky, ale snizeni HP samo o sobe hru neukonci.",
            )
        else:
            self._show_tutorial(
                "campaign.start",
                "Kralem se pohybuj pomoci WASD nebo kliknutim na cil. Tvuj prvni "
                "cil: vstup do farmy a kup prvni farmu za 250 minci; vydela "
                "3 mince za sekundu.",
            )
            self.campaign_intro_zoom_started_at = pygame.time.get_ticks()
            self.zoom = CAMPAIGN_INTRO_START_ZOOM
            self._follow_king_camera()
        if self._is_realtime_campaign():
            self._schedule_bot_turn()

    def _play_move(self, move: Move) -> None:
        game_before = self.game
        moving_piece = self.game.piece_at(move.start)
        target_before = self.game.piece_at(move.end)
        if (
            self._is_realtime_campaign()
            and moving_piece is not None
            and moving_piece.color == WHITE
            and moving_piece.kind == "K"
            and move.end in self.game.shop_tiles
            and self._campaign_shop_owner(move.end) != WHITE
        ):
            self.status = "Nemuzes vstoupit do budov soupere."
            return
        if (
            self._is_realtime_campaign()
            and moving_piece is not None
            and moving_piece.color == WHITE
            and moving_piece.kind == "K"
            and move.end in self._boss_chest_tiles()
        ):
            self._begin_boss_deployment()
            return
        battle_finished = False
        realtime_campaign = self._is_realtime_campaign()
        potion_heal = 0
        if realtime_campaign:
            self.game.turn = WHITE
        team_health_before = self.game.team_health.copy()
        raiders_defeated = 0
        if self.game.play(move):
            if (
                self.active_level == 1
                and moving_piece is not None
                and moving_piece.color == WHITE
            ):
                if target_before is not None and target_before.color != WHITE:
                    self._show_tutorial(
                        "classic.capture",
                        "Zasah ubira figurce HP. Opakovanymi zasahy ji vyradis. "
                        "Vyhrat ale muzes jen zabitim cerneho krale.",
                    )
                elif move.promotion is not None:
                    self._show_tutorial(
                        "classic.promotion",
                        "Pesec dosahl posledni rady a povysil se na silnejsi "
                        "figurku. Damu zvol pro nejvetsi utocnou silu.",
                    )
            if (
                self._is_realtime_campaign()
                and moving_piece is not None
                and moving_piece.color == WHITE
                and moving_piece.kind == "K"
            ):
                raiders_defeated = self.campaign.remove_raiders_near(
                    move.end, self.campaign.realtime_seconds
                )
                if raiders_defeated:
                    self._mark_campaign_dirty()
                potion_heal = self._collect_campaign_potion(move.end)
                if self.campaign.boss_chest_position is not None:
                    self._show_tutorial(
                        "campaign.chest",
                        "Zlata truhla spousti souboj s bossy. Vyber az 4 "
                        "figurky a po vitezstvi ziskas odmenu.",
                    )
            if moving_piece is not None:
                self.piece_move_animation = (
                    moving_piece,
                    move.start,
                    move.end,
                    pygame.time.get_ticks() / 1000,
                )
            if realtime_campaign:
                self.game.turn = WHITE
            self.status = self.game.status()
            if raiders_defeated:
                self.status = f"Kral porazil {raiders_defeated} nepratelske pesce."
            if potion_heal:
                self.status = f"Kral se vylecil o {potion_heal} HP."
            self._record_damage_animations(team_health_before)
            self._sync_campaign_progress()
            if self.game is not game_before:
                self._clear_selection()
                return
            if (
                self.active_level == 2
                and not self.campaign_battle_active
                and moving_piece is not None
                and moving_piece.color == WHITE
                and moving_piece.kind == "K"
            ):
                self._follow_king_camera()
                self.shop_confirmation = None
                shop_kind = self.game.shop_tiles.get(move.end)
                building = self.game.building_tiles.get(move.end)
                if shop_kind is None and building is not None and building[0] == WHITE:
                    shop_kind = building[1]
                if shop_kind is not None:
                    self._open_campaign_building(shop_kind)
                    self.campaign_tab = {
                        "farm": "farms",
                        "city": "city",
                        "recruit": "city",
                        "upgrade": "city",
                        "armory": "armory",
                        "war": "armory",
                    }[self.shop_menu]
                    self.status = "Obchod otevren: " + self._shop_name(self.shop_menu)
            if self.campaign_battle_active and self.game.winner() is not None:
                self._resolve_campaign_battle()
                battle_finished = True
            elif self.active_level == 2 and not self.campaign_battle_active:
                self._collect_campaign_loot(self.game.last_loot_color)
                self._advance_campaign_action(WHITE)
        self._clear_selection()
        self.last_action_was_bot = False
        if not battle_finished:
            self._schedule_bot_turn()
        if raiders_defeated:
            self.status = f"Kral porazil {raiders_defeated} nepratelske pesce."

    def _handle_campaign_click(self, position: tuple[int, int]) -> bool:
        for tab, button in self.campaign_tab_buttons.items():
            if button.collidepoint(position):
                self.campaign_tab = tab
                if tab == "farms" and self.campaign.player.farms == 0:
                    self._show_tutorial(
                        "campaign.first-farm",
                        "Kup svou prvni farmu za 250 minci. Farma ti bude "
                        "automaticky vydelavat 3 mince za sekundu.",
                    )
                return True

        if self.game.turn != WHITE:
            return False
        if self.campaign_tab == "farms":
            if self.farm_button.collidepoint(position):
                if self.campaign.build_farm(WHITE):
                    self._campaign_action_done("Farma postavena.")
                else:
                    self.status = "Na dalsi farmu nemas dost penez."
                return True
            if self.city_button.collidepoint(position):
                if self.campaign.build_city(WHITE):
                    self._campaign_action_done("Mesto odemceno.")
                else:
                    self.status = f"Mesto vyzaduje 3 farmy a {CITY_COST} minci."
                return True
        elif self.campaign_tab == "city":
            if self.city_unlock_button.collidepoint(position):
                if self.campaign.build_city(WHITE):
                    self._campaign_action_done("Mesto odemceno.")
                else:
                    self.status = f"Mesto vyzaduje 3 farmy a {CITY_COST} minci."
                return True
            kind = next(
                (
                    kind
                    for kind, button in self.recruit_buttons.items()
                    if button.collidepoint(position)
                ),
                None,
            )
            if kind is not None:
                if self.campaign.recruit(WHITE, kind):
                    self._campaign_action_done(
                        f"Najata figurka {self._piece_name(kind)}."
                    )
                else:
                    self.status = "Najem vyzaduje mesto, penize a volne misto."
                return True
            upgrade = next(
                (
                    kind
                    for kind, button in self.upgrade_buttons.items()
                    if button.collidepoint(position)
                ),
                None,
            )
            if upgrade is not None:
                if self.campaign.upgrade_pawn(WHITE, upgrade):
                    self._campaign_action_done(
                        f"Pesec povysen na {self._piece_name(upgrade)}."
                    )
                else:
                    self.status = "Povyseni vyzaduje mesto, pesce a penize."
                return True
        elif self.campaign_tab == "armory":
            if self.armory_button.collidepoint(position):
                if self.campaign.build_armory(WHITE):
                    self._campaign_action_done("Zbrojnice postavena.")
                else:
                    self.status = self._purchase_block_reason("armory") or "Zbrojnice se nepodarila postavit."
                return True
            if self.deployment_minus_button.collidepoint(position):
                self.deployment_limit = max(1, self.deployment_limit - 1)
                return True
            if self.deployment_plus_button.collidepoint(position):
                self.deployment_limit = min(8, self.deployment_limit + 1)
                return True
            if self.declare_war_button.collidepoint(position):
                if (
                    self.campaign.player.armory
                    and self.campaign.player.army_size > 0
                    and self.campaign.rival.armory
                    and self.campaign.rival.army_size > 0
                ):
                    self._start_campaign_battle()
                else:
                    self.status = "Ty i souper potrebujete zbrojnici a armadu."
                return True
        return False

    def _start_campaign_battle(self) -> None:
        player_army = self.campaign.select_army(WHITE, self.deployment_limit)
        rival_army = self.campaign.select_army(BLACK, self.deployment_limit)
        if not any(player_army.values()) or not any(rival_army.values()):
            self.status = "Oba kralovstvi potrebuji bojove jednotky."
            return

        self.kingdom_game = self.game
        self.piece_move_animation = None
        self.deployed_armies = {WHITE: player_army, BLACK: rival_army}
        battle = ChessGame(
            board_size=CLASSIC_BOARD_SIZE,
            random_armies=False,
        )
        battle.configure_battle(self.deployed_armies)
        self.game = battle
        self.campaign_battle_active = True
        self.boss_battle_active = False
        self.status = "Bitva 8 x 8 zacala. Poraz souperova krale."
        self._show_tutorial(
            "campaign.war",
            "Vstoupil jsi do valky. Poraz kralem cerneho krale; prezivsi "
            "armada se vrati do mesta.",
        )
        self.zoom = 1.0
        self._clear_selection()

    def _boss_chest_tiles(self) -> set[tuple[int, int]]:
        if (
            self.active_level != 2
            or self.campaign_battle_active
            or self.campaign.boss_chest_claimed
            or self.campaign.player.army_size < 2
        ):
            return set()
        if self.campaign.boss_chest_position is None:
            return set()
        row, col = self.campaign.boss_chest_position
        return {(row, col), (row, col + 1), (row + 1, col), (row + 1, col + 1)}

    def _begin_boss_deployment(self) -> None:
        self._cancel_bot_turn()
        self.kingdom_game = self.game
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.boss_deployment_active = True
        self.shop_menu = None
        self.shop_confirmation = None
        self.status = "Vyber nejvyse 4 figurky do souboje s bossy."
        self._clear_selection()

    def _handle_boss_deployment_click(self, position: tuple[int, int]) -> None:
        if self.boss_cancel_button.collidepoint(position):
            self._cancel_boss_deployment()
            return
        for kind, buttons in self.boss_deployment_buttons.items():
            if buttons["minus"].collidepoint(position):
                self.boss_deployment[kind] = max(
                    0, self.boss_deployment[kind] - 1
                )
                return
            if buttons["plus"].collidepoint(position):
                selected = sum(self.boss_deployment.values())
                available = self.campaign.player.army[kind]
                if selected < 4 and self.boss_deployment[kind] < available:
                    self.boss_deployment[kind] += 1
                return
        if self.boss_start_button.collidepoint(position):
            if sum(self.boss_deployment.values()) == 0:
                self.status = "Vyber alespon jednu figurku."
                return
            self._start_boss_battle()

    def _cancel_boss_deployment(self) -> None:
        self.boss_deployment_active = False
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.kingdom_game = None
        self.status = "K truhle se muzes vratit pozdeji."
        self._schedule_bot_turn()

    def _start_boss_battle(self) -> None:
        player_army = self.boss_deployment.copy()
        progression = min(
            3,
            max(0, (self.campaign.player.army_size - 3) // 3)
            + self.campaign.boss_losses,
        )
        difficulty_range = {"easy": 1, "medium": 2, "hard": 2}
        boss_count = random.randint(
            1,
            min(4, difficulty_range[self.bot_difficulty] + progression),
        )
        difficulty_rank = {"easy": 0, "medium": 1, "hard": 2}[
            self.bot_difficulty
        ]
        strength = min(4, difficulty_rank + progression)
        boss_kinds = random.choices(
            ("P", "N", "B", "R", "Q"),
            weights=(
                max(1, 8 - strength * 2),
                3 + strength,
                3 + strength,
                1 + strength * 2,
                1 + strength * 2,
            ),
            k=boss_count,
        )
        boss_army = {kind: boss_kinds.count(kind) for kind in ARMY_KINDS}
        self.boss_deployed_army = player_army
        self.deployed_armies = {WHITE: player_army, BLACK: boss_army}
        self.piece_move_animation = None
        battle = ChessGame(
            board_size=6,
            random_armies=False,
            king_only=True,
        )
        battle.configure_battle(self.deployed_armies)
        self.game = battle
        self.boss_deployment_active = False
        self.boss_battle_active = True
        self.campaign_battle_active = True
        self.status = "Souboj o truhlu 6 x 6. Poraz krale bossu."
        self.zoom = 1.0
        self.camera_offset = (0, 0)
        self.camera_target_offset = (0, 0)
        self._clear_selection()

    def _resolve_campaign_battle(self) -> None:
        if self.boss_battle_active:
            self._resolve_boss_battle()
            return

        survivors = {WHITE: {}, BLACK: {}}
        for color in (WHITE, BLACK):
            survivors[color] = {kind: 0 for kind in ARMY_KINDS}
        for row in self.game.board:
            for piece in row:
                if piece is not None and piece.kind != "K":
                    survivors[piece.color][piece.kind] += 1

        winner = self.game.winner()
        self.campaign.resolve_battle(self.deployed_armies, survivors)
        self.campaign.player.coins += self.game.coins[WHITE]
        if winner == WHITE:
            self.campaign.faction(winner).coins += 250
        if winner in (WHITE, BLACK):
            result = "Vitezstvi" if winner == WHITE else "Porazka"
            self.status = f"{result}. Prezivsi jednotky se vraci do kralovstvi."
        else:
            self.status = "Bitva skoncila. Prezivsi jednotky se vraci domů."

        self._mark_campaign_dirty()
        battle_result = self.status
        if self.kingdom_game is not None:
            self.game = self.kingdom_game
        self.kingdom_game = None
        self.piece_move_animation = None
        self.campaign_battle_active = False
        self.deployed_armies = {}
        self.game.turn = WHITE
        self._clear_selection()
        self.status = battle_result
        self._flush_campaign_save(force=True)

    def _resolve_boss_battle(self) -> None:
        winner = self.game.winner()
        survivors = {kind: 0 for kind in ARMY_KINDS}
        for row in self.game.board:
            for piece in row:
                if piece is not None and piece.color == WHITE and piece.kind != "K":
                    survivors[piece.kind] += 1

        player = self.campaign.player
        for kind in ARMY_KINDS:
            reserve = max(0, player.army[kind] - self.boss_deployed_army[kind])
            player.army[kind] = reserve + (
                survivors[kind] if winner == WHITE else 0
            )

        if winner == WHITE:
            reward = round(
                180 * FARM_INCOME_PER_SECOND * player.farms
            )
            player.coins += reward
            self.campaign.boss_chest_claimed = True
            result = f"Vitezstvi! Truhla obsahuje {reward} zlata (3 minuty prijmu farem)."
        else:
            self.campaign.boss_losses += 1
            result = "Porazka. Nasazene figurky jsi ztratil a truhla zustava."

        if self.kingdom_game is not None:
            self.game = self.kingdom_game
        self.kingdom_game = None
        self.piece_move_animation = None
        self.campaign_battle_active = False
        self.boss_battle_active = False
        self.boss_deployment_active = False
        self.boss_deployed_army = {}
        self.deployed_armies = {}
        self.game.turn = WHITE
        self._clear_selection()
        self.status = result
        self._mark_campaign_dirty()
        self._flush_campaign_save(force=True)
        self._schedule_bot_turn()

    def _campaign_action_done(self, message: str) -> None:
        self._advance_campaign_action(WHITE)
        if message.startswith("Farma"):
            self._show_tutorial(
                "campaign.farm",
                "Farmy automaticky vydelavaji mince kazdou sekundu. Dalsi farma "
                "je drazsi a mesto odemkne dalsi rozvoj.",
            )
        elif message.startswith("Mesto"):
            self._show_tutorial(
                "campaign.city",
                "Mesto odemyka najem pesaku a dalsich figurek. Najmi alespon "
                "dve jednotky, aby se objevila pokladova truhla.",
            )
        elif message.startswith("Najata"):
            self._show_tutorial(
                "campaign.recruit",
                "Jednotky najimas v zalozce Mesto. Najmi dve pro odemceni "
                "truhly a tri pro pristup do zbrojnice.",
            )
        elif message.startswith("Pesec povysen"):
            self._show_tutorial(
                "campaign.upgrade",
                "V zalozce Mesto muzes povysit pesce na silnejsi figurku. "
                "Vylepseni stoji mince a spotrebuje puvodni jednotku.",
            )
        elif message.startswith("Zbrojnice"):
            self._show_tutorial(
                "campaign.armory",
                "Zbrojnice otevre pripravu valky. Vyber velikost oddilu a "
                "nasad jednotky; v bitve hraje bot proti tobe.",
            )
        elif message.startswith("Valka") or message.startswith("Bitva"):
            self._show_tutorial(
                "campaign.battle",
                "V bitve ovladas figurky stejne jako v uvodni hre. Poraz "
                "soupere a prezivsi jednotky se vrati do armady.",
            )
        if self.active_level == 2 and not self.campaign_battle_active:
            if self._ensure_boss_chest_position():
                self._mark_campaign_dirty()
                self._show_tutorial(
                    "campaign.chest-unlocked",
                    "Truhla se odemkla! Kralem dojdi k truhle, vyber az 4 "
                    "jednotky a poraz strazce pro poklad.",
                )
        if not self._is_realtime_campaign():
            self.game.turn = BLACK
        self.status = message
        self.shop_confirmation = None
        self._clear_selection()
        self.last_action_was_bot = False
        self._schedule_bot_turn()

    def _toggle_tutorials(self) -> None:
        self.tutorial_enabled = not self.tutorial_enabled
        save_tutorials_enabled(self.tutorial_enabled)
        self.tutorial_seen.clear()
        self.tutorial_queue.clear()
        self.tutorial_active = None
        self.tutorial_until = 0
        if not self.tutorial_enabled:
            return
        if self.screen == "game" and self.active_level == 2:
            self._show_tutorial(
                "campaign.start",
                "Kralem se pohybuj pomoci WASD nebo kliknutim na cil. Tvuj prvni "
                "cil: vstup do farmy a kup prvni farmu za 250 minci; vydela "
                "3 mince za sekundu.",
            )
        elif self.screen == "game":
            self._show_tutorial(
                "classic.start",
                "Klikni na svoji figurku a potom na cilove pole. Poraz cerneho "
                "krale, abys vyhral.",
            )

    def _toggle_language(self) -> None:
        self.language = "en" if self.language == "cs" else "cs"
        save_language(self.language)
        pygame.display.set_caption(translate("Šachy — základ", self.language))
        self._rendered_text_cache.clear()

    def _toggle_hardcore(self) -> None:
        disabling = self.hardcore_enabled
        self.hardcore_enabled = not self.hardcore_enabled
        save_hardcore_enabled(self.hardcore_enabled)
        if not disabling:
            return

        self._cancel_bot_turn()
        self.campaign_battle_active = False
        self.boss_battle_active = False
        self.boss_deployment_active = False
        self.kingdom_game = None
        self.selected_level = 2
        self.tutorial_seen.clear()
        self.tutorial_queue.clear()
        self.tutorial_active = None
        self.tutorial_until = 0
        self._start_new_game(reset_campaign=True)
        self.screen = "menu"

    def _advance_campaign_action(self, color: str) -> None:
        self.campaign.advance_day(color)
        if color == BLACK:
            self.campaign.bot_action(self.bot_difficulty)
        self._mark_campaign_dirty()

    def _collect_campaign_loot(self, color: str | None) -> None:
        if color != WHITE or self.game.last_loot_value <= 0:
            return
        faction = self.campaign.player
        loot_value = round(
            self.game.last_loot_value * max(1, faction.farms)
        )
        faction.coins += loot_value
        self.campaign.loot_respawns.append(
            self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
        )
        self.status = f"Kral sebral {loot_value} zlata."
        self._show_tutorial(
            "campaign.coins",
            "Zlate mince sbiras kralem. Kazda se obnovi samostatne po jedne "
            "sekunde a odmena roste s poctem farem.",
        )
        self._mark_campaign_dirty()

    @staticmethod
    def _shop_name(kind: str) -> str:
        return {
            "farm": "Farma",
            "city": "Mesto",
            "armory": "Zbrojnice",
            "recruit": "Najem",
            "upgrade": "Vylepseni",
            "war": "Valka",
        }[kind]

    def _purchase_is_available(self, kind: str) -> bool:
        return self._purchase_block_reason(kind) is None

    def _purchase_block_reason(self, kind: str) -> str | None:
        player = self.campaign.player
        if kind == "farm":
            if player.farms >= FARM_LIMIT:
                return f"Uz mas maximalni pocet {FARM_LIMIT} farem."
            cost = self.campaign.farm_cost(WHITE)
            if player.coins < cost:
                return f"Farma stoji {cost} zlata, mas jen {player.coins}."
            return None
        if kind == "city":
            if player.city:
                return "Mesto uz vlastnis."
            if player.farms < 3:
                return f"Mesto vyzaduje 3 farmy; mas {player.farms}."
            if player.coins < CITY_COST:
                return f"Mesto stoji {CITY_COST} zlata, mas jen {player.coins}."
            return None
        if kind == "armory":
            if player.armory:
                return "Zbrojnici uz vlastnis."
            if not player.city:
                return "Zbrojnice vyzaduje nejdriv postavene mesto."
            if player.army_size < 3:
                return f"Zbrojnice vyzaduje 3 jednotky; mas {player.army_size}."
            if player.coins < ARMORY_COST:
                return f"Zbrojnice stoji {ARMORY_COST} zlata, mas jen {player.coins}."
            return None
        if kind.startswith("recruit_"):
            piece_kind = kind.removeprefix("recruit_")
            cost = RECRUIT_COSTS.get(piece_kind)
            if not player.city:
                return "Najem je dostupny az po postaveni mesta."
            if player.army_size >= 16:
                return "Armada uz ma maximalnich 16 jednotek."
            if cost is not None and player.coins < cost:
                return f"Figurka stoji {cost} zlata, mas jen {player.coins}."
            return None
        if kind.startswith("upgrade_"):
            piece_kind = kind.removeprefix("upgrade_")
            source = UPGRADE_SOURCES.get(piece_kind)
            if source is None:
                return "Tento upgrade neni dostupny."
            if not player.city:
                return "Vylepseni je dostupne az po postaveni mesta."
            if player.army[source] < 1:
                return f"K vylepseni na {self._piece_name(piece_kind)} potrebujes {self._piece_name(source)}."
            cost = ARMY_UPGRADE_COSTS[piece_kind]
            if player.coins < cost:
                return f"Vylepseni stoji {cost} zlata, mas jen {player.coins}."
            return None
        return "Tento nakup neni dostupny."

    def _building_visuals(
        self,
    ) -> dict[tuple[int, int], tuple[str, str, bool, int, int]]:
        result = {}
        for square, (owner, kind) in self.game.building_tiles.items():
            faction = self.campaign.faction(owner)
            owned = {
                "farm": faction.farm_sector,
                "city": faction.city,
                "armory": faction.armory,
            }[kind]
            progress = (
                faction.farms
                if kind == "farm"
                else min(12, faction.army_size)
                if kind == "city"
                else int(owned)
            )
            level = min(6, progress // 2)
            result[square] = (kind, owner, owned, progress, level)
        return result

    def _shop_screen_kind(self) -> str:
        if self.shop_menu in ("city", "recruit", "upgrade"):
            return "city"
        if self.shop_menu in ("armory", "war"):
            return "armory"
        return "farm"

    def _draw_shop_screen(self) -> None:
        screen_kind = self._shop_screen_kind()
        player = self.campaign.player
        titles = {"farm": "FARMA", "city": "MESTO", "armory": "ZBROJNICE"}
        palettes = {
            "farm": (67, 112, 67),
            "city": (66, 101, 132),
            "armory": (143, 75, 60),
        }
        self.surface.fill((24, 31, 29))
        pygame.draw.rect(self.surface, palettes[screen_kind], (0, 0, 1040, 108))
        self._text(titles[screen_kind], self.title_font, (255, 244, 214), (48, 34))
        self._text(
            f"Den {self.campaign.day}   Zlato {player.coins}",
            self.font,
            (255, 244, 214),
            (720, 42),
        )
        self._draw_button(self.shop_screen_back_button, "Zpet na mapu")

        building = pygame.Rect(48, 132, 324, 488)
        pygame.draw.rect(self.surface, (37, 46, 40), building, border_radius=8)
        cell_width = 82
        cell_height = 96
        origin_x = building.x + 38
        origin_y = building.y + 46
        owned = {
            "farm": player.farm_sector,
            "city": player.city,
            "armory": player.armory,
        }[screen_kind]
        base_color = palettes[screen_kind] if owned else tuple(
            max(35, component - 26) for component in palettes[screen_kind]
        )
        progress = (
            player.farms
            if screen_kind == "farm"
            else min(12, player.army_size)
            if screen_kind == "city"
            else int(owned)
        )
        level = min(6, progress // 2)
        for index in range(12):
            row, col = divmod(index, 3)
            tile = pygame.Rect(
                origin_x + col * cell_width,
                origin_y + row * cell_height,
                cell_width - 4,
                cell_height - 4,
            )
            active = owned and (
                index < progress or (screen_kind == "city" and index == 0)
            )
            improved = (
                active
                and index % 2 == 1
                and (index + 1) // 2 <= level
            )
            self.renderer._draw_building_tile(
                self.surface, tile, screen_kind, base_color, active, improved
            )
        if screen_kind == "farm":
            preview_status = f"{player.farms}/{FARM_LIMIT} farm | stupen {level}"
        elif screen_kind == "city":
            preview_status = f"{player.army_size} jednotek | stupen {level}"
        else:
            preview_status = "zbrojnice postavena" if owned else "volna plocha"
        self._center_text(
            preview_status,
            self.small_font,
            (255, 244, 214),
            (building.centerx, building.bottom - 58),
        )
        building_label = self.title_font.render(
            translate(titles[screen_kind], self.language),
            True,
            (255, 244, 214),
        )
        self.surface.blit(
            building_label,
            building_label.get_rect(center=(building.centerx, building.bottom - 18)),
        )

        pygame.draw.rect(self.surface, (34, 42, 38), (405, 132, 587, 488), border_radius=8)
        self._text(
            "Vlastnis" if owned else "Dosud nepostaveno",
            self.font,
            (171, 224, 160) if owned else (238, 194, 133),
            (440, 158),
        )
        buttons: dict[str, pygame.Rect] = {}
        if screen_kind == "farm":
            cost = self.campaign.farm_cost(WHITE)
            self._text(
                f"Vlastni farmy: {player.farms}   Prijem: +{player.farms * FARM_INCOME_PER_SECOND:g} zl/s",
                self.font,
                (232, 235, 224),
                (440, 220),
            )
            buttons["farm"] = pygame.Rect(440, 292, 510, 64)
            self._draw_button(
                buttons["farm"],
                (
                    f"Koupit sektor a prvni farmu - {cost} zl"
                    if not player.farm_sector
                    else f"Postavit dalsi farmu - {cost} zl"
                ),
                enabled=self._purchase_is_available("farm"),
            )
            self._text(
                f"Za kazde 2 farmy se v oblasti postavi sklad ({player.farms // 2}/6).",
                self.small_font,
                (190, 202, 191),
                (440, 382),
            )
            self._text(
                "Farmy generuji zlato prubezne v realnem case.",
                self.small_font,
                (190, 202, 191),
                (440, 406),
            )
        elif screen_kind == "city":
            if not player.city:
                buttons["city"] = pygame.Rect(440, 250, 510, 64)
                self._draw_button(
                    buttons["city"],
                    f"Postavit mesto - {CITY_COST} zl",
                    enabled=self._purchase_is_available("city"),
                )
                self._text("Mesto se odemkne po postaveni tri farem.", self.small_font, (190, 202, 191), (440, 338))
            else:
                self._text("Mesto verbuje pouze pesaky", self.small_font, (232, 235, 224), (440, 208))
                button = pygame.Rect(440, 234, 510, 56)
                buttons["recruit_P"] = button
                self._draw_button(
                    button,
                    f"Pesec x{player.army['P']} - {RECRUIT_COSTS['P']} zl",
                    enabled=self._purchase_is_available("recruit_P"),
                )
                self._text("Vylepsit pesaka", self.small_font, (232, 235, 224), (440, 420))
                for index, kind in enumerate(("N", "B", "R", "Q")):
                    source = UPGRADE_SOURCES[kind]
                    cost = ARMY_UPGRADE_COSTS[kind]
                    button = pygame.Rect(440 + (index % 2) * 260, 446 + (index // 2) * 58, 248, 48)
                    buttons[f"upgrade_{kind}"] = button
                    self._draw_button(
                        button,
                        f"{self._piece_name(source)} na {self._piece_name(kind)} - {cost} zl",
                        enabled=player.army[source] > 0 and player.coins >= cost,
                    )
        elif screen_kind == "armory":
            if not player.armory:
                buttons["armory"] = pygame.Rect(440, 250, 510, 64)
                self._draw_button(
                    buttons["armory"],
                    f"Postavit zbrojnici - {ARMORY_COST} zl",
                    enabled=self._purchase_is_available("armory"),
                )
                self._text("Zbrojnice vyzaduje mesto a tri jednotky.", self.small_font, (190, 202, 191), (440, 338))
            else:
                self._text("Oddil do dalsi bitvy", self.font, (232, 235, 224), (440, 222))
                buttons["deploy_minus"] = pygame.Rect(440, 278, 64, 52)
                buttons["deploy_plus"] = pygame.Rect(790, 278, 64, 52)
                self._draw_button(buttons["deploy_minus"], "-", enabled=True)
                self._draw_button(buttons["deploy_plus"], "+", enabled=True)
                self._center_text(str(self.deployment_limit), self.title_font, (255, 244, 214), (750, 304))
                ready = player.army_size > 0 and self.campaign.rival.armory and self.campaign.rival.army_size > 0
                buttons["war"] = pygame.Rect(440, 370, 510, 64)
                self._draw_button(buttons["war"], "Vyhlasit valku", enabled=ready)
                self._text(
                    f"Tvoje jednotky: {player.army_size}   Souper: {self.campaign.rival.army_size}",
                    self.small_font,
                    (190, 202, 191),
                    (440, 458),
                )
        self.shop_screen_buttons = buttons
        self._text(self.status, self.small_font, (216, 224, 214), (440, 576))
        self.shop_confirmation_buttons = {}
        if self.shop_confirmation is not None:
            overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            overlay.fill((8, 12, 10, 190))
            self.surface.blit(overlay, (0, 0))
            panel = pygame.Rect(245, 224, 550, 300)
            pygame.draw.rect(self.surface, (36, 45, 39), panel, border_radius=8)
            pygame.draw.rect(self.surface, (218, 188, 115), panel, width=2, border_radius=8)
            name = self._shop_name(self.shop_confirmation)
            self._center_text(
                f"Opravdu koupit: {name}?",
                self.title_font,
                (255, 244, 214),
                (panel.centerx, panel.y + 64),
            )
            price = {
                "farm": self.campaign.farm_cost(WHITE),
                "city": CITY_COST,
                "armory": ARMORY_COST,
            }[self.shop_confirmation]
            self._center_text(
                f"Cena {price} zlata | mas {player.coins}",
                self.font,
                (230, 224, 204),
                (panel.centerx, panel.y + 122),
            )
            reason = self._purchase_block_reason(self.shop_confirmation)
            self._center_text(
                reason or "Splnujes podminky pro nakup.",
                self.small_font,
                (244, 170, 142) if reason else (171, 224, 160),
                (panel.centerx, panel.y + 160),
            )
            self.shop_confirmation_buttons = {
                "yes": pygame.Rect(panel.x + 72, panel.y + 190, 170, 56),
                "no": pygame.Rect(panel.x + 308, panel.y + 190, 170, 56),
            }
            self._draw_button(
                self.shop_confirmation_buttons["yes"],
                "Ano",
                enabled=self._purchase_is_available(self.shop_confirmation),
            )
            self._draw_button(self.shop_confirmation_buttons["no"], "Ne")

    def _handle_shop_screen_click(self, position: tuple[int, int]) -> None:
        if self.shop_screen_back_button.collidepoint(position):
            self.shop_menu = None
            self.shop_confirmation = None
            return
        if not self._is_realtime_campaign() and (
            self._bot_is_thinking() or self.game.turn != WHITE
        ):
            return
        if self.shop_confirmation is not None:
            answer = next(
                (
                    name
                    for name, rect in self.shop_confirmation_buttons.items()
                    if rect.collidepoint(position)
                ),
                None,
            )
            if answer == "no":
                self.shop_confirmation = None
            elif answer == "yes":
                kind = self.shop_confirmation
                reason = self._purchase_block_reason(kind)
                if reason is not None:
                    self.status = reason
                    return
                bought = {
                    "farm": self.campaign.build_farm,
                    "city": self.campaign.build_city,
                    "armory": self.campaign.build_armory,
                }[kind](WHITE)
                if bought:
                    self.shop_confirmation = None
                    self._campaign_action_done(
                        {
                            "farm": "Farmarsky sektor a prvni farma postaveny.",
                            "city": "Mesto postaveno.",
                            "armory": "Zbrojnice postavena.",
                        }[kind]
                    )
            return
        action = next(
            (name for name, rect in self.shop_screen_buttons.items() if rect.collidepoint(position)),
            None,
        )
        if action is None:
            return
        if action == "deploy_minus":
            self.deployment_limit = max(1, self.deployment_limit - 1)
        elif action == "deploy_plus":
            self.deployment_limit = min(8, self.deployment_limit + 1)
        elif action == "war":
            self._advance_campaign_action(WHITE)
            self.shop_menu = None
            self._start_campaign_battle()
        elif action.startswith("recruit_"):
            kind = action.removeprefix("recruit_")
            if self.campaign.recruit(WHITE, kind):
                self._campaign_action_done(f"Najata figurka {self._piece_name(kind)}.")
            else:
                self.status = self._purchase_block_reason(action) or "Nabor se nepodaril."
        elif action.startswith("upgrade_"):
            kind = action.removeprefix("upgrade_")
            if self.campaign.upgrade_pawn(WHITE, kind):
                self._campaign_action_done(f"Pesec povysen na {self._piece_name(kind)}.")
            else:
                self.status = self._purchase_block_reason(action) or "Vylepseni se nepodarilo."
        elif action == "farm":
            if self.campaign.build_farm(WHITE):
                self._campaign_action_done(
                    "Farmarsky sektor a prvni farma postaveny."
                    if self.campaign.player.farms == 1
                    else "Farma postavena."
                )
            else:
                self.status = self._purchase_block_reason("farm") or "Farmu se nepodarilo postavit."
        elif action == "city":
            self.shop_confirmation = "city"
        elif action == "armory":
            self.shop_confirmation = "armory"

    def _activate_shop_card(self, kind: str) -> None:
        if self.shop_menu != kind:
            self.status = "Vejdi kralem na barevnou branu teto karty."
            return
        self._show_farm_purchase_tutorial(kind)
        if self.game.turn != WHITE or self._bot_is_thinking():
            return

        success = False
        message = "Na tento nakup nemas dost penez nebo nesplnujes podminky."
        if kind == "farm":
            success = self.campaign.build_farm(WHITE)
            message = "Farma postavena. Okamzite zvysuje prijem."
        elif kind == "city":
            success = self.campaign.build_city(WHITE)
            message = "Mesto postaveno."
        elif kind == "armory":
            success = self.campaign.build_armory(WHITE)
            message = "Zbrojnice postavena."
        elif kind == "recruit":
            success = self.campaign.recruit(WHITE, "P")
            message = "Pesec naverbovan."
        elif kind == "upgrade":
            source = UPGRADE_SOURCES["N"]
            success = self.campaign.upgrade_pawn(WHITE, "N")
            message = "Pesec vylepsen na kone."
        elif kind == "war":
            if (
                self.campaign.player.armory
                and self.campaign.player.army_size > 0
                and self.campaign.rival.armory
                and self.campaign.rival.army_size > 0
            ):
                self._advance_campaign_action(WHITE)
                self.shop_menu = None
                self._start_campaign_battle()
                return
            self.status = "Pro bitvu potrebujes dve zbrojnice a armady."
            return

        if success:
            self._campaign_action_done(message)
        else:
            self.status = message

    def _shop_card_info(
        self, kind: str
    ) -> tuple[str, str, bool, bool]:
        player = self.campaign.player
        if kind == "farm":
            return (
                f"Farma x{player.farms}" if player.farms else "Farma",
                f"{self.campaign.farm_cost(WHITE)} zl | +{FARM_INCOME_PER_SECOND:g} zl/s",
                player.coins >= self.campaign.farm_cost(WHITE)
                and player.farms < FARM_LIMIT,
                player.farms > 0,
            )
        if kind == "city":
            return (
                "Mesto",
                "Vlastni" if player.city else f"{CITY_COST} zl | potrebuje 3 farmy",
                player.city or (player.farms >= 3 and player.coins >= CITY_COST),
                player.city,
            )
        if kind == "armory":
            return (
                "Zbrojnice",
                "Vlastni" if player.armory else f"{ARMORY_COST} zl | potrebuje mesto",
                player.armory or (player.city and player.coins >= ARMORY_COST),
                player.armory,
            )
        if kind == "recruit":
            return (
                "Najem pesce",
                f"{RECRUIT_COSTS['P']} zl | potrebuje mesto",
                player.city and player.coins >= RECRUIT_COSTS["P"] and player.army_size < 16,
                False,
            )
        if kind == "upgrade":
            source = UPGRADE_SOURCES["N"]
            cost = ARMY_UPGRADE_COSTS["N"]
            return (
                "Pesec na kone",
                f"{cost} zl | potrebuje pesce",
                player.city and player.army["P"] > 0 and player.coins >= cost,
                False,
            )
        ready = (
            player.armory
            and player.army_size > 0
            and self.campaign.rival.armory
            and self.campaign.rival.army_size > 0
        )
        return "Vyhlasit valku", "Priprav armadu" if not ready else "Vstup do bitvy", ready, False

    def _draw_shop_cards(self) -> None:
        labels = {
            "farm": "F",
            "city": "M",
            "armory": "Z",
            "recruit": "+",
            "upgrade": "^",
            "war": "!",
        }
        for kind, rect in self.shop_cards.items():
            title, detail, affordable, owned = self._shop_card_info(kind)
            accessible = self.shop_menu == kind and self.game.turn == WHITE
            color = (
                (83, 142, 84)
                if owned
                else (205, 169, 99)
                if accessible and affordable
                else (87, 119, 91)
                if affordable
                else (83, 75, 69)
            )
            pygame.draw.rect(self.surface, (27, 34, 31), rect, border_radius=5)
            tile = rect.inflate(-3, -3)
            pygame.draw.rect(self.surface, color, tile, border_radius=4)
            icon = self.small_font.render(labels[kind], True, (255, 247, 220))
            self.surface.blit(icon, (rect.x + 8, rect.y + 5))
            text_color = (255, 248, 225) if accessible else (218, 222, 211)
            self._text(title, self.small_font, text_color, (rect.x + 34, rect.y + 4))
            self._text(detail, self.small_font, text_color, (rect.x + 34, rect.y + 25))
            indicator = "OK" if affordable else "-"
            indicator_image = self.small_font.render(
                indicator,
                True,
                (170, 245, 171) if affordable else (235, 157, 142),
            )
            self.surface.blit(
                indicator_image,
                indicator_image.get_rect(midright=(rect.right - 8, rect.centery)),
            )

    def _undo(self) -> None:
        if self.hardcore_enabled:
            self.status = "Hardcore: tahy nelze vracet."
            return
        if self.active_level == 1:
            return
        if self.active_level == 2 and not self.campaign_battle_active:
            self.status = "Ekonomicke tahy kampane nelze vratit."
            return
        self._cancel_bot_turn()
        if self.game.undo():
            if self.last_action_was_bot:
                self.game.undo()
            self.last_action_was_bot = False
            self.status = self.game.status()
            success = False
            message = ""
    def _schedule_bot_turn(self) -> None:
        if self._is_realtime_campaign():
            if self.game.winner() is not None or self.campaign.king_dead:
                return
            if self.bot_due_at is not None or self.bot_future is not None:
                return
            self.bot_due_at = pygame.time.get_ticks() + random.randint(250, 500)
            self.status = "Souper rozviji kralovstvi..."
            return
        if self.game.turn != BLACK or self.game.winner() is not None:
            self.status = self.game.status()
            return
        self.bot_due_at = pygame.time.get_ticks() + random.randint(120, 260)
        self.status = "Souper na tahu..."

    def _update_bot_turn(self) -> None:
        realtime_campaign = self._is_realtime_campaign()
        if self.bot_due_at is not None:
            if pygame.time.get_ticks() < self.bot_due_at:
                return
            self.bot_due_at = None
            game_snapshot = deepcopy(self.game)
            if realtime_campaign:
                game_snapshot.turn = BLACK
            self.bot_future = self.bot_executor.submit(
                choose_move, game_snapshot, self.bot_difficulty
            )

        if self.bot_future is None or not self.bot_future.done():
            return

        future = self.bot_future
        self.bot_future = None
        if (
            (not realtime_campaign and self.game.turn != BLACK)
            or self.game.winner() is not None
        ):
            return

        move = future.result()
        game_before = self.game
        moving_piece = self.game.piece_at(move.start) if move is not None else None
        if realtime_campaign:
            self.game.turn = BLACK
        team_health_before = self.game.team_health.copy()

        if move is None:
            if realtime_campaign:
                self.game.turn = WHITE
                self._advance_campaign_action(BLACK)
                self.status = "Souper rozviji kralovstvi..."
                self._schedule_bot_turn()
                return
            if self.game.pass_turn():
                self.status = self.game.status()
                self.last_action_was_bot = True
                return
            self.status = self.game.status()
            self.last_action_was_bot = False
            return

        if (
            realtime_campaign
            and moving_piece is not None
            and moving_piece.color == BLACK
            and moving_piece.kind == "K"
            and move.end in self._boss_chest_tiles()
        ):
            safe_moves = [
                candidate
                for candidate in self.game.all_legal_moves()
                if candidate.end not in self._boss_chest_tiles()
            ]
            if safe_moves:
                move = random.choice(safe_moves)
                moving_piece = self.game.piece_at(move.start)

        if not self.game.play(move):
            legal_moves = self.game.all_legal_moves()
            if not legal_moves:
                if realtime_campaign:
                    self.game.turn = WHITE
                    self._advance_campaign_action(BLACK)
                    self._schedule_bot_turn()
                else:
                    self.status = self.game.status()
                return
            move = random.choice(legal_moves)
            moving_piece = self.game.piece_at(move.start)
            if not self.game.play(move):
                if realtime_campaign:
                    self.game.turn = WHITE
                self.status = "Souper upravuje svuj tah..."
                self._schedule_bot_turn()
                return

        if moving_piece is not None:
            self.piece_move_animation = (
                moving_piece,
                move.start,
                move.end,
                pygame.time.get_ticks() / 1000,
            )
        if realtime_campaign:
            self.game.turn = WHITE
        self.status = self.game.status()
        self._record_damage_animations(team_health_before)
        self.last_action_was_bot = True
        self._sync_campaign_progress()
        if self.game is not game_before:
            return
        if realtime_campaign:
            self._collect_campaign_loot(self.game.last_loot_color)
            self._advance_campaign_action(BLACK)
            self._schedule_bot_turn()
            return
        if self.campaign_battle_active and self.game.winner() is not None:
            self._resolve_campaign_battle()

    def _sync_campaign_progress(self) -> None:
        if (
            self.active_level == 1
            and self.game.winner() == WHITE
        ):
            self._cancel_bot_turn()
            self.unlocked_level = max(self.unlocked_level, 2)
            save_unlocked_level(self.unlocked_level)
            self.selected_level = 2
            self._start_new_game(reset_campaign=False)

    def _advance_campaign_intro_zoom(self) -> None:
        if self.campaign_intro_zoom_started_at is None:
            return
        elapsed = pygame.time.get_ticks() - self.campaign_intro_zoom_started_at
        progress = min(1.0, max(0.0, elapsed / CAMPAIGN_INTRO_ZOOM_DURATION_MS))
        eased = progress * progress * progress * (
            progress * (progress * 6 - 15) + 10
        )
        self.zoom = CAMPAIGN_INTRO_START_ZOOM - (
            CAMPAIGN_INTRO_START_ZOOM - 1.0
        ) * eased
        self._follow_king_camera()
        if progress >= 1.0:
            self.campaign_intro_zoom_started_at = None
            self.zoom = 1.0
            self.camera_offset = (0, 0)
            self.camera_target_offset = (0, 0)

    def _cancel_bot_turn(self) -> None:
        self.bot_due_at = None
        if self.bot_future is not None:
            self.bot_future.cancel()
            self.bot_future = None

    def _bot_is_thinking(self) -> bool:
        return self.bot_due_at is not None or self.bot_future is not None

    def _is_realtime_campaign(self) -> bool:
        return self.active_level == 2 and not self.campaign_battle_active

    def _record_damage_animations(
        self, team_health_before: dict[str, int]
    ) -> None:
        started_at = pygame.time.get_ticks() / 1000
        for color in (WHITE, BLACK):
            before = team_health_before[color]
            after = self.game.team_health[color]
            if before != after:
                self.team_health_animations[color] = (before, after, started_at)

        damage_by_square: dict[tuple[int, int], int] = {}
        for square, damage in self.game.last_damage:
            damage_by_square[square] = damage_by_square.get(square, 0) + damage
            self.damage_popups.append((square, damage, started_at))

        for square, damage in damage_by_square.items():
            piece = self.game.piece_at(square)
            if piece is not None and (piece.health or 0) + damage <= piece.max_health:
                self.piece_health_animations[square] = (
                    (piece.health or 0) + damage,
                    piece.health or 0,
                    started_at,
                )

    @staticmethod
    def _animated_health(
        animation: tuple[int, int, float] | None,
        fallback: int,
        now: float,
    ) -> int:
        if animation is None:
            return fallback
        start, end, started_at = animation
        progress = min(1.0, max(0.0, (now - started_at) / 0.45))
        eased = progress * progress * (3 - 2 * progress)
        return round(start + (end - start) * eased)

    def _clear_selection(self) -> None:
        self.selected = None
        self.legal_moves = []
        self.pending_promotion = []

    def _draw(self) -> None:
        now = pygame.time.get_ticks() / 1000
        self.piece_health_animations = {
            square: animation
            for square, animation in self.piece_health_animations.items()
            if now - animation[2] < 0.45
        }
        self.team_health_animations = {
            color: animation
            for color, animation in self.team_health_animations.items()
            if now - animation[2] < 0.45
        }
        self.damage_popups = [
            popup for popup in self.damage_popups if now - popup[2] < 0.65
        ]
        if self.screen == "menu":
            self._draw_menu()
            self._draw_tutorial()
            return
        if self.screen == "death":
            self._draw_death_screen()
            self._draw_king_banter()
            return

        if self.boss_deployment_active:
            self._draw_boss_deployment()
            self._draw_king_banter()
            return

        if self.shop_menu is not None and self.active_level == 2 and not self.campaign_battle_active:
            self.surface.fill((24, 31, 29))
            self._draw_shop_screen()
            self._draw_tutorial()
            self._draw_king_banter()
            return

        if (
            self.piece_move_animation is not None
            and now - self.piece_move_animation[3] >= 0.18
        ):
            self.piece_move_animation = None

        self.surface.fill((28, 36, 34))
        square_size, board_origin = self._board_layout()
        self.renderer.draw(
            self.surface,
            self.game,
            self.selected,
            self.legal_moves,
            None,
            now,
            self.game.mines,
            self.piece_health_animations,
            self.damage_popups,
            square_size=square_size,
            board_origin=board_origin,
            loot=self.game.loot,
            shop_tiles=self.game.shop_tiles,
            buildings=self._building_visuals(),
            boss_chest_tiles=self._boss_chest_tiles(),
            piece_animation=self.piece_move_animation,
            viewport_rect=(
                pygame.Rect((0, 0), WINDOW_SIZE)
                if self.active_level == 2
                else None
            ),
            raiders=[
                (raider.row, raider.col) for raider in self.campaign.raiders
            ]
            if self.active_level == 2 and not self.campaign_battle_active
            else [],
            potions=set(self.campaign.potions)
            if self.active_level == 2 and not self.campaign_battle_active
            else set(),
            king_attack_progress=(
                1.0 - self.campaign.king_raider_kill_cooldown
                if (
                    self.active_level == 2
                    and not self.campaign_battle_active
                    and self.campaign.king_raider_kill_cooldown > 0
                )
                else None
            ),
            language=self.language,
        )
        self._sync_campaign_progress()
        if self.active_level == 2:
            self._draw_campaign_hud()
        else:
            self._draw_sidebar()
        self._draw_tutorial()
        if self.pending_promotion:
            self._draw_promotion_prompt()
        self._draw_king_banter()

    def _draw_boss_deployment(self) -> None:
        self.surface.fill((24, 31, 29))
        self._center_text(
            "TRUHLA S POKLADEM",
            self.title_font,
            (255, 224, 143),
            (520, 60),
        )
        self._center_text(
            "Vyber az 4 vlastni figurky. Sestavu bossu uvidis az po stisku Hrat.",
            self.small_font,
            (220, 225, 214),
            (520, 101),
        )

        board_left, board_top, tile_size = 54, 142, 56
        preview = pygame.Rect(board_left, board_top, tile_size * 6, tile_size * 6)
        for row in range(6):
            for col in range(6):
                rect = pygame.Rect(
                    board_left + col * tile_size,
                    board_top + row * tile_size,
                    tile_size,
                    tile_size,
                )
                color = (110, 133, 112) if (row + col) % 2 else (190, 184, 154)
                pygame.draw.rect(self.surface, color, rect)
                pygame.draw.rect(self.surface, (39, 48, 41), rect, width=1)
        self._draw_preview_piece((0, 3), "K", BLACK, board_left, board_top, tile_size)
        self._draw_preview_piece((5, 3), "K", WHITE, board_left, board_top, tile_size)
        self._center_text(
            "?",
            self.title_font,
            (244, 190, 79),
            (preview.centerx, board_top + tile_size * 2),
        )

        selected_kinds = [
            kind
            for kind in ARMY_KINDS
            for _ in range(self.boss_deployment[kind])
        ]
        for index, kind in enumerate(selected_kinds):
            row, col = 4 - index // 3, 1 + index % 3
            self._draw_preview_piece(
                (row, col), kind, WHITE, board_left, board_top, tile_size
            )

        panel = pygame.Rect(455, 135, 540, 520)
        pygame.draw.rect(self.surface, (37, 46, 40), panel, border_radius=10)
        total = sum(self.boss_deployment.values())
        self._text(
            f"Nasazeno: {total}/4",
            self.font,
            (255, 224, 143),
            (500, 145),
        )
        names = {
            "P": "Pesec",
            "N": "Kun",
            "B": "Strelec",
            "R": "Vez",
            "Q": "Dama",
        }
        for index, kind in enumerate(ARMY_KINDS):
            y = 177 + index * 66
            self._text(
                f"{names[kind]}: {self.boss_deployment[kind]}/{self.campaign.player.army[kind]}",
                self.font,
                (232, 235, 224),
                (500, y + 6),
            )
            self._draw_button(
                self.boss_deployment_buttons[kind]["minus"],
                "-",
                enabled=self.boss_deployment[kind] > 0,
            )
            can_add = (
                total < 4
                and self.boss_deployment[kind] < self.campaign.player.army[kind]
            )
            self._draw_button(
                self.boss_deployment_buttons[kind]["plus"],
                "+",
                enabled=can_add,
            )
            total = sum(self.boss_deployment.values())

        self._draw_button(
            self.boss_start_button,
            "HRAT - vstoupit do souboje 6 x 6",
            enabled=sum(self.boss_deployment.values()) > 0,
        )
        self._draw_button(self.boss_cancel_button, "Zpet ke kralovstvi")
        self._center_text(
            self.status,
            self.small_font,
            (232, 202, 151),
            (520, 703),
        )

    def _draw_death_screen(self) -> None:
        self.surface.fill((20, 25, 23))
        panel = pygame.Rect(215, 205, 610, 390)
        pygame.draw.rect(self.surface, (42, 49, 43), panel, border_radius=14)
        pygame.draw.rect(self.surface, (156, 73, 61), panel, width=3, border_radius=14)
        self._center_text(
            "KRAL PADL",
            self.title_font,
            (239, 143, 124),
            (520, 280),
        )
        self._center_text(
            self.campaign.king_death_reason or "Kral zemrel.",
            self.font,
            (239, 229, 209),
            (520, 345),
        )
        if self.hardcore_enabled:
            self._center_text(
                "Hardcore: kral je mrtev. Kralovstvi uz nelze obnovit.",
                self.small_font,
                (239, 143, 124),
                (520, 398),
            )
            self.death_menu_button.y = 480
        else:
            self._center_text(
                "Zkus to znovu, nebo se vrat do hlavniho menu.",
                self.small_font,
                (195, 204, 193),
                (520, 398),
            )
            self._draw_menu_button(self.death_retry_button, "Zkusit znovu")
            self.death_menu_button.y = 546
        self._draw_menu_button(self.death_menu_button, "Hlavni menu")

    def _show_tutorial(self, key: str, message: str) -> None:
        if not self.tutorial_enabled or key in self.tutorial_seen:
            return
        self.tutorial_seen.add(key)
        self.tutorial_queue.append((key, message))
        if self.tutorial_active is None:
            self.tutorial_active = self.tutorial_queue.pop(0)
            self.tutorial_until = pygame.time.get_ticks() + 8000

    def _draw_tutorial(self) -> None:
        if not self.tutorial_enabled:
            return
        now = pygame.time.get_ticks()
        if self.tutorial_active is not None and now >= self.tutorial_until:
            self.tutorial_active = (
                self.tutorial_queue.pop(0) if self.tutorial_queue else None
            )
            self.tutorial_until = now + 8000 if self.tutorial_active else 0
        if self.tutorial_active is None:
            return

        _, message = self.tutorial_active
        message = translate(message, self.language)
        panel = self.tutorial_panel
        pygame.draw.rect(self.surface, (24, 31, 28), panel, border_radius=9)
        pygame.draw.rect(self.surface, (224, 190, 119), panel, width=2, border_radius=9)
        self._text("RYCHLY NAVOD", self.small_font, (255, 224, 143), (panel.x + 12, panel.y + 8))
        pygame.draw.rect(self.surface, (82, 91, 84), self.tutorial_close_button, border_radius=4)
        self._center_text("X", self.small_font, (245, 245, 235), self.tutorial_close_button.center)

        words = message.split()
        lines: list[str] = []
        line = ""
        max_width = panel.width - 24
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and self.small_font.size(candidate)[0] > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        for index, text in enumerate(lines[:4]):
            self._text(
                text,
                self.small_font,
                (232, 235, 224),
                (panel.x + 12, panel.y + 38 + index * 20),
            )
        if self.tutorial_queue:
            count = len(self.tutorial_queue) + 1
            self._text(
                f"Dalsi navod {count - 1}x",
                self.small_font,
                (170, 184, 174),
                (panel.x + 12, panel.bottom - 22),
            )

    def _draw_preview_piece(
        self,
        square: tuple[int, int],
        kind: str,
        color: str,
        board_left: int,
        board_top: int,
        tile_size: int,
    ) -> None:
        row, col = square
        self.renderer.draw_piece_sprite(
            self.surface,
            pygame.Rect(
                board_left + col * tile_size,
                board_top + row * tile_size,
                tile_size,
                tile_size,
            ),
            kind,
            color,
        )

    def _draw_campaign_hud(self) -> None:
        self.surface.blit(self.campaign_hud_surface, (0, 0))
        player = self.campaign.player
        title = (
            "BOSSOVI"
            if self.boss_battle_active
            else "BITVA"
            if self.campaign_battle_active
            else "KRALOVSTVI"
        )
        self._text(title, self.title_font, (238, 220, 175), (20, 10))
        self._text(
            f"Den {self.campaign.day} | Zlato {player.coins} | Farmy {player.farms} (+{player.farms * FARM_INCOME_PER_SECOND:g} zl/s) | Armada {player.army_size}",
            self.small_font,
            (230, 224, 204),
            (220, 15),
        )
        self._text(self.status, self.small_font, (246, 239, 220), (760, 15))

    def _draw_king_banter(self) -> None:
        now = pygame.time.get_ticks()
        show_bubble = True
        if self.active_level == 1:
            lines = (
                (BLACK, "Tak ses konecne odvazil mi postavit?"),
                (WHITE, "Jsem tu, abych te porazil. Jsi na tahu."),
                (BLACK, "Uz se unavujes? Ja teprve zacinam."),
                (WHITE, "Mluvis hodne na nekoho, kdo porad ustupuje."),
                (BLACK, "Tvoje figurky padaji jedna po druhe."),
                (WHITE, "A tvuj kral se porad schovava za nimi."),
                (BLACK, "Tenhle tah jsi mel promyslet lip."),
                (WHITE, "Alespon vim, kde je tvuj kral."),
                (BLACK, "Sach. Tak co s tim udelas?"),
                (WHITE, "Neschovavej se. Tohle je mezi nami."),
                (BLACK, "Muj kral se te neboji. Zatim."),
                (WHITE, "Az dojde na krale, zadna vymluva ti nepomuze."),
                (BLACK, "Vazne sis myslel, ze staci porazit par figurek?"),
                (WHITE, "Jeste porad stojim. A ted jsi na tahu ty."),
            )
        else:
            lines = (
                (BLACK, "Tak ses dostal az sem. Uvidime, jak dlouho vydrzis."),
                (WHITE, "Tohle kralovstvi bude moje."),
                (BLACK, "Moji vojaci te uz vyhlizeji."),
                (WHITE, "Tvoje obrana ma vic der nez moje kapsa minci."),
                (BLACK, "Zlato ti odvahu nekoupi."),
                (WHITE, "Ale farmy mi koupi dost casu."),
                (BLACK, "Muj kral se te neboji. Zatim."),
                (WHITE, "Az dojde na krale, zadna vymluva ti nepomuze."),
                (BLACK, "Ten poklad nepatri tobe."),
                (WHITE, "Tak si ho zkus vzit."),
                (BLACK, "Armada vypada lip nez tvoje sance."),
                (WHITE, "Tak se prestan schovavat a posli ji."),
            )
        cycle_position = (now - self.banter_started_at) % 8000
        show_bubble = cycle_position < 4000
        index = ((now - self.banter_started_at) // 8000) % len(lines)
        speaker, message = lines[index]

        if self.active_level == 2:
            portrait_size = 48
            white_portrait = pygame.Rect(126, 690, portrait_size, portrait_size)
            black_portrait = pygame.Rect(866, 82, portrait_size, portrait_size)
            bubble = pygame.Rect(
                250,
                91 if speaker == BLACK else 617,
                590,
                54,
            )
        else:
            portrait_size = 58
            white_portrait = pygame.Rect(4, 695, portrait_size, portrait_size)
            black_portrait = pygame.Rect(4, 2, portrait_size, portrait_size)
            bubble = pygame.Rect(
                74,
                5 if speaker == BLACK else 681,
                560,
                67,
            )

        portraits = [(black_portrait, BLACK)]
        if self.active_level != 2:
            portraits.append((white_portrait, WHITE))
        for portrait, color in portraits:
            chair_color = (142, 98, 48) if color == WHITE else (55, 75, 89)
            pygame.draw.rect(
                self.surface,
                chair_color,
                (portrait.x + 5, portrait.y + 2, portrait.width - 10, portrait.height - 2),
            )
            pygame.draw.rect(
                self.surface,
                (75, 52, 34),
                (portrait.x + 1, portrait.bottom - 8, portrait.width - 2, 8),
            )
            self.renderer.draw_piece_sprite(
                self.surface, portrait.inflate(-8, -4), "K", color
            )

        if not show_bubble:
            return
        pygame.draw.rect(self.surface, (24, 31, 29), bubble)
        pygame.draw.rect(self.surface, (203, 166, 102), bubble, 3)
        pygame.draw.line(
            self.surface,
            (203, 166, 102),
            (bubble.left + 10, bubble.bottom - 5),
            (bubble.right - 10, bubble.bottom - 5),
            2,
        )
        label = "TY" if speaker == WHITE else "CERNY KRAL"
        translated_label = translate(label, self.language)
        translated_message = translate(message, self.language)
        available_width = bubble.width - 24
        lines: list[str] = []
        current = ""
        for word in f"{translated_label}: {translated_message}".split():
            candidate = f"{current} {word}".strip()
            if current and self.small_font.size(candidate)[0] > available_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        line_height = self.small_font.get_linesize()
        total_height = min(len(lines), 2) * line_height
        text_y = bubble.centery - total_height // 2
        for index, line in enumerate(lines[:2]):
            self._center_text(
                line,
                self.small_font,
                (255, 232, 185),
                (bubble.centerx, text_y + index * line_height + line_height // 2),
            )

    def _draw_menu(self) -> None:
        self.surface.fill((28, 36, 34))
        for row in range(4):
            for col in range(4):
                rect = pygame.Rect(80 + col * 80, 82 + row * 80, 80, 80)
                color = (52, 67, 61) if (row + col) % 2 else (68, 83, 74)
                pygame.draw.rect(self.surface, color, rect)

        title = pygame.font.SysFont("consolas", 58, bold=True)
        subtitle = pygame.font.SysFont("consolas", 20)
        self._center_text("ŠACHY", title, (255, 232, 177), (520, 150))
        self._center_text(
            "Hraješ za bílé proti botovi, který hraje za černé",
            subtitle,
            (245, 242, 226),
            (520, 210),
        )
        self._center_text(
            "Obtížnost bota (orientační chess.com Elo)",
            subtitle,
            (245, 242, 226),
            (520, 253),
        )
        for difficulty, rect in self.difficulty_buttons.items():
            self._draw_difficulty_button(
                rect,
                BOT_DIFFICULTIES[difficulty]["label"],
                selected=difficulty == self.bot_difficulty,
            )
        self._center_text(
            "Vyber část hry",
            subtitle,
            (245, 242, 226),
            (520, 350),
        )
        level_labels = {
            1: "Úvodní bitva 8×8",
            2: "Království RPG 20×20",
        }
        for level, rect in self.level_buttons.items():
            enabled = level <= self.unlocked_level or level == 2
            color = (
                (205, 169, 99)
                if enabled and self.selected_level == level
                else (75, 91, 82) if enabled else (57, 65, 60)
            )
            pygame.draw.rect(self.surface, color, rect, border_radius=10)
            self._center_text(
                level_labels[level],
                self.small_font,
                (31, 39, 36) if enabled else (224, 228, 217),
                rect.center,
            )
        play_label = (
            "Pokracovat"
            if self.has_started_game and self.active_level == self.selected_level
            else "Vstoupit do království"
            if self.selected_level == 2
            else "Začít úvodní bitvu"
        )
        self._draw_menu_button(self.menu_play_button, play_label)
        new_game_label = (
            "Hardcore run skoncil"
            if self.hardcore_enabled
            and self.campaign.king_dead
            and self.selected_level == 2
            else "Restartovat kralovstvi"
            if self.selected_level == 2
            else "Nova hra"
        )
        if (
            self.hardcore_enabled
            and self.campaign.king_dead
            and self.selected_level == 2
        ):
            pygame.draw.rect(
                self.surface,
                (82, 91, 84),
                self.menu_new_game_button,
                border_radius=10,
            )
            self._center_text(
                new_game_label,
                self.font,
                (174, 181, 172),
                self.menu_new_game_button.center,
            )
        else:
            self._draw_menu_button(self.menu_new_game_button, new_game_label)
        self._draw_menu_button(self.menu_quit_button, "Ukončit")
        tutorial_label = (
            "Návody: zapnuto"
            if self.tutorial_enabled
            else "Návody: vypnuto"
        )
        tutorial_color = (
            (113, 164, 86) if self.tutorial_enabled else (95, 102, 96)
        )
        pygame.draw.rect(
            self.surface,
            tutorial_color,
            self.tutorial_toggle_button,
            border_radius=8,
        )
        self._center_text(
            tutorial_label,
            self.small_font,
            (245, 245, 235),
            self.tutorial_toggle_button.center,
        )
        language_label = (
            "Jazyk: čeština" if self.language == "cs" else "Language: English"
        )
        pygame.draw.rect(
            self.surface,
            (75, 91, 82),
            self.language_toggle_button,
            border_radius=8,
        )
        self._center_text(
            language_label,
            self.small_font,
            (245, 245, 235),
            self.language_toggle_button.center,
        )
        hardcore_label = (
            "Hardcore: zapnuto"
            if self.hardcore_enabled
            else "Hardcore: vypnuto"
        )
        pygame.draw.rect(
            self.surface,
            (151, 71, 67) if self.hardcore_enabled else (75, 91, 82),
            self.hardcore_toggle_button,
            border_radius=8,
        )
        self._center_text(
            hardcore_label,
            self.small_font,
            (245, 245, 235),
            self.hardcore_toggle_button.center,
        )
        hint = pygame.font.SysFont("consolas", 16)
        self._center_text(
            "V první části vyhraješ jen zabitím černého krále.",
            hint,
            (222, 228, 216),
            (520, 665),
        )
        if self.hardcore_enabled:
            self._center_text(
                "Vypnutí Hardcore smaže království a začne druhou část znovu.",
                hint,
                (239, 178, 150),
                (520, 692),
            )

    def _draw_difficulty_button(
        self, rect: pygame.Rect, label: str, *, selected: bool
    ) -> None:
        color = (205, 169, 99) if selected else (75, 91, 82)
        pygame.draw.rect(self.surface, color, rect, border_radius=10)
        self._center_text(label, self.small_font, (31, 39, 36), rect.center)

    def _draw_menu_button(self, rect: pygame.Rect, label: str) -> None:
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        color = (205, 169, 99) if hovered else (179, 143, 78)
        pygame.draw.rect(self.surface, color, rect, border_radius=10)
        text = translate(label, self.language)
        font = self.font
        max_width = rect.width - 20
        while font.size(text)[0] > max_width and font.get_height() > 14:
            font = pygame.font.SysFont("consolas", font.get_height() - 1, bold=True)
        self._center_text(
            label,
            font,
            (24, 29, 27),
            rect.center,
        )

    def _center_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        center: tuple[int, int],
    ) -> None:
        text = translate(text, self.language)
        image = self._cached_text(text, font, color)
        self.surface.blit(image, image.get_rect(center=center))

    def _draw_sidebar(self) -> None:
        if self.active_level == 2:
            self._draw_campaign_sidebar()
            return

        left = 720
        self._text("RPG ŠACHY", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        self._text(
            "JEDINY CIL: ZABIJ CERNEHO KRALE",
            self.small_font,
            (255, 205, 125),
            (left, 168),
        )
        self._text("Sebrane bile: " + self._captured_text(WHITE),
                   self.small_font, (246, 239, 220), (left, 214))
        self._text("Sebrane cerne: " + self._captured_text(BLACK),
                   self.small_font, (246, 239, 220), (left, 236))
        selected_piece = (
            self.game.piece_at(self.selected) if self.selected is not None else None
        )
        if selected_piece is not None and selected_piece.color == self.game.turn:
            displayed_max_health = max(
                1,
                round(
                    selected_piece.max_health * self.game.piece_health_multiplier
                ),
            )
            health_text = (
                f"{self._piece_name(selected_piece.kind)} "
                f"HP {selected_piece.health}/{displayed_max_health}"
            )
            self._text(
                health_text, self.small_font, (220, 225, 214), (left, 274)
            )
        self._text(
            "Tah: klikni figuru a cil.",
            self.small_font,
            (220, 225, 214),
            (left, 305),
        )
        if self.active_level == 2:
            self._draw_button(
                self.undo_button,
                "Vratit tah",
                enabled=bool(self.game.history) and not self.hardcore_enabled,
            )
        self._draw_button(self.reset_button, "Nova hra")
        self._draw_button(self.in_game_menu_button, "Menu")

    def _draw_campaign_sidebar(self) -> None:
        if self.campaign_battle_active:
            self._draw_battle_sidebar()
            return

        left = 720
        player = self.campaign.player
        rival = self.campaign.rival
        self._text("KRAJINA", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        self._text(
            f"Den {self.campaign.day}   Tvoje zlato {player.coins}",
            self.small_font,
            (220, 194, 123),
            (left, 168),
        )
        shop_message = (
            "Obchod: " + self._shop_name(self.shop_menu)
            if self.shop_menu is not None
            else "Vstup kralem na barevnou branu."
        )
        self._text(shop_message, self.small_font, (195, 205, 194), (left, 190))
        for tab, button in self.campaign_tab_buttons.items():
            selected = tab == self.campaign_tab
            pygame.draw.rect(
                self.surface,
                (205, 169, 99) if selected else (75, 91, 82),
                button,
                border_radius=6,
            )
            label = translate(
                {"farms": "Farmy", "city": "Mesto", "armory": "Zbrojnice"}[tab],
                self.language,
            )
            image = self.small_font.render(label, True, (31, 39, 36))
            self.surface.blit(image, image.get_rect(center=button.center))

        if self.campaign_tab == "farms":
            self._text(
                f"Farmy {player.farms}  |  prijem +{player.farms * FARM_INCOME_PER_SECOND:g} zl/s",
                self.small_font,
                (220, 225, 214),
                (left, 264),
            )
            self._draw_button(
                self.farm_button,
                f"Postavit farmu - {self.campaign.farm_cost(WHITE)}",
                enabled=player.coins >= self.campaign.farm_cost(WHITE)
                and player.farms < FARM_LIMIT,
            )
            city_label = f"Odemknout mesto - {CITY_COST}" if not player.city else "Mesto je odemceno"
            self._draw_button(
                self.city_button,
                city_label,
                enabled=not player.city and player.farms >= 3 and player.coins >= CITY_COST,
            )
            self._text(
                f"Souper: {rival.farms} farem, mesto {'ano' if rival.city else 'ne'}",
                self.small_font,
                (195, 205, 194),
                (left, 418),
            )
        elif self.campaign_tab == "city":
            self._text(
                "Najem figur a postupne vylepsovani armady",
                self.small_font,
                (220, 225, 214),
                (left, 264),
            )
            self._draw_button(
                self.city_unlock_button,
                "Mesto odemceno" if player.city else f"Postavit mesto - {CITY_COST}",
                enabled=player.city or (player.farms >= 3 and player.coins >= CITY_COST),
            )
            for kind, button in self.recruit_buttons.items():
                self._draw_button(
                    button,
                    f"Najmout {self._piece_name(kind)} ({player.army[kind]}) - {RECRUIT_COSTS[kind]}",
                    enabled=player.city
                    and player.coins >= RECRUIT_COSTS[kind]
                    and player.army_size < 16,
                )
            for kind, button in self.upgrade_buttons.items():
                source = UPGRADE_SOURCES[kind]
                upgrade_cost = ARMY_UPGRADE_COSTS[kind]
                self._draw_button(
                    button,
                    f"Povysit {self._piece_name(source)} na {self._piece_name(kind)} - {upgrade_cost}",
                    enabled=player.city
                    and player.army[source] > 0
                    and player.coins >= upgrade_cost,
                )
        else:
            self._draw_button(
                self.armory_button,
                "Zbrojnice odemcena" if player.armory else f"Postavit zbrojnici - {ARMORY_COST}",
                enabled=player.armory or (player.city and player.coins >= ARMORY_COST),
            )
            self._text("Pripravena armada", self.small_font, (220, 225, 214), (left, 360))
            army_text = "  ".join(
                f"{kind}: {player.army[kind]}" for kind in ARMY_KINDS
            )
            self._text(army_text, self.small_font, (246, 239, 220), (left, 386))
            self._draw_button(self.deployment_minus_button, "-", enabled=True)
            self._draw_button(self.deployment_plus_button, "+", enabled=True)
            self._text(
                f"Nasadit jednotek: {self.deployment_limit}",
                self.small_font,
                (220, 225, 214),
                (left + 58, 510),
            )
            self._draw_button(
                self.declare_war_button,
                "Vyhlasit valku",
                enabled=player.armory and player.army_size > 0,
            )
            self._text(
                f"Souper ma {rival.army_size} jednotek",
                self.small_font,
                (195, 205, 194),
                (left, 556),
            )
        self._draw_button(
            self.undo_button,
            "Vratit tah",
            enabled=(
                self.campaign_battle_active
                and bool(self.game.history)
                and not self.hardcore_enabled
            ),
        )
        self._draw_button(self.reset_button, "Nova hra")
        self._draw_button(self.in_game_menu_button, "Menu")

    def _draw_battle_sidebar(self) -> None:
        left = 720
        self._text("BITVA", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        self._text("Poraz souperova krale.", self.small_font, (238, 220, 175), (left, 168))
        for index, color in enumerate((WHITE, BLACK)):
            army = self.deployed_armies.get(color, {})
            side = "Tvoje" if color == WHITE else "Souperovy"
            label = "  ".join(
                f"{kind}:{army.get(kind, 0)}" for kind in ARMY_KINDS
            )
            self._text(
                f"{side}: {label}",
                self.small_font,
                (220, 225, 214),
                (left, 216 + index * 28),
            )
        self._text("Figurky maji vlastni HP bary.", self.small_font, (195, 205, 194), (left, 282))
        self._draw_button(
            self.undo_button,
            "Vratit tah",
            enabled=bool(self.game.history) and not self.hardcore_enabled,
        )
        self._draw_button(self.reset_button, "Nova hra")
        self._draw_button(self.in_game_menu_button, "Menu")

    def _draw_team_health(self, color: str, y: int) -> None:
        label = (
            "Bili hrac"
            if color == WHITE
            else f"Cerny bot ({BOT_DIFFICULTIES[self.bot_difficulty]['label']})"
        )
        self._text(label, self.small_font, (220, 225, 214), (720, y))
        rect = pygame.Rect(720, y + 20, 280, 12)
        pygame.draw.rect(self.surface, (47, 54, 50), rect, border_radius=6)
        now = pygame.time.get_ticks() / 1000
        animation = self.team_health_animations.get(color)
        current = self._animated_health(
            animation,
            self.game.team_health[color],
            now,
        )
        maximum = self.game.team_health_max[color]
        current = min(maximum, max(0, current))
        fill = rect.copy()
        fill.width = int(rect.width * current / maximum) if maximum else 0
        if fill.width:
            bar_color = (81, 190, 107) if color == WHITE else (202, 79, 72)
            pygame.draw.rect(self.surface, bar_color, fill, border_radius=6)
        value = self.small_font.render(f"{current}/{maximum}", True, (245, 244, 233))
        self.surface.blit(value, (rect.right - value.get_width(), y))

    def _draw_button(
        self, rect: pygame.Rect, label: str, enabled: bool = True
    ) -> None:
        color = (179, 143, 78) if enabled else (82, 91, 84)
        pygame.draw.rect(self.surface, color, rect, border_radius=8)
        label = translate(label, self.language)
        text = self.small_font.render(label, True, (31, 39, 36) if enabled else (174, 181, 172))
        self.surface.blit(text, text.get_rect(center=rect.center))

    def _piece_name(self, kind: str) -> str:
        return translate({
            "P": "Pesec",
            "N": "Kun",
            "B": "Strelec",
            "R": "Vez",
            "Q": "Dama",
            "K": "Kral",
        }[kind], self.language)

    def _draw_promotion_prompt(self) -> None:
        panel = pygame.Rect(220, 325, 600, 110)
        pygame.draw.rect(self.surface, (28, 36, 34), panel, border_radius=12)
        pygame.draw.rect(self.surface, (220, 194, 123), panel, width=2, border_radius=12)
        text = self.font.render(
            translate(
                "Promena pesce: Q dama, R vez, B strelec, N kun",
                self.language,
            ),
            True,
            (246, 239, 220),
        )
        self.surface.blit(text, text.get_rect(center=(panel.centerx, panel.centery)))

    def _captured_text(self, color: str) -> str:
        pieces = self.game.captured[color]
        return " ".join(piece.kind for piece in pieces) if pieces else "—"

    def _text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        position: tuple[int, int],
    ) -> None:
        text = translate(text, self.language)
        self.surface.blit(self._cached_text(text, font, color), position)

    def _cached_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        key = (id(font), text, color)
        image = self._rendered_text_cache.get(key)
        if image is None:
            image = font.render(text, True, color)
            self._rendered_text_cache[key] = image
        else:
            self._rendered_text_cache.move_to_end(key)
        if len(self._rendered_text_cache) > 512:
            self._rendered_text_cache.popitem(last=False)
        return image



def run_game() -> None:
    app = ChessApp()
    try:
        app.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    run_game()
