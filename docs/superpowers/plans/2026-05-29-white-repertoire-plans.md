# White Repertoire Plans + Adherence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track adherence to the user's aspirational White repertoire — Colle–Zukertort (vs the London they currently play) and Four Knights with Halloween/Belgrade gambit branches — using move-pattern detection, because ECO family labels can't separate these systems.

**Architecture:** A pure move-pattern matcher (`opening_match.py`) classifies a game from its early SAN. `compute_plan_compliance` branches on whether a `plan.json` entry carries a `match` block (move-pattern) or not (existing exact-family path, unchanged). A new best-effort 12-ply `opening_moves` field on `GameRecord` feeds the matcher so the late b3/Bb2 fianchetto is visible. The dashboard groups plan cards by side and shows a gambit breakdown.

**Tech Stack:** Python 3.12, `python-chess`, `uv`, `pytest`. Static JS dashboard (`dashboard/app.js`).

**Spec:** `docs/superpowers/specs/2026-05-29-white-repertoire-plans-design.md`

**Branch:** `white-repertoire-plans` (already created).

---

## File Structure

- **Create** `chess_tracker/opening_match.py` — pure move-pattern matcher. Responsibility: given an opening SAN string + a `match` rule, decide applicability, on-plan, and gambit flags. No I/O, no chess engine.
- **Create** `tests/test_opening_match.py` — matcher unit tests.
- **Modify** `chess_tracker/play_signature.py` — add `opening_moves_san` (best-effort variant of `first_moves_san`).
- **Modify** `chess_tracker/pgn.py` — add `opening_moves` field + populate in `parse_game`.
- **Modify** `chess_tracker/metrics.py` — branch `compute_plan_compliance` on `match`.
- **Modify** `chess_tracker/plan.json` — add two White entries.
- **Modify** `dashboard/app.js` — side-grouped cards + gambit breakdown.
- **Modify** `tests/test_play_signature.py`, `tests/test_pgn.py`, `tests/test_metrics.py` — tests for the above.

All commands run from `/Users/madisonvelding-vandam/Developer/chess-tracker`. Tests run with `uv run pytest`.

---

### Task 1: Best-effort 12-ply SAN helper

**Files:**
- Modify: `chess_tracker/play_signature.py`
- Test: `tests/test_play_signature.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_play_signature.py`:

```python
# --- opening_moves_san (best-effort, up to N plies) -------------------------
from chess_tracker.play_signature import opening_moves_san


def test_opening_moves_san_returns_up_to_12_plies():
    pgn = ('[Event "x"]\n\n1. d4 d5 2. Nf3 Nf6 3. e3 e6 4. Bd3 c5 '
           '5. b3 Nc6 6. Bb2 Bd6 7. O-O O-O 1-0')
    assert opening_moves_san(_parse(pgn)) == (
        "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6")


def test_opening_moves_san_best_effort_for_short_game():
    # Only 6 plies — returns what exists rather than None.
    pgn = '[Event "x"]\n\n1. e4 e5 2. Nf3 Nc6 3. Nc3 Nf6 1-0'
    assert opening_moves_san(_parse(pgn)) == "1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6"


def test_opening_moves_san_returns_none_for_empty():
    assert opening_moves_san(None) is None
```

Note: `_parse` is the helper already defined in this test file (it wraps `chess.pgn.read_game(StringIO(pgn))`). Confirm it exists near the top before running; if its name differs, use the file's existing PGN-parse helper.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_play_signature.py -k opening_moves_san -v`
Expected: FAIL — `ImportError: cannot import name 'opening_moves_san'`.

- [ ] **Step 3: Write minimal implementation**

In `chess_tracker/play_signature.py`, add after `first_moves_san`:

```python
def opening_moves_san(game: chess.pgn.Game | None, count: int = 12) -> str | None:
    """Like first_moves_san, but best-effort: return as many of the first
    `count` plies as the game actually has (instead of None when shorter).

    Used by the move-pattern opening matcher, which needs to see the b3/Bb2
    fianchetto that lands around plies 9-11 — just past the 8-ply window.
    Returns None only for a missing game or a game with zero moves.
    """
    if game is None:
        return None
    board = game.board()
    tokens: list[str] = []
    plies = 0
    for move in game.mainline_moves():
        if plies >= count:
            break
        san = board.san(move)
        if plies % 2 == 0:
            tokens.append(f"{plies // 2 + 1}.{san}")
        else:
            tokens.append(san)
        board.push(move)
        plies += 1
    return " ".join(tokens) if tokens else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_play_signature.py -k opening_moves_san -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/play_signature.py tests/test_play_signature.py
git commit -m "feat(play_signature): best-effort opening_moves_san (up to 12 plies)"
```

