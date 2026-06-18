"""Named opening trap/system detection.

Scans each game's SAN move list for known attacking patterns the opponent
used against the user.  Detection is a side-aware ordered-subsequence match
against the opponent's moves — intervening moves are allowed.

V1 library: 7 patterns (Scholar's Mate, Fried Liver, Fool's Mate,
Halloween Gambit, Belgrade Gambit, Budapest Gambit, Englund Gambit).

V2 deferred (require board-state): Legal's Trap, Elephant Trap,
Noah's Ark Trap, Back-Rank Mate, Smothered Mate, Opera Mate.
"""
from __future__ import annotations

from chess_tracker.pgn import GameRecord
from chess_tracker.opening_match import _split_plies, _norm

_DRAW_RESULTS = frozenset({
    "agreed", "repetition", "stalemate", "insufficient",
    "50move", "timevsinsufficient",
})

# Deferred-to-V2 count shown in audit.
_PATTERNS_DEFERRED = 6  # Legal, Elephant, Noah's Ark + 3 board-state V2


def _is_subseq(pattern: list[str], moves: list[str]) -> bool:
    """True if every element of pattern appears in moves in order."""
    pi = 0
    for m in moves:
        if pi < len(pattern) and m == pattern[pi]:
            pi += 1
        if pi == len(pattern):
            return True
    return pi == len(pattern)


# Pattern schema:
#   id, name, target_user_side, signature (opponent moves, normalized)
#   alt_signatures: list of alternative signatures — fires if ANY matches
#   requires_result: "win"|"loss"|None — extra filter on user result
_PATTERNS: list[dict] = [
    {
        "id": "scholars_mate",
        "name": "Scholar's Mate",
        "target_user_side": "black",
        # White: e4 Bc4 Qh5 Qxf7#
        "signature": ["Bc4", "Qh5", "Qf7"],
    },
    {
        "id": "fried_liver_attack",
        "name": "Fried Liver Attack",
        "target_user_side": "black",
        # White: e4 Nf3 Bc4 Ng5 exd5 Nxf7
        "signature": ["Nf3", "Bc4", "Ng5", "Nf7"],
    },
    {
        "id": "fools_mate",
        "name": "Fool's Mate",
        "target_user_side": "black",
        # White: f3/f4 then g4; user wins
        "alt_signatures": [["f3", "g4"], ["f4", "g4"]],
        "requires_result": "win",
    },
    {
        "id": "halloween_gambit",
        "name": "Halloween Gambit",
        "target_user_side": "black",
        # White: e4 Nf3 Nc3 Nxe5
        "signature": ["e4", "Nf3", "Nc3", "Ne5"],
    },
    {
        "id": "belgrade_gambit",
        "name": "Belgrade Gambit",
        "target_user_side": "black",
        # White: e4 Nf3 Nc3 d4 Nd5
        "signature": ["Nf3", "Nc3", "d4", "Nd5"],
    },
    {
        "id": "budapest_gambit",
        "name": "Budapest Gambit",
        "target_user_side": "white",
        # Black: e5 Ne4 (Fajarowicz) or Nf6 e5 Ng4 — only after user plays d4
        "alt_signatures": [["e5", "Ne4"], ["Nf6", "e5", "Ng4"]],
        "requires_user_first_move": "d4",
    },
    {
        "id": "englund_gambit",
        "name": "Englund Gambit",
        "target_user_side": "white",
        # Black: e5 Nc6 (counters 1.d4) — Black must play e5 as literal first move
        "signature": ["e5", "Nc6"],
        "requires_user_first_move": "d4",
        "requires_opp_first_move": "e5",
    },
]


def _norm_seq(tokens: list[str]) -> list[str]:
    return [_norm(t) for t in tokens]


def detect_traps(opening_moves: str | None, my_side: str, result: str) -> list[str]:
    """Return list of pattern IDs that fired for this game (one hit max per ID).

    ``opening_moves`` is the SAN string from GameRecord.  ``result`` is the
    user's result string ("win", "timeout", "checkmated", etc.).
    """
    if not opening_moves:
        return []
    white_norm, black_norm = _split_plies(opening_moves, window=None)
    opp_moves = white_norm if my_side == "black" else black_norm
    my_moves = black_norm if my_side == "black" else white_norm

    hits: list[str] = []
    for p in _PATTERNS:
        if p["target_user_side"] != my_side:
            continue

        req_res = p.get("requires_result")
        if req_res == "win" and result != "win":
            continue
        if req_res == "loss" and result in _DRAW_RESULTS | {"win"}:
            continue

        # Guard: user's first move must match (prevents cross-opening false positives)
        req_my_first = p.get("requires_user_first_move")
        if req_my_first and (_norm(req_my_first) not in my_moves[:1]):
            continue

        # Guard: opponent's first move must match (distinguishes e.g. Englund from KID)
        req_opp_first = p.get("requires_opp_first_move")
        if req_opp_first and (_norm(req_opp_first) not in opp_moves[:1]):
            continue

        sigs = p.get("alt_signatures") or [p.get("signature", [])]
        for raw_sig in sigs:
            sig = _norm_seq(raw_sig)
            if _is_subseq(sig, opp_moves):
                hits.append(p["id"])
                break  # one hit per pattern per game

    return hits


def _confidence(n: int) -> str | None:
    if n < 3:
        return None
    if n < 5:
        return "weak"
    if n < 10:
        return "medium"
    return "strong"


def compute_trap_exposures(records: list[GameRecord]) -> dict:
    """Scan all records for named trap/system exposure.

    Returns {"trap_exposures": [...], "trap_exposure_audit": {...}}.
    Only patterns with N >= 3 appear in trap_exposures.
    """
    counters: dict[str, dict] = {
        p["id"]: {"name": p["name"], "wins": 0, "draws": 0, "losses": 0}
        for p in _PATTERNS
    }

    games_scanned = 0
    for r in records:
        games_scanned += 1
        hits = detect_traps(r.opening_moves, r.side, r.result)
        for pid in hits:
            if pid not in counters:
                continue
            if r.result == "win":
                counters[pid]["wins"] += 1
            elif r.result in _DRAW_RESULTS:
                counters[pid]["draws"] += 1
            else:
                counters[pid]["losses"] += 1

    rows = []
    hits_before_filter = 0
    for pid, c in counters.items():
        hit = c["wins"] + c["draws"] + c["losses"]
        if hit == 0:
            continue
        hits_before_filter += hit
        conf = _confidence(hit)
        if conf is None:
            continue
        rows.append({
            "id": pid,
            "name": c["name"],
            "hit_count": hit,
            "win_count": c["wins"],
            "draw_count": c["draws"],
            "loss_count": c["losses"],
            "loss_pct": round(100.0 * c["losses"] / hit, 1) if hit else 0.0,
            "confidence": conf,
        })

    rows.sort(key=lambda r: (
        -r["loss_count"],
        -{"strong": 3, "medium": 2, "weak": 1}.get(r["confidence"], 0),
        -r["loss_pct"],
        -r["hit_count"],
        r["name"],
    ))

    return {
        "trap_exposures": rows,
        "trap_exposure_audit": {
            "games_scanned": games_scanned,
            "hits_before_filter": hits_before_filter,
            "patterns_deferred": _PATTERNS_DEFERRED,
        },
    }
