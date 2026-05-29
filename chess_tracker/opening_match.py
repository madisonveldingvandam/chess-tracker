"""Move-pattern opening matcher.

ECO family labels can't separate close cousins like the London (early Bf4)
from the Colle-Zukertort (e3 + b3/Bb2, bishop stays home). This classifies a
game from its early SAN moves instead. Pure functions, no chess engine.

A `match` rule (from plan.json) may carry:
  applicable_if_black_plays: SAN of Black's first move that must occur for the
                             plan to be reachable at all (e.g. "e5").
  white_requires:     all of these White moves must be present.
  white_requires_any: a list of groups; at least one group must be fully present.
  white_forbids:      none of these White moves may be present.
  gambit_flags:       {name: [moves]} — name is reported when all its moves
                      are present (sub-tags within an on-plan game).
  window_plies:       only consider the first N plies (default: all).
"""


def _norm(tok: str) -> str:
    """Normalize a SAN token for set comparison.

    Strips a leading move-number prefix ("4.Nxe5" -> "Nxe5"), capture/check/
    mate marks, and promotion suffix, so "Bxb2" matches "Bb2" and "Nd5+"
    matches "Nd5".
    """
    tok = tok.lstrip("0123456789.")
    tok = tok.replace("x", "").replace("+", "").replace("#", "")
    return tok.split("=")[0]


def _split_plies(opening_moves: str | None, window: int | None):
    """Return (white_tokens, black_tokens) as normalized SAN, truncated to
    `window` plies if given. Token index 0 is White's move 1, index 1 Black's."""
    if not opening_moves:
        return [], []
    toks = opening_moves.split()
    if window is not None:
        toks = toks[:window]
    white = [_norm(t) for i, t in enumerate(toks) if i % 2 == 0]
    black = [_norm(t) for i, t in enumerate(toks) if i % 2 == 1]
    return white, black


def match_opening(opening_moves: str | None, rule: dict) -> dict:
    """Classify a game against a move-pattern rule.

    Returns {"applicable": bool, "on_plan": bool, "flags": [str, ...]}.
    `applicable` reflects only the black-reply guard; the caller is expected
    to have already filtered by side and White's first move.
    """
    window = rule.get("window_plies")
    white, black = _split_plies(opening_moves, window)
    wset = set(white)

    guard = rule.get("applicable_if_black_plays")
    if guard is not None:
        applicable = bool(black) and black[0] == _norm(guard)
    else:
        applicable = True

    on_plan = applicable
    if on_plan and rule.get("white_requires"):
        on_plan = all(_norm(t) in wset for t in rule["white_requires"])
    if on_plan and rule.get("white_requires_any"):
        on_plan = any(
            all(_norm(t) in wset for t in group)
            for group in rule["white_requires_any"]
        )
    if on_plan and rule.get("white_forbids"):
        on_plan = not any(_norm(t) in wset for t in rule["white_forbids"])

    flags = []
    for name, toks in rule.get("gambit_flags", {}).items():
        if all(_norm(t) in wset for t in toks):
            flags.append(name)

    return {"applicable": applicable, "on_plan": on_plan, "flags": flags}
