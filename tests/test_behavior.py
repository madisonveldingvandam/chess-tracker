"""Tests for the behavioral-signals layer."""
from chess_tracker.pgn import GameRecord
from chess_tracker.behavior import compute_loss_streaks


def _mk(t, result):
    return GameRecord(
        url=f"u{t}", end_time=t, time_class="bullet",
        side="white", my_rating=500, opp_rating=500,
        result=result, opp_result="win" if result != "win" else "checkmated",
        plies=20, fullmoves=10, opening="x", eco="A00",
    )


def test_loss_streaks_current_and_longest_24h():
    # Chronological: W W L L L W L L (current streak = 2, longest = 3 in window)
    records = [
        _mk(1_700_000_000, "win"),
        _mk(1_700_000_060, "win"),
        _mk(1_700_000_120, "checkmated"),
        _mk(1_700_000_180, "timeout"),
        _mk(1_700_000_240, "checkmated"),
        _mk(1_700_000_300, "win"),
        _mk(1_700_000_360, "timeout"),
        _mk(1_700_000_420, "checkmated"),
    ]
    s = compute_loss_streaks(records)
    assert s["current_loss_streak"] == 2
    assert s["current_timeout_loss_streak"] == 0  # most recent is checkmate, not timeout
    assert s["longest_loss_streak_24h"] == 3
    assert s["longest_timeout_loss_streak_24h"] == 1


def test_loss_streaks_empty():
    s = compute_loss_streaks([])
    assert s == {
        "current_loss_streak": 0,
        "current_timeout_loss_streak": 0,
        "longest_loss_streak_24h": 0,
        "longest_timeout_loss_streak_24h": 0,
    }
