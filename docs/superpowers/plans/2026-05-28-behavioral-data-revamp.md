# Behavioral Data Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix six verified correctness bugs in the dashboard pipeline, then add a behavioral-signals layer (loss streaks, revenge-game gap, daily drawdown, time-of-day breakdown, rating-weighted leaks) so the existing data tool surfaces *which habit is costing rating* alongside *which opening to study*.

**Architecture:** Keep the current parse → compute → render → static-JSON pipeline. Add two centralised enrichment passes (`enrich_with_deltas`, `enrich_with_sessions`) that attach per-game `prev_rating`, `rating_delta`, `session_id`, and `game_index_in_session` to `GameRecord` once. All new metrics consume those fields instead of re-deriving them. Surface new metrics via existing dashboard pages plus a new `behavior.html` page that aggregates the behavioral signals; no top-of-page verdict card.

**Tech Stack:** Python 3.11, `python-chess`, pytest. Static dashboard: vanilla JS + Tabulator. No new dependencies.

**Stage map (each task self-contained, group commits per task):**
1. Tasks 1–6: correctness bugs.
2. Tasks 7–8: enrichment plumbing.
3. Tasks 9–15: new behavioral metrics.
4. Tasks 16–18: dashboard surface for the new data.

---

## Task 1: Add `time_control` + `rated` to `GameRecord` and strict-filter at refresh

**Why:** `opening_velocity` hardcodes a 60-second initial clock at [chess_tracker/metrics.py:176](chess_tracker/metrics.py:176); current data has 7/663 unrated bullet games slipping through; `refresh.py` filters on `time_class` only. Without `time_control` and `rated` plumbed end-to-end, future non-1+0 bullet games would silently corrupt clock metrics, and unrated games dilute rating analysis.

**Files:**
- Modify: `chess_tracker/pgn.py` (`GameRecord` dataclass; `parse_game`)
- Modify: `refresh.py` (filter)
- Modify: `tests/fixtures/sample_records.py` (`_r` helper default)
- Modify: `tests/test_pgn.py`
- Modify: `tests/test_refresh.py`

- [ ] **Step 1: Write failing test for `time_control` + `rated` on `GameRecord`**

Add to `tests/test_pgn.py` (append at end of file):

```python
def test_parse_game_extracts_time_control_and_rated():
    g = {
        "url": "https://chess.com/game/1",
        "end_time": 1_700_000_000,
        "time_class": "bullet",
        "time_control": "60",
        "rated": True,
        "white": {"username": "me", "rating": 500, "result": "win"},
        "black": {"username": "opp", "rating": 500, "result": "checkmated"},
        "pgn": '[ECO "C20"]\n[ECOUrl "https://www.chess.com/openings/Kings-Pawn-Opening"]\n1. e4 {[%clk 0:01:00]} e5 {[%clk 0:01:00]} *',
    }
    from chess_tracker.pgn import parse_game
    rec = parse_game(g, username="me")
    assert rec.time_control == "60"
    assert rec.rated is True
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
.venv/bin/pytest tests/test_pgn.py::test_parse_game_extracts_time_control_and_rated -v
```

Expected: FAIL with `AttributeError: 'GameRecord' object has no attribute 'time_control'`.

- [ ] **Step 3: Add fields to `GameRecord` and populate in `parse_game`**

Edit [chess_tracker/pgn.py:14-33](chess_tracker/pgn.py:14) — add two fields with defaults so existing fixtures don't break:

```python
@dataclass
class GameRecord:
    url: str
    end_time: int
    time_class: str
    side: str                # "white" | "black"
    my_rating: int
    opp_rating: int
    result: str              # me['result']
    opp_result: str
    plies: int
    fullmoves: int
    opening: str | None      # full opening label (no move-number suffix, retains variation)
    eco: str | None          # ECO code, e.g. "C42"
    my_clocks: list[float] = field(default_factory=list)
    opp_clocks: list[float] = field(default_factory=list)
    play_signature: str | None = None  # 8-ply canonical FEN signature
    first_moves: str | None = None     # SAN of first 8 plies, e.g. "1.d4 d5 …"
    family: str | None = None          # tier-1 stem (e.g. "Queens Pawn Opening"); auto-derived from opening
    variation: str | None = None       # tier-2 suffix (e.g. "Zukertort Chigorin Variation"); "" for main lines
    time_control: str = "60"           # Chess.com raw TimeControl string, e.g. "60" = 1+0
    rated: bool = True
```

Edit [chess_tracker/pgn.py:140-157](chess_tracker/pgn.py:140) — pass new fields through in `parse_game`'s return:

```python
    return GameRecord(
        url=g.get("url", ""),
        end_time=g["end_time"],
        time_class=g.get("time_class", ""),
        side=side,
        my_rating=me["rating"],
        opp_rating=opp["rating"],
        result=me["result"],
        opp_result=opp["result"],
        plies=plies,
        fullmoves=fullmoves,
        opening=opening,
        eco=eco,
        my_clocks=w_clocks if me_white else b_clocks,
        opp_clocks=b_clocks if me_white else w_clocks,
        play_signature=_compute_play_signature(pgn),
        first_moves=_compute_first_moves_san(pgn),
        time_control=str(g.get("time_control", "60")),
        rated=bool(g.get("rated", True)),
    )
```

- [ ] **Step 4: Run test, verify it passes**

```bash
.venv/bin/pytest tests/test_pgn.py::test_parse_game_extracts_time_control_and_rated -v
```

Expected: PASS.

- [ ] **Step 5: Write failing test for refresh's strict filter**

Append to `tests/test_refresh.py`:

```python
def test_refresh_drops_non_60_and_unrated_bullet(tmp_path, monkeypatch):
    """Only rated 1+0 standard-chess games survive the bullet filter."""
    from refresh import main
    archives = {
        "games": [
            # Keep: rated 60-second standard chess bullet
            {"url": "u1", "end_time": 1, "time_class": "bullet",
             "time_control": "60", "rated": True, "rules": "chess",
             "white": {"username": "me", "rating": 500, "result": "win"},
             "black": {"username": "opp", "rating": 500, "result": "checkmated"},
             "pgn": "[ECO \"A00\"]\n*"},
            # Drop: 2+1 bullet
            {"url": "u2", "end_time": 2, "time_class": "bullet",
             "time_control": "120+1", "rated": True, "rules": "chess",
             "white": {"username": "me", "rating": 500, "result": "win"},
             "black": {"username": "opp", "rating": 500, "result": "checkmated"},
             "pgn": "*"},
            # Drop: unrated
            {"url": "u3", "end_time": 3, "time_class": "bullet",
             "time_control": "60", "rated": False, "rules": "chess",
             "white": {"username": "me", "rating": 500, "result": "win"},
             "black": {"username": "opp", "rating": 500, "result": "checkmated"},
             "pgn": "*"},
            # Drop: variant
            {"url": "u4", "end_time": 4, "time_class": "bullet",
             "time_control": "60", "rated": True, "rules": "kingofthehill",
             "white": {"username": "me", "rating": 500, "result": "win"},
             "black": {"username": "opp", "rating": 500, "result": "checkmated"},
             "pgn": "*"},
        ]
    }
    monkeypatch.setattr("refresh.fetch_archives_index", lambda u: ["arc1"])
    monkeypatch.setattr("refresh.fetch_archive", lambda url, cache_dir, force: archives)
    rc = main(["--username", "me",
               "--data-dir", str(tmp_path / "data"),
               "--dashboard-dir", str(tmp_path / "dash")])
    assert rc == 0
    import json
    payload = json.loads((tmp_path / "data" / "computed.json").read_text())
    # Only u1 should have made it through
    assert payload["kpis"]["games_total"] == 1
```

- [ ] **Step 6: Run test, verify it fails**

```bash
.venv/bin/pytest tests/test_refresh.py::test_refresh_drops_non_60_and_unrated_bullet -v
```

Expected: FAIL (currently returns 4 games, expected 1).

- [ ] **Step 7: Tighten the filter in `refresh.py`**

Replace [refresh.py:46](refresh.py:46) — change the single-condition filter to a strict triple-check:

```python
    print(f"[3/5] Filtering to {args.format} 1+0 rated standard-chess games...")
    def _accept(g):
        return (g.get("time_class") == args.format
                and str(g.get("time_control")) == "60"
                and g.get("rated") is True
                and g.get("rules") == "chess")
    in_format = [g for g in all_games if _accept(g)]
    records = [parse_game(g, username=args.username) for g in in_format]
    print(f"      {len(records)} rated 1+0 {args.format} games parsed")
```

- [ ] **Step 8: Run full test suite to verify no regressions**

```bash
.venv/bin/pytest -q
```

Expected: all green.

- [ ] **Step 9: Commit**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
git add chess_tracker/pgn.py refresh.py tests/test_pgn.py tests/test_refresh.py
git commit -m "filter to rated 1+0 standard bullet; plumb time_control + rated"
```

---

## Task 2: Derive `plies` / `fullmoves` from PGN tree, not clock count

**Why:** [chess_tracker/pgn.py:132-133](chess_tracker/pgn.py:132) computes `plies = len(all_clocks)`. If a Chess.com PGN ever omits a `[%clk ...]` tag on the first move (server lag refund or missing annotation), the count is off and downstream fast-mate buckets get the wrong number of moves. `python-chess` is already a dependency via `play_signature.py`.

**Files:**
- Modify: `chess_tracker/pgn.py` (`parse_game`)
- Modify: `tests/test_pgn.py`

- [ ] **Step 1: Write failing test for move count when clocks are missing**

Append to `tests/test_pgn.py`:

```python
def test_parse_game_move_count_from_pgn_tree_not_clocks():
    """If a [%clk] tag is missing on one move, plies/fullmoves still reflect actual move count."""
    g = {
        "url": "u", "end_time": 1, "time_class": "bullet",
        "time_control": "60", "rated": True,
        "white": {"username": "me", "rating": 500, "result": "win"},
        "black": {"username": "opp", "rating": 500, "result": "checkmated"},
        # 4 plies, only 3 clock annotations
        "pgn": "[ECO \"C20\"]\n1. e4 e5 2. Nf3 {[%clk 0:00:58]} Nc6 {[%clk 0:00:58]} *",
    }
    from chess_tracker.pgn import parse_game
    rec = parse_game(g, username="me")
    assert rec.plies == 4
    assert rec.fullmoves == 2
