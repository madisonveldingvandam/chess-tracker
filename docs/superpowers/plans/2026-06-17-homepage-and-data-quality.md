# Homepage Reorder + Data Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the action card and top leaks to the top of the homepage, reorder remaining sections by decision-relevance, and add smoothed win rates / sample labels / priority scores + plan-status join to the opening-family data.

**Architecture:** Three independent layers implemented sequentially. (1) Backend: `blunders_by_phase` in `analysis.py`, prerequisite for Phase 4 puzzle routing. (2) Frontend: template section reorder + new `renderActionCard` function in `app.js`. (3) Backend + frontend: `plan_status`, `smoothed_win_pct`, `sample_strength`, `priority` added to opening families in `metrics.py`, with plan-status chips in `app.js`.

**Tech Stack:** Python 3.12, pytest, uv, vanilla JS.

**Spec reference:** `docs/superpowers/specs/2026-06-17-comprehensive-improvements-design.md` — Phase 2 (Homepage Reorder) and Phase 3 (Data Quality + Backend Metrics Foundation).

**Worktree:** `.worktrees/homepage-and-data-quality` on branch `feat/homepage-and-data-quality`.

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `chess_tracker/analysis.py` | Add `blunders_by_phase` dict to `summarize()` output; aggregate in `aggregate_move_quality()` |
| Modify | `tests/test_analysis.py` | 3 new tests for `blunders_by_phase` |
| Modify | `chess_tracker/templates/index.html` | Add action-card section, reorder existing sections |
| Modify | `dashboard/app.js` | Add `renderActionCard`; reorder render calls; plan-status chips on plan cards; plan_status column in family table |
| Modify | `tests/test_metrics.py` | 6 new tests for plan_status and smoothed/priority fields |
| Modify | `chess_tracker/metrics.py` | Add `plan` param + `plan_status`, `plan_lookup` to `compute_opening_families`; add `smoothed_win_pct`, `sample_strength`, `priority`; update `compute_all` |

---

## Task 1: blunders_by_phase in analysis.py

**Files:**
- Test: `tests/test_analysis.py`
- Modify: `chess_tracker/analysis.py`

- [ ] **Step 1: Append 3 failing tests to tests/test_analysis.py**

```python
def test_summarize_includes_blunders_by_phase():
    from chess_tracker.analysis import MoveEval, summarize
    moves = [
        MoveEval.from_evals(ply=0, fullmove=1, cp_before=20, cp_after=-600, phase="opening"),
        MoveEval.from_evals(ply=2, fullmove=2, cp_before=20, cp_after=-600, phase="opening"),
        MoveEval.from_evals(ply=4, fullmove=3, cp_before=20, cp_after=-600, phase="middlegame"),
        MoveEval.from_evals(ply=6, fullmove=4, cp_before=20, cp_after=10,   phase="endgame"),
    ]
    s = summarize(moves)
    assert "blunders_by_phase" in s
    assert s["blunders_by_phase"]["opening"] == 2
    assert s["blunders_by_phase"]["middlegame"] == 1
    assert s["blunders_by_phase"].get("endgame", 0) == 0


def test_summarize_blunders_by_phase_empty_when_no_moves():
    from chess_tracker.analysis import summarize
    s = summarize([])
    assert "blunders_by_phase" in s
    assert s["blunders_by_phase"] == {}


def test_aggregate_move_quality_sums_blunders_by_phase():
    from chess_tracker.analysis import aggregate_move_quality
    summaries = [
        {
            "moves_analyzed": 2, "accuracy": 80.0, "avg_cp_loss": 50,
            "blunders": 1, "mistakes": 0, "inaccuracies": 0,
            "acpl_by_phase": {"opening": 50}, "moves_by_phase": {"opening": 2},
            "blunders_by_phase": {"opening": 1},
        },
        {
            "moves_analyzed": 3, "accuracy": 70.0, "avg_cp_loss": 30,
            "blunders": 2, "mistakes": 0, "inaccuracies": 0,
            "acpl_by_phase": {"middlegame": 30}, "moves_by_phase": {"middlegame": 3},
            "blunders_by_phase": {"opening": 1, "middlegame": 1},
        },
    ]
    result = aggregate_move_quality(summaries)
    assert "blunders_by_phase" in result
    assert result["blunders_by_phase"]["opening"] == 2
    assert result["blunders_by_phase"]["middlegame"] == 1
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_analysis.py -k "blunders_by_phase" -v
```

