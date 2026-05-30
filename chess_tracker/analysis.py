"""Per-game move-quality analysis: accuracy%, blunder counts, cp-loss by phase.

An offline Stockfish pass over a game's mainline. For each move *I* made we
compare the engine's eval before (best play available) and after my actual
move, both from my point of view, and turn that into human-legible quality
signals:

  * **win%** via the Lichess win-probability model, so a swing is weighted by
    how much it actually changed the game (losing +8 → +6 barely matters;
    losing 0.0 → -1.5 is decisive);
  * **accuracy%** via the Lichess move-accuracy curve;
  * a **blunder / mistake / inaccuracy** label per move;
  * average centipawn loss bucketed by **game phase**.

This module owns the math (pure, fully unit-tested) and a thin engine driver
that feeds it. The engine is optional and injectable — callers analysing many
games reuse one `SimpleEngine` process, exactly like `puzzles.analyse_game`.

Caveats (deliberate v1 simplifications):
  * `accuracy` is the unweighted mean of per-move accuracies — NOT Lichess's
    volatility-weighted + harmonic blend. Track the *trend* on this one method;
    absolute numbers won't match Chess.com (CAPS2) or Lichess exactly.
  * `game_phase` is a heuristic (opening by move number, endgame by remaining
    non-pawn material), not a ground-truth phase classifier.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from io import StringIO

import chess
import chess.engine
import chess.pgn

from chess_tracker.puzzles import find_engine_path, DEFAULT_DEPTH

# Mate scores collapse to this bound so they compare as plain integers.
MATE_CP = 10_000

# Lichess win-probability constant (logistic steepness over centipawns).
_WIN_K = 0.00368208

# Lichess move-accuracy curve constants.
_ACC_A = 103.1668
_ACC_B = 0.04354
_ACC_C = 3.1669

# Win%-loss thresholds (percentage points) for move labels.
INACCURACY = 10.0
MISTAKE = 20.0
BLUNDER = 30.0

# Opening lasts through this full-move number; endgame begins at/below this many
# non-pawn, non-king pieces remaining on the board.
OPENING_LAST_FULLMOVE = 8
ENDGAME_NON_PAWN_PIECES = 6


def win_pct(cp: int | float) -> float:
    """Expected win percentage (0–100) for a centipawn eval, mover's POV.

    Lichess model: ``100 / (1 + exp(-k·cp))``. Symmetric about 0 (=50%).
    """
    return 100.0 / (1.0 + math.exp(-_WIN_K * cp))


def accuracy_from_winpct_loss(wp_loss: float) -> float:
    """Move accuracy (0–100) for a drop of ``wp_loss`` win-percentage points.

    Lichess curve ``A·exp(-B·loss) - C``, clamped to [0, 100].
    """
    acc = _ACC_A * math.exp(-_ACC_B * wp_loss) - _ACC_C
    return max(0.0, min(100.0, acc))


def classify(wp_loss: float) -> str:
    """Label a move by how much win% it threw away."""
    if wp_loss >= BLUNDER:
        return "blunder"
    if wp_loss >= MISTAKE:
        return "mistake"
    if wp_loss >= INACCURACY:
        return "inaccuracy"
    return "ok"


def game_phase(fullmove: int, non_pawn_pieces: int) -> str:
    """Heuristic phase bucket for a position.

    Opening by move number first; otherwise endgame once heavy material is off,
    else middlegame.
    """
    if fullmove <= OPENING_LAST_FULLMOVE:
        return "opening"
    if non_pawn_pieces <= ENDGAME_NON_PAWN_PIECES:
        return "endgame"
    return "middlegame"


@dataclass
class MoveEval:
    ply: int            # 0-indexed ply of my move
    fullmove: int       # human move number (1-based)
    cp_before: int      # eval (my POV) before my move, best play available
    cp_after: int       # eval (my POV) after my actual move
    cp_loss: int        # max(0, cp_before - cp_after)
    wp_loss: float      # max(0, win% before - win% after), my POV
    phase: str          # opening | middlegame | endgame
    label: str          # ok | inaccuracy | mistake | blunder

    @classmethod
    def from_evals(cls, ply: int, fullmove: int, cp_before: int, cp_after: int,
                   phase: str) -> "MoveEval":
        cp_loss = max(0, cp_before - cp_after)
        wp_loss = max(0.0, win_pct(cp_before) - win_pct(cp_after))
        return cls(ply=ply, fullmove=fullmove, cp_before=cp_before,
                   cp_after=cp_after, cp_loss=cp_loss, wp_loss=wp_loss,
                   phase=phase, label=classify(wp_loss))

    def to_dict(self) -> dict:
        return asdict(self)


def summarize(moves: list[MoveEval]) -> dict:
    """Aggregate per-move evals into a game-level quality summary."""
    n = len(moves)
    if n == 0:
        return {
            "moves_analyzed": 0, "accuracy": None, "avg_cp_loss": None,
            "blunders": 0, "mistakes": 0, "inaccuracies": 0,
            "acpl_by_phase": {},
        }

    accuracy = sum(accuracy_from_winpct_loss(m.wp_loss) for m in moves) / n
    avg_cp_loss = sum(m.cp_loss for m in moves) / n

    by_phase: dict[str, list[int]] = {}
    for m in moves:
        by_phase.setdefault(m.phase, []).append(m.cp_loss)
    acpl_by_phase = {p: round(sum(v) / len(v)) for p, v in by_phase.items()}

    return {
        "moves_analyzed": n,
        "accuracy": round(accuracy, 1),
        "avg_cp_loss": round(avg_cp_loss),
        "blunders": sum(1 for m in moves if m.label == "blunder"),
        "mistakes": sum(1 for m in moves if m.label == "mistake"),
        "inaccuracies": sum(1 for m in moves if m.label == "inaccuracy"),
        "acpl_by_phase": acpl_by_phase,
    }


def _cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    """Centipawns from ``color``'s point of view, with mate clamped."""
    return score.pov(color).score(mate_score=MATE_CP)


