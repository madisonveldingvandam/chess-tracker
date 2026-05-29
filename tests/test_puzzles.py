import pytest

from chess_tracker.puzzles import (
    find_engine_path,
    extract_puzzle,
    analyse_game,
    attach_puzzles,
    _select_puzzle,
    Puzzle,
    DEFAULT_SWING_CP,
)


def _puzzle(ply, cp_before, cp_loss):
    """Minimal Puzzle for selection tests; only the fields _select reads matter."""
    return Puzzle(
        ply=ply, fullmove=ply // 2 + 1, side="white",
        fen_before="8/8/8/8/8/8/8/8 w - - 0 1",
        my_move_uci="e2e4", my_move_san="e4",
        best_move_uci="d2d4", best_move_san="d4",
        cp_before=cp_before, cp_after=cp_before - cp_loss, cp_loss=cp_loss,
    )

import chess
import chess.engine

# A short game where White hangs the queen: after 1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6
# White plays 4.Qxf7+?? — the queen is lost to ...Kxf7 instead of the sound
# 4.Qxe5+ / developing move. Black is "me" in the second case below.
QUEEN_HANG_PGN = (
    '[Event "Test"]\n'
    '[Result "0-1"]\n\n'
    "1. e4 e5 2. Qh5 Nc6 3. Bc4 g6 4. Qf3 Nf6 5. Qb3 Nd4 6. Bxf7+ Ke7 "
    "7. Qc4 b5 8. Qxd4 exd4 0-1\n"
)

engine_required = pytest.mark.skipif(
    find_engine_path() is None,
    reason="Stockfish binary not available (set STOCKFISH_PATH or install stockfish)",
)


def test_find_engine_path_returns_none_or_existing_file():
    path = find_engine_path()
    assert path is None or __import__("os").path.exists(path)


def test_extract_puzzle_returns_none_without_engine(monkeypatch):
    monkeypatch.setattr("chess_tracker.puzzles.find_engine_path", lambda: None)
    assert extract_puzzle(QUEEN_HANG_PGN, "white") is None


def test_select_prefers_earliest_holdable_blunder():
    # An early slip from a fine position (ply 10, eval +0.5) should win over a
    # bigger swing that happened later when already lost (ply 40, eval -6.0).
    early = _puzzle(ply=10, cp_before=50, cp_loss=300)
    late_bigger = _puzzle(ply=40, cp_before=-600, cp_loss=900)
    assert _select_puzzle([late_bigger, early]) is early


def test_select_falls_back_to_biggest_swing_when_all_lost():
    # No holdable position anywhere -> teach the single worst throw.
    a = _puzzle(ply=20, cp_before=-400, cp_loss=300)
    b = _puzzle(ply=30, cp_before=-500, cp_loss=800)
    assert _select_puzzle([a, b]) is b


def test_select_empty_is_none():
    assert _select_puzzle([]) is None


def test_attach_puzzles_no_engine_sets_none(monkeypatch):
    monkeypatch.setattr("chess_tracker.puzzles.find_engine_path", lambda: None)
    losses = [{"game_url": "u1"}, {"game_url": "u2"}]
    found = attach_puzzles(losses, {"u1": QUEEN_HANG_PGN}, {"u1": "white"})
    assert found == 0
    assert all(loss["puzzle"] is None for loss in losses)


@engine_required
def test_analyse_game_flags_a_blunder_with_a_better_move():
    path = find_engine_path()
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        # depth kept low for test speed; the blunders here are gross enough.
        puzzle = analyse_game(QUEEN_HANG_PGN, "white", engine, depth=10)

    assert puzzle is not None, "expected a blunder to be detected"
    assert puzzle.cp_loss >= DEFAULT_SWING_CP
    assert puzzle.side == "white"
    # The puzzle position must be the one *before* my mistake, with me to move.
    board = chess.Board(puzzle.fen_before)
    assert board.turn == chess.WHITE
    # My move and the engine's preferred move must be legal and different.
    assert chess.Move.from_uci(puzzle.my_move_uci) in board.legal_moves
    assert chess.Move.from_uci(puzzle.best_move_uci) in board.legal_moves
    assert puzzle.my_move_uci != puzzle.best_move_uci


@engine_required
def test_clean_side_yields_no_puzzle_for_the_other_color():
    # Black plays only natural developing moves here and is never the one
    # throwing material, so from Black's POV there should be no large swing.
    path = find_engine_path()
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        puzzle = analyse_game(
            "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 1-0\n",
            "black",
            engine,
            depth=10,
        )
    assert puzzle is None
