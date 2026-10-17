from __future__ import annotations

import random

from .constants import BLACK, BOT_DIFFICULTIES, PIECE_VALUES, WHITE
from .models import Move
from .rules import ATTACK_DAMAGE, ChessGame

SEARCH_INFINITY = 1_000_000
WIN_SCORE = 100_000


def choose_move(
    game: ChessGame,
    difficulty: str,
    rng: random.Random | None = None,
) -> Move | None:
    """Pick a black move; stronger settings search deeper with alpha-beta."""
    if game.turn != BLACK:
        return None
    settings = BOT_DIFFICULTIES[difficulty]
    root_limit = {"easy": 10, "medium": 16, "hard": 24}[difficulty]
    moves = _ordered_moves(game, root_limit)
    if not moves:
        return None

    rng = rng or random.Random()
    scored_moves: list[tuple[int, Move]] = []
    for move in moves:
        game.play(move)
        score = _search(
            game,
            settings["depth"] - 1,
            -SEARCH_INFINITY,
            SEARCH_INFINITY,
            1,
        )
        game.undo()
        scored_moves.append((score, move))

    scored_moves.sort(key=lambda entry: entry[0], reverse=True)
    if difficulty == "easy":
        return rng.choice([move for _, move in scored_moves[: min(6, len(moves))]])
    if difficulty == "medium":
        return rng.choice([move for _, move in scored_moves[: min(2, len(moves))]])
    return scored_moves[0][1]


def _search(
    game: ChessGame,
    depth: int,
    alpha: int,
    beta: int,
    ply: int,
) -> int:
    winner = game.winner()
    if winner == BLACK:
        return WIN_SCORE - ply
    if winner == WHITE:
        return -WIN_SCORE + ply
    if winner == "draw":
        return 0
    if depth <= 0:
        return _evaluate(game)

    moves = _ordered_moves(game, 6)
    if not moves:
        return _evaluate(game)

    maximizing = game.turn == BLACK
    best = -SEARCH_INFINITY if maximizing else SEARCH_INFINITY
    for move in moves:
        game.play(move)
        score = _search(game, depth - 1, alpha, beta, ply + 1)
        game.undo()
        if maximizing:
            best = max(best, score)
            alpha = max(alpha, best)
        else:
            best = min(best, score)
            beta = min(beta, best)
        if beta <= alpha:
            break
    return best


def _evaluate(game: ChessGame) -> int:
    score = 0
    center = (game.board_size - 1) / 2
    king_positions: dict[str, tuple[int, int]] = {}
    for row in range(game.board_size):
        for col in range(game.board_size):
            piece = game.board[row][col]
            if piece is None:
                continue
            if piece.kind == "K":
                king_positions[piece.color] = (row, col)
            sign = 1 if piece.color == BLACK else -1
            health = (piece.health or 0) / piece.max_health
            material = PIECE_VALUES[piece.kind] * (0.65 + 0.35 * health)
            center_bonus = max(0, 3 - abs(center - row) - abs(center - col)) * 5
            advance_bonus = (
                row if piece.color == BLACK else game.board_size - 1 - row
            ) * (
                3 if piece.kind == "P" else 1
            )
            score += sign * (int(material) + center_bonus + advance_bonus)
            if piece.color == WHITE and piece.upgrades:
                score -= 35 * len(piece.upgrades)
    score += 2 * (game.team_health[BLACK] - game.team_health[WHITE])
    if len(king_positions) == 2:
        white_king = king_positions[WHITE]
        black_king = king_positions[BLACK]
        for (loot_row, loot_col), value in game.loot.items():
            white_distance = abs(white_king[0] - loot_row) + abs(
                white_king[1] - loot_col
            )
            black_distance = abs(black_king[0] - loot_row) + abs(
                black_king[1] - loot_col
            )
            score += (white_distance - black_distance) * (value // 50)
    return score


def _ordered_moves(game: ChessGame, limit: int | None = None) -> list[Move]:
    moves = game.all_legal_moves()

    def order_score(move: Move) -> int:
        target_square = move.end
        if move.en_passant:
            piece = game.piece_at(move.start)
            if piece is not None:
                target_square = (
                    move.end[0] - game._pawn_direction(piece.color),
                    move.end[1],
                )
        target = game.piece_at(target_square)
        attacker = game.piece_at(move.start)
        score = 0
        if target is not None and attacker is not None:
            damage = ATTACK_DAMAGE[attacker.kind]
            score += min(damage, target.health or 0) * 10
            if damage >= (target.health or 0):
                score += PIECE_VALUES[target.kind]
        if move.promotion is not None:
            score += PIECE_VALUES[move.promotion]
        if move.castle:
            score += 25
        return score

    moves.sort(key=order_score, reverse=True)
    return moves if limit is None else moves[:limit]