---

### Task 2: `opening_moves` field on GameRecord

**Files:**
- Modify: `chess_tracker/pgn.py` (GameRecord fields ~line 32-34; imports ~line 6-8; parse_game return ~line 162-167)
- Test: `tests/test_pgn.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pgn.py`. The file already imports `parse_game` (line 4) and other tests build a Chess.com game dict inline (see `test_parse_game_extracts_time_control_and_rated`, line 138). Mirror that exactly:

```python
def test_parse_game_populates_opening_moves_12_plies():
    g = {
        "url": "https://chess.com/game/1",
        "end_time": 1_700_000_000,
        "time_class": "bullet",
        "time_control": "60",
        "rated": True,
        "white": {"username": "me", "rating": 500, "result": "win"},
        "black": {"username": "opp", "rating": 500, "result": "checkmated"},
        "pgn": '[ECO "D05"]\n1. d4 d5 2. Nf3 Nf6 3. e3 e6 4. Bd3 c5 '
               '5. b3 Nc6 6. Bb2 Bd6 7. O-O O-O *',
    }
    rec = parse_game(g, username="me")
    # opening_moves carries 12 plies (past the 8-ply first_moves)
    assert rec.opening_moves == (
        "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6")
    # first_moves stays 8 plies, unchanged
    assert rec.first_moves == "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pgn.py -k opening_moves -v`
Expected: FAIL — `AttributeError: 'GameRecord' object has no attribute 'opening_moves'`.

- [ ] **Step 3: Write minimal implementation**

In `chess_tracker/pgn.py`:

(a) Extend the import block (~line 6-8):

```python
from chess_tracker.play_signature import (
    play_signature as _compute_play_signature,
    first_moves_san as _compute_first_moves_san,
    opening_moves_san as _compute_opening_moves_san,
)
```

(b) Add the field right after `first_moves` in the `GameRecord` dataclass (~line 33):

```python
    first_moves: str | None = None     # SAN of first 8 plies, e.g. "1.d4 d5 …"
    opening_moves: str | None = None   # SAN of up to 12 plies; feeds the move-pattern matcher
```

(c) In the `parse_game` return (~line 166), add the field right after `first_moves=...`:

```python
        first_moves=_compute_first_moves_san(game_tree),
        opening_moves=_compute_opening_moves_san(game_tree),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pgn.py -k opening_moves -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/pgn.py tests/test_pgn.py
git commit -m "feat(pgn): add 12-ply opening_moves field to GameRecord"
```

---

### Task 3: Move-pattern matcher module

**Files:**
- Create: `chess_tracker/opening_match.py`
- Test: `tests/test_opening_match.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_opening_match.py`:

