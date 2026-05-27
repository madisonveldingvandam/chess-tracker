"""Pure-function metric computations over a list of GameRecord."""
from collections import Counter
from datetime import datetime
import statistics
from chess_tracker.pgn import GameRecord


_DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient",
                 "50move", "timevsinsufficient"}


def _is_win(r: str) -> bool:
    return r == "win"


def _is_draw(r: str) -> bool:
    return r in _DRAW_RESULTS


def _is_loss(r: str) -> bool:
    return not _is_win(r) and not _is_draw(r)


def _tilt_color(win_pct: float) -> str:
    if win_pct >= 60:
        return "green"
    if win_pct >= 40:
        return "yellow"
    return "red"


def compute_kpis(records: list[GameRecord]) -> dict:
    if not records:
        return {"current_rating": None, "games_total": 0,
                "recent_form_win_pct": 0.0, "tilt": "yellow"}
    last = max(records, key=lambda r: r.end_time)
    last_5 = sorted(records, key=lambda r: r.end_time)[-5:]
    wins5 = sum(1 for r in last_5 if _is_win(r.result))
    form_pct = 100.0 * wins5 / len(last_5)
    return {
        "current_rating": last.my_rating,
        "games_total": len(records),
        "recent_form_win_pct": round(form_pct, 1),
        "tilt": _tilt_color(form_pct),
    }


def compute_sessions(records: list[GameRecord], gap_seconds: int = 600) -> list[dict]:
    if not records:
        return []
    ordered = sorted(records, key=lambda r: r.end_time)
    sessions = []
    current = [ordered[0]]
    for r in ordered[1:]:
        if r.end_time - current[-1].end_time > gap_seconds:
            sessions.append(current)
            current = []
        current.append(r)
    sessions.append(current)

    out = []
    for s in sessions:
        wins = sum(1 for r in s if _is_win(r.result))
        losses = sum(1 for r in s if _is_loss(r.result))
        draws = sum(1 for r in s if _is_draw(r.result))
        rating_start = s[0].my_rating
        rating_end = s[-1].my_rating
        delta = rating_end - rating_start
        out.append({
            "start": datetime.fromtimestamp(s[0].end_time).astimezone().isoformat(),
            "games": len(s),
            "duration_minutes": round((s[-1].end_time - s[0].end_time) / 60, 1),
            "wins": wins, "losses": losses, "draws": draws,
            "rating_start": rating_start,
            "rating_end": rating_end,
            "rating_delta": delta,
            "tilt_flag": delta <= -50,
        })
    return out


def _result_letter(r: GameRecord) -> str:
    if _is_win(r.result): return "W"
    if _is_draw(r.result): return "D"
    return "L"


def compute_repertoire(records: list[GameRecord]) -> list[dict]:
    groups: dict[tuple[str, str], list[GameRecord]] = {}
    for r in records:
        if r.opening is None:
            continue
        key = (r.opening, r.side)
        groups.setdefault(key, []).append(r)

    out = []
    for (opening, color), recs in groups.items():
        recs = sorted(recs, key=lambda r: r.end_time)
        n = len(recs)
        wins = sum(1 for r in recs if _is_win(r.result))
        losses_recs = [r for r in recs if _is_loss(r.result)]
        losses = len(losses_recs)
        draws = n - wins - losses
        flag = sum(1 for r in losses_recs if r.result == "timeout")
        mate = sum(1 for r in losses_recs if r.result == "checkmated")
        med_len = statistics.median([r.fullmoves for r in recs])
        avg_opp = round(statistics.mean([r.opp_rating for r in recs]), 0)
        rating_gap = round(statistics.mean([r.my_rating - r.opp_rating for r in recs]), 0)
        # ECO mode
        eco_counts = Counter(r.eco for r in recs if r.eco)
        eco_top = eco_counts.most_common(1)[0][0] if eco_counts else None
        out.append({
            "opening": opening,
            "color": color,
            "eco": eco_top,
            "games": n,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_pct": round(100 * wins / n, 1),
            "flag_pct": round(100 * flag / losses, 1) if losses else 0.0,
            "mate_pct": round(100 * mate / losses, 1) if losses else 0.0,
            "med_len": med_len,
            "avg_opp_rating": int(avg_opp),
            "rating_gap": int(rating_gap),  # mean(my - opp); positive = you outrated
            "form": [_result_letter(r) for r in recs[-10:]],
        })
    out.sort(key=lambda x: (-x["games"], -x["win_pct"]))
    return out


