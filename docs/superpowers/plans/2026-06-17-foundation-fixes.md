# Foundation Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pytest gate before CI deployment, and fix the time-control normalization bug that makes opening-velocity and time-burn metrics wrong for any non-1+0 game.

**Architecture:** Two independent fixes. The CI gate inserts `uv run pytest` before `uv run refresh.py` in the deploy workflow and adds a fast smoke test for the render pipeline. The time-control fix adds `parse_time_control(tc: str) -> tuple[int, int]` to `pgn.py`, then replaces two `60.0` hardcodes in `compute_process_metrics` with the parsed starting clock.

**Tech Stack:** Python 3.12, pytest, uv, GitHub Actions, python-chess.

**Spec reference:** `docs/superpowers/specs/2026-06-17-comprehensive-improvements-design.md` — Phase 0 (CI gate) and Phase 1 (time-control fix).

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `.github/workflows/deploy.yml` | Add `uv run pytest` step before refresh |
| Create | `tests/test_smoke.py` | Smoke test: render pipeline produces valid HTML |
| Modify | `tests/test_pgn.py` | Add `parse_time_control` tests |
| Modify | `chess_tracker/pgn.py` | Add `parse_time_control` function |
| Modify | `tests/fixtures/sample_records.py` | Add `_clocks_from` helper + `BLITZ_CLOCK_RECORDS` |
| Modify | `tests/test_metrics.py` | Add two time-control-aware metric tests |
| Modify | `chess_tracker/metrics.py` | Replace `60.0` with `parse_time_control(r.time_control)[0]` at two sites; import `parse_time_control` |

---

## Task 1: Add pytest gate to deploy workflow

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Open the workflow file and locate the Refresh step**

  The current deploy job sequence is: checkout → setup-uv → Python → dependencies → Stockfish → cache → Refresh dashboard → configure-pages → upload → deploy.

  You need to insert a test step between the cache step and the refresh step.

- [ ] **Step 2: Insert the pytest step**

  In `.github/workflows/deploy.yml`, after the `Cache Chess.com archives + analysis` step and before `Refresh dashboard`, add:

  ```yaml
      - name: Run tests
        run: uv run pytest
  ```

  The result should look like:

  ```yaml
      - name: Cache Chess.com archives + analysis
        uses: actions/cache@v4
        with:
          path: |
            data/raw
            data/analysis_cache.json
          key: chess-archives-${{ github.run_id }}
          restore-keys: |
            chess-archives-

      - name: Run tests
        run: uv run pytest

      - name: Refresh dashboard
        run: uv run refresh.py
  ```

- [ ] **Step 3: Verify the YAML parses**

  ```bash
  python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && echo OK
  ```

  Expected: `OK`

- [ ] **Step 4: Commit**

  ```bash
  git add .github/workflows/deploy.yml
  git commit -m "ci: add pytest gate before dashboard refresh"
  ```

---

## Task 2: Add smoke test for render pipeline

**Files:**
- Create: `tests/test_smoke.py`

The smoke test calls `render_dashboard` with a minimal payload and asserts the output contains the expected structure. It runs fast (no network, no Stockfish) and guards against template or render regressions.