def _non_pawn_pieces(board: chess.Board) -> int:
    """Count pieces that are neither king nor pawn (both colors)."""
    return sum(1 for p in board.piece_map().values()
               if p.piece_type not in (chess.KING, chess.PAWN))


def analyze_move_quality(
    pgn: str,
    side: str,
    engine: chess.engine.SimpleEngine | None = None,
    *,
    depth: int = DEFAULT_DEPTH,
) -> dict | None:
    """Move-quality summary for the side I played, or ``None`` if unavailable.

    ``side`` is "white" or "black". Pass an open ``engine`` to reuse one process
    across many games; if omitted, one is opened from `find_engine_path` and
    closed before returning. Returns ``None`` when no engine is available or the
    PGN can't be parsed.
    """
    if engine is None:
        path = find_engine_path()
        if path is None:
            return None
        with chess.engine.SimpleEngine.popen_uci(path) as eng:
            return analyze_move_quality(pgn, side, eng, depth=depth)

    game = chess.pgn.read_game(StringIO(pgn))
    if game is None:
        return None

    my_color = chess.WHITE if side == "white" else chess.BLACK
    limit = chess.engine.Limit(depth=depth)
    board = game.board()
    moves: list[MoveEval] = []

    for move in game.mainline_moves():
        if board.turn != my_color:
            board.push(move)
            continue

        info_before = engine.analyse(board, limit)
        cp_before = _cp(info_before["score"], my_color)
        phase = game_phase(board.fullmove_number, _non_pawn_pieces(board))
        ply = board.ply()
        fullmove = board.fullmove_number

        board.push(move)
        info_after = engine.analyse(board, limit)
        cp_after = _cp(info_after["score"], my_color)

        moves.append(MoveEval.from_evals(ply=ply, fullmove=fullmove,
                                         cp_before=cp_before, cp_after=cp_after,
                                         phase=phase))

    summary = summarize(moves)
    summary["side"] = side
    return summary