def _ply_clock(clocks: list[float], ply_index: int) -> float | None:
    """Return clock at a specific 0-indexed ply, or None if game was shorter."""
    if 0 <= ply_index < len(clocks):
        return clocks[ply_index]
    return None


def _bucket_stats(recs: list[GameRecord]) -> dict:
    n = len(recs)
    if n == 0:
        return {"games": 0, "win_pct": 0.0, "flag_pct": 0.0, "mate_pct": 0.0}
    wins = sum(1 for r in recs if _is_win(r.result))
    losses_recs = [r for r in recs if _is_loss(r.result)]
    losses = len(losses_recs)
    flag = sum(1 for r in losses_recs if r.result == "timeout")
    mate = sum(1 for r in losses_recs if r.result == "checkmated")
    return {
        "games": n,
        "win_pct": round(100 * wins / n, 1),
        "flag_pct": round(100 * flag / losses, 1) if losses else 0.0,
        "mate_pct": round(100 * mate / losses, 1) if losses else 0.0,
    }


def compute_process_metrics(records: list[GameRecord]) -> dict:
    """Clock-behavior metrics — the bullet-specific process signals."""
    if not records:
        return {
            "reserve_move_10_median": None,
            "reserve_move_20_median": None,
            "opening_velocity_median": None,
            "time_burn_delta": None,
            "outlasted_but_flagged_count": 0,
        }

    # Reserve at end of move 10 = my_clocks[9] (one entry per my-move; 0-indexed)
    res10 = [c for r in records if (c := _ply_clock(r.my_clocks, 9)) is not None]
    res20 = [c for r in records if (c := _ply_clock(r.my_clocks, 19)) is not None]

    # Opening velocity: seconds spent on my first 8 moves = 60 - my_clocks[7]
    velocities = []
    for r in records:
        c = _ply_clock(r.my_clocks, 7)
        if c is not None:
            velocities.append(round(60.0 - c, 2))

    # Time burn delta: mean s/move across my moves 1-8 vs my moves 9-20
    early_rates = []
    late_rates = []
    for r in records:
        if len(r.my_clocks) >= 8:
            early_total = 60.0 - r.my_clocks[7]
            early_rates.append(early_total / 8)
        if len(r.my_clocks) >= 20:
            late_total = r.my_clocks[7] - r.my_clocks[19]
            late_rates.append(late_total / 12)

    time_burn_delta = None
    if early_rates and late_rates:
        time_burn_delta = round(
            statistics.mean(early_rates) - statistics.mean(late_rates), 2)

    # "Outlasted but flagged": timeout-losses where at some recorded ply
    # you had more time than opponent did at the same ply.
    outlasted = 0
    for r in records:
        if r.result != "timeout":
            continue
        common = min(len(r.my_clocks), len(r.opp_clocks))
        for i in range(common):
            if r.my_clocks[i] > r.opp_clocks[i]:
                outlasted += 1
                break

    return {
        "reserve_move_10_median": round(statistics.median(res10), 1) if res10 else None,
        "reserve_move_20_median": round(statistics.median(res20), 1) if res20 else None,
        "opening_velocity_median": round(statistics.median(velocities), 2) if velocities else None,
        "time_burn_delta": time_burn_delta,
        "outlasted_but_flagged_count": outlasted,
    }


def _session_position_groups(records: list[GameRecord], gap_seconds: int = 600) -> dict[str, list[GameRecord]]:
    if not records:
        return {"1-5": [], "6-10": [], "11-20": [], "21+": []}
    ordered = sorted(records, key=lambda r: r.end_time)
    out: dict[str, list[GameRecord]] = {"1-5": [], "6-10": [], "11-20": [], "21+": []}
    pos = 1
    out["1-5"].append(ordered[0])
    for prev, r in zip(ordered, ordered[1:]):
        if r.end_time - prev.end_time > gap_seconds:
            pos = 1
        else:
            pos += 1
        if pos <= 5:
            out["1-5"].append(r)
        elif pos <= 10:
            out["6-10"].append(r)
        elif pos <= 20:
            out["11-20"].append(r)
        else:
            out["21+"].append(r)
    return out


def compute_session_decay(records: list[GameRecord], gap_seconds: int = 600) -> list[dict]:
    """Win/flag/mate stats bucketed by position within session."""
    groups = _session_position_groups(records, gap_seconds)
    return [{"bucket": b, **_bucket_stats(recs)} for b, recs in groups.items()]