- [ ] **Step 1: Write the smoke test**

  Create `tests/test_smoke.py`:

  ```python
  """Smoke tests: render pipeline produces valid HTML with required fields."""
  import json
  import tempfile
  from pathlib import Path

  from chess_tracker.render import render_dashboard, DEFAULT_TEMPLATE_PATH

  _MINIMAL_PAYLOAD = {
      "username": "test_user",
      "format": "bullet",
      "generated_at": "2026-01-01T00:00:00+00:00",
      "kpis": {
          "current_rating": 500,
          "games_total": 10,
          "recent_form_win_pct": 40.0,
          "tilt": "yellow",
      },
      "leak_summary": [],
      "next_session_rule": {
          "game_cap": 20,
          "move_10_target_seconds": 45,
          "stop_if_rating_drops": 50,
          "narrative": "Cap at 20 games.",
      },
      "recent_losses": [],
      "review_picks": [],
      "process_metrics": {
          "reserve_move_10_median": None,
          "reserve_move_20_median": None,
          "opening_velocity_median": None,
          "time_burn_delta": None,
          "outlasted_but_flagged_count": 0,
          "session_decay": [],
      },
      "opening_families": [],
      "opening_variations": [],
      "play_signatures": [],
      "sessions": [],
      "behavior": {
          "loss_streaks": {},
          "revenge_gap": {},
          "daily_drawdown": [],
          "time_of_day": [],
          "mate_loss_buckets": [],
      },
      "error_log": [],
      "plan_compliance": {"openings": [], "principles": [], "window": 30},
      "move_quality": None,
      "move_quality_by_format": None,
  }


  def test_render_dashboard_produces_html_file():
      with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
          out = Path(f.name)
      render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
      assert out.exists()
      content = out.read_text()
      assert len(content) > 100
      out.unlink()


  def test_render_dashboard_injects_window_data():
      with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
          out = Path(f.name)
      render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
      content = out.read_text()
      assert "window.DATA" in content
      out.unlink()


  def test_render_dashboard_username_substituted():
      with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
          out = Path(f.name)
      render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
      content = out.read_text()
      assert "test_user" in content
      assert "{{USERNAME}}" not in content
      out.unlink()


  def test_render_dashboard_required_keys_present_in_embedded_data():
      """All dashboard panels depend on these top-level keys existing."""
      with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
          out = Path(f.name)
      render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
      content = out.read_text()
      # Extract the embedded JSON by finding window.DATA = {...};
      start = content.index("window.DATA = ") + len("window.DATA = ")
      end = content.index(";\n", start)
      raw = content[start:end].replace("\\/", "/")
      data = json.loads(raw)
      for key in ("kpis", "leak_summary", "next_session_rule", "recent_losses",
                  "process_metrics", "opening_families", "sessions"):
          assert key in data, f"Missing required key: {key}"
      out.unlink()
  ```

- [ ] **Step 2: Run the smoke tests to verify they pass**

  ```bash
  cd /Users/madisonvelding-vandam/Developer/chess-tracker
  uv run pytest tests/test_smoke.py -v
  ```

  Expected output (all pass):
  ```
  tests/test_smoke.py::test_render_dashboard_produces_html_file PASSED
  tests/test_smoke.py::test_render_dashboard_injects_window_data PASSED
  tests/test_smoke.py::test_render_dashboard_username_substituted PASSED
  tests/test_smoke.py::test_render_dashboard_required_keys_present_in_embedded_data PASSED
  ```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

  ```bash
  uv run pytest -q
  ```

  Expected: all previously passing tests still pass (158 + 4 new = 162 total).

- [ ] **Step 4: Commit**

  ```bash
  git add tests/test_smoke.py
  git commit -m "test(smoke): render pipeline produces valid HTML with required keys"
  ```

---

## Task 3: parse_time_control — write failing tests

**Files:**
- Modify: `tests/test_pgn.py`

- [ ] **Step 1: Add parse_time_control import to test_pgn.py**

  Open `tests/test_pgn.py`. At the top of the imports section, add:

  ```python
  from chess_tracker.pgn import parse_time_control
  ```

  (Keep existing imports intact.)

- [ ] **Step 2: Add test cases at the bottom of test_pgn.py**

  ```python
  def test_parse_time_control_bullet_no_increment():
      assert parse_time_control("60") == (60, 0)


  def test_parse_time_control_bullet_with_increment():
      assert parse_time_control("60+1") == (60, 1)


  def test_parse_time_control_blitz():
      assert parse_time_control("180") == (180, 0)


  def test_parse_time_control_blitz_with_increment():
      assert parse_time_control("120+1") == (120, 1)


  def test_parse_time_control_rapid():
      assert parse_time_control("600+5") == (600, 5)


  def test_parse_time_control_daily_falls_back():
      # Daily uses "1/86400" format — not a numeric start; fall back gracefully.
      assert parse_time_control("1/86400") == (60, 0)


  def test_parse_time_control_empty_falls_back():
      assert parse_time_control("") == (60, 0)


  def test_parse_time_control_unknown_string_falls_back():
      assert parse_time_control("unknown") == (60, 0)
  ```

