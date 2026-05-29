"""Turn a lost game into a single "find the better move" puzzle.

Offline Stockfish pass over a game's mainline. For each move *I* made, we
compare the engine's best line against what I actually played and record the
largest centipawn drop. That worst moment becomes the puzzle: the position
just before my mistake, my move, and the move the engine prefers.

The engine is optional. `find_engine_path` returns ``None`` when Stockfish
isn't installed, and callers are expected to skip puzzle extraction rather
than crash — the dashboard pipeline must still build without an engine.

Timeout losses often have no real board blunder (you were fine but ran out
of clock); in that case no move clears `swing_cp` and we return ``None``.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, asdict
from io import StringIO

import chess
import chess.engine
import chess.pgn

# Mate scores collapse to this bound so they compare as plain integers.
_MATE_CP = 10_000
# A move must lose at least this many centipawns (from my point of view) to
# count as the puzzle. 150cp ~= losing a minor-piece's worth of advantage.
DEFAULT_SWING_CP = 150
# A position is "still holdable" if my eval before the move is no worse than
# this (i.e. >= -200cp ~ within two pawns). The most instructive puzzle is the
# FIRST blunder from a holdable position — the moment the game actually slipped
# — not a flailing move made when already lost.
HOLDABLE_CP = -200
# Search depth per position. Bullet-mistake detection doesn't need deep search;
# depth 12 is fast and stable enough to rank the worst move in a game.
DEFAULT_DEPTH = 12


@dataclass
class Puzzle:
    ply: int                # 0-indexed ply of my mistake
    fullmove: int           # human move number (1-based)
    side: str               # "white" | "black" — the side to move (me)
    fen_before: str         # position to present on the board
    my_move_uci: str
    my_move_san: str
    best_move_uci: str
    best_move_san: str
    cp_before: int          # eval (my POV) before my move, best play available
    cp_after: int           # eval (my POV) after my actual move
    cp_loss: int            # cp_before - cp_after; how much my move threw away

    def to_dict(self) -> dict:
        return asdict(self)


def find_engine_path() -> str | None:
    """Locate a Stockfish binary, or ``None`` if unavailable.

    Honors ``$STOCKFISH_PATH`` first (lets CI point at a downloaded binary),
    then falls back to a ``stockfish`` on ``PATH``.
    """
    env = os.environ.get("STOCKFISH_PATH")
    if env and os.path.exists(env):
        return env
    return shutil.which("stockfish")


def _cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    """Centipawns from ``color``'s point of view, with mate clamped."""
    return score.pov(color).score(mate_score=_MATE_CP)


def _select_puzzle(candidates: list[Puzzle]) -> Puzzle | None:
    """Pick the most instructive blunder from a game's candidates.

    Prefer the EARLIEST mistake made from a still-holdable position — that's
    where the game actually slipped. Only if every blunder came from an
    already-lost position do we fall back to the single biggest swing.
    """
    if not candidates:
        return None
    holdable = [c for c in candidates if c.cp_before >= HOLDABLE_CP]
    if holdable:
        return min(holdable, key=lambda c: c.ply)
    return max(candidates, key=lambda c: c.cp_loss)


def analyse_game(
    pgn: str,
    side: str,
    engine: chess.engine.SimpleEngine,
    *,
    depth: int = DEFAULT_DEPTH,
    swing_cp: int = DEFAULT_SWING_CP,
) -> Puzzle | None:
    """Find my single worst move in ``pgn``; return it as a `Puzzle` or ``None``.

    ``side`` is "white" or "black" — which colour I played. ``engine`` is an
    already-open ``SimpleEngine`` so a caller analysing many games reuses one
    process. Returns ``None`` when no move loses at least ``swing_cp`` (e.g. a
    clean timeout loss) or the game can't be parsed. When several moves qualify,
    `_select_puzzle` picks the most instructive one.
    """
    game = chess.pgn.read_game(StringIO(pgn))
    if game is None:
        return None
    my_color = chess.WHITE if side == "white" else chess.BLACK
    limit = chess.engine.Limit(depth=depth)

    board = game.board()
    candidates: list[Puzzle] = []

    for move in game.mainline_moves():
        if board.turn != my_color:
            board.push(move)
            continue

        info_before = engine.analyse(board, limit)
        pv = info_before.get("pv") or []
        if not pv:
            board.push(move)
            continue
        best = pv[0]
        cp_before = _cp(info_before["score"], my_color)

        fen_before = board.fen()
        fullmove = board.fullmove_number
        ply = board.ply()
        my_san = board.san(move)
        best_san = board.san(best)

        board.push(move)
        info_after = engine.analyse(board, limit)
        cp_after = _cp(info_after["score"], my_color)

        cp_loss = cp_before - cp_after
        if move != best and cp_loss >= swing_cp:
            candidates.append(Puzzle(
                ply=ply,
                fullmove=fullmove,
                side=side,
                fen_before=fen_before,
                my_move_uci=move.uci(),
                my_move_san=my_san,
                best_move_uci=best.uci(),
                best_move_san=best_san,
                cp_before=cp_before,
                cp_after=cp_after,
                cp_loss=cp_loss,
            ))

    return _select_puzzle(candidates)


def attach_puzzles(
    losses: list[dict],
    pgn_by_url: dict[str, str],
    side_by_url: dict[str, str],
    *,
    engine_path: str | None = None,
    depth: int = DEFAULT_DEPTH,
    swing_cp: int = DEFAULT_SWING_CP,
) -> int:
    """Add a ``puzzle`` field to each loss dict in place; return the count found.

    Looks up each loss's full PGN and side by ``game_url`` (the loss dicts
    themselves only carry the opening's first plies). One Stockfish process is
    reused across all losses. When no engine is available, every loss gets
    ``puzzle = None`` and 0 is returned — the pipeline still builds.
    """
    path = engine_path or find_engine_path()
    if path is None:
        for loss in losses:
            loss["puzzle"] = None
        return 0

    found = 0
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        for loss in losses:
            url = loss.get("game_url")
            pgn = pgn_by_url.get(url)
            side = side_by_url.get(url)
            if not pgn or not side:
                loss["puzzle"] = None
                continue
            puzzle = analyse_game(pgn, side, engine, depth=depth, swing_cp=swing_cp)
            loss["puzzle"] = puzzle.to_dict() if puzzle else None
            if puzzle:
                found += 1
    return found


def extract_puzzle(
    pgn: str,
    side: str,
    *,
    depth: int = DEFAULT_DEPTH,
    swing_cp: int = DEFAULT_SWING_CP,
) -> Puzzle | None:
    """Convenience one-shot: open Stockfish, analyse one game, close it.

    Returns ``None`` if no engine is available. For batch use, open one engine
    and call `analyse_game` directly instead.
    """
    path = find_engine_path()
    if path is None:
        return None
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        return analyse_game(pgn, side, engine, depth=depth, swing_cp=swing_cp)