```python
from chess_tracker.opening_match import match_opening

CZ_RULE = {
    "white_requires_any": [["e3", "b3"], ["e3", "Bb2"]],
    "white_forbids": ["Bf4"],
    "window_plies": 12,
}
FK_RULE = {
    "applicable_if_black_plays": "e5",
    "white_requires": ["Nf3", "Nc3"],
    "gambit_flags": {"Halloween": ["Nxe5"], "Belgrade": ["Nd5"]},
    "window_plies": 8,
}


def test_colle_zukertort_is_on_plan():
    m = match_opening(
        "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6", CZ_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True


def test_london_via_bf4_is_deviated():
    # Bf4 played early -> forbidden -> NOT the Colle, even though e3 appears.
    m = match_opening(
        "1.d4 d5 2.Nf3 Nf6 3.Bf4 e6 4.e3 Bd6 5.Bd3 O-O 6.O-O c5", CZ_RULE)
    assert m["applicable"] is True   # all d4 games are applicable to CZ
    assert m["on_plan"] is False


def test_four_knights_is_on_plan_no_flags():
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Bb5 Bb4", FK_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True
    assert m["flags"] == []


def test_halloween_gambit_flagged():
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Nxe5 Nxe5", FK_RULE)
    assert m["on_plan"] is True
    assert m["flags"] == ["Halloween"]


def test_belgrade_gambit_flagged():
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.d4 exd4 5.Nd5 Nxd5", FK_RULE)
    assert m["on_plan"] is True
    assert m["flags"] == ["Belgrade"]


def test_scotch_is_deviated():
    # 1.e4 e5 with d4 push but NO Nc3 -> fails white_requires.
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.Nxd4 Nf6", FK_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is False


def test_e4_vs_non_e5_is_not_applicable():
    # Scandinavian: black does NOT play ...e5 -> Four Knights impossible.
    m = match_opening("1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5 4.d4 Nf6", FK_RULE)
    assert m["applicable"] is False


def test_token_normalization_capture_and_check():
    # Bxb2 satisfies a "Bb2" requirement; Nd5+ satisfies "Nd5".
    rule = {"white_requires": ["Bb2", "Nd5"], "window_plies": 12}
    m = match_opening("1.d4 Nf6 2.Bb2 e6 3.Nd5+ Be7 4.Bxb2 d5", rule)
    # (contrived line — just exercising normalization on white moves)
    assert m["on_plan"] is True


def test_empty_moves_not_on_plan():
    m = match_opening(None, CZ_RULE)
    assert m["on_plan"] is False
    m2 = match_opening(None, FK_RULE)
    assert m2["applicable"] is False  # can't confirm black ...e5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_opening_match.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chess_tracker.opening_match'`.

- [ ] **Step 3: Write minimal implementation**

Create `chess_tracker/opening_match.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_opening_match.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/opening_match.py tests/test_opening_match.py
git commit -m "feat(opening_match): move-pattern matcher for London/Colle + Four Knights"
```

---

### Task 4: Wire matcher into `compute_plan_compliance`

**Files:**
- Modify: `chess_tracker/metrics.py:698-770` (`compute_plan_compliance`)
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_metrics.py`:

```python
def test_compute_plan_compliance_move_pattern_white_entry():
    """A `match` entry classifies by moves: Colle-Zukertort on-plan, London
    (via Bf4) deviated, even though both can carry a 'Queens Pawn' family."""
    from chess_tracker.metrics import compute_plan_compliance
    from chess_tracker.pgn import GameRecord

    def _w(opening_moves, result, et):
        return GameRecord(
            url="x", end_time=et, time_class="bullet", side="white",
            my_rating=500, opp_rating=500, result=result,
            opp_result="checkmated", plies=24, fullmoves=12,
            opening="Queens Pawn Opening", eco="D02",
            first_moves=" ".join(opening_moves.split()[:8]),
            opening_moves=opening_moves,
        )

    cz = "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6"
    london = "1.d4 d5 2.Nf3 Nf6 3.Bf4 e6 4.e3 Bd6 5.Bd3 O-O 6.O-O c5"
    recs = (
        [_w(cz, "win", 1_700_000_000 + i) for i in range(3)] +      # 3 on-plan
        [_w(london, "win", 1_700_000_100 + i) for i in range(2)]    # 2 deviated
    )
    plan = {"openings": [{
        "name": "Colle-Zukertort System", "side": "white", "vs_first_move": "d4",
        "target_family": "Colle Zukertort System",
        "moves": cz, "plan": "...",
        "match": {"white_requires_any": [["e3", "b3"], ["e3", "Bb2"]],
                  "white_forbids": ["Bf4"], "window_plies": 12},
    }]}
    out = compute_plan_compliance(recs, plan, window=30)
    o = out["openings"][0]
    assert o["applicable_games"] == 5
    assert o["games_on_plan"] == 3
    assert o["adherence_pct"] == 60.0
    assert o["severity"] == "green"


