from __future__ import annotations

from .constants import BLACK, BOARD_SIZE, PROMOTION_PIECES, WHITE
from .models import Move, Piece

class ChessGame:
    """Standard chess rules, kept independent from the Pygame interface."""

    def __init__(self) -> None:
        self.board: list[list[Piece | None]] = []
        self.turn = WHITE
        self.castling_rights = {"K", "Q", "k", "q"}
        self.en_passant_target: tuple[int, int] | None = None
        self.captured: dict[str, list[Piece]] = {WHITE: [], BLACK: []}
        self.coins = {WHITE: 0, BLACK: 0}
        self.reset()

    def reset(self) -> None:
        back_rank = ("R", "N", "B", "Q", "K", "B", "N", "R")
        self.board = [
            [Piece(BLACK, kind) for kind in back_rank],
            [Piece(BLACK, "P") for _ in range(BOARD_SIZE)],
            *([[None] * BOARD_SIZE for _ in range(4)]),
            [Piece(WHITE, "P") for _ in range(BOARD_SIZE)],
            [Piece(WHITE, kind) for kind in back_rank],
        ]
        self.turn = WHITE
        self.castling_rights = {"K", "Q", "k", "q"}
        self.en_passant_target = None
        self.captured = {WHITE: [], BLACK: []}
        self.coins = {WHITE: 0, BLACK: 0}

    def piece_at(self, square: tuple[int, int]) -> Piece | None:
        row, col = square
        return self.board[row][col]

    def legal_moves_from(self, square: tuple[int, int]) -> list[Move]:
        piece = self.piece_at(square)
        if piece is None or piece.color != self.turn:
            return []
        return [
            move
            for move in self._pseudo_moves_from(square)
            if not self._king_in_check(
                piece.color, self._board_after_move(move)
            )
        ]

    def all_legal_moves(self) -> list[Move]:
        moves: list[Move] = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = self.board[row][col]
                if piece is not None and piece.color == self.turn:
                    moves.extend(self.legal_moves_from((row, col)))
        return moves

    def is_in_check(self, color: str) -> bool:
        return self._king_in_check(color, self.board)

    def status(self) -> str:
        in_check = self.is_in_check(self.turn)
        if not self.all_legal_moves():
            if in_check:
                winner = "Bílé" if self.turn == BLACK else "Černé"
                return f"Šachmat! Vyhrály {winner}."
            return "Pat — remíza."
        if in_check:
            return f"Šach! Na tahu jsou {self._side_name(self.turn)}."
        return f"Na tahu jsou {self._side_name(self.turn)}."

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

        captured_square = selected.end
        if selected.en_passant:
            captured_square = (selected.end[0] - self._pawn_direction(piece.color), selected.end[1])
        captured_piece = self.board[captured_square[0]][captured_square[1]]
        if captured_piece is not None:
            self.captured[piece.color].append(captured_piece)
            self._remove_rook_right(captured_piece, captured_square)

        self._remove_moved_piece_right(piece, selected.start)
        self.board = self._board_after_move(selected)
        self.en_passant_target = None
        if piece.kind == "P" and abs(selected.end[0] - selected.start[0]) == 2:
            self.en_passant_target = (
                (selected.start[0] + selected.end[0]) // 2,
                selected.start[1],
            )
        self.turn = self._opponent(self.turn)
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
        start_row = 6 if piece.color == WHITE else 1
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
        last_row = 0 if piece.color == WHITE else 7
        if end[0] == last_row:
            return [Move(start, end, promotion=kind) for kind in PROMOTION_PIECES]
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
        home_row = 7 if king.color == WHITE else 0
        if square != (home_row, 4) or self._king_in_check(king.color, self.board):
            return []

        king_side, queen_side = (
            ("K", "Q") if king.color == WHITE else ("k", "q")
        )
        moves = []
        if (
            king_side in self.castling_rights
            and self._is_piece(self.board[home_row][7], king.color, "R")
            and self.board[home_row][5] is None
            and self.board[home_row][6] is None
            and not self._square_attacked(
                self.board, home_row, 5, self._opponent(king.color)
            )
            and not self._square_attacked(
                self.board, home_row, 6, self._opponent(king.color)
            )
        ):
            moves.append(Move(square, (home_row, 6), castle=True))
        if (
            queen_side in self.castling_rights
            and self._is_piece(self.board[home_row][0], king.color, "R")
            and self.board[home_row][1] is None
            and self.board[home_row][2] is None
            and self.board[home_row][3] is None
            and not self._square_attacked(
                self.board, home_row, 3, self._opponent(king.color)
            )
            and not self._square_attacked(
                self.board, home_row, 2, self._opponent(king.color)
            )
        ):
            moves.append(Move(square, (home_row, 2), castle=True))
        return moves

    def _board_after_move(self, move: Move) -> list[list[Piece | None]]:
        board = [row.copy() for row in self.board]
        start_row, start_col = move.start
        end_row, end_col = move.end
        piece = board[start_row][start_col]
        assert piece is not None
        board[start_row][start_col] = None
        if move.en_passant:
            board[end_row - self._pawn_direction(piece.color)][end_col] = None
        if move.castle:
            rook_start = 7 if end_col == 6 else 0
            rook_end = 5 if end_col == 6 else 3
            board[end_row][rook_end] = board[end_row][rook_start]
            board[end_row][rook_start] = None
        if move.promotion is not None:
            piece = Piece(
                piece.color, move.promotion, piece.level, piece.experience
            )
        board[end_row][end_col] = piece
        return board

    def _king_in_check(
        self, color: str, board: list[list[Piece | None]]
    ) -> bool:
        king_square = next(
            (
                (row, col)
                for row in range(BOARD_SIZE)
                for col in range(BOARD_SIZE)
                if self._is_piece(board[row][col], color, "K")
            ),
            None,
        )
        if king_square is None:
            return True
        return self._square_attacked(
            board, king_square[0], king_square[1], self._opponent(color)
        )

    @classmethod
    def _square_attacked(
        cls,
        board: list[list[Piece | None]],
        row: int,
        col: int,
        by_color: str,
    ) -> bool:
        pawn_row = row - cls._pawn_direction(by_color)
        for pawn_col in (col - 1, col + 1):
            if cls._inside(pawn_row, pawn_col):
                piece = board[pawn_row][pawn_col]
                if cls._is_piece(piece, by_color, "P"):
                    return True

        for row_step, col_step in (
            (-2, -1), (-2, 1), (-1, -2), (-1, 2),
            (1, -2), (1, 2), (2, -1), (2, 1),
        ):
            check_row, check_col = row + row_step, col + col_step
            if cls._inside(check_row, check_col):
                if cls._is_piece(board[check_row][check_col], by_color, "N"):
                    return True

        for row_step, col_step in (
            (-1, -1), (-1, 0), (-1, 1), (0, -1),
            (0, 1), (1, -1), (1, 0), (1, 1),
        ):
            check_row, check_col = row + row_step, col + col_step
            distance = 1
            while cls._inside(check_row, check_col):
                piece = board[check_row][check_col]
                if piece is not None:
                    if piece.color == by_color:
                        if piece.kind == "Q" or (
                            distance == 1 and piece.kind == "K"
                        ):
                            return True
                        if row_step == 0 or col_step == 0:
                            if piece.kind == "R":
                                return True
                        elif piece.kind == "B":
                            return True
                    break
                check_row += row_step
                check_col += col_step
                distance += 1
        return False

    def _remove_moved_piece_right(
        self, piece: Piece, square: tuple[int, int]
    ) -> None:
        row, col = square
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
            (7, 0): "Q",
            (7, 7): "K",
            (0, 0): "q",
            (0, 7): "k",
        }
        right = rights_by_square.get(square)
        if right is not None:
            self.castling_rights.discard(right)

    @staticmethod
    def _inside(row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE

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
        return "bílí" if color == WHITE else "černí"
