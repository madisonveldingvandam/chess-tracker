"""Behavioral-signals layer: streaks, conditional win rates, drawdowns,
and time-of-day breakdowns. All functions consume enriched GameRecords
(see chess_tracker.enrich) and return JSON-ready dicts/lists."""
from datetime import datetime
from collections import defaultdict
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


def compute_revenge_gap(records: list[GameRecord]) -> dict:
    """Conditional win rate after a win vs. after a loss.

    revenge_gap = win_pct_after_loss - win_pct_after_win.
    Negative => you play worse immediately after a loss => tilt.
    Draws are excluded from the "prior" classification (they neither
    confirm momentum nor trigger revenge-requeue).
    """
    if len(records) < 2:
        return {
            "games_after_win": 0, "wins_after_win": 0,
            "games_after_loss": 0, "wins_after_loss": 0,
            "win_pct_after_win": None, "win_pct_after_loss": None,
            "revenge_gap": None,
        }
    ordered = sorted(records, key=lambda r: r.end_time)
    games_after_win = wins_after_win = 0
    games_after_loss = wins_after_loss = 0
    for prev, r in zip(ordered, ordered[1:]):
        if _is_win(prev.result):
            games_after_win += 1
            if _is_win(r.result):
                wins_after_win += 1
        elif _is_loss(prev.result):
            games_after_loss += 1
            if _is_win(r.result):
                wins_after_loss += 1
        # draws excluded
    pct_aw = round(100 * wins_after_win / games_after_win, 1) if games_after_win else None
    pct_al = round(100 * wins_after_loss / games_after_loss, 1) if games_after_loss else None
    gap = round(pct_al - pct_aw, 1) if (pct_aw is not None and pct_al is not None) else None
    return {
        "games_after_win": games_after_win,
        "wins_after_win": wins_after_win,
        "games_after_loss": games_after_loss,
        "wins_after_loss": wins_after_loss,
        "win_pct_after_win": pct_aw,
        "win_pct_after_loss": pct_al,
        "revenge_gap": gap,
    }


def compute_daily_drawdown(records: list[GameRecord]) -> list[dict]:
    """Per local-date OHLC + max intraday drawdown.

    max_drawdown is the most-negative value of (my_rating - running_high) over the day.
    games_after_drawdown_100 counts games played after the running drawdown
    reached -100 or worse — a "kept-playing-through-the-pain" indicator.
    """
    if not records:
        return []
    ordered = sorted(records, key=lambda r: r.end_time)
    by_day: dict[str, list[GameRecord]] = defaultdict(list)
    for r in ordered:
        day = datetime.fromtimestamp(r.end_time).astimezone().date().isoformat()
        by_day[day].append(r)
    out = []
    for day, recs in sorted(by_day.items()):
        ratings = [r.my_rating for r in recs]
        running_high = ratings[0]
        max_dd = 0
        breach_index = None  # index of first game where drawdown <= -100
        for i, rating in enumerate(ratings):
            running_high = max(running_high, rating)
            dd = rating - running_high
            if dd < max_dd:
                max_dd = dd
            if breach_index is None and dd <= -100:
                breach_index = i
        games_after = (len(ratings) - 1 - breach_index) if breach_index is not None else 0
        out.append({
            "date": day,
            "games": len(recs),
            "open": ratings[0],
            "high": max(ratings),
            "low": min(ratings),
            "close": ratings[-1],
            "max_drawdown": max_dd,
            "games_after_drawdown_100": games_after,
        })
    return out