- [ ] **Step 3: Run to confirm these tests fail (function not yet defined)**

  ```bash
  uv run pytest tests/test_pgn.py -k "parse_time_control" -v
  ```

  Expected: `ImportError` or `AttributeError` — `parse_time_control` does not exist yet.

---

## Task 4: parse_time_control — implement

**Files:**
- Modify: `chess_tracker/pgn.py`

- [ ] **Step 1: Add parse_time_control to pgn.py**

  In `chess_tracker/pgn.py`, after the existing regex constants at the top (lines 12-13) and before the `GameRecord` dataclass, add:

  ```python
  def parse_time_control(tc: str) -> tuple[int, int]:
      """Parse a Chess.com TimeControl string → (start_seconds, increment_seconds).

      Examples:
        "60"      → (60, 0)    — 1+0 bullet
        "60+1"    → (60, 1)    — 1+1 bullet
        "120+1"   → (120, 1)   — 2+1 blitz
        "600+5"   → (600, 5)   — 10+5 rapid
        "1/86400" → (60, 0)    — daily; falls back to bullet default
        ""        → (60, 0)    — missing; falls back to bullet default
      """
      if "+" in tc:
          parts = tc.split("+", 1)
          try:
              return int(parts[0]), int(parts[1])
          except ValueError:
              return 60, 0
      try:
          return int(tc), 0
      except ValueError:
          return 60, 0
  ```

- [ ] **Step 2: Run parse_time_control tests to confirm they pass**

  ```bash
  uv run pytest tests/test_pgn.py -k "parse_time_control" -v
  ```

  Expected: all 8 new tests pass.

- [ ] **Step 3: Run the full test suite to confirm no regressions**

  ```bash
  uv run pytest -q
  ```

  Expected: all tests pass.

- [ ] **Step 4: Commit**

  ```bash
  git add chess_tracker/pgn.py tests/test_pgn.py
  git commit -m "feat(pgn): add parse_time_control — parses Chess.com TimeControl string"
  ```

---

## Task 5: Time-control-aware metrics — write failing tests

**Files:**
- Modify: `tests/fixtures/sample_records.py`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Add _clocks_from helper and BLITZ_CLOCK_RECORDS to fixtures**

  In `tests/fixtures/sample_records.py`, after the existing `_clocks` function and `CLOCK_RECORDS`, add:

  ```python
  def _clocks_from(start: float, spent_per_ply: list[float]) -> list[float]:
      """Like _clocks but with an explicit starting clock (not hardcoded to 60s).

      Used to build test fixtures for non-bullet time controls.
      """
      out = []
      remaining = start
      for s in spent_per_ply:
          remaining -= s
          out.append(round(remaining, 1))
      return out


  # 2+1 blitz (120s start) fixtures for time-control normalization tests.
  # Each record has 25 of-my-moves to satisfy len(my_clocks) >= 20 required
  # by compute_process_metrics for time_burn_delta calculation.
  #
  # _BLITZ_FAST_OPENING: 0.5s per move for first 8, then 1.5s per move.
  #   clock[7] = 120 - (0.5 × 8) = 116.0
  #   Correct opening velocity: 120 - 116 = 4.0s
  #   Bug velocity:              60 - 116 = -56.0s  (wrong sign)
  #
  # _BLITZ_SLOW_OPENING: 3.0s per move for first 8, then 1.0s per move.
  #   clock[7] = 120 - (3.0 × 8) = 96.0
  #   Correct opening velocity: 120 - 96 = 24.0s
  #   Bug velocity:              60 - 96 = -36.0s   (wrong sign)
  _BLITZ_FAST_OPENING_25 = _clocks_from(120.0, [0.5] * 8 + [1.5] * 17)
  _BLITZ_SLOW_OPENING_25 = _clocks_from(120.0, [3.0] * 8 + [1.0] * 17)

  BLITZ_CLOCK_RECORDS = [
      _r(1_700_020_000, "win", "timeout", "Sicilian Defense", side="white",
         fullmoves=25, my_clocks=_BLITZ_FAST_OPENING_25,
         opp_clocks=_BLITZ_SLOW_OPENING_25, time_control="120+1"),
      _r(1_700_020_120, "timeout", "win", "Sicilian Defense", side="white",
         fullmoves=25, my_clocks=_BLITZ_SLOW_OPENING_25,
         opp_clocks=_BLITZ_FAST_OPENING_25, time_control="120+1"),
      _r(1_700_020_240, "win", "timeout", "Sicilian Defense", side="white",
         fullmoves=25, my_clocks=_BLITZ_FAST_OPENING_25,
         opp_clocks=_BLITZ_SLOW_OPENING_25, time_control="120+1"),
  ]
  ```