Expected: 3 FAIL — `blunders_by_phase` key missing.

- [ ] **Step 3: Add blunders_by_phase to the zero-moves return in summarize()**

In `chess_tracker/analysis.py`, find the `summarize` function's early return (line ~131):

```python
    if n == 0:
        return {
            "moves_analyzed": 0, "accuracy": None, "avg_cp_loss": None,
            "blunders": 0, "mistakes": 0, "inaccuracies": 0,
            "acpl_by_phase": {}, "moves_by_phase": {},
        }
```

Replace with:

```python
    if n == 0:
        return {
            "moves_analyzed": 0, "accuracy": None, "avg_cp_loss": None,
            "blunders": 0, "mistakes": 0, "inaccuracies": 0,
            "acpl_by_phase": {}, "moves_by_phase": {}, "blunders_by_phase": {},
        }
```

- [ ] **Step 4: Add blunders_by_phase computation before the main return in summarize()**

Find the main `return {` at the end of `summarize` (line ~146). Just before it, add:

```python
    blunders_by_phase: dict[str, int] = {}
    for m in moves:
        if m.label == "blunder":
            blunders_by_phase[m.phase] = blunders_by_phase.get(m.phase, 0) + 1
```

Then add `"blunders_by_phase": blunders_by_phase,` to the return dict so it becomes:

```python
    return {
        "moves_analyzed": n,
        "accuracy": round(accuracy, 1),
        "avg_cp_loss": round(avg_cp_loss),
        "blunders": sum(1 for m in moves if m.label == "blunder"),
        "mistakes": sum(1 for m in moves if m.label == "mistake"),
        "inaccuracies": sum(1 for m in moves if m.label == "inaccuracy"),
        "acpl_by_phase": acpl_by_phase,
        "moves_by_phase": moves_by_phase,
        "blunders_by_phase": blunders_by_phase,
    }
```

- [ ] **Step 5: Add blunders_by_phase aggregation to aggregate_move_quality()**

In `chess_tracker/analysis.py`, find `aggregate_move_quality` (line ~263). Just before its `return {`, add:

```python
    agg_blunders_by_phase: dict[str, int] = {}
    for s in summaries:
        for phase, count in s.get("blunders_by_phase", {}).items():
            agg_blunders_by_phase[phase] = agg_blunders_by_phase.get(phase, 0) + count
```

Then add `"blunders_by_phase": agg_blunders_by_phase,` to the return dict.

- [ ] **Step 6: Run the 3 new tests to confirm they pass**

```bash
uv run pytest tests/test_analysis.py -k "blunders_by_phase" -v
```

Expected: 3 PASS.

- [ ] **Step 7: Run the full suite**

```bash
uv run pytest -q
```

Expected: 172 + 3 = 175 passing.

- [ ] **Step 8: Commit**

```bash
git add chess_tracker/analysis.py tests/test_analysis.py
git commit -m "feat(analysis): add blunders_by_phase to summarize() and aggregate_move_quality()"
```

---

## Task 2: Homepage reorder + action card

**Files:**
- Modify: `chess_tracker/templates/index.html`
- Modify: `dashboard/app.js`

No new unit tests (JS functions; the smoke test guards HTML structure). If the smoke test breaks, the task is not complete.

- [ ] **Step 1: Replace the entire `<main>...</main>` block in chess_tracker/templates/index.html**

Current `<main>` block (lines 11–57):

