---
title: Chess Tracker — Comprehensive Improvements Plan
date: 2026-06-17
status: approved
---

# Chess Tracker — Comprehensive Improvements Design

## Context

This spec covers all 15 proposed improvements from the June 2026 handoff, filtered through an adversarial audit combining code inspection, chess training research, and external review. Items are categorized: **Build**, **Modified** (build with changed scope/approach), or **Defer/Config**.

The design principle throughout: every new metric or module must feed the prescription layer ("what do I do next session?"). Analytics that don't produce an action are not built.

---

## Adversarial Audit Findings (Summary)

### Technical

- **Time-control bug is real.** `metrics.py` hardcodes `60.0` at two sites; `GameRecord.time_control` already carries the raw string.
- **No test gate in CI.** `deploy.yml` runs `uv run refresh.py` without a pytest step. 158 passing tests exist.
- **Opening status labels on family tables require a backend join.** `plan.json` → `compute_opening_families` join by `(target_family, side)` is needed; not purely frontend.
- **Static puzzle-theme mapping is wrong approach.** The app already has `acpl_by_phase` + loss type; use those, not opening name.
- **Book depth requires Lichess Opening Explorer API** (~10 req/min unauthenticated, thousands of calls for 656 games). Cacheable but high-infrastructure for low training value at rating 449.
- **Full motif classification (fork/pin/discovered) requires move-generation analysis** beyond what Stockfish cp-delta provides. Feasible proxy: did opponent's best response capture material?

### Chess Training Methodology

- **Silman allocates 10% study time to openings for sub-1400 players** (vs 30% tactics, 30% game analysis). Opening book-depth tracking is the wrong training lever at 449.
- **Castling timing correlates with results but is confounded.** Proxy for king-safety understanding, not a causal signal. Surface as context, not prescription.
- **Static opening → puzzle-theme routing is invalid.** A Pirc loss doesn't indicate a kingside-attack knowledge gap; a blunder in move 6-10 with material capture by the opponent does.
- **Puzzle order matters.** At this rating: build vocabulary (forks/pins/skewers) before applying it to personal losses. Reversed from the handoff's proposed order.
- **Basic mate recognition is not premature at 449.** Mate-in-1, mate-in-2, back-rank, "opponent threatens mate" recognition are fundamentals. Complex mate-defense study is deferred; basic pattern recognition is not.
- **Englund Gambit note:** at 449 it can be acceptable as a bullet-only chaos weapon; opponents are unlikely to know the refutation. This is a `plan.json` annotation, not a feature.

---

## Ordered Implementation Plan

### Phase 0 — CI Gate (one session, ~30 min)