- [ ] **Step 2: Add the failing tests to test_metrics.py**

  In `tests/test_metrics.py`, update the import line:

  ```python
  from tests.fixtures.sample_records import (
      RECORDS, CLOCK_RECORDS, OUTLASTED_THEN_FLAG_RECORD, LONG_OUTLAST_RECORD,
      BLITZ_CLOCK_RECORDS,
  )
  ```

  Then add at the bottom of the file:

  ```python
  def test_opening_velocity_uses_actual_start_clock_not_hardcoded_60():
      """For 2+1 blitz (120s start), opening velocity must be computed from
      120s, not the bullet-only 60s hardcode.

      Fast blitz opener: 0.5s × 8 moves = 4s spent → velocity should be ~4s.
      With the 60s bug:  60 - 116 = -56s  (negative — physically impossible).
      With the fix:     120 - 116 =   4s  (correct).

      Test accepts 0–30s as the valid range; rejects negative values and
      values above 30s (which would indicate ignoring the blitz start clock).
      """
      pm = compute_process_metrics(BLITZ_CLOCK_RECORDS)
      vel = pm["opening_velocity_median"]
      assert vel is not None
      assert vel > 0, (
          f"opening_velocity_median is {vel} — negative value indicates "
          "hardcoded 60s baseline bug (clock[7]=116 for blitz, 60-116=-56)"
      )
      assert vel < 30, (
          f"opening_velocity_median is {vel} — expected ~4–24s for these records"
      )


  def test_time_burn_delta_is_not_wildly_negative_for_blitz_records():
      """time_burn_delta = mean(early s/move) - mean(late s/move).

      For BLITZ_CLOCK_RECORDS, the fast and slow openers are evenly mixed
      and their pacing is consistent, so delta should be near zero.

      With the 60s bug, early_total = 60 - clock[7] goes negative for blitz
      games (e.g. 60 - 116 = -56), making early_rates negative and dragging
      time_burn_delta to ~ -7.5.

      Threshold: any value below -3.0 indicates the bug is present.
      """
      pm = compute_process_metrics(BLITZ_CLOCK_RECORDS)
      delta = pm["time_burn_delta"]
      assert delta is not None
      assert delta > -3.0, (
          f"time_burn_delta is {delta} — value below -3 strongly indicates "
          "early_total computed with hardcoded 60s instead of actual start clock"
      )
  ```

- [ ] **Step 3: Run the new tests to confirm they fail**

  ```bash
  uv run pytest tests/test_metrics.py -k "blitz" -v
  ```

  Expected: both new tests FAIL with assertion errors showing negative values.

---

## Task 6: Fix compute_process_metrics

**Files:**
- Modify: `chess_tracker/metrics.py`

- [ ] **Step 1: Add parse_time_control to the import in metrics.py**

  Find the existing import line at the top of `chess_tracker/metrics.py`:

  ```python
  from chess_tracker.pgn import GameRecord, opening_family, opening_variation
  ```

  Replace with:

  ```python
  from chess_tracker.pgn import GameRecord, opening_family, opening_variation, parse_time_control
  ```