```

- [ ] **Step 2: Run test, verify it fails**

```bash
.venv/bin/pytest tests/test_pgn.py::test_parse_game_move_count_from_pgn_tree_not_clocks -v
```

Expected: FAIL — `rec.plies == 2` because only 2 clocks were parsed.

- [ ] **Step 3: Replace clock-derived move count with `chess.pgn` parse**

Edit [chess_tracker/pgn.py:1-12](chess_tracker/pgn.py:1) — add imports at the top of the file alongside the existing ones:

```python
"""Parse a Chess.com game dict into a GameRecord."""
from dataclasses import dataclass, field
from io import StringIO
import re
import chess.pgn
from chess_tracker.play_signature import (
    play_signature as _compute_play_signature,
    first_moves_san as _compute_first_moves_san,
)
```

Edit [chess_tracker/pgn.py:121-134](chess_tracker/pgn.py:121) — replace the clock-derived ply count with a PGN-tree count:

```python
def parse_game(g: dict, username: str) -> GameRecord:
    me_white = g["white"]["username"].lower() == username.lower()
    me = g["white"] if me_white else g["black"]
    opp = g["black"] if me_white else g["white"]
    side = "white" if me_white else "black"

    pgn = g.get("pgn", "")
    all_clocks = _parse_clocks(pgn)
    w_clocks = all_clocks[0::2]
    b_clocks = all_clocks[1::2]

    # Move count from PGN tree, not from clock annotations (some plies may
    # be missing [%clk] tags due to server-side lag refunds).
    game_tree = chess.pgn.read_game(StringIO(pgn))
    plies = sum(1 for _ in game_tree.mainline_moves()) if game_tree else 0
    fullmoves = (plies + 1) // 2
```

Leave the rest of the function unchanged. `all_clocks`, `w_clocks`, `b_clocks` continue to be populated from the regex for the clock-based metrics; only the move count changes source.

- [ ] **Step 4: Run test, verify it passes**

```bash
.venv/bin/pytest tests/test_pgn.py::test_parse_game_move_count_from_pgn_tree_not_clocks -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest -q
```

Expected: all green. (Existing tests use synthetic clock arrays where `len(all_clocks) == fullmoves * 2` already, so the change is consistent.)

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/pgn.py tests/test_pgn.py
git commit -m "derive plies/fullmoves from PGN tree, not clock annotations"
```

---

## Task 3: Fix process-card alert threshold (sign-inversion)

**Why:** `opening_velocity_median` is *seconds spent on first 8 moves*; lower is faster. The leak detector at [chess_tracker/metrics.py:277](chess_tracker/metrics.py:277) treats `>8.0s` as a leak. But the drill-in card at [dashboard/app.js:348-351](dashboard/app.js:348) alerts when `velocity < 18` and prints "Target ≥ 18s". The two pieces disagree about which direction is bad; the card is telling the user to spend *more* time, which is the opposite of the actual leak.

**Files:**
- Modify: `dashboard/app.js`

This task is JS-only (no Python test infrastructure for the dashboard). Verify manually after editing.

- [ ] **Step 1: Replace the inverted threshold and label**

Edit [dashboard/app.js:347-351](dashboard/app.js:347):

```javascript
    // Process card: alert when opening_velocity_median > 8 (seconds spent
    // on first 8 moves; matches the leak detector's "time_burn_opening"
    // threshold of >8s). Lower velocity = faster opening play = better.
    const velocity = pm.opening_velocity_median;
    const processHeadline = velocity == null ? "—" : `${velocity}s @ 8`;
    const processSub = velocity == null ? "insufficient data" : "Target ≤ 8s";
    const processAlert = velocity != null && velocity > 8;
```

- [ ] **Step 2: Verify visually**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
.venv/bin/python refresh.py
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
# Open http://localhost:8000/dashboard/index.html in a browser and confirm
# the Process card now shows "Target ≤ 8s" and is red iff velocity > 8.
kill $SERVER_PID
```

Expected: The Process drill-in card text reads `Target ≤ 8s`; alert styling fires when median velocity > 8s.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app.js
git commit -m "fix process card threshold inversion: lower velocity is the target"
```

---

## Task 4: Fix oldest-vs-newest session bug in KPI strip + drill-in card

**Why:** [chess_tracker/metrics.py:51](chess_tracker/metrics.py:51) sorts records ascending and `compute_sessions` returns sessions in that same chronological order. Three JS consumers reach into the array assuming index 0 is *newest*:
- [dashboard/app.js:33](dashboard/app.js:33) — `d.sessions[0].rating_delta` for the "Last session" KPI.
- [dashboard/app.js:355](dashboard/app.js:355) — `sessions.slice(0, 5)` to count tilted sessions among "last 5".
- [dashboard/app.js:359](dashboard/app.js:359) — `sessions[0].tilt_flag` to alert when last session was tilted.

All three are reading the *oldest* sessions. The sessions table on `sessions.html` is unaffected because Tabulator sorts descending in the browser (`initialSort: [{column: "start", dir: "desc"}]`).

The fix is to read from the end of the array (sessions stay chronological in JSON; consumers explicitly pick "latest").

**Files:**
- Modify: `dashboard/app.js`

- [ ] **Step 1: Fix all three consumers**

Edit [dashboard/app.js:33](dashboard/app.js:33):

```javascript
    const lastDelta = (d.sessions && d.sessions.length > 0)
      ? d.sessions[d.sessions.length - 1].rating_delta
      : null;
```

Edit [dashboard/app.js:354-359](dashboard/app.js:354):

```javascript
    // Sessions card: alert when most-recent session was tilted.
    // sessions are stored chronologically (oldest first); use slice(-5) and
    // [-1] (via .at) to read the latest entries.
    const sessionCount = sessions.length;
    const last5 = sessions.slice(-5);
    const tiltedCount = last5.filter(s => s.tilt_flag).length;
    const sessionsSub = sessionCount === 0 ? "no sessions"
      : `${tiltedCount} tilted of last 5`;
    const lastSession = sessions.length > 0 ? sessions[sessions.length - 1] : null;
    const sessionsAlert = lastSession != null && lastSession.tilt_flag === true;
```

- [ ] **Step 2: Verify visually**

```bash
.venv/bin/python refresh.py
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
# Open http://localhost:8000/dashboard/index.html
# - "Last session" KPI should equal the rating_delta of the FIRST row in the
#   Sessions table (which is sorted desc, so it's the most-recent session).
# - "Sessions" drill-in card alert should match whether that same first row
#   has the tilt indicator on.
kill $SERVER_PID
```

Expected: KPI value matches the top sessions-table row.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app.js
git commit -m "fix KPI and sessions card: read latest session, not oldest"
```

---

## Task 5: Include the first game in session rating delta

**Why:** [chess_tracker/metrics.py:66-68](chess_tracker/metrics.py:66) sets `rating_start = s[0].my_rating` and `rating_end = s[-1].my_rating`. Because `my_rating` is the *postgame* rating, the first game's swing is excluded from the session delta. A session that starts with a 10-point loss and grinds back to flat will be reported as `+0` instead of `-10` → tilt detection silently undercounts the damage.

The fix: use the previous global record's `my_rating` as the session's `rating_start` (when one exists). For the very first session in the dataset, fall back to the current behaviour and flag `rating_start_exact: False`.

**Files:**
- Modify: `chess_tracker/metrics.py`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_metrics.py`:

```python
def test_compute_sessions_includes_first_game_delta():
    """Session rating delta uses prior global game's postgame rating as start,
    so the first game in a session contributes to the session's delta."""
    from chess_tracker.pgn import GameRecord
    from chess_tracker.metrics import compute_sessions

    def _mk(t, rating, result="win", opp_result="checkmated"):
        return GameRecord(
            url=f"u{t}", end_time=t, time_class="bullet",
            side="white", my_rating=rating, opp_rating=500,
            result=result, opp_result=opp_result,
            plies=20, fullmoves=10, opening="x", eco="A00",
            play_signature="sig",
        )

    # Two sessions, separated by a >10min gap.
    # Session 1: 500 → 510 → 520 (two wins after starting at 490 prior). Delta should be 30 (520-490).
    # Session 2: starts with a 20-point loss (rating 520→500), then steady at 500. Delta should be -20.
    records = [
        _mk(1_700_000_000, 500),   # first game ever: prior rating unknown; falls back to postgame=500
        _mk(1_700_000_060, 510),   # +10
        _mk(1_700_000_120, 520),   # +10
        # Gap of 30 min
        _mk(1_700_002_000, 500, result="checkmated", opp_result="win"),  # -20 from 520
        _mk(1_700_002_060, 500),   # +0
    ]
    sessions = compute_sessions(records)
    assert len(sessions) == 2
    # Session 1: first session has no prior record → rating_start = 500 (postgame of game 1)
    assert sessions[0]["rating_start"] == 500
    assert sessions[0]["rating_end"] == 520
    assert sessions[0]["rating_delta"] == 20
    assert sessions[0]["rating_start_exact"] is False
    # Session 2: prior global record is rating 520 → start = 520
    assert sessions[1]["rating_start"] == 520
    assert sessions[1]["rating_end"] == 500
    assert sessions[1]["rating_delta"] == -20
    assert sessions[1]["rating_start_exact"] is True
```