```html
  <main>
    <section id="move-quality-block">
      <h2>Move quality <small>recent games · engine-analyzed</small></h2>
      <div id="move-quality-cards" class="behavior-grid"></div>
    </section>
    <section id="move-quality-by-format">
      <h2>By format <small>accuracy &amp; blunders per time class</small></h2>
      <div id="mqf-table"></div>
    </section>
    <section id="plan-block">
      <h2>Plan &amp; adherence <small>last 30 games · edit chess_tracker/plan.json to change</small></h2>
      <div id="plan-openings" class="plan-grid"></div>
    </section>
    <section id="behavior-block">
      <h2>Behavior — current state</h2>
      <div id="behavior-cards" class="behavior-grid"></div>
    </section>
    <section id="white-block">
      <h2>White <small>click a row to see the position · double-click to drill into variations</small></h2>
      <div class="sig-split">
        <div id="white-families-table"></div>
        <aside class="board-panel">
          <div class="board-large" id="white-board"></div>
          <div class="board-meta" id="white-board-meta"></div>
        </aside>
      </div>
    </section>
    <section id="black-block">
      <h2>Black <small>click a row to see the position · double-click to drill into variations</small></h2>
      <div class="sig-split">
        <div id="black-families-table"></div>
        <aside class="board-panel">
          <div class="board-large" id="black-board"></div>
          <div class="board-meta" id="black-board-meta"></div>
        </aside>
      </div>
    </section>
    <section id="drillin-section">
      <h2>Drill in</h2>
      <div id="drillin-cards" class="drillin-grid"></div>
    </section>
    <section id="principles-block">
      <h3>Universal principles</h3>
      <ol id="plan-principles" class="plan-principles"></ol>
    </section>
  </main>
```

Replace with:

```html
  <main>
    <!-- 1. Action card: next-session rule + top 1-2 leaks inline -->
    <section id="action-card-block">
      <div id="action-card"></div>
      <div id="current-leak-inline"></div>
    </section>
    <!-- 2. Repertoire adherence (moved up) -->
    <section id="plan-block">
      <h2>Plan &amp; adherence <small>last 30 games · edit chess_tracker/plan.json to change</small></h2>
      <div id="plan-openings" class="plan-grid"></div>
    </section>
    <!-- 3. Move quality (moved down) -->
    <section id="move-quality-block">
      <h2>Move quality <small>recent games · engine-analyzed</small></h2>
      <div id="move-quality-cards" class="behavior-grid"></div>
    </section>
    <section id="move-quality-by-format">
      <h2>By format <small>accuracy &amp; blunders per time class</small></h2>
      <div id="mqf-table"></div>
    </section>
    <!-- 4. Opening tables -->
    <section id="white-block">
      <h2>White <small>click a row to see the position · double-click to drill into variations</small></h2>
      <div class="sig-split">
        <div id="white-families-table"></div>
        <aside class="board-panel">
          <div class="board-large" id="white-board"></div>
          <div class="board-meta" id="white-board-meta"></div>
        </aside>
      </div>
    </section>
    <section id="black-block">
      <h2>Black <small>click a row to see the position · double-click to drill into variations</small></h2>
      <div class="sig-split">
        <div id="black-families-table"></div>
        <aside class="board-panel">
          <div class="board-large" id="black-board"></div>
          <div class="board-meta" id="black-board-meta"></div>
        </aside>
      </div>
    </section>
    <!-- 5. Behavior -->
    <section id="behavior-block">
      <h2>Behavior — current state</h2>
      <div id="behavior-cards" class="behavior-grid"></div>
    </section>
    <!-- 6. Drill-in + principles -->
    <section id="drillin-section">
      <h2>Drill in</h2>
      <div id="drillin-cards" class="drillin-grid"></div>
    </section>
    <section id="principles-block">
      <h3>Universal principles</h3>
      <ol id="plan-principles" class="plan-principles"></ol>
    </section>
  </main>
```

- [ ] **Step 2: Replace the render call block at the top of the IIFE in dashboard/app.js**

Find (lines 14–34):