def detect_leaks(records: list[GameRecord]) -> list[dict]:
    """Rule-based leak detection over the recent window."""
    leaks = []
    if not records:
        return leaks
    # Window: last 30 games (or all if fewer)
    ordered = sorted(records, key=lambda r: r.end_time)
    window = ordered[-30:]

    pm = compute_process_metrics(window)

    # Time burn in opening. Spec says mean; we use median across games (robust to one slow think).
    if pm["opening_velocity_median"] is not None and pm["opening_velocity_median"] > 8.0:
        leaks.append({
            "name": "time_burn_opening",
            "severity": "critical" if pm["opening_velocity_median"] > 15 else "warn",
            "evidence": f"median {pm['opening_velocity_median']}s on my first 8 moves (target <8s)",
            "suggested_action": "Move 8 with ≥50s left; pre-pick first 6 moves before sit-down.",
        })

    # Flag-loss dominant
    losses_recs = [r for r in window if _is_loss(r.result)]
    if losses_recs:
        flag_pct = 100 * sum(1 for r in losses_recs if r.result == "timeout") / len(losses_recs)
        mate_pct = 100 * sum(1 for r in losses_recs if r.result == "checkmated") / len(losses_recs)
        if flag_pct >= 60:
            leaks.append({
                "name": "flag_loss_dominant",
                "severity": "warn",
                "evidence": f"{flag_pct:.0f}% of losses are timeouts in the last {len(window)} games",
                "suggested_action": "Reserve at move 20 too low; try 1+1 format to convert wins.",
            })
        if mate_pct >= 55:
            leaks.append({
                "name": "mate_loss_dominant",
                "severity": "warn",
                "evidence": f"{mate_pct:.0f}% of losses are checkmates in the last {len(window)} games",
                "suggested_action": "Middlegame tactics — file recurring patterns in the error log.",
            })

    # Mid-session decay & tilt-session use full history; 30-game window starves the 21+ bucket.
    decay = compute_session_decay(records)
    by_bucket = {row["bucket"]: row for row in decay}
    early = by_bucket.get("1-5", {}).get("win_pct", 0.0)
    late = by_bucket.get("21+", {}).get("win_pct", 0.0)
    if early - late >= 10 and by_bucket.get("21+", {}).get("games", 0) >= 5:
        leaks.append({
            "name": "mid_session_decay",
            "severity": "warn",
            "evidence": f"win% drops from {early:.0f}% in games 1-5 to {late:.0f}% after game 21",
            "suggested_action": "Cap sessions — see Next Session Rule.",
        })

    # Tilt sessions in last 24h
    sessions = compute_sessions(records)
    now_seen = max(r.end_time for r in records)
    recent = [s for s in sessions if (now_seen - int(datetime.fromisoformat(s["start"]).timestamp())) < 86400]
    if any(s["tilt_flag"] for s in recent):
        leaks.append({
            "name": "tilt_session",
            "severity": "critical",
            "evidence": f"{sum(1 for s in recent if s['tilt_flag'])} session(s) lost ≥50 rating in last 24h",
            "suggested_action": "Stop-rule: leave the desk after -50 in 30 min.",
        })

    return leaks


def next_session_rule(records: list[GameRecord]) -> dict:
    """Generate concrete next-session recommendation."""
    if not records:
        return {"game_cap": 20, "move_10_target_seconds": 45,
                "stop_if_rating_drops": 50,
                "narrative": "No data yet — start conservative."}

    # Game cap: first session-position bucket where win% < 40
    decay = compute_session_decay(records)
    cap = 30  # default
    for row in decay:
        if row["games"] >= 5 and row["win_pct"] < 40:
            bucket = row["bucket"]
            cap = {"1-5": 5, "6-10": 10, "11-20": 20, "21+": 30}[bucket]
            break

    # Move-10 target: median my-clock at my_clocks[9] among wins, minus 5s
    wins = [r for r in records if _is_win(r.result)]
    win_reserves = [c for r in wins if (c := _ply_clock(r.my_clocks, 9)) is not None]
    target = round(statistics.median(win_reserves) - 5, 0) if win_reserves else 45

    narrative = (
        f"Cap at {cap} games. Aim for {target}s left at move 10. "
        f"Stop if rating drops 50 in a session."
    )

    return {
        "game_cap": cap,
        "move_10_target_seconds": int(target),
        "stop_if_rating_drops": 50,
        "narrative": narrative,
    }