def test_compute_plan_compliance_gambit_breakdown():
    """Four Knights entry tallies gambit flags and ignores non-...e5 games."""
    from chess_tracker.metrics import compute_plan_compliance
    from chess_tracker.pgn import GameRecord

    def _w(opening_moves, et):
        return GameRecord(
            url="x", end_time=et, time_class="bullet", side="white",
            my_rating=500, opp_rating=500, result="win",
            opp_result="checkmated", plies=20, fullmoves=10,
            opening="Four Knights Game", eco="C47",
            first_moves=" ".join(opening_moves.split()[:8]),
            opening_moves=opening_moves,
        )

    recs = [
        _w("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Nxe5 Nxe5", 1_700_000_000),   # Halloween
        _w("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.d4 exd4 5.Nd5 Nxd5", 1_700_000_001),  # Belgrade
        _w("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Bb5 Bb4", 1_700_000_002),     # plain FK
        _w("1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5 4.d4 Nf6", 1_700_000_003),    # Scandinavian: N/A
    ]
    plan = {"openings": [{
        "name": "Four Knights", "side": "white", "vs_first_move": "e4",
        "target_family": "Four Knights Game", "moves": "...", "plan": "...",
        "match": {"applicable_if_black_plays": "e5",
                  "white_requires": ["Nf3", "Nc3"],
                  "gambit_flags": {"Halloween": ["Nxe5"], "Belgrade": ["Nd5"]},
                  "window_plies": 8},
    }]}
    out = compute_plan_compliance(recs, plan, window=30)
    o = out["openings"][0]
    assert o["applicable_games"] == 3          # Scandinavian excluded
    assert o["games_on_plan"] == 3
    assert o["gambit_breakdown"] == {"Halloween": 1, "Belgrade": 1}


