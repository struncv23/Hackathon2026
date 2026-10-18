from __future__ import annotations

import random

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "Game"

from .constants import BLACK, BOT_DIFFICULTIES, PIECE_VALUES, WHITE
from .models import Move, Piece
from .rules import ATTACK_DAMAGE, ChessGame

SEARCH_INFINITY = 1_000_000
WIN_SCORE = 100_000
SEARCH_WIDTH = {"easy": 4, "medium": 6, "hard": 8}


def choose_move(
    game: ChessGame,
    difficulty: str,
    rng: random.Random | None = None,
) -> Move | None:
    """Pick a black move; stronger settings search deeper with alpha-beta."""
    if game.turn != BLACK:
        return None
    if game.capture_majority:
        return _choose_king_hunt_move(game, rng)

    settings = BOT_DIFFICULTIES[difficulty]
    root_limit = {"easy": 10, "medium": 16, "hard": 24}[difficulty]
    search_width = SEARCH_WIDTH[difficulty]
    moves = _ordered_moves(game, root_limit)
    if not moves:
        return None

    rng = rng or random.Random()
    scored_moves: list[tuple[int, Move]] = []
    best_score = -SEARCH_INFINITY
    for move in moves:
        game.play(move)
        score = _search(
            game,
            settings["depth"] - 1,
            best_score if difficulty == "hard" else -SEARCH_INFINITY,
            SEARCH_INFINITY,
            1,
            search_width,
        )
        game.undo()
        scored_moves.append((score, move))
        best_score = max(best_score, score)

    scored_moves.sort(key=lambda entry: entry[0], reverse=True)
    if difficulty == "easy":
        return rng.choice([move for _, move in scored_moves[: min(6, len(moves))]])
    if difficulty == "medium":
        return rng.choice([move for _, move in scored_moves[: min(2, len(moves))]])
    return scored_moves[0][1]


def _choose_king_hunt_move(
    game: ChessGame,
    rng: random.Random | None = None,
) -> Move | None:
    white_king = next(
        (
            (row, col)
            for row in range(game.board_size)
            for col in range(game.board_size)
            if (piece := game.board[row][col]) is not None
            and piece.color == WHITE
            and piece.kind == "K"
        ),
        None,
    )
    if white_king is None:
        return None

    rng = rng or random.Random()
    scored_moves: list[tuple[int, Move]] = []
    for move in game.all_legal_moves():
        target = _target_piece(game, move)
        attacker = game.piece_at(move.start)
        if attacker is None:
            continue
        damage = ATTACK_DAMAGE[attacker.kind]
        if target is not None and target.color == WHITE and target.kind == "K":
            if not game.play(move):
                continue
            victory = game.winner() == BLACK
            threat_penalty = (
                0 if victory else _black_piece_threat_penalty(game)
            )
            game.undo()
            scored_moves.append(
                (
                    20_000 + damage * 10 - threat_penalty,
                    move,
                )
            )
            continue

        old_distance = abs(move.start[0] - white_king[0]) + abs(
            move.start[1] - white_king[1]
        )
        new_distance = abs(move.end[0] - white_king[0]) + abs(
            move.end[1] - white_king[1]
        )
        progress_score = (old_distance - new_distance) * 250 - new_distance * 8
        if target is not None:
            progress_score += min(damage, target.health or 0) * 4
            if damage >= (target.health or 0):
                progress_score += PIECE_VALUES[target.kind] * 2
        if move.promotion is not None:
            progress_score += PIECE_VALUES[move.promotion]
        if move.castle:
            progress_score += 100

        if not game.play(move):
            continue
        threat_penalty = _black_piece_threat_penalty(game)
        game.undo()
        scored_moves.append((progress_score - threat_penalty, move))

    if not scored_moves:
        return None
    best_score = max(score for score, _ in scored_moves)
    best_moves = [move for score, move in scored_moves if score == best_score]
    return rng.choice(best_moves)


