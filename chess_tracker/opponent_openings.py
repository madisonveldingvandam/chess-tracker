"""Opponent opening pattern analysis.

Groups all games by the opening moves the opponent played to surface which
systems beat the user most often.  All games are used (not only losses) so
that loss_pct has a real denominator.

Grouping levels tried in order of specificity:
  exact_line     — opponent's first four moves as an ordered sequence
  play_signature — canonical 8-ply board FEN (collapses transpositions)

If neither level produces a cluster with N >= 5, an empty list is returned
and the caller falls back to the existing opening_family rollup.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from chess_tracker.pgn import GameRecord
from chess_tracker.opening_match import _split_plies

_DRAW_RESULTS = frozenset({
    "agreed", "repetition", "stalemate", "insufficient",
    "50move", "timevsinsufficient",
})


def _is_win(result: str) -> bool:
    return result == "win"


def _is_draw(result: str) -> bool:
    return result in _DRAW_RESULTS


def _is_loss(result: str) -> bool:
    return not _is_win(result) and not _is_draw(result)


def _confidence(n: int) -> str | None:
    """Confidence label for a cluster of size n; None means hidden (N < 3)."""
    if n < 3:
        return None
    if n < 5:
        return "weak"
    if n < 10:
        return "medium"
    return "strong"


def extract_opp_moves(
    opening_moves: str | None, my_side: str
) -> tuple[list[str] | None, str]:
    """Extract the opponent's first (up to 4) normalized SAN moves.

    Returns (moves, skip_reason).  skip_reason is "" on success, or one of:
      "null_opening" — opening_moves is None/empty
      "too_short"    — fewer than 2 opponent moves available

    Reuses _split_plies from opening_match so normalization is consistent
    (move numbers stripped, captures/checks normalized, castling kept).
    """
    if not opening_moves:
        return None, "null_opening"
    white_moves, black_moves = _split_plies(opening_moves, window=None)
    opp = white_moves if my_side == "black" else black_moves
    opp = opp[:4]
    if len(opp) < 2:
        return None, "too_short"
    return opp, ""


def _group_stats(
    entries: list[dict],
    opp_side: str,
    opp_moves: list[str],
    opp_line: str,
    grouping_level: str,
) -> dict:
    n = len(entries)
    wins = sum(1 for e in entries if _is_win(e["result"]))
    draws = sum(1 for e in entries if _is_draw(e["result"]))
    losses = n - wins - draws
    return {
        "opponent_side": opp_side,
        "opp_moves": opp_moves,
        "opp_line": opp_line,
        "opp_move_count": len(opp_moves),
        "game_count": n,
        "win_count": wins,
        "draw_count": draws,
        "loss_count": losses,
        "loss_pct": round(100.0 * losses / n, 1) if n else 0.0,
        "confidence": _confidence(n),
        "grouping_level": grouping_level,
    }


def _sort_rows(rows: list[dict]) -> list[dict]:
    _conf_rank = {"strong": 3, "medium": 2, "weak": 1, None: 0}
    return sorted(rows, key=lambda r: (
        -r["loss_count"],
        -_conf_rank.get(r["confidence"], 0),
        -r["loss_pct"],
        -r["game_count"],
    ))


def _has_medium_plus(rows: list[dict]) -> bool:
    return any(r["confidence"] in ("medium", "strong") for r in rows)


def _build_exact_rows(groups: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for _key, entries in groups.items():
        e0 = entries[0]
        opp_side = e0["opp_side"]
        opp_moves = e0["opp_moves"] or []
        side_label = "White" if opp_side == "white" else "Black"
        opp_line = f"{side_label}: {' '.join(opp_moves)}"
        rows.append(_group_stats(entries, opp_side, opp_moves, opp_line, "exact_line"))
    return rows


def _build_sig_rows(groups: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for _key, entries in groups.items():
        e0 = entries[0]
        opp_side = e0["opp_side"]
        family_ctr = Counter(e["family"] for e in entries if e["family"])
        label = family_ctr.most_common(1)[0][0] if family_ctr else "Unknown"
        moves_ctr = Counter(
            tuple(e["opp_moves"]) for e in entries if e["opp_moves"]
        )
        rep_moves = list(moves_ctr.most_common(1)[0][0]) if moves_ctr else []
        side_label = "White" if opp_side == "white" else "Black"
        opp_line = f"{side_label}: {label}"
        rows.append(
            _group_stats(entries, opp_side, rep_moves, opp_line, "play_signature")
        )
    return rows


def compute_opponent_opening_stats(records: list[GameRecord]) -> dict:
    """Group all games by the opponent's first four opening moves.

    Returns {"rows": [...], "audit": {...}, "grouping_level": str}.
    rows is empty when no level meets the N >= 5 threshold.
    """
    audit: dict[str, int] = {
        "total_groups_before_filter": 0,
        "groups_hidden_low_sample": 0,
        "groups_shown": 0,
        "games_excluded_null_opening": 0,
        "games_excluded_too_short": 0,
    }
    if not records:
        return {"rows": [], "audit": audit, "grouping_level": "none"}

    exact_groups: dict[str, list[dict]] = defaultdict(list)
    sig_groups: dict[str, list[dict]] = defaultdict(list)

    for r in records:
        opp_side = "white" if r.side == "black" else "black"
        opp_moves, skip_reason = extract_opp_moves(r.opening_moves, r.side)

        if skip_reason == "null_opening":
            audit["games_excluded_null_opening"] += 1
            continue
        if skip_reason == "too_short":
            audit["games_excluded_too_short"] += 1
            continue

        entry = {
            "opp_side": opp_side,
            "opp_moves": opp_moves,
            "result": r.result,
            "family": r.family,
        }
        exact_key = f"{opp_side}:{' '.join(opp_moves)}"
        exact_groups[exact_key].append(entry)

        if r.play_signature:
            sig_key = f"{opp_side}:{r.play_signature}"
            sig_groups[sig_key].append(entry)

    # Select most specific level with at least one medium-or-strong cluster.
    exact_rows = _build_exact_rows(exact_groups)
    if _has_medium_plus(exact_rows):
        all_rows = exact_rows
        grouping_level = "exact_line"
    else:
        sig_rows = _build_sig_rows(sig_groups)
        if _has_medium_plus(sig_rows):
            all_rows = sig_rows
            grouping_level = "play_signature"
        else:
            # Kill criterion: both levels too sparse; caller falls back to
            # the existing opening_family rollup.
            return {"rows": [], "audit": audit, "grouping_level": "none"}

    visible = [r for r in all_rows if r["confidence"] is not None]
    hidden = [r for r in all_rows if r["confidence"] is None]

    audit["total_groups_before_filter"] = len(all_rows)
    audit["groups_hidden_low_sample"] = len(hidden)
    audit["groups_shown"] = len(visible)

    return {
        "rows": _sort_rows(visible),
        "audit": audit,
        "grouping_level": grouping_level,
    }
