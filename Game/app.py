from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
import random

import pygame

from .constants import (
    BOT_DIFFICULTIES,
    BLACK,
    BOARD_VIEW_PIXELS,
    BOARD_LEFT,
    BOARD_SIZE,
    BOARD_TOP,
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
from .effects import Effects
from .models import Move
from .renderer import BoardRenderer
from .progress import load_unlocked_level, save_unlocked_level
from .rules import ChessGame
from .textures import SceneTextures

class ChessApp:
    def __init__(self, effects: Effects | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("Sachy — zaklad")
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.unlocked_level = load_unlocked_level()
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

    @staticmethod
    def _create_level_game(level: int) -> ChessGame:
        if level == 1:
            return ChessGame(
                board_size=CLASSIC_BOARD_SIZE,
                random_armies=False,
                capture_majority=True,
            )
        if level == 2:
            return ChessGame(board_size=BOARD_SIZE, random_armies=True)
        raise ValueError(f"Unknown game level: {level}")

    def run(self) -> None:
        try:
            while self.running:
                self._handle_events()
                self._update_bot_turn()
                self._draw()
                pygame.display.flip()
                self.clock.tick(60)
        finally:
            self.bot_executor.shutdown(wait=False, cancel_futures=True)

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key, event.mod)
            elif event.type == pygame.MOUSEWHEEL and self.screen == "game":
                self.zoom = min(2.0, max(0.5, self.zoom * (1.1 ** event.y)))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _handle_key(self, key: int, modifiers: int = 0) -> None:
        if self.screen == "menu":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self._start_or_continue()
            return

        if key == pygame.K_ESCAPE:
            if self.selected is not None or self.pending_promotion:
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

    def _handle_click(self, position: tuple[int, int]) -> None:
        if self.screen == "menu":
            level_choice = next(
                (
                    level
                    for level, rect in self.level_buttons.items()
                    if rect.collidepoint(position)
                    and level <= self.unlocked_level
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
                self.has_started_game
                and self.menu_new_game_button.collidepoint(position)
            ):
                self._start_new_game()
            elif self.menu_quit_button.collidepoint(position):
                self.running = False
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
            self._start_new_game()
            return
        if self._bot_is_thinking():
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
        square_size, (origin_x, origin_y) = self._board_layout()
        if not pygame.Rect(
            BOARD_LEFT, BOARD_TOP, BOARD_VIEW_PIXELS, BOARD_VIEW_PIXELS
        ).collidepoint(position):
            return
        col = (position[0] - origin_x) // square_size
        row = (position[1] - origin_y) // square_size
        if not self.game._inside(row, col):
            return
        square = (row, col)

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

    def _board_layout(self) -> tuple[int, tuple[int, int]]:
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

    def _start_or_continue(self) -> None:
        if not self.has_started_game or self.active_level != self.selected_level:
            self._start_new_game()
        self.screen = "game"

    def _start_new_game(self) -> None:
        self._cancel_bot_turn()
        if self.selected_level > self.unlocked_level:
            return
        self.active_level = self.selected_level
        self.game = self._create_level_game(self.active_level)
        self.zoom = 1.0
        self.status = self.game.status()
        self.has_started_game = True
        self.last_action_was_bot = False
        self._clear_selection()

    def _play_move(self, move: Move) -> None:
        team_health_before = self.game.team_health.copy()
        if self.game.play(move):
            self.status = self.game.status()
            self._record_damage_animations(team_health_before)
            self._sync_campaign_progress()
        self._clear_selection()
        self.last_action_was_bot = False
        self._schedule_bot_turn()

    def _undo(self) -> None:
        self._cancel_bot_turn()
        if self.game.undo():
            if self.last_action_was_bot:
                self.game.undo()
            self.last_action_was_bot = False
            self.status = self.game.status()
            self._clear_selection()

    def _schedule_bot_turn(self) -> None:
        if self.game.turn != BLACK or self.game.winner() is not None:
            self.status = self.game.status()
            return
        self.bot_due_at = pygame.time.get_ticks() + random.randint(1000, 3000)
        self.status = "Bot premysli..."

    def _update_bot_turn(self) -> None:
        if self.bot_due_at is not None:
            if pygame.time.get_ticks() < self.bot_due_at:
                return
            self.bot_due_at = None
            game_snapshot = deepcopy(self.game)
            self.bot_future = self.bot_executor.submit(
                choose_move, game_snapshot, self.bot_difficulty
            )

        if self.bot_future is None or not self.bot_future.done():
            return

        future = self.bot_future
        self.bot_future = None
        if self.game.turn != BLACK or self.game.winner() is not None:
            return
        move = future.result()
        team_health_before = self.game.team_health.copy()
        if move is None:
            if self.game.pass_turn():
                self.status = self.game.status()
                self.last_action_was_bot = True
                return
            self.status = self.game.status()
            self.last_action_was_bot = False
            return
        if not self.game.play(move):
            raise RuntimeError(f"Bot selected an invalid move: {move!r}")
        self.status = self.game.status()
        self._record_damage_animations(team_health_before)
        self.last_action_was_bot = True
        self._sync_campaign_progress()

    def _sync_campaign_progress(self) -> None:
        if (
            self.active_level == 1
            and self.unlocked_level < 2
            and self.game.winner() == WHITE
        ):
            save_unlocked_level(2)
            self.unlocked_level = 2

    def _cancel_bot_turn(self) -> None:
        self.bot_due_at = None
        if self.bot_future is not None:
            self.bot_future.cancel()
            self.bot_future = None

    def _bot_is_thinking(self) -> bool:
        return self.bot_due_at is not None or self.bot_future is not None

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
        )
        self._sync_campaign_progress()
        self._draw_sidebar()
        if self.pending_promotion:
            self._draw_promotion_prompt()

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
            "Vyber level",
            subtitle,
            (220, 225, 214),
            (520, 350),
        )
        level_labels = {
            1: "Level 1: Sachy 8x8",
            2: (
                "Level 2: RPG mapa 25x25"
                if self.unlocked_level >= 2
                else "Level 2: Zamceno"
            ),
        }
        for level, rect in self.level_buttons.items():
            enabled = level <= self.unlocked_level
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
            else f"Spustit level {self.selected_level}"
        )
        self._draw_menu_button(self.menu_play_button, play_label)
        self._draw_menu_button(self.menu_new_game_button, "Nova hra")
        self._draw_menu_button(self.menu_quit_button, "Ukoncit")
        hint = pygame.font.SysFont("segoeui", 16)
        self._center_text(
            "Prvni level vyhrajes po ubrani poloviny HP soupere; tim odemknes level 2.",
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
        left = 720
        self._text("RPG SACHY", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        objective = (
            f"Cil: dostat HP soupere na {self.game.victory_health_threshold[BLACK]}"
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