**[#15] Add pytest gate to deploy workflow**

In `.github/workflows/deploy.yml`, insert before `uv run refresh.py`:

```yaml
- name: Run tests
  run: uv run pytest
```

Also add a smoke test (separate pytest file) that asserts after `refresh.py` runs:
- `dashboard/index.html` exists
- `dashboard/app.js` exists
- `window.DATA` string is present in `index.html`
- Required top-level keys (`kpis`, `leak_summary`, `next_session_rule`) are present

---

### Phase 1 — Time-Control Fix (one session, ~1-2 hours)

**[#1] Replace hardcoded `60.0` with time-control-aware calculation**

Add to `pgn.py` or `metrics.py`:

```python
def parse_time_control(tc: str) -> tuple[int, int]:
    """Parse Chess.com TimeControl string → (start_seconds, increment_seconds).
    Examples: "60" → (60, 0), "120+1" → (120, 1), "180" → (180, 0).
    Falls back to (60, 0) on unrecognized format.
    """
    if "+" in tc:
        base, inc = tc.split("+", 1)
        return int(base), int(inc)
    try:
        return int(tc), 0
    except ValueError:
        return 60, 0
```

Replace the two hardcoded sites in `compute_process_metrics`:

```python
# Before: velocities.append(round(60.0 - c, 2))
start_sec, _ = parse_time_control(r.time_control)
velocities.append(round(start_sec - c, 2))

# Before: early_total = 60.0 - r.my_clocks[7]
start_sec, _ = parse_time_control(r.time_control)
early_total = start_sec - r.my_clocks[7]
```

Display time-burn metrics as percentage of starting time (not raw seconds) when mixed formats coexist in the window: `pct_spent = spent / start_sec * 100`.

Tests: add parametrized cases for `parse_time_control` and update `test_metrics.py` to include records with non-bullet time controls.

---

### Phase 2 — Homepage Reorder (one session, ~2-3 hours)

**[#3] Move next-session rule + current leak + puzzle queue to top of homepage**

New section order in `chess_tracker/templates/index.html`:

1. **Action card** — next-session rule (already computed as `next_session_rule`)
2. **Current leak** — top 1-2 leaks from `leak_summary` (not all; the rest go to the leaks page)
3. **Repertoire adherence** — plan compliance block (existing `plan-block`)
4. **Puzzle queue** — personal-loss puzzles (see Phase 4)
5. **Move quality** — (existing block, moved down)
6. **White / Black opening tables** — (existing blocks)
7. **Drill-in / Universal principles** — (existing blocks)

Action card copy format:

```
Next-session rule:
[game_cap] games max. [move_10_target_seconds]s left at move 10.
Stop if rating drops [stop_if_rating_drops] in a session.

Current leak: [top leak name] — [evidence]
Action: [suggested_action]
```

`app.js` render order changes accordingly.

---

### Phase 3 — Data Quality + Backend Metrics Foundation (one session, ~2-3 hours)

**Backend metrics foundation (prerequisite for Phase 4 and Phase 5)**

Add `blunders_by_phase: dict[str, int]` to `summarize()` in `analysis.py`, counting blunder-labeled moves per phase bucket. This is the shared field consumed by Phase 4 (puzzle theme routing) and Phase 5 (accuracy bucketing). Add it once here; both later phases reference it as already available.

```python
# in summarize(), alongside acpl_by_phase:
blunders_by_phase = {}
for m in moves:
    if m.label == "blunder":
        blunders_by_phase[m.phase] = blunders_by_phase.get(m.phase, 0) + 1
```

Add to the `summarize()` return dict and propagate through `aggregate_move_quality`.

---

**[#5] Sample-size protection + smoothed win rate + corrected priority formula**

Add `smoothed_win_pct` to `compute_opening_families` and `compute_opening_variations`:

```python
smoothed_win_pct = (wins + 2) / (games + 4)  # Laplace prior at 50%
```

Add `sample_strength` label:
```python
if games < 10: sample_strength = "ignore"
elif games < 30: sample_strength = "weak"
elif games < 100: sample_strength = "usable"
else: sample_strength = "strong"
```

Priority formula — two separate sort keys for two separate lists:

```
underperformance = max(0, overall_win_pct - smoothed_win_pct)
# where overall_win_pct = player's total win rate across all games

repertoire_weight:
  active = 2.0
  bench  = 0.5
  other  = 0.25  # not in plan.json at all

priority = games × underperformance × repertoire_weight
```

Display as two lists in the opening section:
- **Repertoire repairs**: active or bench entries sorted by `priority`
- **Other costly openings**: entries not in plan.json, sorted by `priority`

This keeps the user from confusing "you play this opening and it's costing you" with "you shouldn't play this opening at all."

---

**[#4] Opening status labels on plan cards + optional join to opening-family tables**

Plan cards already pass `status` through `compute_plan_compliance`. Display `active` / `bench` as colored label chips on the plan card frontend (green / gray).

For the opening-family tables: add a backend join in `compute_opening_families`. When building each row, check if `(family, color)` matches any `(target_family, side)` entry in `plan.json`. If so, attach `plan_status` and `plan_name`. This is a pure computation addition — no external data needed.

```python
plan_lookup = {
    (op["target_family"], op["side"]): op.get("status", "active")
    for op in plan.get("openings", [])
}
# in the row builder:
row["plan_status"] = plan_lookup.get((family, color))
```

Pass `plan` (the loaded `plan.json` dict) as a new optional parameter to `compute_opening_families`.

---

### Phase 4 — Puzzle Queue Centrality (one session, ~2-3 hours)

**[#6] Personal puzzle queue as a primary section**

Move the puzzle section from its current position to directly below the action card on the homepage. Structure:

```
Today's puzzles
  [5 personal-loss puzzles from recent_losses[].puzzle]
  ──
  Themes to practice (computed in Phase 4 from blunders_by_phase + loss types)
```

Puzzle card shows: FEN board position, "find the better move" prompt, opponent's threat, reveal button. Current frontend already has drill infrastructure — promote it to homepage.

Training rules surfaced in the UI (not just documentation):
- Solve in candidate-move order: name the move before revealing
- Repeat missed positions until solved twice in a row
- Stop the drill session after 3 missed in a row

---

**[#7 modified] Phase-based puzzle theme recommendations**

Do not use static opening-name → theme mapping.

Instead, compute `recommended_puzzle_themes` using `blunders_by_phase` (added in Phase 3) and loss-type counts from the recent window.

All theme slugs must appear in the validated slug map below. Any slug not in the map must not be emitted — a missing slug produces a silent broken link.

```python
# Validated Lichess puzzle theme slugs.
# Verify new entries at https://lichess.org/training/{slug} before adding.
LICHESS_PUZZLE_SLUGS = {
    # Tactics
    "fork", "pin", "skewer", "hangingPiece", "discoveredAttack",
    "attackingF2F7", "capturingDefender", "deflection", "attraction",
    "trappedPiece",
    # Mate
    "mateIn1", "mateIn2", "backRankMate", "exposedKing",
    # Endgame
    "rookEndgame", "pawnEndgame", "queenEndgame", "bishopEndgame",
    "knightEndgame",
    # Defense / other
    "defensiveMove", "advancedPawn",
}

def recommend_puzzle_themes(blunders_by_phase: dict, loss_type_counts: dict) -> list[str]:
    """Route puzzle themes from where blunders happened + how games were lost.

    blunders_by_phase: {"opening": N, "middlegame": N, "endgame": N}
      — sourced from summarize().blunders_by_phase (added in Phase 3)
    loss_type_counts:  {"timeout": N, "checkmated": N, "resigned": N}
    """
    themes = []
    total_blunders = sum(blunders_by_phase.values()) or 1
    total_losses = sum(loss_type_counts.values()) or 1

    opening_pct    = blunders_by_phase.get("opening", 0)    / total_blunders
    middlegame_pct = blunders_by_phase.get("middlegame", 0) / total_blunders
    endgame_pct    = blunders_by_phase.get("endgame", 0)    / total_blunders

    if opening_pct > 0.4:
        themes += ["fork", "pin", "attackingF2F7", "discoveredAttack"]
    if middlegame_pct > 0.4:
        themes += ["hangingPiece", "capturingDefender", "fork", "pin"]
    if endgame_pct > 0.3:
        themes += ["rookEndgame", "pawnEndgame"]

    mate_pct    = loss_type_counts.get("checkmated", 0) / total_losses
    timeout_pct = loss_type_counts.get("timeout", 0)    / total_losses

    if mate_pct > 0.5:
        themes += ["mateIn1", "mateIn2", "backRankMate"]
    if timeout_pct > 0.5:
        themes += ["pawnEndgame", "rookEndgame"]

    # Always lead with basic vocabulary themes
    for t in ["fork", "pin", "hangingPiece"]:
        if t not in themes:
            themes.insert(0, t)

    validated = [t for t in dict.fromkeys(themes) if t in LICHESS_PUZZLE_SLUGS]
    return validated
```

Surface the theme list as "Practice these on Lichess today:" with clickable links `https://lichess.org/training/{theme}`. Add a unit test that asserts every slug emitted by `recommend_puzzle_themes` is in `LICHESS_PUZZLE_SLUGS`.

---

### Phase 5 — Analytics Modules (1-2 sessions)

**[#8 modified] Bucketed accuracy by move range**

Add `acpl_by_move_bucket` to the `summarize()` aggregate in `analysis.py`:

```python
MOVE_BUCKETS = [(1, 5), (6, 10), (11, 15), (16, 25), (26, 999)]

def bucket_label(fullmove: int) -> str:
    for lo, hi in MOVE_BUCKETS:
        if lo <= fullmove <= hi:
            return f"{lo}+" if hi >= 999 else f"{lo}-{hi}"
    return "26+"
```

Add to `MoveEval` and propagate through `summarize()`. Surface on the leaks page as a bar or table: average accuracy by move range. If moves 1-5 accuracy is notably lower than 6-10, that's an opening-tactics gap. If 26+ is low, that's time trouble.

---

**[#10 modified] Castling timing as context**

Add `castle_fullmove: int | None` to `GameRecord` in `parse_game`. Detection:

```python
# In parse_game, after building board:
castle_fullmove = None
board = game.board()
for move in game.mainline_moves():
    if board.turn == (chess.WHITE if me_white else chess.BLACK):
        if board.is_castling(move):
            castle_fullmove = board.fullmove_number
            break
    board.push(move)
```

Aggregate in `compute_opening_families` as `median_castle_move` and `never_castled_pct`. Display in opening-family table rows as context columns, not as a leak trigger. Example: `Castle: move 9 median (18% never)`.

Do not create a "castle earlier" prescription unless `never_castled_pct > 30%` AND win rate is notably lower for never-castled games — both conditions required.

---

**[#9 modified] Material-loss proxy (not motif classifier)**

Rename scope clearly: this is a **material-loss proxy**, not a motif classifier.

Add to `analysis.py` alongside `MoveEval`. For each of my moves that was labeled `blunder` or `mistake`, check whether the engine's principal variation response captures one of my pieces:

```python
def is_material_loss(board_after_my_move: chess.Board,
                     engine_best_reply: chess.Move) -> bool:
    """True if the engine's reply to my move captures a piece."""
    return board_after_my_move.is_capture(engine_best_reply)
```

Store `material_loss_blunders: int` per game alongside the existing blunder count. Aggregate into a dashboard field: `material_loss_pct = material_loss_blunders / total_blunders`. If > 50%, surface as: "More than half your blunders leave a piece hanging."

This gates into Phase 5 naturally — it builds on the existing Stockfish pass with minimal overhead.

---

### Phase 6 — Privacy + Row Actions (light session, ~1-2 hours)

**[#2 reduced] README privacy warning**

Add to `README.md`:

```
> **Note:** The published dashboard at [chess-tracker](https://madisonveldingvandam.github.io/chess-tracker/)
> is public and includes game URLs, recent loss analysis, opening repertoire plans,
> and training notes. If you fork this project, review `chess_tracker/plan.json`
> and `chess_tracker/annotations.py` before deploying publicly.
```

Full `PUBLIC_MODE` redaction: deferred. Implement if/when the URL is shared with opponents.

**[#13 partial] Row actions: Copy FEN + Lichess analysis**

On puzzle cards and loss rows, add two buttons:

- **Copy FEN** — copies `fen_before` to clipboard via `navigator.clipboard.writeText()`
- **Open in Lichess** — opens `https://lichess.org/analysis/{url-encoded-fen}` in a new tab

Use `textContent` for display strings; DOM construction for the link element. No `innerHTML` interpolation of game data.

---

## Deferred / Not Built

| Item | Reason |
|------|---------|
| #11 Opening mastery / book depth | Requires Lichess API + thousands of calls; low training value at 449 |
| #2 Full public/private mode | Medium complexity, no active need |
| #9 Full motif classification (fork/pin/discovered) | Requires move-generation analysis; out of scope |
| #12 Repertoire discipline as feature | `plan.json` annotation edit; no code needed |
| Full Chess.com Insights clone | Existing analysis.py covers the useful modules; remainder is low-value |

---

## Training Methodology Decisions

### Puzzle session order (revised from handoff)

```
1. 10-15 basic motif puzzles (forks, pins, skewers, simple tactics)
2. 5 hanging-piece / board-awareness puzzles
3. 2-5 personal-loss puzzles (application layer — vocabulary first)
4. Brief review: what motif did the personal puzzle use?
```

Personal-loss puzzles are kept as the application step, not demoted. They are the app's strongest personalization feature. The correction is that they come after vocabulary practice, not before it.

### Mate recognition

Do not build a major mate-defense study module. Keep: mate-in-1, mate-in-2, back-rank, "opponent threatens mate" recognition. These are fundamentals, not advanced study. Surface in puzzle theme recommendations as `mateIn1`, `mateIn2`, `backRankMate` — not `exposedKing` or complex mate patterns yet.

### Opening study

No book-depth tracking at this rating. The relevant opening question is: "did I execute my plan?" — which `compute_plan_compliance` already answers. That is a better proxy for opening success than book depth.

### Castling timing

Compute it, surface as context. Only flag if `never_castled_pct > 30%` and that subset shows worse results. Do not make "castle by move 8" a blind rule.

---

## Data Schema Additions (summary)

| Location | New field | Type |
|----------|-----------|------|
| `GameRecord` | `castle_fullmove` | `int | None` |
| `compute_opening_families` row | `smoothed_win_pct`, `sample_strength`, `plan_status`, `median_castle_move`, `never_castled_pct`, `priority` | float/str |
| `MoveEval` | (no change) | — |
| `summarize()` output | `blunders_by_phase` (Phase 3), `acpl_by_move_bucket` (Phase 5), `material_loss_blunders` (Phase 5) | dict/int |
| `compute_all` output | `recommended_puzzle_themes` | list[str] |

---

## Out of Scope for This Plan

- Piece accuracy by piece type (bishop/knight/rook blunder breakdown)
- Time-of-day scheduling recommendations
- Advanced mate-defense training modules
- Any feature that doesn't feed `next_session_rule` or the puzzle queue
