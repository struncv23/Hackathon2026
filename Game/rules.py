from __future__ import annotations

import random
from dataclasses import dataclass

from .constants import (
    BLACK,
    BOARD_SIZE,
    PURCHASE_COSTS,
    RANDOM_EXTRA_PIECES_PER_SIDE,
    PIECE_VALUES,
    UPGRADE_COSTS,
    WHITE,
)
from .models import Move, Piece

ATTACK_DAMAGE = {
    kind: value // 2 for kind, value in PIECE_VALUES.items()
}
ATTACK_DAMAGE["Q"] = 200
UPGRADE_DAMAGE = {"B": 99, "R": 199}
MINE_DAMAGE = 200


@dataclass
class _GameSnapshot:
    board: list[list[Piece | None]]
    turn: str
    castling_rights: set[str]
    en_passant_target: tuple[int, int] | None
    captured: dict[str, list[Piece]]
    coins: dict[str, int]
    mines: dict[tuple[int, int], str]
    loot: dict[tuple[int, int], int]
    shop_tiles: dict[tuple[int, int], str]
    building_tiles: dict[tuple[int, int], tuple[str, str]]
    loot_rank: int
    last_loot_value: int
    last_loot_color: str | None
    team_health: dict[str, int]
    team_health_max: dict[str, int]
    last_damage: list[tuple[tuple[int, int], int]]


