"""Training prescription derivation.

Assembles one clear next-session action from available signals:
  blunder_phases  → when the blunder happened (opening vs early middlegame)
  loss_type       → clock vs mate-defense vs material work
  engine_coverage → whether phase data meets minimum thresholds

Spec rules:
  - Minimum threshold to show engine-derived prescription:
      engine_coverage.analyzed_games >= 20
      phase user_move_count >= 50
      blunder_count >= 3
  - If threshold unmet: fall back to loss_type only
  - Phase tie-break: blunder_rate desc → affected_games desc →
      avg_loss_cp desc → early_middlegame before opening if still tied
  - One prescription, no filler
"""
from __future__ import annotations

from chess_tracker.pgn import GameRecord

_DRAW_RESULTS = frozenset({
    "agreed", "repetition", "stalemate", "insufficient",
    "50move", "timevsinsufficient",
})

_LOSS_TYPE_MAP = {
    "timeout": "Use a clock rule this session: no move longer than X seconds before move 20.",
    "checkmated": "Do basic mate-in-1, mate-in-2, and back-rank recognition before playing.",
    "resignation": "Review 2 recent resignation losses before playing; identify the first material drop.",
}

_PHASE_LABELS = {
    "opening": "Opening blunders",
    "early_middlegame": "Early middlegame blunders",
}

_MIN_ANALYZED = 20
_MIN_MOVE_COUNT = 50
_MIN_BLUNDERS = 3


def _dominant_loss_type(records: list[GameRecord]) -> str | None:
    """Most common loss type over the last 30 games, or None if unclear."""
    ordered = sorted(records, key=lambda r: r.end_time)
    window = ordered[-30:]
    losses = [r for r in window
              if r.result not in _DRAW_RESULTS and r.result != "win"]
    if not losses:
        return None
    counts: dict[str, int] = {}
    for r in losses:
        lt = r.result
        counts[lt] = counts.get(lt, 0) + 1
    dominant = max(counts, key=lambda k: counts[k])
    if counts[dominant] / len(losses) >= 0.4:
        return dominant
    return None


def _phase_tiebreak_key(phase_data: dict) -> tuple:
    """Larger = higher priority phase to address."""
    return (
        phase_data.get("blunder_rate", 0),
        phase_data.get("affected_games", 0),
        phase_data.get("avg_loss_cp") or 0,
    )


def _pick_phase(blunder_phases: dict) -> str | None:
    """Return spec phase name ('opening' | 'early_middlegame') with most blunders.

    Returns None if neither phase meets the minimum threshold.
    """
    candidates = []
    for phase_name, pd in blunder_phases.items():
        mc = pd.get("user_move_count", 0)
        bc = pd.get("blunder_count", 0)
        if mc >= _MIN_MOVE_COUNT and bc >= _MIN_BLUNDERS:
            candidates.append((phase_name, pd))

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0][0]

    # Tie-break: blunder_rate → affected_games → avg_loss_cp → prefer early_middlegame
    def _key(item):
        name, pd = item
        return _phase_tiebreak_key(pd) + (1 if name == "early_middlegame" else 0,)

    return max(candidates, key=_key)[0]


def compute_training_prescription(
    blunder_phases: dict | None,
    engine_coverage: dict | None,
    records: list[GameRecord],
) -> dict | None:
    """Return training_prescription dict, or None if no signal is clear enough.

    Frontend renders exactly what the backend returns — no frontend reasoning.
    """
    coverage = engine_coverage or {}
    analyzed = coverage.get("analyzed_games", 0)
    eligible = coverage.get("eligible_games", 0)

    phases = blunder_phases or {}
    phase_name = None

    if analyzed >= _MIN_ANALYZED:
        phase_name = _pick_phase(phases)

    if phase_name is not None:
        pd = phases[phase_name]
        bc = pd["blunder_count"]
        ag = pd["affected_games"]
        br = pd.get("blunder_rate", 0)
        label = _PHASE_LABELS[phase_name]

        do_steps = ["10 basic tactics"]
        avg_cp = pd.get("avg_loss_cp")
        if avg_cp and avg_cp >= 150:
            do_steps.append("5 hanging-piece checks")
        do_steps.append(f"2 personal-loss puzzles from {phase_name.replace('_', ' ')} positions")

        return {
            "title": label,
            "why": (
                f"{bc} blunder{'s' if bc != 1 else ''} across {ag} game{'s' if ag != 1 else ''}; "
                f"{round(br * 100, 1)}% of analyzed user moves."
            ),
            "do": do_steps,
            "avoid": "Do not start a long blitz session before completing the prep.",
            "confidence": (
                "strong" if analyzed >= 50 and bc >= 10 else
                "medium" if analyzed >= 20 and bc >= 3 else
                "weak"
            ),
            "source": ["blunder_phases", "engine_coverage"],
        }

    # Fallback to loss-type prescription
    loss_type = _dominant_loss_type(records)
    if loss_type and loss_type in _LOSS_TYPE_MAP:
        ordered = sorted(records, key=lambda r: r.end_time)
        window = sorted(ordered[-30:], key=lambda r: r.end_time)
        losses = [r for r in window
                  if r.result not in _DRAW_RESULTS and r.result != "win"]
        lt_count = sum(1 for r in losses if r.result == loss_type)
        label_map = {"timeout": "Clock losses", "checkmated": "Checkmate losses",
                     "resignation": "Resignation losses"}
        return {
            "title": label_map.get(loss_type, "Loss pattern"),
            "why": (
                f"{lt_count} of last {len(losses)} losses were {loss_type}. "
                f"Engine analysis {'not yet available' if analyzed == 0 else f'covers {analyzed} of {eligible} games'}."
            ),
            "do": [_LOSS_TYPE_MAP[loss_type]],
            "avoid": None,
            "confidence": "weak",
            "source": ["loss_type"],
        }

    return None