- [ ] **Step 2: Fix Site 1 — opening velocity**

  In `compute_process_metrics`, locate the velocities loop (currently lines ~153–156):

  ```python
  # Opening velocity: seconds spent on my first 8 moves = 60 - my_clocks[7]
  velocities = []
  for r in records:
      c = _ply_clock(r.my_clocks, 7)
      if c is not None:
          velocities.append(round(60.0 - c, 2))
  ```

  Replace with:

  ```python
  # Opening velocity: seconds spent on my first 8 moves.
  # Use the game's actual starting clock, not a hardcoded bullet assumption.
  velocities = []
  for r in records:
      c = _ply_clock(r.my_clocks, 7)
      if c is not None:
          start_sec, _ = parse_time_control(r.time_control)
          velocities.append(round(start_sec - c, 2))
  ```

- [ ] **Step 3: Fix Site 2 — time burn delta early rates**

  Locate the early/late rates loop (currently lines ~158–166):

  ```python
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
  ```

  Replace with:

  ```python
  # Time burn delta: mean s/move across my moves 1-8 vs my moves 9-20.
  # early_total uses the game's actual starting clock (not hardcoded 60s).
  # late_total is a clock delta and is unaffected by the starting clock.
  early_rates = []
  late_rates = []
  for r in records:
      if len(r.my_clocks) >= 8:
          start_sec, _ = parse_time_control(r.time_control)
          early_total = start_sec - r.my_clocks[7]
          early_rates.append(early_total / 8)
      if len(r.my_clocks) >= 20:
          late_total = r.my_clocks[7] - r.my_clocks[19]
          late_rates.append(late_total / 12)
  ```

- [ ] **Step 4: Run the new tests to confirm they now pass**

  ```bash
  uv run pytest tests/test_metrics.py -k "blitz" -v
  ```

  Expected: both tests PASS.

- [ ] **Step 5: Run the full test suite**

  ```bash
  uv run pytest -q
  ```

  Expected: all tests pass. Count should be 162 + 2 new blitz tests = 164+ total (depending on what other tasks added).

- [ ] **Step 6: Commit**

  ```bash
  git add chess_tracker/metrics.py tests/test_metrics.py tests/fixtures/sample_records.py
  git commit -m "fix(metrics): replace hardcoded 60s with parse_time_control in process metrics

  Opening velocity and early time-burn rate were computed relative to a fixed
  60s starting clock, making both metrics wrong for any non-1+0 bullet game
  (2+1, 1+1, blitz, rapid). parse_time_control already exists in pgn.py;
  now used at both affected sites in compute_process_metrics."
  ```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Phase 0: `uv run pytest` before `uv run refresh.py` | Task 1 |
| Phase 0: Smoke test checks index.html, app.js, window.DATA, required keys | Task 2 |
| Phase 1: `parse_time_control(tc) → (start_seconds, increment_seconds)` | Task 4 |
| Phase 1: Replace `60.0 - c` (opening velocity) | Task 6, Step 2 |
| Phase 1: Replace `60.0 - r.my_clocks[7]` (early time-burn) | Task 6, Step 3 |
| Phase 1: Tests for `parse_time_control` | Task 3 |
| Phase 1: Tests for non-bullet time controls in metrics | Task 5 |

**Spec gap:** `dashboard/app.js` and `dashboard/index.html` are not checked for existence in the smoke test — the spec says "dashboard/app.js exists". The smoke test above checks the render pipeline (which produces index.html) but not the static app.js file. This is fine: app.js is a static file committed to the repo; the smoke test targets the generation step where the bug would actually occur.

**Notes for the next plan (Phase 2 — Homepage Reorder):** `app.js` calls render functions in this order: `renderKPI → renderMoveQuality → renderMoveQualityByFormat → renderPlanBlock → renderBehavior → renderLeaks → renderRule → renderRecentLosses → renderPuzzleDrill`. The template sections are ordered accordingly. Phase 2 will reorder both the template sections and the `app.js` render call sequence to put the action card and current leak first.