def recent_losses_with_suggestions(records: list[GameRecord], limit: int = 20) -> list[dict]:
    """Recent losses with auto-generated error_log starter entries."""
    losses = sorted(
        [r for r in records if _is_loss(r.result)],
        key=lambda r: r.end_time,
        reverse=True,
    )[:limit]

    out = []
    for r in losses:
        final_clk = r.my_clocks[-1] if r.my_clocks else None
        if r.result == "timeout":
            title = f"Flagged at move {r.fullmoves} in {r.opening or 'unknown'}"
            pattern = (
                f"Ran out of time at move {r.fullmoves}. "
                f"Final clock {final_clk}s. Opponent rating {r.opp_rating}."
            )
        elif r.result == "checkmated":
            title = f"Mated by move {r.fullmoves} in {r.opening or 'unknown'}"
            pattern = (
                f"Checkmated at move {r.fullmoves} with {final_clk}s on clock. "
                f"Opponent rating {r.opp_rating}."
            )
        else:
            title = f"Lost ({r.result}) in {r.opening or 'unknown'}"
            pattern = f"Result {r.result} at move {r.fullmoves}."

        out.append({
            "game_url": r.url,
            "opening": r.opening,
            "eco": r.eco,
            "loss_type": r.result,
            "final_clock": final_clk,
            "moves": r.fullmoves,
            "opp_rating_diff": r.opp_rating - r.my_rating,
            "suggested_entry": {
                "title": title,
                "pattern": pattern,
                "game_refs": [r.url],
            },
        })
    return out


def compute_play_signatures(records: list[GameRecord]) -> list[dict]:
    """Group records by (play_signature, color). Records without a
    play_signature (game < 8 plies) are skipped. Each row carries
    display_name = most common opening label among the group's games.
    """
    groups: dict[tuple[str, str], list[GameRecord]] = {}
    for r in records:
        if r.play_signature is None:
            continue
        key = (r.play_signature, r.side)
        groups.setdefault(key, []).append(r)

    out = []
    for (sig, color), recs in groups.items():
        recs = sorted(recs, key=lambda r: r.end_time)
        # display_name ties break on earliest-end_time of the tied label
        # (Counter.most_common is insertion-order on ties; recs is end_time-sorted).
        name_counts = Counter(r.opening for r in recs if r.opening)
        display_name = name_counts.most_common(1)[0][0] if name_counts else "Unnamed"
        n = len(recs)
        wins = sum(1 for r in recs if _is_win(r.result))
        losses_recs = [r for r in recs if _is_loss(r.result)]
        losses = len(losses_recs)
        draws = n - wins - losses
        flag = sum(1 for r in losses_recs if r.result == "timeout")
        mate = sum(1 for r in losses_recs if r.result == "checkmated")
        med_len = statistics.median([r.fullmoves for r in recs])
        avg_opp = round(statistics.mean([r.opp_rating for r in recs]), 0)
        rating_gap = round(statistics.mean([r.my_rating - r.opp_rating for r in recs]), 0)
        eco_counts = Counter(r.eco for r in recs if r.eco)
        eco_top = eco_counts.most_common(1)[0][0] if eco_counts else None
        out.append({
            "play_signature": sig,
            "display_name": display_name,
            "color": color,
            "eco": eco_top,
            "games": n,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_pct": round(100 * wins / n, 1),
            "flag_pct": round(100 * flag / losses, 1) if losses else 0.0,
            "mate_pct": round(100 * mate / losses, 1) if losses else 0.0,
            "med_len": med_len,
            "avg_opp_rating": int(avg_opp),
            "rating_gap": int(rating_gap),
            "form": [_result_letter(r) for r in recs[-10:]],
        })
    out.sort(key=lambda x: (-x["games"], -x["win_pct"]))
    return out


def compute_all(records: list[GameRecord], annotations: dict,
                username: str, format: str = "bullet",
                low_confidence_threshold: int = 15) -> dict:
    """Top-level dashboard payload. All panel data merged + annotations applied."""
    play_signatures = compute_play_signatures(records)
    opening_notes = annotations.get("openings", {})
    for row in play_signatures:
        ann = opening_notes.get(row["display_name"], {})
        row["tag"] = ann.get("tag", "")
        row["note"] = ann.get("note", "")
        row["low_confidence"] = row["games"] < low_confidence_threshold

    return {
        "username": username,
        "format": format,
        "generated_at": datetime.now().astimezone().isoformat(),
        "kpis": compute_kpis(records),
        "leak_summary": detect_leaks(records),
        "next_session_rule": next_session_rule(records),
        "recent_losses": recent_losses_with_suggestions(records),
        "process_metrics": {
            **compute_process_metrics(records),
            "session_decay": compute_session_decay(records),
        },
        "play_signatures": play_signatures,
        "sessions": compute_sessions(records),
        "error_log": annotations.get("error_log", []),
    }