def _black_piece_threat_penalty(game: ChessGame) -> int:
    worst_threat = 0
    for move in game.all_legal_moves():
        target = _target_piece(game, move)
        attacker = game.piece_at(move.start)
        if target is None or target.color != BLACK or attacker is None:
            continue
        damage = min(ATTACK_DAMAGE[attacker.kind], target.health or 0)
        if target.kind == "K":
            return 50_000 + damage * 10
        threat = damage * 4
        if damage >= (target.health or 0):
            threat += PIECE_VALUES[target.kind] * 2
        worst_threat = max(worst_threat, threat)
    return worst_threat


def _search(
    game: ChessGame,
    depth: int,
    alpha: int,
    beta: int,
    ply: int,
    width: int,
) -> int:
    winner = game.winner()
    if winner == BLACK:
        return WIN_SCORE - ply
    if winner == WHITE:
        return -WIN_SCORE + ply
    if winner == "draw":
        return 0
    if depth <= 0:
        return _quiescence(game, alpha, beta, ply, 3)

    moves = _ordered_moves(game, width)
    if not moves:
        return _evaluate(game)

    maximizing = game.turn == BLACK
    best = -SEARCH_INFINITY if maximizing else SEARCH_INFINITY
    for move in moves:
        game.play(move)
        score = _search(game, depth - 1, alpha, beta, ply + 1, width)
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


def _quiescence(
    game: ChessGame,
    alpha: int,
    beta: int,
    ply: int,
    remaining: int,
) -> int:
    winner = game.winner()
    if winner == BLACK:
        return WIN_SCORE - ply
    if winner == WHITE:
        return -WIN_SCORE + ply
    if winner == "draw":
        return 0

    stand_pat = _evaluate(game)
    if remaining == 0:
        return stand_pat

    maximizing = game.turn == BLACK
    if maximizing:
        if stand_pat >= beta:
            return stand_pat
        alpha = max(alpha, stand_pat)
        best = stand_pat
    else:
        if stand_pat <= alpha:
            return stand_pat
        beta = min(beta, stand_pat)
        best = stand_pat

    tactical_moves = [
        move
        for move in _ordered_moves(game)
        if move.promotion is not None or _target_piece(game, move) is not None
    ]
    for move in tactical_moves:
        game.play(move)
        score = _quiescence(game, alpha, beta, ply + 1, remaining - 1)
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
    white_king = next(
        (
            (row, col)
            for row in range(game.board_size)
            for col in range(game.board_size)
            if (piece := game.board[row][col]) is not None
            and piece.color == WHITE
            and piece.kind == "K"
        ),
        None,
    )
    for row in range(game.board_size):
        for col in range(game.board_size):
            piece = game.board[row][col]
            if piece is None:
                continue
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
            if (
                game.capture_majority
                and piece.color == BLACK
                and white_king is not None
            ):
                distance = abs(row - white_king[0]) + abs(col - white_king[1])
                score += max(0, 2 * game.board_size - distance) * 3
            if piece.color == WHITE and piece.upgrades:
                score -= 35 * len(piece.upgrades)
    score += 2 * (game.team_health[BLACK] - game.team_health[WHITE])
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
            if target.color == WHITE and target.kind == "K":
                score += WIN_SCORE
        if move.promotion is not None:
            score += PIECE_VALUES[move.promotion]
        if move.castle:
            score += 25
        return score

    moves.sort(key=order_score, reverse=True)
    return moves if limit is None else moves[:limit]


def _target_piece(game: ChessGame, move: Move) -> Piece | None:
    target_square = move.end
    if move.en_passant:
        piece = game.piece_at(move.start)
        if piece is not None:
            target_square = (
                move.end[0] - game._pawn_direction(piece.color),
                move.end[1],
            )
    return game.piece_at(target_square)


if __name__ == "__main__":
    import pygame

    from .app import ChessApp

    app = ChessApp()
    try:
        app.run()
    finally:
        pygame.quit()
