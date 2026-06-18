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

import json
import math
from dataclasses import dataclass, asdict
from io import StringIO
from pathlib import Path

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
            "acpl_by_phase": {}, "moves_by_phase": {},
        }

    accuracy = sum(accuracy_from_winpct_loss(m.wp_loss) for m in moves) / n
    avg_cp_loss = sum(m.cp_loss for m in moves) / n

    by_phase: dict[str, list[int]] = {}
    blunders_by_phase: dict[str, int] = {}
    blunder_cp_sum_by_phase: dict[str, int] = {}
    blunder_worst_cp_by_phase: dict[str, int] = {}
    for m in moves:
        by_phase.setdefault(m.phase, []).append(m.cp_loss)
        if m.label == "blunder":
            blunders_by_phase[m.phase] = blunders_by_phase.get(m.phase, 0) + 1
            blunder_cp_sum_by_phase[m.phase] = (
                blunder_cp_sum_by_phase.get(m.phase, 0) + m.cp_loss
            )
            blunder_worst_cp_by_phase[m.phase] = max(
                blunder_worst_cp_by_phase.get(m.phase, 0), m.cp_loss
            )
    acpl_by_phase = {p: round(sum(v) / len(v)) for p, v in by_phase.items()}
    moves_by_phase = {p: len(v) for p, v in by_phase.items()}

    return {
        "moves_analyzed": n,
        "accuracy": round(accuracy, 1),
        "avg_cp_loss": round(avg_cp_loss),
        "blunders": sum(1 for m in moves if m.label == "blunder"),
        "mistakes": sum(1 for m in moves if m.label == "mistake"),
        "inaccuracies": sum(1 for m in moves if m.label == "inaccuracy"),
        "acpl_by_phase": acpl_by_phase,
        "moves_by_phase": moves_by_phase,
        "blunders_by_phase": blunders_by_phase,
        "blunder_cp_sum_by_phase": blunder_cp_sum_by_phase,
        "blunder_worst_cp_by_phase": blunder_worst_cp_by_phase,
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


def select_recent_games(games, max_games: int) -> list[dict]:
    """The ``max_games`` most recent games by ``end_time`` (newest first).

    ``max_games <= 0`` means no limit (returns all, unordered). Bounding the
    engine pass keeps first-run cost tractable; the per-URL cache then fills
    incrementally across refreshes.
    """
    if max_games <= 0:
        return list(games)
    return sorted(games, key=lambda g: g.get("end_time", 0), reverse=True)[:max_games]


def attach_move_quality(games, side_by_url, cache, *, depth, analyze_fn) -> list[dict]:
    """Return per-game summaries, reusing/updating ``cache`` (url -> entry).

    ``cache`` maps game URL to ``{"depth": int, "summary": dict}``. A game is
    re-analyzed only when absent or cached at a different depth — so repeat
    refreshes touch the engine only for new games. ``analyze_fn(pgn, side,
    depth)`` returns a summary dict or ``None`` (skipped). ``cache`` is mutated
    in place.
    """
    summaries: list[dict] = []
    for g in games:
        url = g.get("url")
        pgn = g.get("pgn")
        side = side_by_url.get(url)
        if not url or not pgn or not side:
            continue
        entry = cache.get(url)
        if entry and entry.get("depth") == depth:
            summaries.append(entry["summary"])
            continue
        summary = analyze_fn(pgn, side, depth)
        if summary is None:
            continue
        cache[url] = {"depth": depth, "summary": summary}
        summaries.append(summary)
    return summaries


def aggregate_move_quality(summaries: list[dict]) -> dict | None:
    """Roll per-game summaries into one move-quality overview, or ``None``.

    Accuracy is move-weighted across games; phase ACPL is weighted by the
    number of moves in each phase.
    """
    summaries = [s for s in summaries if s and s.get("moves_analyzed")]
    if not summaries:
        return None

    total_moves = sum(s["moves_analyzed"] for s in summaries)
    blunders = sum(s.get("blunders", 0) for s in summaries)
    mistakes = sum(s.get("mistakes", 0) for s in summaries)
    inaccuracies = sum(s.get("inaccuracies", 0) for s in summaries)

    weighted_acc = sum(s["accuracy"] * s["moves_analyzed"] for s in summaries)

    phase_cp: dict[str, float] = {}
    phase_n: dict[str, int] = {}
    for s in summaries:
        acpl = s.get("acpl_by_phase", {})
        nbp = s.get("moves_by_phase", {})
        for phase, n in nbp.items():
            phase_cp[phase] = phase_cp.get(phase, 0.0) + acpl.get(phase, 0) * n
            phase_n[phase] = phase_n.get(phase, 0) + n
    acpl_by_phase = {p: round(phase_cp[p] / phase_n[p]) for p in phase_n if phase_n[p]}

    return {
        "games_analyzed": len(summaries),
        "moves_analyzed": total_moves,
        "accuracy": round(weighted_acc / total_moves, 1),
        "avg_cp_loss": round(
            sum(s.get("avg_cp_loss", 0) * s["moves_analyzed"] for s in summaries)
            / total_moves),
        "blunders": blunders,
        "mistakes": mistakes,
        "inaccuracies": inaccuracies,
        "blunders_per_100_moves": round(100 * blunders / total_moves, 1),
        "acpl_by_phase": acpl_by_phase,
    }


def aggregate_by_format(games_by_format, side_by_url, cache, *, analyze_fn,
                        depth, max_games) -> dict:
    """Move-quality aggregate per time class: ``{fmt: aggregate|None}``.

    Each format's most-recent ``max_games`` are analyzed (cache shared across
    formats, so a game counted under its class is analyzed once). A format with
    no games maps to ``None``.
    """
    out = {}
    for fmt, games in games_by_format.items():
        recent = select_recent_games(games, max_games)
        summaries = attach_move_quality(recent, side_by_url, cache,
                                        depth=depth, analyze_fn=analyze_fn)
        out[fmt] = aggregate_move_quality(summaries)
    return out


def run_move_quality_by_format(games_by_format, side_by_url, cache, *,
                               engine_path=None, depth: int = DEFAULT_DEPTH,
                               max_games: int = 200) -> dict:
    """Open one Stockfish process and aggregate move quality for each format.

    Returns ``{fmt: None}`` for every format when no engine is available.
    """
    path = engine_path or find_engine_path()
    if path is None:
        return {fmt: None for fmt in games_by_format}
    with chess.engine.SimpleEngine.popen_uci(path) as eng:
        def analyze_fn(pgn, side, d):
            return analyze_move_quality(pgn, side, eng, depth=d)
        return aggregate_by_format(games_by_format, side_by_url, cache,
                                   analyze_fn=analyze_fn, depth=depth,
                                   max_games=max_games)


def load_quality_cache(path) -> dict:
    """Load the per-URL analysis cache, or an empty dict if missing/corrupt."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_quality_cache(path, cache: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2))


def run_move_quality_pass(games, side_by_url, cache, *, engine_path=None,
                          depth: int = DEFAULT_DEPTH) -> list[dict]:
    """Open one Stockfish process and analyze all uncached games.

    Returns ``[]`` (and leaves ``cache`` untouched) when no engine is available.
    """
    path = engine_path or find_engine_path()
    if path is None:
        return []
    with chess.engine.SimpleEngine.popen_uci(path) as eng:
        def analyze_fn(pgn, side, d):
            return analyze_move_quality(pgn, side, eng, depth=d)
        return attach_move_quality(games, side_by_url, cache,
                                   depth=depth, analyze_fn=analyze_fn)
