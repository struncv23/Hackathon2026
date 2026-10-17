from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
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
    PURCHASE_COSTS,
    SQUARE_SIZE,
    UPGRADE_COSTS,
    UPGRADE_NAMES,
    WHITE,
    WINDOW_SIZE,
)
from .bot import choose_move
from .campaign import (
    ARMY_KINDS,
    ARMORY_COST,
    CITY_COST,
    RECRUIT_COSTS,
    UPGRADE_SOURCES,
    Campaign,
)
from .effects import Effects
from .models import Move
from .renderer import BoardRenderer
from .progress import (
    load_campaign,
    load_unlocked_level,
    save_campaign,
    save_unlocked_level,
)
from .rules import ChessGame
from .textures import SceneTextures

class ChessApp:
    def __init__(self, effects: Effects | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("Sachy — zaklad")
        self.windowed_size = WINDOW_SIZE
        self.fullscreen = False
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.unlocked_level = load_unlocked_level()
        self.campaign = load_campaign()
        self.selected_level = 1
        self.active_level = 1
        self.game = self._create_level_game(self.active_level)
        self.textures = SceneTextures()
        self.renderer = BoardRenderer(effects, self.textures)
        self.font = pygame.font.SysFont("segoeui", 22)
        self.small_font = pygame.font.SysFont("segoeui", 16)
        self.title_font = pygame.font.SysFont("segoeui", 30, bold=True)
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
        self.purchase_buttons = {
            kind: pygame.Rect(720, 329 + index * 28, 280, 25)
            for index, kind in enumerate(("P", "N", "B", "R", "Q"))
        }
        self.sacrifice_button = pygame.Rect(720, 519, 280, 34)
        self.shop_button = pygame.Rect(720, 475, 280, 38)
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
        self.piece_health_animations: dict[
            tuple[int, int], tuple[int, int, float]
        ] = {}
        self.damage_popups: list[tuple[tuple[int, int], int, float]] = []
        self.campaign_tab = "farms"
        self.kingdom_game: ChessGame | None = None
        self.campaign_battle_active = False
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

    @staticmethod
    def _create_level_game(level: int) -> ChessGame:
        if level == 1:
            return ChessGame(
                board_size=CLASSIC_BOARD_SIZE,
                random_armies=False,
                capture_majority=True,
            )
        if level == 2:
            return ChessGame(
                board_size=CAMPAIGN_BOARD_SIZE,
                random_armies=False,
                king_only=True,
            )
        raise ValueError(f"Unknown game level: {level}")

    def run(self) -> None:
        try:
            while self.running:
                self._handle_events()
                self._update_bot_turn()
                self._draw()
                pygame.display.flip()
                elapsed_seconds = self.clock.tick(60) / 1000
                self._advance_realtime_campaign(elapsed_seconds)
        finally:
            self.bot_executor.shutdown(wait=False, cancel_futures=True)

    def _advance_realtime_campaign(self, elapsed_seconds: float) -> None:
        if (
            self.active_level == 2
            and not self.campaign_battle_active
            and self.campaign.accrue_income(elapsed_seconds)
        ):
            save_campaign(self.campaign)

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key, event.mod)
            elif event.type == pygame.MOUSEWHEEL and self.screen == "game":
                self.zoom = min(2.0, max(0.5, self.zoom * (1.1 ** event.y)))
                self._clamp_camera_offset()
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
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.drag_start = None
                if (
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
            elif self.menu_play_button.collidepoint(position):
                self._start_or_continue()
            elif (
                (self.has_started_game or self.selected_level == 2)
                and self.menu_new_game_button.collidepoint(position)
            ):
                self._start_new_game()
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
        if self.undo_button.collidepoint(position):
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
        purchase_kind = next(
            (
                kind
                for kind, rect in self.purchase_buttons.items()
                if rect.collidepoint(position)
            ),
            None,
        )
        if purchase_kind is not None:
            team_health_before = self.game.team_health.copy()
            if self.game.buy_piece(purchase_kind):
                self.status = self.game.status()
                self._clear_selection()
                self._record_damage_animations(team_health_before)
                self.last_action_was_bot = False
                self._schedule_bot_turn()
            return
        if self.shop_button.collidepoint(position):
            if self.selected is not None and self.game.buy_upgrade(self.selected):
                self.last_action_was_bot = False
                self.status = self.game.status()
                self.legal_moves = self.game.legal_moves_from(self.selected)
            return
        if self.sacrifice_button.collidepoint(position):
            team_health_before = self.game.team_health.copy()
            if self.selected is not None and self.game.sacrifice_queen(self.selected):
                self.status = self.game.status()
                self._record_damage_animations(team_health_before)
                self._clear_selection()
                self.last_action_was_bot = False
                self._schedule_bot_turn()
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

    def _board_layout(self) -> tuple[int, tuple[int, int]]:
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
        if self.active_level != 2:
            self.camera_offset = (0, 0)
            return
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
        self.camera_offset = (
            min(max_x, max(min_x, self.camera_offset[0])),
            min(max_y, max(min_y, self.camera_offset[1])),
        )

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
        col = (position[0] - origin_x) // square_size
        row = (position[1] - origin_y) // square_size
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
            origin_x + destination[1] * square_size + square_size // 2,
            origin_y + destination[0] * square_size + square_size // 2,
        )
        self._handle_click(destination_position)

    def _start_or_continue(self) -> None:
        if not self.has_started_game or self.active_level != self.selected_level:
            self._start_new_game(reset_campaign=self.selected_level != 2)
        self.screen = "game"

    def _start_new_game(self, *, reset_campaign: bool = True) -> None:
        if self.campaign_battle_active:
            self.status = "Bitvu nelze prerusit resetem."
            return
        self._cancel_bot_turn()
        self.active_level = self.selected_level
        if self.active_level == 2 and reset_campaign:
            self.campaign = Campaign()
            save_campaign(self.campaign)
        self.game = self._create_level_game(self.active_level)
        self.campaign_battle_active = False
        self.kingdom_game = None
        self.zoom = 1.0
        self.camera_offset = (0, 0)
        self.shop_menu = None
        self.shop_confirmation = None
        self.status = self.game.status()
        self.has_started_game = True
        self.last_action_was_bot = False
        self._clear_selection()
        if self._is_realtime_campaign():
            self._schedule_bot_turn()

    def _play_move(self, move: Move) -> None:
        game_before = self.game
        moving_piece = self.game.piece_at(move.start)
        battle_finished = False
        realtime_campaign = self._is_realtime_campaign()
        if realtime_campaign:
            self.game.turn = WHITE
        team_health_before = self.game.team_health.copy()
        if self.game.play(move):
            if realtime_campaign:
                self.game.turn = WHITE
            self.status = self.game.status()
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

    def _handle_campaign_click(self, position: tuple[int, int]) -> bool:
        for tab, button in self.campaign_tab_buttons.items():
            if button.collidepoint(position):
                self.campaign_tab = tab
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
                    self.status = "Mesto vyzaduje farmu a 900 minci."
                return True
        elif self.campaign_tab == "city":
            if self.city_unlock_button.collidepoint(position):
                if self.campaign.build_city(WHITE):
                    self._campaign_action_done("Mesto odemceno.")
                else:
                    self.status = "Mesto vyzaduje farmu a 900 minci."
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
        self.deployed_armies = {WHITE: player_army, BLACK: rival_army}
        battle = ChessGame(
            board_size=CAMPAIGN_BOARD_SIZE,
            random_armies=False,
            king_only=True,
        )
        battle.configure_battle(self.deployed_armies)
        self.game = battle
        self.campaign_battle_active = True
        self.status = "Bitva zacala. Poraz souperova krale."
        self.zoom = 1.0
        self._clear_selection()

    def _resolve_campaign_battle(self) -> None:
        survivors = {WHITE: {}, BLACK: {}}
        for color in (WHITE, BLACK):
            survivors[color] = {kind: 0 for kind in ARMY_KINDS}
        for row in self.game.board:
            for piece in row:
                if piece is not None and piece.kind != "K":
                    survivors[piece.color][piece.kind] += 1

        winner = self.game.winner()
        self.campaign.resolve_battle(self.deployed_armies, survivors)
        for color in (WHITE, BLACK):
            self.campaign.faction(color).coins += self.game.coins[color]
        if winner in (WHITE, BLACK):
            self.campaign.faction(winner).coins += 250
            result = "Vitezstvi" if winner == WHITE else "Porazka"
            self.status = f"{result}. Prezivsi jednotky se vraci do kralovstvi."
        else:
            self.status = "Bitva skoncila. Prezivsi jednotky se vraci domů."

        save_campaign(self.campaign)
        battle_result = self.status
        if self.kingdom_game is not None:
            self.game = self.kingdom_game
        self.kingdom_game = None
        self.campaign_battle_active = False
        self.deployed_armies = {}
        self.game.turn = WHITE
        self._clear_selection()
        self.status = battle_result

    def _campaign_action_done(self, message: str) -> None:
        self._advance_campaign_action(WHITE)
        if not self._is_realtime_campaign():
            self.game.turn = BLACK
        self.status = message
        self.shop_confirmation = None
        self._clear_selection()
        self.last_action_was_bot = False
        self._schedule_bot_turn()

    def _advance_campaign_action(self, color: str) -> None:
        self.campaign.advance_day(color)
        if color == BLACK:
            self.campaign.bot_action(self.bot_difficulty)
        save_campaign(self.campaign)

    def _collect_campaign_loot(self, color: str | None) -> None:
        if color is None or self.game.last_loot_value <= 0:
            return
        self.campaign.faction(color).coins += self.game.last_loot_value
        self.status = f"Kral sebral {self.game.last_loot_value} zlata."

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
            if player.farms >= 8:
                return "Uz mas maximalni pocet osmi farem."
            cost = self.campaign.farm_cost(WHITE)
            if player.coins < cost:
                return f"Farma stoji {cost} zlata, mas jen {player.coins}."
            return None
        if kind == "city":
            if player.city:
                return "Mesto uz vlastnis."
            if player.farms < 3:
                return f"Mesto vyzaduje 3 farmy; mas {player.farms}."
            if player.coins < 900:
                return f"Mesto stoji 900 zlata, mas jen {player.coins}."
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
            cost = RECRUIT_COSTS[piece_kind] - RECRUIT_COSTS[source]
            if player.coins < cost:
                return f"Vylepseni stoji {cost} zlata, mas jen {player.coins}."
            return None
        return "Tento nakup neni dostupny."

    def _building_visuals(self) -> dict[tuple[int, int], tuple[str, str, bool]]:
        result = {}
        for square, (owner, kind) in self.game.building_tiles.items():
            faction = self.campaign.faction(owner)
            owned = {
                "farm": faction.farm_sector,
                "city": faction.city,
                "armory": faction.armory,
            }[kind]
            result[square] = (kind, owner, owned)
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
        for row in range(4):
            for col in range(3):
                tile = pygame.Rect(
                    origin_x + col * cell_width,
                    origin_y + row * cell_height,
                    cell_width - 4,
                    cell_height - 4,
                )
                pygame.draw.rect(self.surface, base_color, tile, border_radius=3)
                pygame.draw.rect(self.surface, (35, 42, 37), tile, width=2, border_radius=3)
        building_label = self.title_font.render(titles[screen_kind], True, (255, 244, 214))
        self.surface.blit(building_label, building_label.get_rect(center=(building.centerx, building.bottom - 28)))

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
                f"Vlastni farmy: {player.farms}   Prijem: +{player.farms} zl/s",
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
            self._text("Farmy generuji zlato prubezne v realnem case.", self.small_font, (190, 202, 191), (440, 382))
        elif screen_kind == "city":
            if not player.city:
                buttons["city"] = pygame.Rect(440, 250, 510, 64)
                self._draw_button(
                    buttons["city"],
                    "Postavit mesto - 900 zl",
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
                    cost = RECRUIT_COSTS[kind] - RECRUIT_COSTS[source]
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
                "city": 900,
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
        if self.game.turn != WHITE or self._bot_is_thinking():
            return

        success = False
        message = "Na tento nakup nemas dost penez nebo nesplnujes podminky."
        if kind == "farm":
            success = self.campaign.build_farm(WHITE)
            message = "Farma postavena. Prijem zacne dalsi den."
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
                f"{self.campaign.farm_cost(WHITE)} zl | +1 zl/s",
                player.coins >= self.campaign.farm_cost(WHITE) and player.farms < 8,
                player.farms > 0,
            )
        if kind == "city":
            return (
                "Mesto",
                "Vlastni" if player.city else "900 zl | potrebuje farmu",
                player.city or (player.farms > 0 and player.coins >= 900),
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
            cost = RECRUIT_COSTS["N"] - RECRUIT_COSTS[source]
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
            if self.game.winner() is not None:
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
            if not self.game.play(move):
                if realtime_campaign:
                    self.game.turn = WHITE
                self.status = "Souper upravuje svuj tah..."
                self._schedule_bot_turn()
                return

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
            and self.unlocked_level < 2
            and self.game.winner() == WHITE
        ):
            save_unlocked_level(2)
            self.unlocked_level = 2
            self.selected_level = 2
            self.active_level = 2
            self.game = self._create_level_game(2)
            self.zoom = 1.0
            self.campaign_tab = "farms"
            self.status = "Vyhrano. Kralovstvi je odemceno, vydej se pro poklady."
            self.has_started_game = True
            save_campaign(self.campaign)
            self._clear_selection()
            self._schedule_bot_turn()

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
            return

        if self.shop_menu is not None and self.active_level == 2 and not self.campaign_battle_active:
            self.surface.fill((24, 31, 29))
            self._draw_shop_screen()
            return

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
            viewport_rect=(
                pygame.Rect((0, 0), WINDOW_SIZE)
                if self.active_level == 2
                else None
            ),
        )
        self._sync_campaign_progress()
        if self.active_level == 2:
            self._draw_campaign_hud()
        else:
            self._draw_sidebar()
        if self.pending_promotion:
            self._draw_promotion_prompt()

    def _draw_campaign_hud(self) -> None:
        hud = pygame.Surface((WINDOW_SIZE[0], 68), pygame.SRCALPHA)
        hud.fill((20, 27, 24, 228))
        self.surface.blit(hud, (0, 0))
        player = self.campaign.player
        rival = self.campaign.rival
        title = "BITVA" if self.campaign_battle_active else "KRALOVSTVI"
        self._text(title, self.title_font, (238, 220, 175), (20, 10))
        self._text(
            f"Den {self.campaign.day} | Zlato {player.coins} | Farmy {player.farms} (+{player.farms} zl/s) | Armada {player.army_size}",
            self.small_font,
            (230, 224, 204),
            (220, 15),
        )
        self._text(
            f"Souper: {rival.coins} zl | armada {rival.army_size}     LMB: tah / prazdno = posun | Kolečko: zoom | Esc: menu",
            self.small_font,
            (196, 207, 194),
            (220, 40),
        )
        self._text(self.status, self.small_font, (246, 239, 220), (760, 15))

    def _draw_menu(self) -> None:
        self.surface.fill((28, 36, 34))
        for row in range(4):
            for col in range(4):
                rect = pygame.Rect(80 + col * 80, 82 + row * 80, 80, 80)
                color = (52, 67, 61) if (row + col) % 2 else (68, 83, 74)
                pygame.draw.rect(self.surface, color, rect)

        title = pygame.font.SysFont("segoeui", 58, bold=True)
        subtitle = pygame.font.SysFont("segoeui", 20)
        self._center_text("SACHY", title, (238, 220, 175), (520, 150))
        self._center_text(
            "Hrajes za bile proti botovi, ktery hraje za cerne",
            subtitle,
            (220, 225, 214),
            (520, 210),
        )
        self._center_text(
            "Obtiznost bota (orientacni chess.com Elo)",
            subtitle,
            (220, 225, 214),
            (520, 253),
        )
        for difficulty, rect in self.difficulty_buttons.items():
            self._draw_difficulty_button(
                rect,
                BOT_DIFFICULTIES[difficulty]["label"],
                selected=difficulty == self.bot_difficulty,
            )
        self._center_text(
            "Vyber cast hry",
            subtitle,
            (220, 225, 214),
            (520, 350),
        )
        level_labels = {
            1: "Uvodni valka 8x8",
            2: "Kralovstvi RPG 20x20",
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
                (31, 39, 36) if enabled else (155, 161, 152),
                rect.center,
            )
        play_label = (
            "Pokracovat"
            if self.has_started_game and self.active_level == self.selected_level
            else "Vstoupit do kralovstvi"
            if self.selected_level == 2
            else "Zacit uvodni valku"
        )
        self._draw_menu_button(self.menu_play_button, play_label)
        new_game_label = (
            "Restartovat kralovstvi"
            if self.selected_level == 2
            else "Nova hra"
        )
        self._draw_menu_button(self.menu_new_game_button, new_game_label)
        self._draw_menu_button(self.menu_quit_button, "Ukoncit")
        hint = pygame.font.SysFont("segoeui", 16)
        self._center_text(
            "Vyhra v uvodni valce odemkne RPG kralovstvi a trvalou kampan.",
            hint,
            (170, 184, 174),
            (520, 670),
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
        self._center_text(
            label,
            self.font,
            (31, 39, 36),
            rect.center,
        )

    def _center_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        center: tuple[int, int],
    ) -> None:
        image = font.render(text, True, color)
        self.surface.blit(image, image.get_rect(center=center))

    def _draw_sidebar(self) -> None:
        if self.active_level == 2:
            self._draw_campaign_sidebar()
            return

        left = 720
        self._text("RPG SACHY", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        objective = (
            f"Cil: porazit krale nebo snizit HP na {self.game.victory_health_threshold[BLACK]}"
            if self.game.capture_majority
            else "Cil: sebrat vsechny souperovy figurky"
        )
        self._text(objective, self.small_font, (238, 220, 175), (left, 168))
        self._text(
            f"Penez en: bile {self.game.coins[WHITE]} | cerne {self.game.coins[BLACK]}",
            self.small_font,
            (220, 194, 123),
            (left, 190),
        )
        self._text("Sebrane bile: " + self._captured_text(WHITE),
                   self.small_font, (246, 239, 220), (left, 214))
        self._text("Sebrane cerne: " + self._captured_text(BLACK),
                   self.small_font, (246, 239, 220), (left, 236))
        self._text("Figurka / obchod", self.small_font, (238, 220, 175), (left, 263))
        self._text(
            "Najmi figurku (bily; nakup ukonci tah):",
            self.small_font,
            (220, 225, 214),
            (left, 307),
        )
        for kind, rect in self.purchase_buttons.items():
            cost = PURCHASE_COSTS[kind]
            enabled = (
                self.game.turn == WHITE
                and not self._bot_is_thinking()
                and self.game.coins[WHITE] >= cost
                and self.game.winner() is None
            )
            self._draw_button(
                rect,
                f"{self._piece_name(kind)}  -  {cost} coinu",
                enabled=enabled,
            )
        selected_piece = (
            self.game.piece_at(self.selected) if self.selected is not None else None
        )
        if selected_piece is None or selected_piece.color != self.game.turn:
            self._text("Vyber svoji figurku.", self.small_font, (220, 225, 214), (left, 288))
            self._draw_button(self.shop_button, "Vyber figurku", enabled=False)
            self._draw_button(self.sacrifice_button, "Vyber damu k obeti", enabled=False)
        else:
            health_text = (
                f"{self._piece_name(selected_piece.kind)} "
                f"HP {selected_piece.health}/{selected_piece.max_health}"
            )
            self._text(health_text, self.small_font, (220, 225, 214), (left, 288))
            upgrade_name = UPGRADE_NAMES.get(selected_piece.kind)
            if upgrade_name is None:
                self._draw_button(self.shop_button, "Pesec nema upgrade", enabled=False)
            elif selected_piece.kind in selected_piece.upgrades:
                self._draw_button(self.shop_button, "Upgrade uz koupen", enabled=False)
            else:
                cost = UPGRADE_COSTS[selected_piece.kind]
                affordable = self.game.coins[self.game.turn] >= cost
                self._draw_button(
                    self.shop_button,
                    f"{upgrade_name} - {cost} coinu",
                    enabled=affordable,
                )
            description = self.game.upgrade_description(selected_piece.kind)
            if description:
                self._text(
                    description[:42],
                    self.small_font,
                    (195, 205, 194),
                    (left, 559),
                )
                self._text(
                    description[42:84],
                    self.small_font,
                    (195, 205, 194),
                    (left, 579),
                )
            is_queen = selected_piece.kind == "Q"
            self._draw_button(
                self.sacrifice_button,
                (
                    f"Obetovat damu (+{selected_piece.health} HP)"
                    if is_queen
                    else "Dama se obetuje za HP"
                ),
                enabled=is_queen and selected_piece.color == WHITE and self.game.turn == WHITE,
            )
        self._text("Tah: klikni figuru a cil.", self.small_font, (220, 225, 214), (left, 606))
        instructions = (
            "Bily kupuje | bot za cerne nekupuje.",
            "Kolecko mysi = priblizeni / oddaleni.",
        )
        for index, line in enumerate(instructions):
            self._text(
                line,
                self.small_font,
                (220, 225, 214),
                (left, 625 + index * 18),
            )
        self._draw_button(self.undo_button, "Vratit tah", enabled=bool(self.game.history))
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
            f"Den {self.campaign.day}   Zlato {player.coins}   Souper {rival.coins}",
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
            label = {"farms": "Farmy", "city": "Mesto", "armory": "Zbrojnice"}[tab]
            image = self.small_font.render(label, True, (31, 39, 36))
            self.surface.blit(image, image.get_rect(center=button.center))

        if self.campaign_tab == "farms":
            self._text(
                f"Farmy {player.farms}  |  prijem +{player.farms} zl/s",
                self.small_font,
                (220, 225, 214),
                (left, 264),
            )
            self._draw_button(
                self.farm_button,
                f"Postavit farmu - {self.campaign.farm_cost(WHITE)}",
                enabled=player.coins >= self.campaign.farm_cost(WHITE) and player.farms < 8,
            )
            city_label = "Odemknout mesto - 900" if not player.city else "Mesto je odemceno"
            self._draw_button(
                self.city_button,
                city_label,
                enabled=not player.city and player.farms > 0 and player.coins >= 900,
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
                "Mesto odemceno" if player.city else "Postavit mesto - 900",
                enabled=player.city or (player.farms > 0 and player.coins >= 900),
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
                upgrade_cost = RECRUIT_COSTS[kind] - RECRUIT_COSTS[source]
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
            enabled=self.campaign_battle_active and bool(self.game.history),
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
        self._draw_button(self.undo_button, "Vratit tah", enabled=bool(self.game.history))
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
        if color == BLACK and self.game.capture_majority and maximum:
            target_x = rect.x + round(
                rect.width
                * self.game.victory_health_threshold[BLACK]
                / maximum
            )
            pygame.draw.line(
                self.surface,
                (245, 194, 75),
                (target_x, rect.y - 2),
                (target_x, rect.bottom + 2),
                2,
            )
        value = self.small_font.render(f"{current}/{maximum}", True, (245, 244, 233))
        self.surface.blit(value, (rect.right - value.get_width(), y))

    def _draw_button(
        self, rect: pygame.Rect, label: str, enabled: bool = True
    ) -> None:
        color = (179, 143, 78) if enabled else (82, 91, 84)
        pygame.draw.rect(self.surface, color, rect, border_radius=8)
        text = self.small_font.render(label, True, (31, 39, 36) if enabled else (174, 181, 172))
        self.surface.blit(text, text.get_rect(center=rect.center))

    @staticmethod
    def _piece_name(kind: str) -> str:
        return {
            "P": "Pesec",
            "N": "Kun",
            "B": "Strelec",
            "R": "Vez",
            "Q": "Dama",
            "K": "Kral",
        }[kind]

    def _draw_promotion_prompt(self) -> None:
        panel = pygame.Rect(220, 325, 600, 110)
        pygame.draw.rect(self.surface, (28, 36, 34), panel, border_radius=12)
        pygame.draw.rect(self.surface, (220, 194, 123), panel, width=2, border_radius=12)
        text = self.font.render(
            "Promena pesce: Q dama, R vez, B strelec, N kun",
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
        self.surface.blit(font.render(text, True, color), position)



def run_game() -> None:
    app = ChessApp()
    try:
        app.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    run_game()