```js
  renderKPI(D);
  renderMoveQuality(D.move_quality);
  renderMoveQualityByFormat(D.move_quality_by_format, D.format);
  renderPlanBlock(D.plan_compliance);
  renderBehavior(D.behavior);
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderPuzzleDrill(D.recent_losses);
  renderLossSummary(D);
  renderReviewPicks(D.review_picks);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics?.session_decay);
  renderFamilyBlock(D.opening_families, "white",
    "#white-families-table", "white-board", "white-board-meta", false);
  renderFamilyBlock(D.opening_families, "black",
    "#black-families-table", "black-board", "black-board-meta", true);
  renderOpeningDetail(D);
  renderSessions(D.sessions);
  renderDrillinCards(D);
```

Replace with:

```js
  renderKPI(D);
  renderActionCard(D);
  renderPlanBlock(D.plan_compliance);
  renderMoveQuality(D.move_quality);
  renderMoveQualityByFormat(D.move_quality_by_format, D.format);
  renderFamilyBlock(D.opening_families, "white",
    "#white-families-table", "white-board", "white-board-meta", false);
  renderFamilyBlock(D.opening_families, "black",
    "#black-families-table", "black-board", "black-board-meta", true);
  renderBehavior(D.behavior);
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderPuzzleDrill(D.recent_losses);
  renderLossSummary(D);
  renderReviewPicks(D.review_picks);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics?.session_decay);
  renderOpeningDetail(D);
  renderSessions(D.sessions);
  renderDrillinCards(D);
```

- [ ] **Step 3: Add the renderActionCard function to dashboard/app.js**

After the closing `}` of `renderKPI` (around line 60), insert:

```js
  // Action card: top of index.html only. Shows next-session rule + the top
  // 1-2 leaks so the most actionable info is visible without scrolling.
  // Falls back gracefully if elements are absent (other pages don't have them).
  function renderActionCard(D) {
    const cardRoot = document.getElementById("action-card");
    const leakRoot = document.getElementById("current-leak-inline");
    if (!cardRoot) return;
    const rule = D.next_session_rule;
    if (!rule) { cardRoot.innerHTML = ""; return; }
    cardRoot.innerHTML = `
      <h2>Next session</h2>
      <div class="action-rule">
        <span>${rule.game_cap} games max</span> ·
        <span>${rule.move_10_target_seconds}s left at move 10</span> ·
        <span>Stop if rating drops ${rule.stop_if_rating_drops}</span>
      </div>
      <div class="rule-narrative">${rule.narrative}</div>
    `;
    if (!leakRoot) return;
    const leaks = D.leak_summary || [];
    if (leaks.length === 0) {
      leakRoot.innerHTML = `<div class="leak severity-neutral">No active leaks — all clear.</div>`;
      return;
    }
    leakRoot.innerHTML = leaks.slice(0, 2).map(L => `
      <div class="leak severity-${L.severity}">
        <div class="leak-name">${L.name.replace(/_/g, " ")}</div>
        <div class="leak-evidence">${L.evidence}</div>
        <div class="leak-action">→ ${L.suggested_action}</div>
      </div>
    `).join("");
  }
```

- [ ] **Step 4: Run smoke tests to confirm they still pass**

```bash
uv run pytest tests/test_smoke.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run the full suite**

```bash
uv run pytest -q
```

Expected: 175 passing.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/templates/index.html dashboard/app.js
git commit -m "feat(ui): reorder homepage — action card first, move quality after repertoire"
```

---

## Task 3: plan_status backend join in compute_opening_families

**Files:**
- Test: `tests/test_metrics.py`
- Modify: `chess_tracker/metrics.py`

- [ ] **Step 1: Append 3 failing tests to tests/test_metrics.py**