- [ ] **Step 2: Run test, verify it fails**

```bash
.venv/bin/pytest tests/test_metrics.py::test_compute_sessions_includes_first_game_delta -v
```

Expected: FAIL — current `rating_delta` for session 2 is 0 (500 − 500), expected −20; field `rating_start_exact` doesn't exist.

- [ ] **Step 3: Update `compute_sessions` to use prior global rating as start**

Replace [chess_tracker/metrics.py:48-79](chess_tracker/metrics.py:48):

```python
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

    # For each session, the "start rating" should be the postgame rating of
    # the prior global game (so the first game of the session contributes to
    # the session delta). For the very first session in the dataset there is
    # no prior game — fall back to the first game's postgame rating and flag
    # rating_start_exact=False so consumers can show an asterisk.
    out = []
    prev_end_rating = None  # postgame rating of last record in the previous session
    for s in sessions:
        wins = sum(1 for r in s if _is_win(r.result))
        losses = sum(1 for r in s if _is_loss(r.result))
        draws = sum(1 for r in s if _is_draw(r.result))
        if prev_end_rating is not None:
            rating_start = prev_end_rating
            rating_start_exact = True
        else:
            rating_start = s[0].my_rating
            rating_start_exact = False
        rating_end = s[-1].my_rating
        delta = rating_end - rating_start
        out.append({
            "start": datetime.fromtimestamp(s[0].end_time).astimezone().isoformat(),
            "games": len(s),
            "duration_minutes": round((s[-1].end_time - s[0].end_time) / 60, 1),
            "wins": wins, "losses": losses, "draws": draws,
            "rating_start": rating_start,
            "rating_start_exact": rating_start_exact,
            "rating_end": rating_end,
            "rating_delta": delta,
            "tilt_flag": delta <= -50,
        })
        prev_end_rating = rating_end
    return out
```

- [ ] **Step 4: Run failing test, then full suite**

```bash
.venv/bin/pytest tests/test_metrics.py::test_compute_sessions_includes_first_game_delta -v
.venv/bin/pytest -q
```

