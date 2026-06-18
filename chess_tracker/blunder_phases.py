"""Blunder phase analysis.

Aggregates per-game move-quality summaries (from the Stockfish quality cache)
into the blunder_phases + engine_coverage objects for computed.json.

Phase mapping from existing analysis.py labels:
  "opening"    (fullmove <= 8)  →  spec "opening"         (plies 0-15)
  "middlegame" (fullmove > 8)   →  spec "early_middlegame" (plies 16-39)
  "endgame"                     →  excluded from both spec phases

Returns empty structs when no summaries are available (graceful degradation).
"""
from __future__ import annotations

_PHASE_MAP = {
    "opening": "opening",
    "middlegame": "early_middlegame",
}

_EMPTY_PHASE = {
    "user_move_count": 0,
    "blunder_count": 0,
    "blunder_rate": 0.0,
    "affected_games": 0,
    "phase_eligible_games": 0,
    "affected_game_pct": 0.0,
    "avg_loss_cp": None,
    "worst_single_loss_cp": None,
}


def compute_blunder_phases(summaries: list[dict], total_eligible: int) -> dict:
    """Aggregate per-game summaries into blunder phase stats.

    ``summaries``      — list of per-game summary dicts from the quality cache
                         (each entry is cache[url]["summary"]).
    ``total_eligible`` — total games that could have been analyzed (for
                         engine_coverage.eligible_games).

    Returns {"blunder_phases": {...}, "engine_coverage": {...}}.
    Returns empty structs if summaries is empty.
    """
    if not summaries:
        return {
            "blunder_phases": {
                "opening": dict(_EMPTY_PHASE),
                "early_middlegame": dict(_EMPTY_PHASE),
            },
            "engine_coverage": {
                "analyzed_games": 0,
                "eligible_games": total_eligible,
            },
        }

    # Accumulators keyed by spec phase name
    move_count: dict[str, int] = {"opening": 0, "early_middlegame": 0}
    blunder_count: dict[str, int] = {"opening": 0, "early_middlegame": 0}
    affected_games: dict[str, int] = {"opening": 0, "early_middlegame": 0}
    eligible_games: dict[str, int] = {"opening": 0, "early_middlegame": 0}
    cp_sum: dict[str, int] = {"opening": 0, "early_middlegame": 0}
    cp_worst: dict[str, int] = {"opening": 0, "early_middlegame": 0}

    for s in summaries:
        mbp = s.get("moves_by_phase", {})
        bbp = s.get("blunders_by_phase", {})
        cs = s.get("blunder_cp_sum_by_phase", {})
        cw = s.get("blunder_worst_cp_by_phase", {})

        for src_phase, spec_phase in _PHASE_MAP.items():
            moves_in_phase = mbp.get(src_phase, 0)
            if moves_in_phase == 0:
                continue
            eligible_games[spec_phase] += 1
            move_count[spec_phase] += moves_in_phase

            b = bbp.get(src_phase, 0)
            blunder_count[spec_phase] += b
            if b > 0:
                affected_games[spec_phase] += 1
                cp_sum[spec_phase] += cs.get(src_phase, 0)
                cp_worst[spec_phase] = max(cp_worst[spec_phase],
                                           cw.get(src_phase, 0))

    def _phase_row(spec_phase: str) -> dict:
        mc = move_count[spec_phase]
        bc = blunder_count[spec_phase]
        ag = affected_games[spec_phase]
        eg = eligible_games[spec_phase]
        return {
            "user_move_count": mc,
            "blunder_count": bc,
            "blunder_rate": round(bc / mc, 4) if mc else 0.0,
            "affected_games": ag,
            "phase_eligible_games": eg,
            "affected_game_pct": round(100.0 * ag / eg, 1) if eg else 0.0,
            "avg_loss_cp": round(cp_sum[spec_phase] / bc) if bc else None,
            "worst_single_loss_cp": cp_worst[spec_phase] if bc else None,
        }

    return {
        "blunder_phases": {
            "opening": _phase_row("opening"),
            "early_middlegame": _phase_row("early_middlegame"),
        },
        "engine_coverage": {
            "analyzed_games": len(summaries),
            "eligible_games": total_eligible,
        },
    }