def test_compute_plan_compliance_family_entry_unchanged_has_no_breakdown():
    """Entries without a `match` block keep the family path and omit breakdown."""
    from chess_tracker.metrics import compute_plan_compliance
    from chess_tracker.pgn import GameRecord

    rec = GameRecord(
        url="x", end_time=1_700_000_000, time_class="bullet", side="black",
        my_rating=500, opp_rating=500, result="win", opp_result="checkmated",
        plies=20, fullmoves=10, opening="Modern Defense", eco="B06",
        first_moves="1.e4 g6 2.d4 Bg7 3.Nc3 d6 4.f4 c6")
    plan = {"openings": [{"name": "Modern", "side": "black",
                          "vs_first_move": "e4", "target_family": "Modern Defense"}]}
    out = compute_plan_compliance([rec], plan)
    o = out["openings"][0]
    assert o["games_on_plan"] == 1
    assert o["gambit_breakdown"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py -k "move_pattern or gambit_breakdown or family_entry_unchanged" -v`
Expected: FAIL — `KeyError: 'gambit_breakdown'` (and on-plan counts wrong, because the family path miscounts move-pattern entries).

- [ ] **Step 3: Write minimal implementation**

In `chess_tracker/metrics.py`, add the import near the top of the file (with the other `from chess_tracker...` imports):

```python
from chess_tracker.opening_match import match_opening
```

Then replace the body of the per-opening loop in `compute_plan_compliance`. The current code (lines ~733-736) is:

```python
        total = len(applicable)
        played = [r for r in applicable if r.family == target]
        deviated = [r for r in applicable if r.family != target]
```

Replace those three lines with:

```python
        match_rule = op.get("match")
        gambit_breakdown = None
        if match_rule:
            verdicts = [(r, match_opening(r.opening_moves or r.first_moves,
                                          match_rule)) for r in applicable]
            applicable_recs = [r for r, m in verdicts if m["applicable"]]
            played = [r for r, m in verdicts if m["applicable"] and m["on_plan"]]
            deviated = [r for r, m in verdicts
                        if m["applicable"] and not m["on_plan"]]
            total = len(applicable_recs)
            gambit_breakdown = {}
            for r, m in verdicts:
                if m["applicable"] and m["on_plan"]:
                    for flag in m["flags"]:
                        gambit_breakdown[flag] = gambit_breakdown.get(flag, 0) + 1
            if not gambit_breakdown:
                gambit_breakdown = None if not match_rule.get("gambit_flags") else {}
        else:
            total = len(applicable)
            played = [r for r in applicable if r.family == target]
            deviated = [r for r in applicable if r.family != target]
```

Then, in the `out_openings.append({...})` dict (after the `"severity": severity,` line ~764), add:

```python
            "severity": severity,
            "gambit_breakdown": gambit_breakdown,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -k "plan_compliance" -v`
Expected: all plan_compliance tests pass (the 3 new ones + the 3 pre-existing family-path ones — confirming backward compatibility).

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): move-pattern adherence + gambit breakdown in plan compliance"
```

---

### Task 5: Add the two White entries to `plan.json`

**Files:**
- Modify: `chess_tracker/plan.json`
- Test: `tests/test_metrics.py` (a guard test that the shipped plan loads and produces White entries)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_metrics.py`:

```python
def test_shipped_plan_has_white_entries_with_match_rules():
    """The shipped plan.json carries the two White move-pattern entries."""
    from chess_tracker.plan import load_plan

    plan = load_plan()
    by_name = {o["name"]: o for o in plan["openings"]}
    cz = by_name["Colle–Zukertort System"]
    assert cz["side"] == "white" and cz["vs_first_move"] == "d4"
    assert cz["match"]["white_forbids"] == ["Bf4"]
    fk = by_name["Four Knights (Belgrade / Halloween)"]
    assert fk["side"] == "white" and fk["vs_first_move"] == "e4"
    assert set(fk["match"]["gambit_flags"]) == {"Halloween", "Belgrade"}
    # Existing Black entries are still present and untouched (no match block).
    assert "Englund Gambit" in by_name
    assert "match" not in by_name["Englund Gambit"]
```

Note the en-dash in `"Colle–Zukertort System"` (U+2013), matching the spec.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py -k shipped_plan_has_white -v`
Expected: FAIL — `KeyError: 'Colle–Zukertort System'`.

- [ ] **Step 3: Write minimal implementation**

In `chess_tracker/plan.json`, add these two objects to the `openings` array (after the existing Englund Gambit entry, before the closing `]`):

```json
    {
      "name": "Colle–Zukertort System",
      "side": "white",
      "vs_first_move": "d4",
      "target_family": "Colle Zukertort System",
      "moves": "1.d4 d5  2.Nf3 Nf6  3.e3 e6  4.Bd3 c5  5.b3 Nc6  6.Bb2 Bd6",
      "plan": "e3 + b3 + Bb2 fianchetto, dark bishop stays home (NO early Bf4). Aim the e4 break and kingside attack.",
      "match": {
        "white_requires_any": [["e3", "b3"], ["e3", "Bb2"]],
        "white_forbids": ["Bf4"],
        "window_plies": 12
      }
    },
    {
      "name": "Four Knights (Belgrade / Halloween)",
      "side": "white",
      "vs_first_move": "e4",
      "target_family": "Four Knights Game",
      "moves": "1.e4 e5  2.Nf3 Nc6  3.Nc3 Nf6  4.Nxe5 (Halloween)  /  4.d4 exd4 5.Nd5 (Belgrade)",
      "plan": "Develop both knights (Four Knights). Spring Halloween 4.Nxe5 or Belgrade 4.d4 exd4 5.Nd5 for bullet surprise.",
      "match": {
        "applicable_if_black_plays": "e5",
        "white_requires": ["Nf3", "Nc3"],
        "gambit_flags": { "Halloween": ["Nxe5"], "Belgrade": ["Nd5"] },
        "window_plies": 8
      }
    }
```

Remember the comma after the Englund Gambit entry's closing `}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -k shipped_plan_has_white -v`
Expected: PASS. Also confirm valid JSON: `uv run python -c "import json; json.load(open('chess_tracker/plan.json'))"` (no output = valid).

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/plan.json tests/test_metrics.py
git commit -m "feat(plan): add Colle-Zukertort + Four Knights White entries"
```

---

### Task 6: Dashboard — side grouping + gambit breakdown

**Files:**
- Modify: `dashboard/app.js` (`renderPlanBlock`, lines ~64-145)

This is presentation JS with no unit-test harness in the repo; it is verified in Task 7 via the live dashboard. Keep the change surgical.

- [ ] **Step 1: Sort openings by side and inject group headers**

In `renderPlanBlock`, replace the line:

```javascript
      root.innerHTML = openings.map((o, i) => {
```

with an ordered copy (Black first, then White) and a header injected when the side changes:

```javascript
      const ordered = [...openings].sort((a, b) =>
        (a.side === "black" ? 0 : 1) - (b.side === "black" ? 0 : 1));
      let lastSide = null;
      root.innerHTML = ordered.map((o, i) => {
        const header = o.side !== lastSide
          ? `<h3 class="plan-side-header">${o.side === "black" ? "As Black" : "As White"}</h3>`
          : "";
        lastSide = o.side;
```

Then, at the end of that same `.map(...)` callback, prepend `header` to the returned card markup. The callback currently returns a template literal beginning with `` return ` `` and `<div class="plan-card ...">`. Change it to:

```javascript
        return `
          ${header}
          <div class="plan-card severity-${o.severity}">
```

- [ ] **Step 2: Add the gambit breakdown line**

Inside the card markup, right after the `plan-counts` div (the `${o.games_on_plan} of ${o.applicable_games} games played on plan` block), add:

```javascript
            ${(o.gambit_breakdown && Object.keys(o.gambit_breakdown).length)
              ? `<div class="plan-gambits">of on-plan: ${
                  Object.entries(o.gambit_breakdown)
                    .map(([k, v]) => `${v} ${k}`).join(" · ")}</div>`
              : ""}
```

- [ ] **Step 3: Update the board-wiring loop to use the ordered array**

The `openings.forEach((o, i) => {...})` loop that wires each board MUST iterate the same `ordered` array (its `i` indexes the `plan-board-${i}` ids emitted above). Change:

```javascript
      openings.forEach((o, i) => {
```

to:

```javascript
      ordered.forEach((o, i) => {
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/app.js
git commit -m "feat(dashboard): group plan cards by side + show gambit breakdown"
```

---

### Task 7: Integration — regenerate data, full suite, verify dashboard

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: all green. If any pre-existing test broke, fix the regression before continuing.

- [ ] **Step 2: Regenerate the dashboard data**

Run: `uv run refresh.py`
Expected: completes; rewrites `data/computed.json`.

- [ ] **Step 3: Verify the new White entries computed**

Run:
```bash
uv run python -c "
import json
pc = json.load(open('data/computed.json'))['plan_compliance']
for o in pc['openings']:
    print(o['side'], '|', o['name'], '|', o['adherence_pct'], '% over',
          o['applicable_games'], 'games | gambits:', o.get('gambit_breakdown'))
"
```
Expected: 4 rows — 2 black, 2 white. The Colle–Zukertort row should show low adherence today (the user is mid-switch from the London — that's the intended baseline), and the Four Knights row should show a gambit breakdown.

- [ ] **Step 4: Verify the dashboard renders**

Start the server and load the index using the preview tools (per the verification workflow): confirm the plan section shows **As Black** / **As White** headers, four cards, the move-stepper boards still work on the new cards, and the Four Knights card shows the gambit breakdown line. Capture a screenshot of the plan section as proof.

- [ ] **Step 5: Final commit (if refresh changed tracked data)**

```bash
git add data/computed.json
git commit -m "chore(data): regenerate computed.json with White plan compliance"
```

(Only if `data/computed.json` is tracked and changed; skip if gitignored.)

---

## Self-Review

**Spec coverage:**
- Move-pattern matcher → Task 3. ✓
- ECO-family-insufficiency handled by branching → Task 4. ✓
- 12-ply `opening_moves` field + best-effort helper → Tasks 1, 2. ✓
- `compute_plan_compliance` branch + applicability guard + gambit sub-counts → Task 4. ✓
- Two White `plan.json` entries → Task 5. ✓
- Dashboard side grouping + gambit breakdown → Task 6. ✓
- Tests incl. London-via-Bf4 deviated, Scotch deviated, non-...e5 not-applicable, token normalization, backward-compat family path → Tasks 3, 4. ✓
- Out-of-scope items (Koltanowski split, engine judgement) correctly absent. ✓

**Placeholder scan:** No TBD/TODO; all code shown. The two spots that say "use the file's existing helper" (Tasks 1, 2) are deliberate — they adapt to the test file's established PGN-parse helper rather than inventing a parallel one; the assertion code is fully specified.

**Type consistency:** `match_opening(opening_moves, rule) -> {applicable, on_plan, flags}` used identically in Tasks 3 and 4. `opening_moves` field name consistent across Tasks 2, 4, 7. `gambit_breakdown` key consistent across Tasks 4, 6, 7. `opening_moves_san` name consistent across Tasks 1, 2.