Expected: new test PASS; pre-existing `test_compute_sessions_tracks_rating_delta` may fail because session 1 in the existing fixture now reports a different delta. **Update that pre-existing test** at `tests/test_metrics.py` — the docstring/assert needs to reflect that session 1 starts at the first game's postgame rating (because no prior session exists) and session 2 now uses session 1's last postgame rating as its start. Adjust the asserts to match the new semantics. (Reading the existing fixture in `tests/fixtures/sample_records.py`: session 1 ratings end at 510; session 2's first game is `my_rating=505`. Under the new logic session 2's `rating_start` = 510 (postgame of session 1's last game) not 505, and its `rating_end` is 490, so `rating_delta = -20`.)

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "session rating_delta now includes the first game's swing"
```

---

## Task 6: Tighten `outlasted_but_flagged` definition

**Why:** [chess_tracker/metrics.py:196-204](chess_tracker/metrics.py:196) currently counts a timeout loss if `my_clocks[i] > opp_clocks[i]` at *any* recorded ply. A 0.1-second lead at move 2 in a game I later mismanaged is not "outlasted but flagged." Tighten to: had a ≥5-second clock edge at move 10 or later, and still timed out. This matches the dashboard's claim that the metric isolates panic-conversion failures.

**Files:**
- Modify: `chess_tracker/metrics.py`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_metrics.py`:

```python
def test_outlasted_but_flagged_requires_5s_edge_after_move_10():
    """Tighter definition: timeout loss with ≥5s clock edge at any ply
    from move 10 onward (my_clocks index >= 9). Tiny early edges don't count."""
    from chess_tracker.pgn import GameRecord
    from chess_tracker.metrics import compute_process_metrics

    def _mk(my_clocks, opp_clocks):
        return GameRecord(
            url="u", end_time=1, time_class="bullet",
            side="white", my_rating=500, opp_rating=500,
            result="timeout", opp_result="win",
            plies=len(my_clocks) * 2, fullmoves=len(my_clocks),
            opening="x", eco="A00",
            my_clocks=my_clocks, opp_clocks=opp_clocks,
        )

    # Case 1: 0.2s edge at move 2, then opponent leads the rest. Should NOT count.
    too_early = _mk(
        my_clocks=[59.0, 50.0, 40.0, 30.0, 20.0, 10.0, 5.0, 2.0, 1.0, 0.0],
        opp_clocks=[58.8, 51.0, 45.0, 38.0, 30.0, 25.0, 20.0, 15.0, 12.0, 10.0],
    )
    # Case 2: 7s edge at move 10, still timed out. Should count.
    real_choke = _mk(
        my_clocks=[55.0, 50.0, 45.0, 40.0, 35.0, 30.0, 25.0, 20.0, 15.0, 12.0,
                   5.0, 0.0],
        opp_clocks=[50.0, 45.0, 40.0, 35.0, 30.0, 25.0, 20.0, 15.0, 10.0, 5.0,
                    4.0, 3.0],
    )
    pm = compute_process_metrics([too_early, real_choke])
    assert pm["outlasted_but_flagged_count"] == 1
```

- [ ] **Step 2: Run test, verify it fails**

```bash
.venv/bin/pytest tests/test_metrics.py::test_outlasted_but_flagged_requires_5s_edge_after_move_10 -v
```

Expected: FAIL — current count is 2 (both qualify under loose definition).

- [ ] **Step 3: Tighten the metric**

Replace the `outlasted` loop in `compute_process_metrics` ([chess_tracker/metrics.py:194-204](chess_tracker/metrics.py:194)):

```python
    # "Outlasted but flagged": timeout-losses where I had a ≥5s clock edge
    # at some ply from move 10 onward (my_clocks index ≥ 9). Tiny early
    # edges don't count — this isolates panic-conversion failures.
    outlasted = 0
    EDGE_SECONDS = 5.0
    MIN_PLY_INDEX = 9
    for r in records:
        if r.result != "timeout":
            continue
        common = min(len(r.my_clocks), len(r.opp_clocks))
        for i in range(MIN_PLY_INDEX, common):
            if r.my_clocks[i] - r.opp_clocks[i] >= EDGE_SECONDS:
                outlasted += 1
                break
```

- [ ] **Step 4: Run test, verify it passes; check no regressions**

```bash
.venv/bin/pytest tests/test_metrics.py::test_outlasted_but_flagged_requires_5s_edge_after_move_10 -v
.venv/bin/pytest -q
```

Expected: new test PASS. The existing `OUTLASTED_THEN_FLAG_RECORD` fixture only has 8 plies of clock data — it will no longer satisfy the ≥move-10 condition, so any pre-existing test asserting that fixture counts as "outlasted" needs to be updated. Grep for `OUTLASTED_THEN_FLAG_RECORD` in `tests/` and update those tests to expect `0` for the loose case, then add a longer-fixture case that does qualify. If the only consumer is one assertion, update it inline; if it's many, deprecate the fixture and write a new `_LONG_OUTLAST_RECORD` in `tests/fixtures/sample_records.py` with 12+ plies of clock data showing the user holding a 7-second lead at move 10.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py tests/fixtures/sample_records.py
git commit -m "tighten outlasted-but-flagged: ≥5s edge at move 10+"
```

---

## Task 7: Add `enrich_with_deltas`: per-game `prev_rating` + `rating_delta`

**Why:** Without per-game rating delta, every rating-weighted metric (daily drawdown, rating-weighted leaks, post-loss conditional win rate's rating component) has to re-derive adjacency. Compute it once in an enrichment pass and attach to each `GameRecord`. First record's `prev_rating` is `None` and `rating_delta` is `None`.

**Files:**
- Modify: `chess_tracker/pgn.py` (add fields)
- Create: `chess_tracker/enrich.py`
- Create: `tests/test_enrich.py`

- [ ] **Step 1: Add fields to `GameRecord`**

Edit [chess_tracker/pgn.py:14-34](chess_tracker/pgn.py:14) — append two more optional fields after the ones added in Task 1:

```python
    time_control: str = "60"
    rated: bool = True
    prev_rating: int | None = None     # postgame rating of the prior chronological game; None for first
    rating_delta: int | None = None    # my_rating - prev_rating; None for first
```

- [ ] **Step 2: Write failing test**

Create `tests/test_enrich.py`:

```python
"""Tests for the enrichment pass that attaches per-game derived fields."""
from chess_tracker.pgn import GameRecord
from chess_tracker.enrich import enrich_with_deltas


def _mk(t, rating, result="win"):
    return GameRecord(
        url=f"u{t}", end_time=t, time_class="bullet",
        side="white", my_rating=rating, opp_rating=500,
        result=result, opp_result="checkmated",
        plies=20, fullmoves=10, opening="x", eco="A00",
    )


def test_enrich_with_deltas_first_record_is_none():
    records = [_mk(1, 500)]
    enrich_with_deltas(records)
    assert records[0].prev_rating is None
    assert records[0].rating_delta is None


def test_enrich_with_deltas_computes_adjacent_swing():
    records = [_mk(3, 510), _mk(1, 500), _mk(2, 495)]  # deliberately out-of-order input
    enrich_with_deltas(records)
    # Sort by end_time before reading: chronological order is t=1 (500), t=2 (495), t=3 (510)
    by_time = sorted(records, key=lambda r: r.end_time)
    assert by_time[0].prev_rating is None
    assert by_time[0].rating_delta is None
    assert by_time[1].prev_rating == 500
    assert by_time[1].rating_delta == -5
    assert by_time[2].prev_rating == 495
    assert by_time[2].rating_delta == 15


def test_enrich_with_deltas_mutates_in_place():
    """Enrichment mutates the GameRecord objects directly (no new list returned)."""
    records = [_mk(1, 500), _mk(2, 510)]
    ret = enrich_with_deltas(records)
    assert ret is records  # same list object
    assert records[1].rating_delta == 10
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_enrich.py -v
```

Expected: FAIL — `chess_tracker.enrich` module doesn't exist.

- [ ] **Step 4: Create the enrichment module**

Create `chess_tracker/enrich.py`:

```python
"""Single-pass enrichment of GameRecord lists with derived fields.

Each function mutates records in place and returns the same list.
Centralising this here lets downstream metrics consume prev_rating /
rating_delta / session_id / game_index_in_session without re-deriving
adjacency or session boundaries.
"""
from chess_tracker.pgn import GameRecord


def enrich_with_deltas(records: list[GameRecord]) -> list[GameRecord]:
    """Attach prev_rating and rating_delta to each record.

    Sorts a copy by end_time to determine adjacency, then mutates the
    original records. First chronological record has prev_rating=None
    and rating_delta=None.
    """
    if not records:
        return records
    ordered = sorted(records, key=lambda r: r.end_time)
    prev = None
    for r in ordered:
        if prev is None:
            r.prev_rating = None
            r.rating_delta = None
        else:
            r.prev_rating = prev.my_rating
            r.rating_delta = r.my_rating - prev.my_rating
        prev = r
    return records
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_enrich.py -v
```

Expected: all three PASS.

- [ ] **Step 6: Call enrichment from `compute_all`**

Edit [chess_tracker/metrics.py:584-613](chess_tracker/metrics.py:584) — call `enrich_with_deltas` at the top of `compute_all` so every metric sees enriched records:

```python
def compute_all(records: list[GameRecord], annotations: dict,
                username: str, format: str = "bullet",
                low_confidence_threshold: int = 15) -> dict:
    """Top-level dashboard payload. All panel data merged + annotations applied."""
    from chess_tracker.enrich import enrich_with_deltas
    enrich_with_deltas(records)

    play_signatures = compute_play_signatures(records)
    # ... rest unchanged
```

- [ ] **Step 7: Full test run**

```bash
.venv/bin/pytest -q
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add chess_tracker/pgn.py chess_tracker/enrich.py chess_tracker/metrics.py tests/test_enrich.py
git commit -m "add enrich_with_deltas: per-game prev_rating + rating_delta"
```

---

## Task 8: Add `enrich_with_sessions`: per-game `session_id` + `game_index_in_session`

**Why:** Three places currently re-derive session boundaries: `compute_sessions`, `_session_position_groups`, and the leak detector's tilt check. Centralise the boundary logic into one enrichment pass so behavioral metrics (loss-streak, revenge gap, daily drawdown) can use the shared session_id without recomputing it.

**Files:**
- Modify: `chess_tracker/pgn.py` (add fields)
- Modify: `chess_tracker/enrich.py`
- Modify: `tests/test_enrich.py`

- [ ] **Step 1: Add fields to `GameRecord`**

Append to [chess_tracker/pgn.py:14-34](chess_tracker/pgn.py:14) — two more optional fields after the ones from Task 7:

```python
    prev_rating: int | None = None
    rating_delta: int | None = None
    session_id: int | None = None              # 0-indexed; assigned by enrich_with_sessions
    game_index_in_session: int | None = None   # 1-indexed; first game in a session is 1
```

- [ ] **Step 2: Write failing test**

Append to `tests/test_enrich.py`:

```python
from chess_tracker.enrich import enrich_with_sessions


def test_enrich_with_sessions_assigns_id_and_index():
    """Session boundary = >gap_seconds idle. session_id is 0-indexed by start time;
    game_index_in_session is 1-indexed within each session."""
    records = [
        _mk(1_700_000_000, 500),
        _mk(1_700_000_060, 505),
        # >10 min gap
        _mk(1_700_002_000, 510),
        _mk(1_700_002_060, 515),
        _mk(1_700_002_120, 520),
    ]
    enrich_with_sessions(records, gap_seconds=600)
    by_time = sorted(records, key=lambda r: r.end_time)
    assert [r.session_id for r in by_time] == [0, 0, 1, 1, 1]
    assert [r.game_index_in_session for r in by_time] == [1, 2, 1, 2, 3]
```

- [ ] **Step 3: Run test, verify it fails**

```bash
.venv/bin/pytest tests/test_enrich.py::test_enrich_with_sessions_assigns_id_and_index -v
```

Expected: FAIL — `enrich_with_sessions` doesn't exist.

- [ ] **Step 4: Add `enrich_with_sessions` to `chess_tracker/enrich.py`**

Append:

```python
def enrich_with_sessions(records: list[GameRecord], gap_seconds: int = 600) -> list[GameRecord]:
    """Attach session_id (0-indexed) and game_index_in_session (1-indexed).

    Session boundaries: a gap >gap_seconds between consecutive end_times
    starts a new session.
    """
    if not records:
        return records
    ordered = sorted(records, key=lambda r: r.end_time)
    session_id = 0
    idx = 1
    ordered[0].session_id = 0
    ordered[0].game_index_in_session = 1
    for prev, r in zip(ordered, ordered[1:]):
        if r.end_time - prev.end_time > gap_seconds:
            session_id += 1
            idx = 1
        else:
            idx += 1
        r.session_id = session_id
        r.game_index_in_session = idx
    return records
```

- [ ] **Step 5: Run test, verify it passes**

```bash
.venv/bin/pytest tests/test_enrich.py::test_enrich_with_sessions_assigns_id_and_index -v
```

Expected: PASS.

- [ ] **Step 6: Call from `compute_all`**

Edit `compute_all` in [chess_tracker/metrics.py:584](chess_tracker/metrics.py:584) — add the second enrichment call:

```python
def compute_all(records: list[GameRecord], annotations: dict,
                username: str, format: str = "bullet",
                low_confidence_threshold: int = 15) -> dict:
    from chess_tracker.enrich import enrich_with_deltas, enrich_with_sessions
    enrich_with_deltas(records)
    enrich_with_sessions(records)
    # ... rest unchanged
```

- [ ] **Step 7: Full test run**

```bash
.venv/bin/pytest -q
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add chess_tracker/pgn.py chess_tracker/enrich.py chess_tracker/metrics.py tests/test_enrich.py
git commit -m "add enrich_with_sessions: per-game session_id + game_index_in_session"
```

---

## Task 9: Compute current and longest loss streaks

**Why:** A current-state hazard counter ("you have lost 4 in a row") is the most actionable single signal in the whole tool. Cheap to compute. Also track the longest streak in the last 24 hours of data, and split timeout-loss streaks from total-loss streaks (the two failure modes have different fixes).

**Files:**
- Create: `chess_tracker/behavior.py`
- Create: `tests/test_behavior.py`
- Modify: `chess_tracker/metrics.py` (call from `compute_all`)

- [ ] **Step 1: Write failing test**

Create `tests/test_behavior.py`:

```python
"""Tests for the behavioral-signals layer."""
from chess_tracker.pgn import GameRecord
from chess_tracker.behavior import compute_loss_streaks


def _mk(t, result):
    return GameRecord(
        url=f"u{t}", end_time=t, time_class="bullet",
        side="white", my_rating=500, opp_rating=500,
        result=result, opp_result="win" if result != "win" else "checkmated",
        plies=20, fullmoves=10, opening="x", eco="A00",
    )


def test_loss_streaks_current_and_longest_24h():
    # Chronological: W W L L L W L L (current streak = 2, longest = 3 in window)
    records = [
        _mk(1_700_000_000, "win"),
        _mk(1_700_000_060, "win"),
        _mk(1_700_000_120, "checkmated"),
        _mk(1_700_000_180, "timeout"),
        _mk(1_700_000_240, "checkmated"),
        _mk(1_700_000_300, "win"),
        _mk(1_700_000_360, "timeout"),
        _mk(1_700_000_420, "checkmated"),
    ]
    s = compute_loss_streaks(records)
    assert s["current_loss_streak"] == 2
    assert s["current_timeout_loss_streak"] == 0  # most recent is checkmate, not timeout
    assert s["longest_loss_streak_24h"] == 3
    assert s["longest_timeout_loss_streak_24h"] == 1


def test_loss_streaks_empty():
    s = compute_loss_streaks([])
    assert s == {
        "current_loss_streak": 0,
        "current_timeout_loss_streak": 0,
        "longest_loss_streak_24h": 0,
        "longest_timeout_loss_streak_24h": 0,
    }
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_behavior.py::test_loss_streaks_current_and_longest_24h -v
```

Expected: FAIL — `chess_tracker.behavior` doesn't exist.

- [ ] **Step 3: Create `chess_tracker/behavior.py`**

```python
"""Behavioral-signals layer: streaks, conditional win rates, drawdowns,
and time-of-day breakdowns. All functions consume enriched GameRecords
(see chess_tracker.enrich) and return JSON-ready dicts/lists."""
from datetime import datetime
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
    # Current streaks: count back from the end until a non-loss.
    cur_loss = 0
    cur_timeout = 0
    for r in reversed(ordered):
        if _is_loss(r.result):
            cur_loss += 1
            if r.result == "timeout":
                cur_timeout += 1
            else:
                # Mixed-mode loss breaks the timeout streak but not total-loss streak.
                if cur_timeout > 0:
                    break_timeout = True
                    cur_timeout = cur_timeout  # already capped above
        else:
            break
    # Reset timeout streak walk: it must be contiguous timeouts at the tail.
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
```

- [ ] **Step 4: Run tests, verify pass**

```bash
.venv/bin/pytest tests/test_behavior.py -v
```

Expected: PASS.

- [ ] **Step 5: Add to `compute_all` payload**

Edit `compute_all` at [chess_tracker/metrics.py:596-613](chess_tracker/metrics.py:596) — add a `behavior` key in the returned dict:

```python
    from chess_tracker.behavior import compute_loss_streaks
    return {
        "username": username,
        # ... existing fields ...
        "behavior": {
            "loss_streaks": compute_loss_streaks(records),
        },
        # ... rest unchanged
    }
```

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/behavior.py chess_tracker/metrics.py tests/test_behavior.py
git commit -m "add loss-streak signals (current + 24h longest, total + timeout-only)"
```

---

## Task 10: Revenge-game conditional win rate

**Why:** `P(win | previous game was a loss)` minus `P(win | previous game was a win)` is the sharpest statistical proxy for tilt. If the gap is materially negative, requeueing after losses is itself the leak. One pass over chronologically sorted records.

**Files:**
- Modify: `chess_tracker/behavior.py`
- Modify: `tests/test_behavior.py`
- Modify: `chess_tracker/metrics.py` (add to payload)

- [ ] **Step 1: Write failing test**

Append to `tests/test_behavior.py`:

```python
from chess_tracker.behavior import compute_revenge_gap


def test_revenge_gap_negative_when_post_loss_is_worse():
    # Games in chronological order: W W L L W L W W L W
    # Pairs (prev, this): (W,W) (W,L) (L,L) (L,W) (W,L) (L,W) (W,W) (W,L) (L,W)
    # After-win:  W L L W L  -> wins=2/5 = 40%
    # After-loss: L W W   W  -> wins=3/4 = 75%
    results = ["win", "win", "checkmated", "timeout", "win",
               "checkmated", "win", "win", "checkmated", "win"]
    records = [_mk(1_700_000_000 + i*60, r) for i, r in enumerate(results)]
    out = compute_revenge_gap(records)
    assert out["games_after_win"] == 5
    assert out["wins_after_win"] == 2
    assert out["games_after_loss"] == 4
    assert out["wins_after_loss"] == 3
    assert out["win_pct_after_win"] == 40.0
    assert out["win_pct_after_loss"] == 75.0
    # gap = after_loss% - after_win% (positive means you play *better* after a loss,
    # negative means revenge-tilt costs you).
    assert out["revenge_gap"] == 35.0


def test_revenge_gap_handles_too_few_games():
    out = compute_revenge_gap([_mk(1, "win")])
    assert out["games_after_win"] == 0
    assert out["games_after_loss"] == 0
    assert out["revenge_gap"] is None
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_behavior.py::test_revenge_gap_negative_when_post_loss_is_worse -v
```

Expected: FAIL — `compute_revenge_gap` doesn't exist.

- [ ] **Step 3: Implement**

Append to `chess_tracker/behavior.py`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_behavior.py -v
```

Expected: PASS.

- [ ] **Step 5: Add to payload**

In `compute_all`, extend the `behavior` block:

```python
    from chess_tracker.behavior import compute_loss_streaks, compute_revenge_gap
    # ...
        "behavior": {
            "loss_streaks": compute_loss_streaks(records),
            "revenge_gap": compute_revenge_gap(records),
        },
```

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/behavior.py chess_tracker/metrics.py tests/test_behavior.py
git commit -m "add revenge-gap: conditional win rate after-win vs after-loss"
```

---

## Task 11: Daily drawdown (worst intraday rating slide)

**Why:** Session-level tilt is too narrow. A day where the first session ends flat but the second loses 80 points is invisible to per-session detection. Group by local date and compute open/high/low/close + max drawdown. Also count `games_after_drawdown_100`: how many games were played that day after being already down 100 from the day's high.

**Files:**
- Modify: `chess_tracker/behavior.py`
- Modify: `tests/test_behavior.py`
- Modify: `chess_tracker/metrics.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_behavior.py`:

```python
from chess_tracker.behavior import compute_daily_drawdown


def test_daily_drawdown_tracks_max_intraday_slide():
    # All on the same local date (UTC midnight + small offsets).
    # Ratings sequence: 500 -> 520 -> 510 -> 480 -> 460 -> 490
    # High = 520, low = 460, max drawdown = -60, close = 490.
    # Games after being down 100: 0 (worst drawdown is -60, never reached -100).
    base = 1_700_000_000  # arbitrary unix ts
    ratings = [500, 520, 510, 480, 460, 490]
    records = []
    for i, rating in enumerate(ratings):
        records.append(GameRecord(
            url=f"u{i}", end_time=base + i*60, time_class="bullet",
            side="white", my_rating=rating, opp_rating=500,
            result="win", opp_result="checkmated",
            plies=20, fullmoves=10, opening="x", eco="A00",
        ))
    days = compute_daily_drawdown(records)
    assert len(days) == 1
    d = days[0]
    assert d["open"] == 500
    assert d["high"] == 520
    assert d["low"] == 460
    assert d["close"] == 490
    assert d["max_drawdown"] == -60
    assert d["games_after_drawdown_100"] == 0
    assert d["games"] == 6
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_behavior.py::test_daily_drawdown_tracks_max_intraday_slide -v
```

Expected: FAIL — `compute_daily_drawdown` missing.

- [ ] **Step 3: Implement**

Append to `chess_tracker/behavior.py`:

```python
from datetime import datetime
from collections import defaultdict


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
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_behavior.py -v
```

Expected: PASS.

- [ ] **Step 5: Wire into payload**

```python
    from chess_tracker.behavior import (
        compute_loss_streaks, compute_revenge_gap, compute_daily_drawdown,
    )
    # ...
        "behavior": {
            "loss_streaks": compute_loss_streaks(records),
            "revenge_gap": compute_revenge_gap(records),
            "daily_drawdown": compute_daily_drawdown(records),
        },
```

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/behavior.py chess_tracker/metrics.py tests/test_behavior.py
git commit -m "add daily drawdown: per-date OHLC + games-after-100-down"
```

---

## Task 12: Time-of-day session breakdown

**Why:** Bullet collapses tend to cluster in specific hours (late night, lunch break, post-work decompression). Bucket sessions by their *start hour* in local time and report games / win-rate / mean session rating-delta per bucket. Lets the user see "my 10pm-1am sessions average -25 rating, my 8am-10am average +8."

**Files:**
- Modify: `chess_tracker/behavior.py`
- Modify: `tests/test_behavior.py`
- Modify: `chess_tracker/metrics.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_behavior.py`:

```python
from chess_tracker.behavior import compute_time_of_day


def test_time_of_day_groups_sessions_by_start_hour():
    """One bucket per hour-of-day (0-23); sessions are grouped by their
    first game's local-time hour. Aggregates total games, wins, and mean
    rating delta across all sessions starting in that hour."""
    from chess_tracker.metrics import compute_sessions

    # Two sessions starting at the same hour-bucket and one at a different hour.
    # Hour values depend on the local timezone of the test runner, so just
    # assert that bucketing works structurally rather than asserting the hour
    # number. Build three sessions deliberately separated by >10min gaps.
    base = 1_700_000_000
    def _mk_session(start_ts, deltas):
        rating = 500
        recs = []
        for i, dr in enumerate(deltas):
            rating += dr
            recs.append(GameRecord(
                url=f"u{start_ts}-{i}", end_time=start_ts + i*60,
                time_class="bullet", side="white",
                my_rating=rating, opp_rating=500,
                result="win" if dr > 0 else "checkmated",
                opp_result="checkmated" if dr > 0 else "win",
                plies=20, fullmoves=10, opening="x", eco="A00",
            ))
        return recs

    records = (
        _mk_session(base, [10, -5, 10])           # net +15
        + _mk_session(base + 3600 * 6, [-20, -10, -10])  # 6h later, net -40
    )
    buckets = compute_time_of_day(records)
    # Two distinct buckets expected (one per session start-hour).
    assert len(buckets) == 2
    # Each bucket reports its session count.
    assert sum(b["sessions"] for b in buckets) == 2
    # Total games preserved across buckets.
    assert sum(b["games"] for b in buckets) == 6
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_behavior.py::test_time_of_day_groups_sessions_by_start_hour -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `chess_tracker/behavior.py`:

```python
def compute_time_of_day(records: list[GameRecord], gap_seconds: int = 600) -> list[dict]:
    """Per local hour-of-day: session count, games, win rate, mean rating delta.

    Bucketed by the *start hour* of each session — captures "when do I begin
    to play" rather than "when do I play any given game."
    """
    if not records:
        return []
    ordered = sorted(records, key=lambda r: r.end_time)
    # Build sessions inline (same boundary rule as compute_sessions).
    sessions: list[list[GameRecord]] = [[ordered[0]]]
    for r in ordered[1:]:
        if r.end_time - sessions[-1][-1].end_time > gap_seconds:
            sessions.append([])
        sessions[-1].append(r)

    # For session delta, use the same logic as compute_sessions (prior-session
    # postgame rating as start; fall back to first game's postgame for the
    # very first session).
    by_hour: dict[int, dict] = {}
    prev_end_rating = None
    for s in sessions:
        hour = datetime.fromtimestamp(s[0].end_time).astimezone().hour
        start = prev_end_rating if prev_end_rating is not None else s[0].my_rating
        delta = s[-1].my_rating - start
        b = by_hour.setdefault(hour, {"hour": hour, "sessions": 0, "games": 0,
                                       "wins": 0, "delta_sum": 0})
        b["sessions"] += 1
        b["games"] += len(s)
        b["wins"] += sum(1 for r in s if _is_win(r.result))
        b["delta_sum"] += delta
        prev_end_rating = s[-1].my_rating

    out = []
    for hour in sorted(by_hour):
        b = by_hour[hour]
        out.append({
            "hour": hour,
            "sessions": b["sessions"],
            "games": b["games"],
            "win_pct": round(100 * b["wins"] / b["games"], 1) if b["games"] else 0.0,
            "mean_session_delta": round(b["delta_sum"] / b["sessions"], 1) if b["sessions"] else 0.0,
        })
    return out
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_behavior.py -v
```

Expected: PASS.

- [ ] **Step 5: Wire into payload**

```python
        "behavior": {
            "loss_streaks": compute_loss_streaks(records),
            "revenge_gap": compute_revenge_gap(records),
            "daily_drawdown": compute_daily_drawdown(records),
            "time_of_day": compute_time_of_day(records),
        },
```

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/behavior.py chess_tracker/metrics.py tests/test_behavior.py
git commit -m "add time-of-day session breakdown"
```

---

## Task 13: Abandonment as a distinct loss bucket + leak

**Why:** Chess.com's `result == "abandoned"` is currently lumped into the generic loss bucket. Abandonment in bullet is an unambiguous tilt-or-rage-quit signal. Surface it as its own count and, when it occurs in the last 30 games, raise a leak.

**Files:**
- Modify: `chess_tracker/metrics.py` (leak detection + payload)
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_metrics.py`:

```python
def test_abandonment_leak_fires_on_any_abandonment_in_window():
    from chess_tracker.pgn import GameRecord
    from chess_tracker.metrics import detect_leaks

    def _mk(t, result):
        return GameRecord(
            url=f"u{t}", end_time=t, time_class="bullet",
            side="white", my_rating=500, opp_rating=500,
            result=result, opp_result="win",
            plies=20, fullmoves=10, opening="x", eco="A00",
        )

    # 30 games: 29 timeouts (boring losses), 1 abandonment. Should fire abandonment leak.
    records = [_mk(1_700_000_000 + i*60, "timeout") for i in range(29)]
    records.append(_mk(1_700_001_800, "abandoned"))
    leaks = detect_leaks(records)
    names = [L["name"] for L in leaks]
    assert "abandonment" in names
    ab = next(L for L in leaks if L["name"] == "abandonment")
    assert ab["severity"] == "critical"
    assert "1" in ab["evidence"]  # mentions the count
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_metrics.py::test_abandonment_leak_fires_on_any_abandonment_in_window -v
```

Expected: FAIL.

- [ ] **Step 3: Add leak rule**

Edit [chess_tracker/metrics.py:265-331](chess_tracker/metrics.py:265) — add the abandonment check before the `tilt_session` block:

```python
    # Any abandonment in last 30 games is a high-confidence tilt signal.
    abandoned = [r for r in window if r.result == "abandoned"]
    if abandoned:
        leaks.append({
            "name": "abandonment",
            "severity": "critical",
            "evidence": f"{len(abandoned)} abandoned game(s) in the last {len(window)} games",
            "suggested_action": "Walk away after the urge to close the tab — that is the stop signal.",
        })
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_metrics.py::test_abandonment_leak_fires_on_any_abandonment_in_window -v
.venv/bin/pytest -q
```

Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "surface abandonment as a critical tilt leak"
```

---

## Task 14: Fast-mate buckets on checkmated losses

**Why:** "Checkmated" losses bucket together regardless of game length. A mate by move 12 is a different problem from a mate by move 40 — the former is opening/early-tactical, the latter is middlegame. Group checkmated losses by `fullmoves` bucket (`≤15`, `16-25`, `>25`) and split by `side`.

**Files:**
- Modify: `chess_tracker/behavior.py`
- Modify: `tests/test_behavior.py`
- Modify: `chess_tracker/metrics.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_behavior.py`:

```python
from chess_tracker.behavior import compute_mate_loss_buckets


def test_mate_loss_buckets_split_by_length_and_side():
    """Checkmated losses bucketed by fullmoves: ≤15, 16-25, >25; split by side."""
    def _mk_mate(side, fullmoves, t=1):
        return GameRecord(
            url=f"u{t}-{fullmoves}", end_time=t, time_class="bullet",
            side=side, my_rating=500, opp_rating=500,
            result="checkmated", opp_result="win",
            plies=fullmoves*2, fullmoves=fullmoves, opening="x", eco="A00",
        )
    records = [
        _mk_mate("white", 10, t=1),
        _mk_mate("white", 12, t=2),
        _mk_mate("black", 10, t=3),
        _mk_mate("white", 22, t=4),
        _mk_mate("white", 40, t=5),
        # Non-mate losses should be ignored.
        GameRecord(
            url="u-x", end_time=6, time_class="bullet",
            side="white", my_rating=500, opp_rating=500,
            result="timeout", opp_result="win",
            plies=40, fullmoves=20, opening="x", eco="A00",
        ),
    ]
    out = compute_mate_loss_buckets(records)
    # Expect rows keyed by (side, bucket); only mate-losses counted.
    table = {(r["side"], r["bucket"]): r["count"] for r in out}
    assert table[("white", "≤15")] == 2
    assert table[("black", "≤15")] == 1
    assert table[("white", "16-25")] == 1
    assert table[("white", ">25")] == 1
    # Total = 5 mates
    assert sum(r["count"] for r in out) == 5
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_behavior.py::test_mate_loss_buckets_split_by_length_and_side -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `chess_tracker/behavior.py`:

```python
def compute_mate_loss_buckets(records: list[GameRecord]) -> list[dict]:
    """Checkmated losses grouped by fullmoves bucket and side."""
    def bucket(fm):
        if fm <= 15:
            return "≤15"
        if fm <= 25:
            return "16-25"
        return ">25"
    buckets: dict[tuple[str, str], int] = {}
    for r in records:
        if r.result != "checkmated":
            continue
        key = (r.side, bucket(r.fullmoves))
        buckets[key] = buckets.get(key, 0) + 1
    return [
        {"side": side, "bucket": b, "count": n}
        for (side, b), n in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_behavior.py -v
```

Expected: PASS.

- [ ] **Step 5: Wire into payload**

```python
    from chess_tracker.behavior import (
        compute_loss_streaks, compute_revenge_gap, compute_daily_drawdown,
        compute_time_of_day, compute_mate_loss_buckets,
    )
    # ...
        "behavior": {
            "loss_streaks": compute_loss_streaks(records),
            "revenge_gap": compute_revenge_gap(records),
            "daily_drawdown": compute_daily_drawdown(records),
            "time_of_day": compute_time_of_day(records),
            "mate_loss_buckets": compute_mate_loss_buckets(records),
        },
```

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/behavior.py chess_tracker/metrics.py tests/test_behavior.py
git commit -m "add fast-mate buckets: checkmated losses by length and side"
```

---

## Task 15: Rating-weighted leak scores on opening families

**Why:** Opening tables currently sort by games and win-pct ([chess_tracker/metrics.py:464](chess_tracker/metrics.py:464)). That treats a 4-game opening with a bad win rate the same as a 60-game leak. Replace the sort with `sum(rating_delta)` — actual rating points won or lost in that family. Same denominator (each game contributes once), interpretable units. Per-row also report `sum_rating_delta`, `avg_rating_delta`, `timeout_rating_delta`, `checkmate_rating_delta`.

Requires `rating_delta` enrichment from Task 7.

**Files:**
- Modify: `chess_tracker/metrics.py` (`compute_opening_families`, `compute_opening_variations`)
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_metrics.py`:

```python
def test_opening_families_rating_weighted_columns_and_sort():
    """Each family row carries sum_rating_delta / avg_rating_delta /
    timeout_rating_delta / checkmate_rating_delta, and the default sort
    is by sum_rating_delta ascending (worst-bleeding family first)."""
    from chess_tracker.pgn import GameRecord
    from chess_tracker.enrich import enrich_with_deltas
    from chess_tracker.metrics import compute_opening_families

    def _mk(t, rating, opening, result, side="white"):
        return GameRecord(
            url=f"u{t}", end_time=t, time_class="bullet",
            side=side, my_rating=rating, opp_rating=500,
            result=result, opp_result="win" if result != "win" else "checkmated",
            plies=20, fullmoves=10, opening=opening, eco="A00",
        )

    # London System: net -30 across two games (timeout cost 20, mate cost 10)
    # Italian Game: net +20 across two games
    records = [
        _mk(1, 500, "London System", "win"),                # prev=None → delta=None
        _mk(2, 480, "London System", "timeout"),            # -20 timeout
        _mk(3, 470, "London System", "checkmated"),         # -10 mate
        _mk(4, 480, "Italian Game", "win"),                 # +10
        _mk(5, 490, "Italian Game", "win"),                 # +10
    ]
    enrich_with_deltas(records)
    rows = compute_opening_families(records)
    london = next(r for r in rows if r["family"] == "London System")
    italian = next(r for r in rows if r["family"] == "Italian Game")
    assert london["sum_rating_delta"] == -30
    assert london["timeout_rating_delta"] == -20
    assert london["checkmate_rating_delta"] == -10
    assert italian["sum_rating_delta"] == 20
    # Sort: worst (most negative sum) first
    assert rows[0]["family"] == "London System"
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_metrics.py::test_opening_families_rating_weighted_columns_and_sort -v
```

Expected: FAIL — fields don't exist; sort is by `-games`.

- [ ] **Step 3: Update `compute_opening_families`**

In [chess_tracker/metrics.py:411-465](chess_tracker/metrics.py:411) — extend the row dict and change the sort. After computing `mate` and before `med_len`:

```python
        # Rating-weighted aggregates (require enrich_with_deltas to have run).
        deltas = [r.rating_delta for r in recs if r.rating_delta is not None]
        sum_delta = sum(deltas)
        avg_delta = round(sum_delta / len(deltas), 1) if deltas else 0.0
        timeout_delta = sum(
            r.rating_delta for r in recs
            if r.result == "timeout" and r.rating_delta is not None
        )
        mate_delta = sum(
            r.rating_delta for r in recs
            if r.result == "checkmated" and r.rating_delta is not None
        )
```

Add to the row dict alongside `mate_pct`:

```python
            "sum_rating_delta": sum_delta,
            "avg_rating_delta": avg_delta,
            "timeout_rating_delta": timeout_delta,
            "checkmate_rating_delta": mate_delta,
```

Replace the existing final sort line with:

```python
    out.sort(key=lambda x: (x["sum_rating_delta"], -x["games"]))
    return out
```

- [ ] **Step 4: Same for `compute_opening_variations`**

Apply the identical block of additions + sort change inside [chess_tracker/metrics.py:468-523](chess_tracker/metrics.py:468). (Duplicating the code is intentional — DRY-by-extracting would mean introducing a helper that takes a record list and returns the four rating-delta fields; do that *only if* a third caller appears.)

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_metrics.py::test_opening_families_rating_weighted_columns_and_sort -v
.venv/bin/pytest -q
```

Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "opening tables: add rating-weighted columns + sort by sum_rating_delta"
```

---

## Task 16: Render the behavioral block on `index.html`

**Why:** Surface the four new behavioral signals (loss streaks, revenge gap, daily drawdown, time-of-day) on the main page in a single compact block so the user sees the *current state* alongside the existing leak summary. Pure data display — no verdict cards, no STOP banners. Each cell has a tooltip explaining the metric.

**Files:**
- Modify: `chess_tracker/templates/index.html` (add section)
- Modify: `dashboard/app.js` (new `renderBehavior` function and call)
- Modify: `dashboard/styles.css` (style the block)

- [ ] **Step 1: Add the section in the index template**

Open [chess_tracker/templates/index.html](chess_tracker/templates/index.html). Find the `#leak-list` container (it follows the KPI strip). Add a `<section id="behavior-block">` directly *after* `#leak-list` and before whatever comes next. The exact insertion content:

```html
    <section id="behavior-block" class="panel">
      <h2>Behavior — current state</h2>
      <div id="behavior-cards" class="behavior-grid"></div>
    </section>
```

- [ ] **Step 2: Add the renderer in `dashboard/app.js`**

Add a new function and call it from the top-level renderer block. Insert before the closing IIFE at [dashboard/app.js:425](dashboard/app.js:425):

```javascript
  function renderBehavior(b) {
    const root = document.getElementById("behavior-cards");
    if (!root || !b) return;
    const ls = b.loss_streaks || {};
    const rg = b.revenge_gap || {};
    const dd = (b.daily_drawdown || []).slice(-7);  // last 7 days
    const tod = (b.time_of_day || []);
    const todWorst = [...tod].sort((a, b) => a.mean_session_delta - b.mean_session_delta)[0];
    const todBest = [...tod].sort((a, b) => b.mean_session_delta - a.mean_session_delta)[0];

    const cell = (label, value, sub, alert=false) =>
      `<div class="behavior-card${alert ? " alert" : ""}">
         <div class="bh-label">${label}</div>
         <div class="bh-value">${value}</div>
         <div class="bh-sub">${sub}</div>
       </div>`;

    const cards = [];
    cards.push(cell(
      "Current loss streak",
      String(ls.current_loss_streak ?? 0),
      ls.current_timeout_loss_streak
        ? `${ls.current_timeout_loss_streak} of them on time`
        : "",
      (ls.current_loss_streak ?? 0) >= 3
    ));
    cards.push(cell(
      "Longest loss streak (24h)",
      String(ls.longest_loss_streak_24h ?? 0),
      ls.longest_timeout_loss_streak_24h
        ? `timeout streak: ${ls.longest_timeout_loss_streak_24h}`
        : "",
      (ls.longest_loss_streak_24h ?? 0) >= 5
    ));
    const gap = rg.revenge_gap;
    cards.push(cell(
      "Revenge gap",
      gap == null ? "—" : `${gap > 0 ? "+" : ""}${gap}pp`,
      `${rg.wins_after_loss}/${rg.games_after_loss} after losses vs ${rg.wins_after_win}/${rg.games_after_win} after wins`,
      gap != null && gap <= -8
    ));
    const worstDay = dd.length ? dd.reduce((acc, d) =>
      d.max_drawdown < acc.max_drawdown ? d : acc, dd[0]) : null;
    cards.push(cell(
      "Worst day this week",
      worstDay ? `${worstDay.max_drawdown}` : "—",
      worstDay ? `${worstDay.date} (${worstDay.games} games)` : "",
      worstDay && worstDay.max_drawdown <= -50
    ));
    cards.push(cell(
      "Best time-of-day",
      todBest ? `${String(todBest.hour).padStart(2, "0")}:00` : "—",
      todBest ? `mean session Δ ${todBest.mean_session_delta > 0 ? "+" : ""}${todBest.mean_session_delta}` : ""
    ));
    cards.push(cell(
      "Worst time-of-day",
      todWorst ? `${String(todWorst.hour).padStart(2, "0")}:00` : "—",
      todWorst ? `mean session Δ ${todWorst.mean_session_delta > 0 ? "+" : ""}${todWorst.mean_session_delta}` : "",
      todWorst && todWorst.mean_session_delta <= -20
    ));
    root.innerHTML = cards.join("");
  }
```

And add the call in the bootstrap block at [dashboard/app.js:14-27](dashboard/app.js:14):

```javascript
  renderKPI(D);
  renderLeaks(D.leak_summary);
  renderBehavior(D.behavior);
  renderRule(D.next_session_rule);
  // ... rest unchanged
```

- [ ] **Step 3: Style the block in `dashboard/styles.css`**

Append to [dashboard/styles.css](dashboard/styles.css):

```css
.behavior-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.behavior-card {
  background: var(--panel-bg, #1a1a1a);
  border: 1px solid var(--border, #333);
  border-radius: 4px;
  padding: 0.75rem;
}
.behavior-card.alert {
  border-color: var(--warn, #d05050);
}
.behavior-card .bh-label {
  font-size: 0.8rem;
  color: var(--muted, #888);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.behavior-card .bh-value {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0.25rem 0;
}
.behavior-card .bh-sub {
  font-size: 0.85rem;
  color: var(--muted, #888);
}
```

(If existing CSS uses different variable names — check [dashboard/styles.css](dashboard/styles.css) — adjust to match. The fallback colors after `var(...,` keep the cards usable even if vars are missing.)

- [ ] **Step 4: Verify visually**

```bash
.venv/bin/python refresh.py
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
# Open http://localhost:8000/dashboard/index.html. Confirm:
# - "Behavior — current state" section appears below the leak list.
# - Six cards render with current data.
# - Alert outline (red) appears on cards that meet the alert thresholds
#   (loss streak ≥ 3, longest 24h streak ≥ 5, revenge gap ≤ -8pp, worst-day
#   drawdown ≤ -50, worst hour mean delta ≤ -20).
kill $SERVER_PID
```

Expected: section visible, six cards, alerts firing where appropriate.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/templates/index.html dashboard/app.js dashboard/styles.css
git commit -m "render behavior block on index: streaks, revenge gap, drawdown, time-of-day"
```

---

## Task 17: Surface fast-mate buckets + abandonment counter on `losses.html`

**Why:** The recent-losses page should answer "what *kind* of loss is dominating right now" before showing the raw row list. Add a small summary strip with: total losses in window, % timeout, % mate, % abandonment, and a fast-mate bucket breakdown.

**Files:**
- Modify: `chess_tracker/templates/losses.html` (add summary)
- Modify: `dashboard/app.js` (new `renderLossSummary`)

- [ ] **Step 1: Add the summary container in `losses.html`**

Open [chess_tracker/templates/losses.html](chess_tracker/templates/losses.html). Before the existing `#losses-table` container, insert:

```html
    <section id="loss-summary" class="panel">
      <h2>Loss summary</h2>
      <div id="loss-summary-cards" class="behavior-grid"></div>
      <h3 style="margin-top:1rem">Fast-mate buckets</h3>
      <div id="mate-buckets"></div>
    </section>
```

- [ ] **Step 2: Add renderer in `dashboard/app.js`**

Add this function before the closing IIFE, and call it from the bootstrap section *after* `renderRecentLosses`:

```javascript
  function renderLossSummary(D) {
    const root = document.getElementById("loss-summary-cards");
    const bucketsRoot = document.getElementById("mate-buckets");
    if (!root) return;
    const losses = D.recent_losses || [];
    if (losses.length === 0) {
      root.innerHTML = `<p style="color:var(--muted)">No losses in window.</p>`;
      if (bucketsRoot) bucketsRoot.innerHTML = "";
      return;
    }
    const byType = {};
    losses.forEach(L => { byType[L.loss_type] = (byType[L.loss_type] || 0) + 1; });
    const pct = (n) => `${Math.round(100 * n / losses.length)}%`;
    const cell = (label, value, sub) =>
      `<div class="behavior-card">
         <div class="bh-label">${label}</div>
         <div class="bh-value">${value}</div>
         <div class="bh-sub">${sub}</div>
       </div>`;
    root.innerHTML = [
      cell("Losses in window", String(losses.length), ""),
      cell("Timeouts", `${byType.timeout || 0}`, pct(byType.timeout || 0)),
      cell("Mates", `${byType.checkmated || 0}`, pct(byType.checkmated || 0)),
      cell("Abandoned", `${byType.abandoned || 0}`, pct(byType.abandoned || 0)),
    ].join("");

    if (bucketsRoot) {
      const mb = (D.behavior && D.behavior.mate_loss_buckets) || [];
      if (mb.length === 0) {
        bucketsRoot.innerHTML = `<p style="color:var(--muted)">No mate losses yet.</p>`;
      } else {
        new Tabulator("#mate-buckets", {
          data: mb, layout: "fitColumns",
          columns: [
            {title: "Side", field: "side"},
            {title: "Length", field: "bucket"},
            {title: "Count", field: "count", sorter: "number"},
          ],
          initialSort: [{column: "count", dir: "desc"}],
        });
      }
    }
  }
```

Add the call in the bootstrap right after the existing `renderRecentLosses(D.recent_losses);`:

```javascript
  renderRecentLosses(D.recent_losses);
  renderLossSummary(D);
```

- [ ] **Step 3: Verify visually**

```bash
.venv/bin/python refresh.py
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
# Open http://localhost:8000/dashboard/losses.html.
# Confirm: summary cards (losses count + timeout/mate/abandoned breakdown),
# fast-mate bucket table populated (or "no mate losses" message).
kill $SERVER_PID
```

Expected: summary block above the existing losses table; bucket counts match the raw data.

- [ ] **Step 4: Commit**

```bash
git add chess_tracker/templates/losses.html dashboard/app.js
git commit -m "render loss summary + fast-mate buckets on losses page"
```

---

## Task 18: Add a top-3 "Review these" picker to recent losses

**Why:** The recent-losses table currently asks the user to scan rows and pick what to review. Front-load three review prompts — one *timeout*, one *fast mate*, one *largest single-game rating loss* — with the question to ask of each. Pure data product; nothing prescriptive about what to *do* differently, just *which games to look at*.

**Files:**
- Modify: `chess_tracker/metrics.py` (extend `recent_losses_with_suggestions`)
- Modify: `tests/test_metrics.py`
- Modify: `chess_tracker/templates/losses.html`
- Modify: `dashboard/app.js`

- [ ] **Step 1: Failing test**

Append to `tests/test_metrics.py`:

```python
def test_review_picks_one_timeout_one_mate_one_biggest_loss():
    from chess_tracker.pgn import GameRecord
    from chess_tracker.enrich import enrich_with_deltas
    from chess_tracker.metrics import compute_review_picks

    def _mk(t, rating, result, fullmoves=20):
        return GameRecord(
            url=f"u{t}", end_time=t, time_class="bullet",
            side="white", my_rating=rating, opp_rating=500,
            result=result, opp_result="win",
            plies=fullmoves*2, fullmoves=fullmoves, opening="x", eco="A00",
        )

    records = [
        _mk(1, 500, "win"),
        _mk(2, 480, "timeout"),                  # -20 timeout
        _mk(3, 470, "checkmated", fullmoves=12), # -10 fast mate
        _mk(4, 430, "checkmated", fullmoves=40), # -40 long-game mate, largest single-game loss
        _mk(5, 425, "timeout"),                  # -5 timeout
    ]
    enrich_with_deltas(records)
    picks = compute_review_picks(records)
    # Three picks: kinds in this order.
    kinds = [p["kind"] for p in picks]
    assert kinds == ["biggest_loss", "timeout", "fast_mate"]
    # biggest_loss = -40 mate at game 4
    assert picks[0]["url"] == "u4"
    # timeout = most recent timeout (game 5)
    assert picks[1]["url"] == "u5"
    # fast_mate = most recent checkmated game with fullmoves <= 15 (game 3)
    assert picks[2]["url"] == "u3"
```

- [ ] **Step 2: Run, verify failure**

```bash
.venv/bin/pytest tests/test_metrics.py::test_review_picks_one_timeout_one_mate_one_biggest_loss -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Add to [chess_tracker/metrics.py](chess_tracker/metrics.py) (alongside the other compute_* functions):

```python
def compute_review_picks(records: list[GameRecord], window: int = 30) -> list[dict]:
    """Pick up to 3 recent-loss games worth a manual review.

    - biggest_loss: the loss in the recent window with the most-negative rating_delta.
    - timeout: the most recent timeout loss in the window.
    - fast_mate: the most recent checkmated loss with fullmoves <= 15.

    Each pick carries a one-line `question` framing what to look for.
    Returns [] if no losses in the window.
    """
    if not records:
        return []
    ordered = sorted(records, key=lambda r: r.end_time)
    win_recs = ordered[-window:]
    losses = [r for r in win_recs if _is_loss(r.result)]
    if not losses:
        return []
    picks = []
    seen_urls = set()

    losses_with_delta = [r for r in losses if r.rating_delta is not None]
    if losses_with_delta:
        biggest = min(losses_with_delta, key=lambda r: r.rating_delta)
        picks.append({
            "kind": "biggest_loss",
            "url": biggest.url,
            "moves": biggest.fullmoves,
            "loss_type": biggest.result,
            "rating_delta": biggest.rating_delta,
            "question": "What single move made the position lost? Mark the ply.",
        })
        seen_urls.add(biggest.url)

    timeouts = [r for r in losses if r.result == "timeout" and r.url not in seen_urls]
    if timeouts:
        recent_timeout = timeouts[-1]
        picks.append({
            "kind": "timeout",
            "url": recent_timeout.url,
            "moves": recent_timeout.fullmoves,
            "loss_type": "timeout",
            "rating_delta": recent_timeout.rating_delta,
            "question": "At which move did the clock first slip below the opponent's by 5+ seconds?",
        })
        seen_urls.add(recent_timeout.url)

    fast_mates = [r for r in losses
                  if r.result == "checkmated" and r.fullmoves <= 15
                  and r.url not in seen_urls]
    if fast_mates:
        recent_fm = fast_mates[-1]
        picks.append({
            "kind": "fast_mate",
            "url": recent_fm.url,
            "moves": recent_fm.fullmoves,
            "loss_type": "checkmated",
            "rating_delta": recent_fm.rating_delta,
            "question": "Which opponent move first threatened mate? What did you miss?",
        })
    return picks
```

Add to `compute_all`'s returned dict alongside `recent_losses`:

```python
        "review_picks": compute_review_picks(records),
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_metrics.py::test_review_picks_one_timeout_one_mate_one_biggest_loss -v
.venv/bin/pytest -q
```

Expected: PASS, no regressions.

- [ ] **Step 5: Render picks on `losses.html`**

In [chess_tracker/templates/losses.html](chess_tracker/templates/losses.html), insert *above* the `#loss-summary` block added in Task 17:

```html
    <section id="review-picks" class="panel">
      <h2>Review these 3 games</h2>
      <ol id="review-picks-list"></ol>
    </section>
```

Add the renderer in `dashboard/app.js` and call it from the bootstrap right after `renderLossSummary(D);`:

```javascript
  function renderReviewPicks(picks) {
    const root = document.getElementById("review-picks-list");
    if (!root) return;
    if (!picks || picks.length === 0) {
      root.innerHTML = `<li style="color:var(--muted)">No recent losses to review.</li>`;
      return;
    }
    const label = {
      biggest_loss: "Biggest single-game rating loss",
      timeout: "Most recent timeout",
      fast_mate: "Most recent fast mate (≤15 moves)",
    };
    root.innerHTML = picks.map(p => {
      const delta = p.rating_delta == null ? "" :
        ` (${p.rating_delta > 0 ? "+" : ""}${p.rating_delta} rating)`;
      return `<li>
        <strong>${label[p.kind] || p.kind}</strong>${delta} —
        <a href="${escapeAttr(p.url)}" target="_blank">${p.loss_type}, ${p.moves} moves</a>
        <div style="color:var(--muted);font-size:0.9rem">${p.question}</div>
      </li>`;
    }).join("");
  }
```

And in the bootstrap:

```javascript
  renderLossSummary(D);
  renderReviewPicks(D.review_picks);
```

- [ ] **Step 6: Verify visually**

```bash
.venv/bin/python refresh.py
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
# http://localhost:8000/dashboard/losses.html
# Confirm: "Review these 3 games" section at top with up to 3 ordered items,
# each linking to a game URL and including the framing question.
kill $SERVER_PID
```

Expected: 1-3 review items render correctly with links and questions.

- [ ] **Step 7: Commit**

```bash
git add chess_tracker/metrics.py chess_tracker/templates/losses.html dashboard/app.js tests/test_metrics.py
git commit -m "add top-3 review picks: biggest loss / timeout / fast mate"
```

---

## Self-review notes

**Spec coverage:** All eight agreed items are covered.
- Bugs 1-6 (KPI/sessions sort, process inversion, session delta, time_control filter, move count): Tasks 4, 3, 5, 1, 2.
- Outlasted tightening: Task 6.
- Per-game rating delta + sessionization plumbing: Tasks 7, 8.
- Loss streaks: Task 9. Revenge gap: Task 10. Daily drawdown: Task 11. Time-of-day: Task 12.
- Abandonment bucket: Task 13. Fast-mate buckets: Task 14.
- Rating-weighted leaks on openings: Task 15.
- UX surface ("what to study, how to improve bad habits") via data: Tasks 16-18.

**Out of scope by design** (per your call): top-of-page verdict card; engine integration; repertoire-churn metric; opening-table de-emphasis; lifestyle advice ("play rapid instead").

**Calibration deferred:** leak thresholds left at current conservative values (flag_pct ≥ 60, mate_pct ≥ 55, tilt ≤ -50). Revisit after Tasks 9-15 ship and a week of real data passes through.

**Cross-task field consistency check:**
- `time_control: str` added in Task 1, referenced nowhere later — pure plumbing for future filtering. OK.
- `rated: bool` added in Task 1, used in Task 1's refresh filter only. OK.
- `prev_rating`, `rating_delta` added Task 7, consumed by Tasks 15 (opening sort) and 18 (biggest-loss pick). OK.
- `session_id`, `game_index_in_session` added Task 8 — *not* consumed by any later task in this plan. They're the seed for follow-up work (post-tilt re-entry, breach-point in sessions). Leaving them in: cost is two integers per record, value is unblocking the next plan without a separate plumbing task. If you'd rather defer, drop Task 8.
- `behavior` payload key introduced Task 9, extended in Tasks 10/11/12/14, consumed by renderers in Tasks 16/17. OK.

---

**Plan complete and saved to [docs/superpowers/plans/2026-05-28-behavioral-data-revamp.md](docs/superpowers/plans/2026-05-28-behavioral-data-revamp.md).**