class ChessGame:
    """Chess movement with RPG upgrades, hit points, coins, and undo."""

    def __init__(
        self,
        board_size: int = BOARD_SIZE,
        random_armies: bool = True,
        capture_majority: bool = False,
        king_only: bool = False,
        starting_coins: int = 0,
    ) -> None:
        if board_size < 8:
            raise ValueError("The board must be at least 8 by 8.")
        if starting_coins < 0:
            raise ValueError("Starting coins cannot be negative.")
        self.board_size = board_size
        self.random_armies = random_armies
        self.capture_majority = capture_majority
        self.king_only = king_only
        self.starting_coins = starting_coins
        self.standard_start_col = (board_size - 8) // 2
        self.standard_black_back_row = (board_size - 8) // 2
        self.standard_white_back_row = self.standard_black_back_row + 7
        self.board: list[list[Piece | None]] = []
        self.turn = WHITE
        self.castling_rights: set[str] = set()
        self.en_passant_target: tuple[int, int] | None = None
        self.captured: dict[str, list[Piece]] = {WHITE: [], BLACK: []}
        self.coins = {WHITE: 0, BLACK: 0}
        self.mines: dict[tuple[int, int], str] = {}
        self.loot: dict[tuple[int, int], int] = {}
        self.shop_tiles: dict[tuple[int, int], str] = {}
        self.building_tiles: dict[tuple[int, int], tuple[str, str]] = {}
        self.loot_rank = 1
        self.last_loot_value = 0
        self.last_loot_color: str | None = None
        self.team_health = {WHITE: 0, BLACK: 0}
        self.team_health_max = {WHITE: 0, BLACK: 0}
        self.victory_health_threshold = {WHITE: 0, BLACK: 0}
        self.last_damage: list[tuple[tuple[int, int], int]] = []
        self.history: list[_GameSnapshot] = []
        self.reset()

    def reset(self) -> None:
        back_rank = ("R", "N", "B", "Q", "K", "B", "N", "R")
        self.board = [[None] * self.board_size for _ in range(self.board_size)]
        self.shop_tiles = {}
        self.building_tiles = {}
        if self.king_only:
            center_col = self.board_size // 2
            self.board[5][center_col] = Piece(BLACK, "K")
            self.board[self.board_size - 6][center_col] = Piece(WHITE, "K")
            for color, base_start, gate_row in (
                (BLACK, 0, 4),
                (WHITE, self.board_size - 4, self.board_size - 5),
            ):
                for kind, gate_col in zip(
                    ("farm", "city", "armory"),
                    (center_col - 4, center_col, center_col + 4),
                ):
                    self.shop_tiles[(gate_row, gate_col)] = kind
                    for row in range(base_start, base_start + 4):
                        for col in range(gate_col - 1, gate_col + 2):
                            self.building_tiles[(row, col)] = (color, kind)
        else:
            black_pawn_row = self.standard_black_back_row + 1
            white_pawn_row = self.standard_white_back_row - 1
            for offset, kind in enumerate(back_rank):
                col = self.standard_start_col + offset
                self.board[self.standard_black_back_row][col] = Piece(BLACK, kind)
                self.board[self.standard_white_back_row][col] = Piece(WHITE, kind)
                self.board[black_pawn_row][col] = Piece(BLACK, "P")
                self.board[white_pawn_row][col] = Piece(WHITE, "P")

        if self.random_armies and not self.king_only:
            self._spawn_random_armies()
        self.turn = WHITE
        self.castling_rights = {"K", "Q", "k", "q"}
        self.en_passant_target = None
        self.captured = {WHITE: [], BLACK: []}
        self.coins = {WHITE: self.starting_coins, BLACK: self.starting_coins}
        self.mines = {}
        self.loot = {}
        self.loot_rank = 1
        if self.king_only:
            self._spawn_loot(1)
        self.last_loot_value = 0
        self.last_loot_color = None
        total_health = {
            color: sum(
                piece.max_health
                for row in self.board
                for piece in row
                if piece is not None and piece.color == color
            )
            for color in (WHITE, BLACK)
        }
        if self.king_only:
            self.team_health_max = {WHITE: 30_000, BLACK: 30_000}
            self.team_health = self.team_health_max.copy()
        else:
            self.team_health_max = total_health
            self.team_health = total_health.copy()
        self.victory_health_threshold = {
            color: (health * 3 + 3) // 4 if self.capture_majority else 0
            for color, health in total_health.items()
        }
        self.last_damage = []
        self.history = []

    def configure_battle(self, armies: dict[str, dict[str, int]]) -> None:
        self.board = [[None] * self.board_size for _ in range(self.board_size)]
        self.shop_tiles = {}
        self.building_tiles = {}
        center = self.board_size // 2
        black_king = (1, center)
        white_king = (self.board_size - 2, center)
        self.board[black_king[0]][black_king[1]] = Piece(BLACK, "K")
        self.board[white_king[0]][white_king[1]] = Piece(WHITE, "K")

        for color in (WHITE, BLACK):
            home_rows = (
                range(self.board_size - 5, self.board_size - 1)
                if color == WHITE
                else range(1, 5)
            )
            positions = [
                (row, col)
                for row in home_rows
                for col in range(max(0, center - 4), min(self.board_size, center + 5))
                if self.board[row][col] is None
            ]
            unit_index = 0
            for kind in ("P", "N", "B", "R", "Q"):
                for _ in range(max(0, armies.get(color, {}).get(kind, 0))):
                    if unit_index >= len(positions):
                        raise ValueError("Too many units for this battle map.")
                    row, col = positions[unit_index]
                    self.board[row][col] = Piece(color, kind)
                    unit_index += 1

        self.king_only = False
        self.random_armies = False
        self.capture_majority = False
        self.turn = WHITE
        self.castling_rights = set()
        self.en_passant_target = None
        self.captured = {WHITE: [], BLACK: []}
        self.coins = {WHITE: 0, BLACK: 0}
        self.mines = {}
        self.loot = {}
        self.shop_tiles = {}
        self.loot_rank = 1
        self.last_loot_value = 0
        self.last_loot_color = None
        self.team_health_max = {
            color: sum(
                piece.max_health
                for row in self.board
                for piece in row
                if piece is not None and piece.color == color
            )
            for color in (WHITE, BLACK)
        }
        self.team_health = self.team_health_max.copy()
        self.victory_health_threshold = {WHITE: 0, BLACK: 0}
        self.last_damage = []
        self.history = []

    def _spawn_random_armies(self) -> None:
        rng = random.Random()
        extra_kinds = ("P", "P", "P", "N", "B", "R", "Q")
        available = [
            (row, col)
            for row in range(self.board_size)
            for col in range(self.board_size)
            if self.board[row][col] is None
        ]
        spawn_squares = rng.sample(
            available,
            min(2 * RANDOM_EXTRA_PIECES_PER_SIDE, len(available)),
        )
        for index, (row, col) in enumerate(spawn_squares):
            color = BLACK if index < RANDOM_EXTRA_PIECES_PER_SIDE else WHITE
            self.board[row][col] = Piece(color, rng.choice(extra_kinds))

    def _spawn_loot(self, count: int) -> None:
        if self.loot:
            return
        available = [
            (row, col)
            for row in range(self.board_size)
            for col in range(self.board_size)
            if self.board[row][col] is None and (row, col) not in self.loot
            and (row, col) not in self.shop_tiles
            and (row, col) not in self.building_tiles
        ]
        for square in random.sample(available, min(count, len(available))):
            self.loot[square] = random.choice((300, 600, 1_000, 1_500)) * self.loot_rank

    def piece_at(self, square: tuple[int, int]) -> Piece | None:
        row, col = square
        return self.board[row][col]

    def legal_moves_from(self, square: tuple[int, int]) -> list[Move]:
        piece = self.piece_at(square)
        if piece is None or piece.color != self.turn or self.winner() is not None:
            return []
        moves = self._pseudo_moves_from(square)
        if self.king_only:
            moves = [move for move in moves if move.end not in self.building_tiles]
            if piece.kind != "K":
                moves = [move for move in moves if move.end not in self.shop_tiles]
        return moves

    def all_legal_moves(self) -> list[Move]:
        if self.winner() is not None:
            return []
        moves: list[Move] = []
        for row in range(self.board_size):
            for col in range(self.board_size):
                piece = self.board[row][col]
                if piece is not None and piece.color == self.turn:
                    moves.extend(self._pseudo_moves_from((row, col)))
        return moves

    def winner(self) -> str | None:
        has_king = {
            color: any(
                piece is not None and piece.color == color and piece.kind == "K"
                for row in self.board
                for piece in row
            )
            for color in (WHITE, BLACK)
        }
        if not has_king[WHITE] and not has_king[BLACK]:
            return "draw"
        if not has_king[WHITE]:
            return BLACK
        if not has_king[BLACK]:
            return WHITE

        health_victories = {
            color: self.capture_majority
            and self.team_health[color] <= self.victory_health_threshold[color]
            for color in (WHITE, BLACK)
        }
        if health_victories[WHITE] and health_victories[BLACK]:
            return "draw"
        if health_victories[WHITE]:
            return BLACK
        if health_victories[BLACK]:
            return WHITE

        has_pieces = {
            color: any(
                piece is not None and piece.color == color
                for row in self.board
                for piece in row
            )
            for color in (WHITE, BLACK)
        }
        if not has_pieces[WHITE] and not has_pieces[BLACK]:
            return "draw"
        if not has_pieces[WHITE]:
            return BLACK
        if not has_pieces[BLACK]:
            return WHITE
        return None

    def status(self) -> str:
        winner = self.winner()
        if winner == "draw":
            return "Obe strany byly porazeny — remiza."
        if winner is not None:
            loser = BLACK if winner == WHITE else WHITE
            loser_has_king = any(
                piece is not None and piece.color == loser and piece.kind == "K"
                for row in self.board
                for piece in row
            )
            if not loser_has_king:
                return f"{self._side_name(winner)} vyhrali — padl souperuv kral."
            if self.capture_majority:
                return f"{self._side_name(winner)} vyhrali — souper ztratil dost zdravi."
            return f"{self._side_name(winner)} vyhrali — souper nema zadne figurky."
        if not self.all_legal_moves():
            return f"{self._side_name(self.turn)} nemaji tah — stiskni P pro preskoceni."
        return f"Na tahu jsou {self._side_name(self.turn)}."

    def pass_turn(self) -> bool:
        if self.winner() is not None or self.all_legal_moves():
            return False
        self._save_history()
        self.turn = self._opponent(self.turn)
        return True

    def buy_upgrade(self, square: tuple[int, int]) -> bool:
        piece = self.piece_at(square)
        if piece is None or piece.color != WHITE or piece.color != self.turn:
            return False
        cost = UPGRADE_COSTS.get(piece.kind)
        if cost is None or piece.kind in piece.upgrades:
            return False
        if self.coins[piece.color] < cost:
            return False

        self._save_history()
        self.coins[piece.color] -= cost
        self.board[square[0]][square[1]] = Piece(
            piece.color,
            piece.kind,
            piece.level,
            piece.experience,
            piece.health,
            piece.upgrades | {piece.kind},
        )
        return True

    def buy_piece(self, kind: str) -> bool:
        cost = PURCHASE_COSTS.get(kind)
        if (
            self.turn != WHITE
            or self.winner() is not None
            or cost is None
            or self.coins[WHITE] < cost
        ):
            return False

        spawn_squares = [
            (row, col)
            for row in range(
                max(0, self.standard_white_back_row - 4),
                min(self.board_size, self.standard_white_back_row + 5),
            )
            for col in range(
                max(0, self.standard_start_col - 3),
                min(self.board_size, self.standard_start_col + 11),
            )
            if self.board[row][col] is None
        ]
        if not spawn_squares:
            return False

        self._save_history()
        square = random.choice(spawn_squares)
        self.board[square[0]][square[1]] = Piece(WHITE, kind)
        self.coins[WHITE] -= cost
        self.team_health_max[WHITE] += PIECE_VALUES[kind]
        self.team_health[WHITE] += PIECE_VALUES[kind]
        self.turn = BLACK
        return True

    def sacrifice_queen(self, square: tuple[int, int]) -> bool:
        row, col = square
        piece = self.board[row][col]
        if (
            piece is None
            or piece.color != WHITE
            or piece.kind != "Q"
            or self.turn != WHITE
            or self.winner() is not None
        ):
            return False
        self._save_history()
        self.board[row][col] = None
        self.team_health[WHITE] = min(
            self.team_health_max[WHITE],
            self.team_health[WHITE] + (piece.health or 0),
        )
        self.turn = BLACK
        return True

    def upgrade_description(self, kind: str) -> str:
        return {
            "N": "Mina: 200 poskozeni na poli, odkud kun odskocil.",
            "B": "Odraz: po tahu ubere 99 HP dalsi figure na diagonale.",
            "R": "Rentgen: ubere 199 HP vsem v rade a sloupci.",
            "Q": "Leceni: pri utoku na krale vyleci vlastniho krale.",
            "K": "Pesec: vytvori pesce na volnem poli pred kralem.",
        }.get(kind, "")

    def play(self, move: Move) -> bool:
        legal_moves = self.legal_moves_from(move.start)
        matching = [
            candidate for candidate in legal_moves if candidate.end == move.end
        ]
        if not matching:
            return False

        selected = next(
            (
                candidate
                for candidate in matching
                if candidate.promotion == move.promotion
            ),
            None,
        )
        if selected is None:
            selected = next(
                (candidate for candidate in matching if candidate.promotion == "Q"),
                matching[0],
            )
        piece = self.board[selected.start[0]][selected.start[1]]
        assert piece is not None
        self._save_history()
        self.last_damage = []
        self.last_loot_value = 0
        self.last_loot_color = None

        target_square = selected.end
        if selected.en_passant:
            target_square = (
                selected.end[0] - self._pawn_direction(piece.color),
                selected.end[1],
            )
        target = self.board[target_square[0]][target_square[1]]
        if piece.color == WHITE and piece.kind == "Q" and "Q" in piece.upgrades:
            self._heal_king(piece.color)

        if target is not None:
            killed = self._damage_piece(
                target_square, piece.color, ATTACK_DAMAGE[piece.kind]
            )
            if not killed:
                self.en_passant_target = None
                self.turn = self._opponent(self.turn)
                return True

        if selected.castle:
            king_start_col = self.standard_start_col + 4
            king_side = selected.end[1] > king_start_col
            rook_start = self.standard_start_col + (7 if king_side else 0)
            rook_end = self.standard_start_col + (6 if king_side else 3)
            self.board[selected.end[0]][rook_end] = self.board[selected.end[0]][rook_start]
            self.board[selected.end[0]][rook_start] = None

        self._remove_moved_piece_right(piece, selected.start)
        self.board[selected.start[0]][selected.start[1]] = None
        moved_piece = piece
        if selected.promotion is not None:
            moved_piece = Piece(
                piece.color, selected.promotion, piece.level, piece.experience
            )
        self.board[selected.end[0]][selected.end[1]] = moved_piece

        self.en_passant_target = None
        if piece.kind == "P" and abs(selected.end[0] - selected.start[0]) == 2:
            self.en_passant_target = (
                (selected.start[0] + selected.end[0]) // 2,
                selected.start[1],
            )

        self._trigger_mine(selected.end)
        piece_on_destination = self.board[selected.end[0]][selected.end[1]]
        if (
            piece_on_destination is not None
            and piece_on_destination.color == moved_piece.color
            and piece_on_destination.kind == moved_piece.kind
            and piece_on_destination.upgrades == moved_piece.upgrades
        ):
            self._use_upgrade_abilities(
                piece_on_destination, selected.start, selected.end
            )
        if (
            self.king_only
            and piece.kind == "K"
            and self.board[selected.end[0]][selected.end[1]] is not None
        ):
            self.last_loot_value = self.loot.pop(selected.end, 0)
            if self.last_loot_value:
                self.last_loot_color = piece.color
                self.coins[piece.color] += self.last_loot_value
                self.loot_rank += 1
                self._spawn_loot(1)
        self.turn = self._opponent(self.turn)
        return True

    def undo(self) -> bool:
        if not self.history:
            return False
        snapshot = self.history.pop()
        self.board = snapshot.board
        self.turn = snapshot.turn
        self.castling_rights = snapshot.castling_rights.copy()
        self.en_passant_target = snapshot.en_passant_target
        self.captured = {
            color: pieces.copy() for color, pieces in snapshot.captured.items()
        }
        self.coins = snapshot.coins.copy()
        self.mines = snapshot.mines.copy()
        self.loot = snapshot.loot.copy()
        self.shop_tiles = snapshot.shop_tiles.copy()
        self.building_tiles = snapshot.building_tiles.copy()
        self.loot_rank = snapshot.loot_rank
        self.last_loot_value = snapshot.last_loot_value
        self.last_loot_color = snapshot.last_loot_color
        self.team_health = snapshot.team_health.copy()
        self.team_health_max = snapshot.team_health_max.copy()
        self.last_damage = snapshot.last_damage.copy()
        return True

    def _save_history(self) -> None:
        self.history.append(
            _GameSnapshot(
                [row.copy() for row in self.board],
                self.turn,
                self.castling_rights.copy(),
                self.en_passant_target,
                {color: pieces.copy() for color, pieces in self.captured.items()},
                self.coins.copy(),
                self.mines.copy(),
                self.loot.copy(),
                self.shop_tiles.copy(),
                self.building_tiles.copy(),
                self.loot_rank,
                self.last_loot_value,
                self.last_loot_color,
                self.team_health.copy(),
                self.team_health_max.copy(),
                self.last_damage.copy(),
            )
        )

    def _use_upgrade_abilities(
        self,
        piece: Piece,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        if piece.color != WHITE:
            return
        if piece.kind == "N" and "N" in piece.upgrades:
            self.mines[start] = piece.color
        elif piece.kind == "B" and "B" in piece.upgrades:
            self._bishop_bounce(piece, start, end)
        elif piece.kind == "R" and "R" in piece.upgrades:
            self._rook_xray(piece, end)
        elif piece.kind == "K" and "K" in piece.upgrades:
            self._spawn_king_pawn(piece, end)

    def _heal_king(self, color: str) -> None:
        for row in range(self.board_size):
            for col in range(self.board_size):
                piece = self.board[row][col]
                if piece is not None and piece.color == color and piece.kind == "K":
                    restored = piece.max_health - (piece.health or 0)
                    self.board[row][col] = Piece(
                        piece.color,
                        piece.kind,
                        piece.level,
                        piece.experience,
                        piece.max_health,
                        piece.upgrades,
                    )
                    self.team_health[color] = min(
                        self.team_health_max[color],
                        self.team_health[color] + restored,
                    )
                    return

    def _bishop_bounce(
        self,
        piece: Piece,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        row_step = 1 if end[0] > start[0] else -1
        col_step = 1 if end[1] > start[1] else -1
        row, col = end
        visited = {end, start}
        for _ in range(self.board_size * self.board_size):
            next_row, next_col = row + row_step, col + col_step
            if not self._inside(next_row, next_col):
                if not self._inside(row + row_step, col):
                    row_step *= -1
                elif not self._inside(row, col + col_step):
                    col_step *= -1
                next_row, next_col = row + row_step, col + col_step
            square = (next_row, next_col)
            if square in visited:
                return
            visited.add(square)
            row, col = square
            if self.board[row][col] is not None:
                self._damage_piece(square, piece.color, UPGRADE_DAMAGE["B"])
                return

    def _rook_xray(self, piece: Piece, square: tuple[int, int]) -> None:
        row, col = square
        targets = [
            (row, other_col)
            for other_col in range(self.board_size)
            if other_col != col and self.board[row][other_col] is not None
        ]
        targets.extend(
            (other_row, col)
            for other_row in range(self.board_size)
            if other_row != row and self.board[other_row][col] is not None
        )
        for target in targets:
            if self.board[target[0]][target[1]] is not None:
                self._damage_piece(target, piece.color, UPGRADE_DAMAGE["R"])

    def _spawn_king_pawn(
        self, king: Piece, square: tuple[int, int]
    ) -> None:
        row, col = square
        pawn_row = row + self._pawn_direction(king.color)
        if not self._inside(pawn_row, col):
            pawn_row = self.board_size - 1 if king.color == BLACK else 0
        target = self.board[pawn_row][col]
        if target is not None:
            self._damage_piece((pawn_row, col), king.color, target.health or 0)
        self.board[pawn_row][col] = Piece(king.color, "P")
        self.team_health_max[king.color] += PIECE_VALUES["P"]
        self.team_health[king.color] += PIECE_VALUES["P"]

    def _trigger_mine(self, square: tuple[int, int]) -> None:
        owner = self.mines.pop(square, None)
        if owner is not None and self.board[square[0]][square[1]] is not None:
            self._damage_piece(square, owner, MINE_DAMAGE)

    def _damage_piece(
        self, square: tuple[int, int], attacker: str, damage: int
    ) -> bool:
        row, col = square
        target = self.board[row][col]
        if target is None:
            return False
        current_health = target.health or 0
        actual_damage = min(current_health, damage)
        self.last_damage.append((square, actual_damage))
        remaining_health = current_health - actual_damage
        if remaining_health > 0:
            self.board[row][col] = Piece(
                target.color,
                target.kind,
                target.level,
                target.experience,
                remaining_health,
                target.upgrades,
            )
            return False

        self.board[row][col] = None
        self.team_health[target.color] = max(
            0, self.team_health[target.color] - (target.health or 0)
        )
        if attacker != target.color:
            self.coins[attacker] += target.value
            self.captured[attacker].append(target)
        return True

    def _pseudo_moves_from(self, square: tuple[int, int]) -> list[Move]:
        row, col = square
        piece = self.board[row][col]
        if piece is None:
            return []

        if piece.kind == "P":
            return self._pawn_moves(square, piece)
        if piece.kind == "N":
            return self._step_moves(square, piece, (
                (-2, -1), (-2, 1), (-1, -2), (-1, 2),
                (1, -2), (1, 2), (2, -1), (2, 1),
            ))
        if piece.kind == "K":
            moves = self._step_moves(
                square,
                piece,
                (
                    (-1, -1), (-1, 0), (-1, 1), (0, -1),
                    (0, 1), (1, -1), (1, 0), (1, 1),
                ),
            )
            moves.extend(self._castle_moves(square, piece))
            return moves
        if piece.kind == "B":
            directions = ((-1, -1), (-1, 1), (1, -1), (1, 1))
        elif piece.kind == "R":
            directions = ((-1, 0), (1, 0), (0, -1), (0, 1))
        else:
            directions = (
                (-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1),
            )
        return self._slide_moves(square, piece, directions)

    def _pawn_moves(self, square: tuple[int, int], piece: Piece) -> list[Move]:
        row, col = square
        direction = self._pawn_direction(piece.color)
        start_row = (
            self.standard_white_back_row - 1
            if piece.color == WHITE
            else self.standard_black_back_row + 1
        )
        moves: list[Move] = []
        next_row = row + direction

        if self._inside(next_row, col) and self.board[next_row][col] is None:
            moves.extend(self._promotion_moves(square, (next_row, col), piece))
            two_rows = row + 2 * direction
            if row == start_row and self.board[two_rows][col] is None:
                moves.append(Move(square, (two_rows, col)))

        for next_col in (col - 1, col + 1):
            if not self._inside(next_row, next_col):
                continue
            target = self.board[next_row][next_col]
            if target is not None and target.color != piece.color:
                moves.extend(
                    self._promotion_moves(square, (next_row, next_col), piece)
                )
            elif self.en_passant_target == (next_row, next_col):
                moves.append(Move(square, (next_row, next_col), en_passant=True))
        return moves

    def _promotion_moves(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        piece: Piece,
    ) -> list[Move]:
        return [Move(start, end)]

    def _step_moves(
        self,
        square: tuple[int, int],
        piece: Piece,
        directions: tuple[tuple[int, int], ...],
    ) -> list[Move]:
        row, col = square
        moves = []
        for row_step, col_step in directions:
            next_row, next_col = row + row_step, col + col_step
            if not self._inside(next_row, next_col):
                continue
            target = self.board[next_row][next_col]
            if target is None or target.color != piece.color:
                moves.append(Move(square, (next_row, next_col)))
        return moves

    def _slide_moves(
        self,
        square: tuple[int, int],
        piece: Piece,
        directions: tuple[tuple[int, int], ...],
    ) -> list[Move]:
        moves = []
        for row_step, col_step in directions:
            row, col = square
            while self._inside(row + row_step, col + col_step):
                row += row_step
                col += col_step
                target = self.board[row][col]
                if target is None:
                    moves.append(Move(square, (row, col)))
                else:
                    if target.color != piece.color:
                        moves.append(Move(square, (row, col)))
                    break
        return moves

    def _castle_moves(
        self, square: tuple[int, int], king: Piece
    ) -> list[Move]:
        home_row = (
            self.standard_white_back_row
            if king.color == WHITE
            else self.standard_black_back_row
        )
        king_col = self.standard_start_col + 4
        if square != (home_row, king_col):
            return []
        king_side, queen_side = (
            ("K", "Q") if king.color == WHITE else ("k", "q")
        )
        moves = []
        king_rook_col = self.standard_start_col + 7
        queen_rook_col = self.standard_start_col
        if (
            king_side in self.castling_rights
            and self._is_piece(self.board[home_row][king_rook_col], king.color, "R")
            and self.board[home_row][king_col + 1] is None
            and self.board[home_row][king_col + 2] is None
        ):
            moves.append(Move(square, (home_row, king_col + 2), castle=True))
        if (
            queen_side in self.castling_rights
            and self._is_piece(self.board[home_row][queen_rook_col], king.color, "R")
            and self.board[home_row][king_col - 1] is None
            and self.board[home_row][king_col - 2] is None
            and self.board[home_row][king_col - 3] is None
        ):
            moves.append(Move(square, (home_row, king_col - 2), castle=True))
        return moves

    def _remove_moved_piece_right(
        self, piece: Piece, square: tuple[int, int]
    ) -> None:
        if piece.kind == "K":
            self.castling_rights.difference_update(
                ("K", "Q") if piece.color == WHITE else ("k", "q")
            )
        elif piece.kind == "R":
            self._remove_rook_right(piece, square)

    def _remove_rook_right(
        self, piece: Piece, square: tuple[int, int]
    ) -> None:
        if piece.kind != "R":
            return
        rights_by_square = {
            (self.standard_white_back_row, self.standard_start_col): "Q",
            (self.standard_white_back_row, self.standard_start_col + 7): "K",
            (self.standard_black_back_row, self.standard_start_col): "q",
            (self.standard_black_back_row, self.standard_start_col + 7): "k",
        }
        right = rights_by_square.get(square)
        if right is not None:
            self.castling_rights.discard(right)

    def _inside(self, row: int, col: int) -> bool:
        return 0 <= row < self.board_size and 0 <= col < self.board_size

    @staticmethod
    def _is_piece(piece: Piece | None, color: str, kind: str) -> bool:
        return piece is not None and piece.color == color and piece.kind == kind

    @staticmethod
    def _pawn_direction(color: str) -> int:
        return -1 if color == WHITE else 1

    @staticmethod
    def _opponent(color: str) -> str:
        return BLACK if color == WHITE else WHITE

    @staticmethod
    def _side_name(color: str) -> str:
        return "bili" if color == WHITE else "cerna"