```python
def test_compute_opening_families_plan_status_none_without_plan():
    """Without a plan arg, every row has plan_status=None."""
    from chess_tracker.metrics import compute_opening_families
    families = compute_opening_families(RECORDS)
    for row in families:
        assert "plan_status" in row
        assert row["plan_status"] is None


def test_compute_opening_families_plan_status_active():
    """plan_status='active' when family+side matches an active plan entry.
    RECORDS has 'London System' as white and 'Italian Game' as black.
    """
    from chess_tracker.metrics import compute_opening_families
    plan = {
        "openings": [
            {"target_family": "London System", "side": "white",
             "name": "London System", "status": "active"},
        ]
    }
    families = compute_opening_families(RECORDS, plan=plan)
    london_white = next(r for r in families
                        if r["family"] == "London System" and r["color"] == "white")
    assert london_white["plan_status"] == "active"
    italian_black = next(r for r in families
                         if r["family"] == "Italian Game" and r["color"] == "black")
    assert italian_black["plan_status"] is None


def test_compute_opening_families_bench_status_propagated():
    """plan_status='bench' when plan entry has status='bench'."""
    from chess_tracker.metrics import compute_opening_families
    plan = {
        "openings": [
            {"target_family": "London System", "side": "white",
             "name": "London System", "status": "bench"},
        ]
    }
    families = compute_opening_families(RECORDS, plan=plan)
    london_white = next(r for r in families
                        if r["family"] == "London System" and r["color"] == "white")
    assert london_white["plan_status"] == "bench"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_metrics.py -k "plan_status" -v
```

Expected: 3 FAIL — `compute_opening_families` doesn't accept `plan` and `plan_status` key is absent.

- [ ] **Step 3: Update compute_opening_families signature in chess_tracker/metrics.py**

Find the function definition (line ~491):

```python
def compute_opening_families(records: list[GameRecord]) -> list[dict]:
```

Replace with:

```python
def compute_opening_families(records: list[GameRecord], plan: dict | None = None) -> list[dict]:
```

- [ ] **Step 4: Add plan_lookup after the docstring in compute_opening_families**

After the `"""..."""` docstring block, before `groups: dict[tuple[str, str], list[GameRecord]] = {}`, add:

```python
    plan_lookup: dict[tuple[str, str], str] = {}
    for op in (plan or {}).get("openings", []):
        tf = op.get("target_family")
        side = op.get("side")
        if tf and side:
            plan_lookup[(tf, side)] = op.get("status", "active")
```

- [ ] **Step 5: Add plan_status local var just before out.append() in the loop body**

Inside the `for (family, color), recs in groups.items():` loop, just before the `out.append({` call, add:

```python
        plan_status = plan_lookup.get((family, color))
```

Then add `"plan_status": plan_status,` to the `out.append({...})` dict.

- [ ] **Step 6: Update compute_all to pass plan to compute_opening_families**

Find in `compute_all` (line ~841):

```python
        "opening_families": compute_opening_families(records),
```

Replace with:

```python
        "opening_families": compute_opening_families(records, plan=plan or {}),
```

- [ ] **Step 7: Run the plan_status tests to confirm they pass**

```bash
uv run pytest tests/test_metrics.py -k "plan_status" -v
```

Expected: 3 PASS.

- [ ] **Step 8: Run the full suite**

```bash
uv run pytest -q
```

Expected: 175 + 3 = 178 passing.

- [ ] **Step 9: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): add plan_status to compute_opening_families via plan.json backend join"
```

---

## Task 4: smoothed_win_pct + sample_strength + priority

**Files:**
- Test: `tests/test_metrics.py`
- Modify: `chess_tracker/metrics.py`

- [ ] **Step 1: Append 3 failing tests to tests/test_metrics.py**

```python
def test_compute_opening_families_smoothed_win_pct_laplace():
    """smoothed_win_pct = round((wins + 2) / (games + 4), 3) for every row."""
    from chess_tracker.metrics import compute_opening_families
    families = compute_opening_families(RECORDS)
    for row in families:
        assert "smoothed_win_pct" in row
        expected = round((row["wins"] + 2) / (row["games"] + 4), 3)
        assert abs(row["smoothed_win_pct"] - expected) < 0.001


