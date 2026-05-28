"""Tests for the behavioral-signals layer."""
from chess_tracker.pgn import GameRecord
from chess_tracker.behavior import compute_loss_streaks, compute_revenge_gap, compute_daily_drawdown


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


def test_revenge_gap_negative_when_post_loss_is_worse():
    # Games in chronological order: W W L L W L W W L W
    # Pairs (prev, this): (W,W) (W,L) (L,L) (L,W) (W,L) (L,W) (W,W) (W,L) (L,W)
    # After-win:  W L L W L  -> wins=2/5 = 40%
    # After-loss: L W W   W  -> wins=3/4 = 75%
    results = ["win", "win", "checkmated", "timeout", "win",
               "checkmated", "win", "win", "checkmated", "win"]
    records = [_mk(1_700_000_000 + i*60, r) for i, r in enumerate(results)]
    out = compute_revenge_gap(records)
    assert out["games_after_win"] == 5
    assert out["wins_after_win"] == 2
    assert out["games_after_loss"] == 4
    assert out["wins_after_loss"] == 3
    assert out["win_pct_after_win"] == 40.0
    assert out["win_pct_after_loss"] == 75.0
    # gap = after_loss% - after_win% (positive means you play *better* after a loss,
    # negative means revenge-tilt costs you).
    assert out["revenge_gap"] == 35.0


def test_revenge_gap_handles_too_few_games():
    out = compute_revenge_gap([_mk(1, "win")])
    assert out["games_after_win"] == 0
    assert out["games_after_loss"] == 0
    assert out["revenge_gap"] is None


def test_daily_drawdown_tracks_max_intraday_slide():
    # All on the same local date (UTC midnight + small offsets).
    # Ratings sequence: 500 -> 520 -> 510 -> 480 -> 460 -> 490
    # High = 520, low = 460, max drawdown = -60, close = 490.
    # Games after being down 100: 0 (worst drawdown is -60, never reached -100).
    base = 1_700_000_000  # arbitrary unix ts
    ratings = [500, 520, 510, 480, 460, 490]
    records = []
    for i, rating in enumerate(ratings):
        records.append(GameRecord(
            url=f"u{i}", end_time=base + i*60, time_class="bullet",
            side="white", my_rating=rating, opp_rating=500,
            result="win", opp_result="checkmated",
            plies=20, fullmoves=10, opening="x", eco="A00",
        ))
    days = compute_daily_drawdown(records)
    assert len(days) == 1
    d = days[0]
    assert d["open"] == 500
    assert d["high"] == 520
    assert d["low"] == 460
    assert d["close"] == 490
    assert d["max_drawdown"] == -60
    assert d["games_after_drawdown_100"] == 0
    assert d["games"] == 6
