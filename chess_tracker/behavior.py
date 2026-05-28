"""Behavioral-signals layer: streaks, conditional win rates, drawdowns,
and time-of-day breakdowns. All functions consume enriched GameRecords
(see chess_tracker.enrich) and return JSON-ready dicts/lists."""
from chess_tracker.pgn import GameRecord


_DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient",
                 "50move", "timevsinsufficient"}


def _is_win(r): return r == "win"
def _is_draw(r): return r in _DRAW_RESULTS
def _is_loss(r): return not _is_win(r) and not _is_draw(r)


def compute_loss_streaks(records: list[GameRecord]) -> dict:
    """Current and longest-in-last-24h loss streaks (total + timeout-only)."""
    if not records:
        return {
            "current_loss_streak": 0,
            "current_timeout_loss_streak": 0,
            "longest_loss_streak_24h": 0,
            "longest_timeout_loss_streak_24h": 0,
        }
    ordered = sorted(records, key=lambda r: r.end_time)

    # Current total-loss streak: count back from the end until a non-loss.
    cur_loss = 0
    for r in reversed(ordered):
        if _is_loss(r.result):
            cur_loss += 1
        else:
            break

    # Current timeout-loss streak: must be contiguous timeouts at the tail.
    cur_timeout = 0
    for r in reversed(ordered):
        if r.result == "timeout":
            cur_timeout += 1
        else:
            break

    # Longest in last 24h (relative to most-recent observed end_time).
    now_seen = ordered[-1].end_time
    window = [r for r in ordered if now_seen - r.end_time <= 86400]
    longest_loss = 0
    longest_timeout = 0
    run_loss = 0
    run_timeout = 0
    for r in window:
        if _is_loss(r.result):
            run_loss += 1
            longest_loss = max(longest_loss, run_loss)
        else:
            run_loss = 0
        if r.result == "timeout":
            run_timeout += 1
            longest_timeout = max(longest_timeout, run_timeout)
        else:
            run_timeout = 0

    return {
        "current_loss_streak": cur_loss,
        "current_timeout_loss_streak": cur_timeout,
        "longest_loss_streak_24h": longest_loss,
        "longest_timeout_loss_streak_24h": longest_timeout,
    }