def test_compute_opening_families_sample_strength_thresholds():
    """sample_strength labels: <10→ignore, <30→weak, <100→usable, ≥100→strong."""
    from chess_tracker.pgn import GameRecord
    from chess_tracker.metrics import compute_opening_families

    def _mk(n, result="win"):
        return [GameRecord(
            url=f"u{i}", end_time=i, time_class="bullet",
            side="white", my_rating=500, opp_rating=500,
            result=result, opp_result="checkmated",
            plies=20, fullmoves=10, opening="Test Opening", eco="A00",
        ) for i in range(n)]

    for n, expected_label in [(5, "ignore"), (15, "weak"), (50, "usable"), (100, "strong")]:
        rows = compute_opening_families(_mk(n))
        assert rows[0]["sample_strength"] == expected_label, (
            f"{n} games → expected {expected_label!r}, "
            f"got {rows[0]['sample_strength']!r}"
        )


def test_compute_opening_families_priority_underperformers_rank_higher():
    """priority ≥ 0 always; a below-average opening outranks an above-average one."""
    from chess_tracker.pgn import GameRecord
    from chess_tracker.metrics import compute_opening_families

    good = [GameRecord(url=f"g{i}", end_time=i, time_class="bullet",
                       side="white", my_rating=500, opp_rating=500,
                       result="win", opp_result="checkmated",
                       plies=20, fullmoves=10, opening="Good Opening", eco="A00")
            for i in range(10)]
    bad = [GameRecord(url=f"b{i}", end_time=100 + i, time_class="bullet",
                      side="white", my_rating=500, opp_rating=500,
                      result="timeout", opp_result="win",
                      plies=20, fullmoves=10, opening="Bad Opening", eco="B00")
           for i in range(10)]
    rows = compute_opening_families(good + bad)
    for row in rows:
        assert row["priority"] >= 0
    good_row = next(r for r in rows if r["family"] == "Good Opening")
    bad_row = next(r for r in rows if r["family"] == "Bad Opening")
    assert bad_row["priority"] > good_row["priority"]
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_metrics.py -k "smoothed_win_pct or sample_strength or priority_under" -v
```

Expected: 3 FAIL — fields not present.

- [ ] **Step 3: Add overall_win_pct before the groups loop in compute_opening_families**

In `chess_tracker/metrics.py`, inside `compute_opening_families`, after `plan_lookup` is built and before `groups: dict = {}`, add:

```python
    total_records = len(records)
    overall_win_pct = (
        sum(1 for r in records if _is_win(r.result)) / total_records
        if total_records else 0.5
    )
```

- [ ] **Step 4: Add smoothed_win_pct, sample_strength, and priority just before out.append() in the loop**

In the loop body, after `plan_status = plan_lookup.get((family, color))` (added in Task 3), add:

```python
        smoothed_win_pct = round((wins + 2) / (n + 4), 3)

        if n < 10:
            sample_strength = "ignore"
        elif n < 30:
            sample_strength = "weak"
        elif n < 100:
            sample_strength = "usable"
        else:
            sample_strength = "strong"

        if plan_status == "active":
            repertoire_weight = 2.0
        elif plan_status == "bench":
            repertoire_weight = 0.5
        else:
            repertoire_weight = 0.25
        underperformance = max(0.0, overall_win_pct - smoothed_win_pct)
        priority = round(n * underperformance * repertoire_weight, 2)
```

Then add these three fields to `out.append({...})`:

```python
            "smoothed_win_pct": smoothed_win_pct,
            "sample_strength": sample_strength,
            "priority": priority,
```

- [ ] **Step 5: Run the 3 new tests to confirm they pass**

```bash
uv run pytest tests/test_metrics.py -k "smoothed_win_pct or sample_strength or priority_under" -v
```

Expected: 3 PASS.

- [ ] **Step 6: Run the full suite**

```bash
uv run pytest -q
```

Expected: 178 + 3 = 181 passing.

- [ ] **Step 7: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): add smoothed_win_pct, sample_strength, priority to opening families"
```

---

## Task 5: Plan status chips + plan_status column (app.js only)

**Files:**
- Modify: `dashboard/app.js`

No unit tests (JS rendering). Smoke tests guard HTML structure.

- [ ] **Step 1: Add status chip to plan cards in renderPlanBlock**

In `renderPlanBlock`, find the template literal building the `plan-head` div. Currently:

