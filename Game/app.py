from __future__ import annotations

import pygame

from .constants import (
    BLACK,
    BOARD_LEFT,
    BOARD_SIZE,
    BOARD_TOP,
    SQUARE_SIZE,
    WHITE,
    WINDOW_SIZE,
)
from .effects import Effects
from .models import Move, Piece
from .renderer import BoardRenderer
from .rules import ChessGame

class ChessApp:
    def __init__(self, effects: Effects | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("Sachy — zaklad")
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.game = ChessGame()
        self.renderer = BoardRenderer(effects)
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
        self.menu_play_button = pygame.Rect(380, 330, 280, 58)
        self.menu_new_game_button = pygame.Rect(380, 405, 280, 58)
        self.menu_quit_button = pygame.Rect(380, 480, 280, 58)
        self.reset_button = pygame.Rect(720, 665, 280, 48)
        self.in_game_menu_button = pygame.Rect(720, 600, 280, 48)

    def run(self) -> None:
        while self.running:
            self._handle_events()
            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _handle_key(self, key: int) -> None:
        if self.screen == "menu":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self._start_or_continue()
            return

        if key == pygame.K_ESCAPE:
            if self.selected is not None or self.pending_promotion:
                self._clear_selection()
            else:
                self.screen = "menu"
        elif key == pygame.K_r and not self.pending_promotion:
            self.game.reset()
            self.status = self.game.status()
            self._clear_selection()
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
            if self.menu_play_button.collidepoint(position):
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
        if self.reset_button.collidepoint(position):
            self._start_new_game()
            return
        col = (position[0] - BOARD_LEFT) // SQUARE_SIZE
        row = (position[1] - BOARD_TOP) // SQUARE_SIZE
        if not ChessGame._inside(row, col):
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
        if piece is not None and piece.color == self.game.turn:
            self.selected = square
            self.legal_moves = self.game.legal_moves_from(square)
        else:
            self._clear_selection()

    def _start_or_continue(self) -> None:
        if not self.has_started_game:
            self._start_new_game()
        self.screen = "game"

    def _start_new_game(self) -> None:
        self.game.reset()
        self.status = self.game.status()
        self.has_started_game = True
        self._clear_selection()

    def _play_move(self, move: Move) -> None:
        if self.game.play(move):
            self.status = self.game.status()
        self._clear_selection()

    def _clear_selection(self) -> None:
        self.selected = None
        self.legal_moves = []
        self.pending_promotion = []

    def _draw(self) -> None:
        if self.screen == "menu":
            self._draw_menu()
            return

        self.surface.fill((28, 36, 34))
        checked_king = None
        if self.game.is_in_check(self.game.turn):
            checked_king = next(
                (
                    (row, col)
                    for row in range(BOARD_SIZE)
                    for col in range(BOARD_SIZE)
                    if ChessGame._is_piece(
                        self.game.board[row][col], self.game.turn, "K"
                    )
                ),
                None,
            )
        self.renderer.draw(
            self.surface,
            self.game,
            self.selected,
            self.legal_moves,
            checked_king,
            pygame.time.get_ticks() / 1000,
        )
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
        self._center_text("SACHY", title, (238, 220, 175), (520, 205))
        self._center_text(
            "Zakladni sachova hra — vyber si, co chces delat",
            subtitle,
            (220, 225, 214),
            (520, 270),
        )
        play_label = "Pokracovat" if self.has_started_game else "Hrat"
        self._draw_menu_button(self.menu_play_button, play_label)
        if self.has_started_game:
            self._draw_menu_button(self.menu_new_game_button, "Nova hra")
        self._draw_menu_button(self.menu_quit_button, "Ukoncit")
        hint = pygame.font.SysFont("segoeui", 16)
        self._center_text(
            "Klikni na tlacitko, nebo stiskni Enter.",
            hint,
            (170, 184, 174),
            (520, 570),
        )

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
        self._text("SACHY", self.title_font, (238, 220, 175), (left, 62))
        self._text(self.status, self.font, (240, 240, 231), (left, 122))
        self._text(
            f"Co in:  {self.game.coins[WHITE]}  |  {self.game.coins[BLACK]}",
            self.font,
            (220, 194, 123),
            (left, 184),
        )
        self._text("Bile figurky", self.small_font, (195, 205, 194), (left, 254))
        self._text(
            self._captured_text(WHITE), self.font, (246, 239, 220), (left, 280)
        )
        self._text("Cerne figurky", self.small_font, (195, 205, 194), (left, 334))
        self._text(
            self._captured_text(BLACK), self.font, (246, 239, 220), (left, 360)
        )
        self._text("Pravidla", self.small_font, (195, 205, 194), (left, 430))
        instructions = (
            "Klikni na figurku a pak na cil.",
            "Tah se nesmi vystavit sachu.",
            "Rosenada, en passant, promena.",
            "R = nova hra  |  Esc = zrusit vyber",
        )
        for index, line in enumerate(instructions):
            self._text(
                line,
                self.small_font,
                (220, 225, 214),
                (left, 458 + index * 25),
            )
        pygame.draw.rect(self.surface, (179, 143, 78), self.reset_button, border_radius=8)
        button_text = self.font.render("Nova hra", True, (31, 39, 36))
        self.surface.blit(button_text, button_text.get_rect(center=self.reset_button.center))
        pygame.draw.rect(
            self.surface, (75, 91, 82), self.in_game_menu_button, border_radius=8
        )
        menu_text = self.font.render("Menu", True, (240, 240, 231))
        self.surface.blit(
            menu_text, menu_text.get_rect(center=self.in_game_menu_button.center)
        )

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