```js
            <div class="plan-head">
              <span class="plan-vs">${vs}</span>
              <span class="plan-name">${o.name}</span>
              <span class="plan-adherence">${o.adherence_pct}% adherence</span>
            </div>
```

Replace with:

```js
            <div class="plan-head">
              <span class="plan-vs">${vs}</span>
              <span class="plan-name">${o.name}</span>
              <span class="severity-${o.status === 'bench' ? 'neutral' : 'green'}" style="font-size:0.75rem;padding:1px 6px;border-radius:3px;">${o.status || 'active'}</span>
              <span class="plan-adherence">${o.adherence_pct}% adherence</span>
            </div>
```

- [ ] **Step 2: Add plan_status column to renderFamilyBlock Tabulator columns**

In `renderFamilyBlock`, find the `columns:` array. After the `Opening` column definition, add:

```js
        {title: "Plan", field: "plan_status", width: 70, headerSort: false,
         formatter: c => {
           const v = c.getValue();
           if (!v) return "";
           const cls = v === "active" ? "severity-green" : "severity-neutral";
           return `<span class="${cls}" style="font-size:0.75rem;padding:1px 5px;border-radius:3px;">${v}</span>`;
         }},
```

The full columns array should start:

```js
      columns: [
        {title: "Opening", field: "family", headerFilter: "input", minWidth: 180},
        {title: "Plan", field: "plan_status", width: 70, headerSort: false,
         formatter: c => {
           const v = c.getValue();
           if (!v) return "";
           const cls = v === "active" ? "severity-green" : "severity-neutral";
           return `<span class="${cls}" style="font-size:0.75rem;padding:1px 5px;border-radius:3px;">${v}</span>`;
         }},
        {title: "Games", field: "games", width: 75, sorter: "number"},
        ...rest unchanged...
      ],
```

- [ ] **Step 3: Run smoke tests**

```bash
uv run pytest tests/test_smoke.py -v
```

Expected: 4 PASS.

- [ ] **Step 4: Run full suite**

```bash
uv run pytest -q
```

Expected: 181 passing.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "feat(ui): plan status chips on adherence cards; plan_status column in family tables"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Phase 2: Section order — action card → plan block → move quality → opening tables → behavior → drillin → principles | Task 2 |
| Phase 2: Action card with game_cap, move_10_target_seconds, stop_if_rating_drops | Task 2 |
| Phase 2: Top 1-2 leaks inline (rest on leaks page) | Task 2 |
| Phase 2: app.js render order updated | Task 2 |
| Phase 3: `blunders_by_phase` in `summarize()` | Task 1 |
| Phase 3: `blunders_by_phase` aggregated in `aggregate_move_quality()` | Task 1 |
| Phase 3: `smoothed_win_pct = (wins + 2) / (games + 4)` | Task 4 |
| Phase 3: `sample_strength` labels (ignore/weak/usable/strong) | Task 4 |
| Phase 3: `plan_status` via backend join in `compute_opening_families` | Task 3 |
| Phase 3: `priority = games × underperformance × weight` | Task 4 |
| Phase 3: `repertoire_weight` active=2.0 bench=0.5 other=0.25 | Task 4 |
| Phase 3: `plan` passed through `compute_all` | Task 3 |
| Phase 3: Active/bench chips on plan cards | Task 5 |
| Phase 3: `plan_status` column in family tables | Task 5 |

**Known gaps:**
- `smoothed_win_pct` and `sample_strength` not yet added to `compute_opening_variations`. The spec says "add to both functions" — deferred to avoid scope creep; the opening detail page (opening.html) is lower priority than the main page.
- The spec describes "two lists — Repertoire repairs vs Other costly openings" as a frontend display. This plan adds the `plan_status` and `priority` data but shows them as a single table column, not split tables. A full split would require two Tabulator instances per color-block and is scoped to a follow-up UI task.
- Phase 4 section order slot (puzzle queue placeholder) — puzzle rendering already exists as `renderPuzzleDrill` on losses.html; homepage promotion deferred to Phase 4 plan.
