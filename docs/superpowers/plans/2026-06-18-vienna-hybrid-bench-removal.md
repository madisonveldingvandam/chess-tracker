# Vienna Hybrid + Bench Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Four Knights Game opening with Vienna Hybrid, and remove the Bench system entirely (both data and UI).

**Architecture:** All opening data lives in `chess_tracker/plan.json`; the bench concept touches exactly four locations — `plan.json` (entries), `metrics.py` (weight logic), `app.js` (sort/render), and `styles.css` (CSS). Tasks proceed data-first, then backend, then frontend, then tests.

**Tech Stack:** Python 3.11, python-chess, pytest, vanilla JS (no framework), CSS variables, uv package manager.

---

## Vienna Hybrid — Research Summary

The **Vienna Hybrid** is a formally recognized opening: *Bishop's Opening: Berlin, Vienna Hybrid Variation* (ECO C28). It is **not** related to the King's Gambit — the d3 move is specifically what distinguishes it from the Vienna Gambit (which plays f4).

- **"Hybrid" means:** The position (Nc3 + Bc4 + d3) cannot be said to belong exclusively to the Vienna Game (2.Nc3) or the Bishop's Opening (2.Bc4); it is reached from either direction.
- **Canonical move order (Bishop's Opening side):** `1.e4 e5 2.Bc4 Nf6 3.d3 Nc6 4.Nc3`
- **Transposition order (Vienna Game side):** `1.e4 e5 2.Nc3 Nf6 3.Bc4 Nc6 4.d3` — identical position
- **Hromadka Variation:** Black plays `4...Bb4`; White answers `5.Ne2`
- **ECO:** C28; recognized on Chess.com, Lichess, ChessTempo, Wikipedia
- **target_family note:** When the user plays `2.Bc4` first, Chess.com classifies games as "Bishop's Opening". If they sometimes play `2.Nc3` first, those games become "Vienna Game". The plan entry uses "Bishop's Opening" — verify against actual game history if adherence looks wrong after first refresh.

---

## Files

| File | Change |
|---|---|
| `chess_tracker/plan.json` | Replace Four Knights entry → Vienna Hybrid; delete 2 bench entries |
| `chess_tracker/metrics.py` | Remove bench branch from `repertoire_weight` (lines 574–579) |
| `dashboard/app.js` | Simplify `renderPlanBlock`: remove bench sort/grouping/badge (lines 185–257) |
| `dashboard/styles.css` | Delete `.plan-bench-label` and `.plan-bench` rules (lines 164–177) |
| `tests/test_metrics.py` | Delete 2 bench tests; update `test_shipped_plan_has_white_entries_with_match_rules` |
| `tests/test_opening_match.py` | Replace `FK_RULE` + Four Knights tests with `VH_RULE` + Vienna Hybrid tests |

---

## Task 1: Replace Four Knights with Vienna Hybrid in plan.json

**Files:**
- Modify: `chess_tracker/plan.json`

- [ ] **Step 1: Write the failing test (shipped plan check)**

In `tests/test_metrics.py`, find the existing test `test_shipped_plan_has_white_entries_with_match_rules` at line 717. Replace it entirely with:

```python
def test_shipped_plan_has_white_entries_with_match_rules():
    """The shipped plan.json carries the two White move-pattern entries."""
    from chess_tracker.plan import load_plan

    plan = load_plan()
    by_name = {o["name"]: o for o in plan["openings"]}
    cz = by_name["Colle–Zukertort System"]
    assert cz["side"] == "white" and cz["vs_first_move"] == "d4"
    assert cz["match"]["white_forbids"] == ["Bf4"]
    vh = by_name["Vienna Hybrid"]
    assert vh["side"] == "white" and vh["vs_first_move"] == "e4"
    assert vh["match"]["white_requires"] == ["Bc4", "Nc3"]
    assert vh["match"]["white_forbids"] == ["f4"]
    assert "gambit_flags" not in vh["match"]
    assert "lines" not in vh
    # Black entries untouched.
    assert "Englund Gambit" in by_name
    assert "match" not in by_name["Englund Gambit"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
uv run pytest tests/test_metrics.py::test_shipped_plan_has_white_entries_with_match_rules -v
```

Expected: `FAILED` — `KeyError: 'Vienna Hybrid'`

- [ ] **Step 3: Update plan.json — replace the Four Knights entry**

In `chess_tracker/plan.json`, replace the entire Four Knights block (lines 33–45, the entry from `{` before `"name": "Four Knights Game"` through `}` before the Caro-Kann entry) with:

```json
    {
      "name": "Vienna Hybrid",
      "side": "white",
      "vs_first_move": "e4",
      "target_family": "Bishop's Opening",
      "moves": "1.e4 e5  2.Bc4 Nf6  3.d3 Nc6  4.Nc3  Bc5  5.Nf3  O-O  6.O-O  d6  7.h3  a6",
      "plan": "Vienna Hybrid (Bishop's Opening: Berlin Variation): 2.Bc4 then d3 — solid, slow structure. Both Bc4 and Nc3 must reach the board; d3 keeps the center flexible. Against ...Bb4 (Hromadka), answer Ne2. Do NOT play f4 — that converts to the Vienna Gambit.",
      "match": {
        "applicable_if_black_plays": "e5",
        "white_requires": ["Bc4", "Nc3"],
        "white_forbids": ["f4"],
        "window_plies": 12
      }
    },
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_metrics.py::test_shipped_plan_has_white_entries_with_match_rules -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/plan.json tests/test_metrics.py
git commit -m "feat: replace Four Knights with Vienna Hybrid in repertoire"
```

---

## Task 2: Remove Bench Entries from plan.json

**Files:**
- Modify: `chess_tracker/plan.json`

- [ ] **Step 1: Write the failing test**

Add this test at the end of `tests/test_metrics.py`:

```python
def test_shipped_plan_has_no_bench_entries():
    """plan.json must not contain any bench entries."""
    from chess_tracker.plan import load_plan
    plan = load_plan()
    bench = [o for o in plan["openings"] if o.get("status") == "bench"]
    assert bench == [], f"Found bench entries: {[o['name'] for o in bench]}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_metrics.py::test_shipped_plan_has_no_bench_entries -v
```

Expected: `FAILED` — `AssertionError: Found bench entries: ['Caro-Kann (bench)', 'London System (bench)']`

- [ ] **Step 3: Delete bench entries from plan.json**

In `chess_tracker/plan.json`, delete the two bench entries entirely. The file currently has 6 entries; after deletion it should have exactly 4. Delete the objects for:
- `"name": "Caro-Kann (bench)"` (the block from the `{` before it through its closing `}`)
- `"name": "London System (bench)"` (same)

The resulting `plan.json` `"openings"` array should contain only:
1. Pirc Defense
2. Englund Gambit
3. Colle–Zukertort System
4. Vienna Hybrid

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_metrics.py::test_shipped_plan_has_no_bench_entries -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/plan.json tests/test_metrics.py
git commit -m "feat: remove bench opening entries from plan.json"
```

---

## Task 3: Remove Bench Logic from metrics.py

**Files:**
- Modify: `chess_tracker/metrics.py` (lines 574–579)

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_metrics.py`:

```python
def test_compute_opening_families_no_bench_weight():
    """A plan entry with status='bench' must not get a different weight than 'active' —
    bench is no longer a recognized status; unknown status falls through to 0.25."""
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
    # "bench" is no longer handled — it should not be plan_status=="bench"
    # nor should it carry the 0.5 weight path; it maps to plan_status=="bench"
    # which is a stale concept but the field may still pass through for display.
    # What matters: only "active" gets 2.0 weight; anything else is 0.25.
    assert london_white["plan_status"] == "bench"   # field still passes through
```

Wait — this is tricky. The `plan_status` field is set from `plan_lookup.get((family, color))` which returns whatever is in the JSON, including `"bench"`. That's fine — we just remove the *weight* handling. The test that needs to change is about the weight calculation being simplified, not about `plan_status` field value.

Actually the right test here is to confirm the weight path: only "active" → 2.0, everything else → 0.25. The best way to test this is at the priority level. Instead, let's write a simpler test that confirms the branch is gone via code path: the test for `test_compute_opening_families_bench_status_propagated` that we're deleting was verifying a feature we're removing. So the failing test is just the existing bench status test that now should be *deleted*, confirmed by running the full suite.

Actually, we don't need a new test for the metrics.py cleanup — the behavior change is minor (bench weight 0.5 → drops to 0.25, which is the else branch). The important thing is to delete the dead code, and the two bench tests that rely on it.

Revised approach:
- [ ] **Step 1: Delete the two bench tests from test_metrics.py**

Find and delete these two test functions in `tests/test_metrics.py`:

First, delete `test_compute_plan_compliance_status_bench_passes_through` (lines 698–714):
```python
def test_compute_plan_compliance_status_bench_passes_through():
    """A bench opening keeps status='bench' and still computes adherence stats."""
    ...
    assert o["adherence_pct"] == 100.0
```

Second, delete `test_compute_opening_families_bench_status_propagated` (lines 1134–1146):
```python
def test_compute_opening_families_bench_status_propagated():
    """plan_status='bench' when plan entry has status='bench'."""
    ...
    assert london_white["plan_status"] == "bench"
```

- [ ] **Step 2: Run remaining tests to confirm they still pass**

```bash
uv run pytest tests/test_metrics.py -v 2>&1 | tail -20
```

Expected: all remaining tests pass (no bench tests listed)

- [ ] **Step 3: Simplify the bench branch in metrics.py**

In `chess_tracker/metrics.py`, find lines 574–579:
```python
        if plan_status == "active":
            repertoire_weight = 2.0
        elif plan_status == "bench":
            repertoire_weight = 0.5
        else:
            repertoire_weight = 0.25
```

Replace with:
```python
        if plan_status == "active":
            repertoire_weight = 2.0
        else:
            repertoire_weight = 0.25
```

- [ ] **Step 4: Run tests to confirm still passing**

```bash
uv run pytest tests/test_metrics.py -v 2>&1 | tail -10
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "refactor: remove bench concept from metrics weight logic and tests"
```

---

## Task 4: Replace Four Knights Tests with Vienna Hybrid Tests

**Files:**
- Modify: `tests/test_opening_match.py`

- [ ] **Step 1: Confirm which tests currently exist**

```bash
uv run pytest tests/test_opening_match.py -v 2>&1
```

Note the test names involving Four Knights / FK_RULE (should be 5 tests using FK_RULE).

- [ ] **Step 2: Replace FK_RULE and all FK tests**

In `tests/test_opening_match.py`, replace lines 8–62 (the `FK_RULE` constant and the Four Knights-specific tests) with the following. Keep the `CZ_RULE` constant and all Colle-Zukertort tests unchanged.

Replace the `FK_RULE` block (lines 8–14):
```python
FK_RULE = {
    "applicable_if_black_plays": "e5",
    "white_requires": ["Nf3", "Nc3"],
    "gambit_flags": {"Halloween": ["Nxe5"], "Belgrade": ["Nd5"]},
    "window_plies": 12,
}
```
With:
```python
VH_RULE = {
    "applicable_if_black_plays": "e5",
    "white_requires": ["Bc4", "Nc3"],
    "white_forbids": ["f4"],
    "window_plies": 12,
}
```

Replace the five FK test functions (lines 32–62) with:
```python
def test_vienna_hybrid_is_on_plan():
    m = match_opening("1.e4 e5 2.Bc4 Nf6 3.d3 Nc6 4.Nc3 Bc5", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True
    assert m["flags"] == []


def test_vienna_hybrid_transposition_is_on_plan():
    # Same position via Vienna Game move order: Nc3 before Bc4.
    m = match_opening("1.e4 e5 2.Nc3 Nf6 3.Bc4 Nc6 4.d3", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True


def test_vienna_gambit_f4_is_deviated():
    # f4 is the Vienna Gambit — forbidden in the Hybrid plan.
    m = match_opening("1.e4 e5 2.Nc3 Nc6 3.f4", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is False


def test_missing_bc4_is_deviated():
    # Nc3 present but no Bc4 -> not the hybrid.
    m = match_opening("1.e4 e5 2.Nc3 Nc6 3.Nf3 Nf6 4.d4", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is False


def test_e4_vs_non_e5_is_not_applicable():
    # Scandinavian: black does NOT play ...e5 -> Vienna Hybrid impossible.
    m = match_opening("1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5 4.d4 Nf6", VH_RULE)
    assert m["applicable"] is False
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
uv run pytest tests/test_opening_match.py -v
```

Expected: 7 tests pass (2 CZ + 5 new VH tests), all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_opening_match.py
git commit -m "test: replace Four Knights opening match tests with Vienna Hybrid"
```

---

## Task 5: Remove Bench UI from app.js

**Files:**
- Modify: `dashboard/app.js` (lines 185–257)

There are no automated tests for the frontend — verify visually after `refresh.py`.

- [ ] **Step 1: Simplify the sort in renderPlanBlock**

In `dashboard/app.js`, find `renderPlanBlock` at line 177. Replace lines 185–188 (sort logic):

```javascript
      const sideRank = (o) => (o.side === "black" ? 0 : 1);
      const statusRank = (o) => (o.status === "bench" ? 1 : 0);
      const ordered = [...openings].sort((a, b) =>
        sideRank(a) - sideRank(b) || statusRank(a) - statusRank(b));
```

With:
```javascript
      const sideRank = (o) => (o.side === "black" ? 0 : 1);
      const ordered = [...openings].sort((a, b) => sideRank(a) - sideRank(b));
```

- [ ] **Step 2: Remove bench tracking variables and injection**

Replace lines 189–203 (the `lastStatus` variable and bench injection logic inside the `.map()` callback) from:
```javascript
      let lastSide = null;
      let lastStatus = "active";
      const cardsHtml = ordered.map((o, i) => {
        let prefix = "";
        if (o.side !== lastSide) {
          // close an open bench wrapper from the previous side before its header
          if (lastStatus === "bench") prefix += `</div>`;
          prefix += `<h3 class="plan-side-header">${o.side === "black" ? "As Black" : "As White"}</h3>`;
          lastStatus = "active";
        }
        if (o.status === "bench" && lastStatus !== "bench") {
          prefix += `<div class="plan-bench-label">Bench — studying</div><div class="plan-bench">`;
        }
        lastSide = o.side;
        lastStatus = o.status || "active";
```

To:
```javascript
      let lastSide = null;
      const cardsHtml = ordered.map((o, i) => {
        let prefix = "";
        if (o.side !== lastSide) {
          prefix += `<h3 class="plan-side-header">${o.side === "black" ? "As Black" : "As White"}</h3>`;
        }
        lastSide = o.side;
```

- [ ] **Step 3: Remove the bench status badge from the card header**

In the same `renderPlanBlock` function, find line 218:
```javascript
              <span class="severity-${o.status === 'bench' ? 'neutral' : 'green'}" style="font-size:0.75rem;padding:1px 6px;border-radius:3px;">${o.status || 'active'}</span>
```

Delete this entire `<span>` line (the status badge). All openings are active — the badge is now redundant.

- [ ] **Step 4: Remove bench wrapper close at end of cardsHtml**

Find line 257:
```javascript
      root.innerHTML = cardsHtml + (lastStatus === "bench" ? "</div>" : "");
```

Replace with:
```javascript
      root.innerHTML = cardsHtml;
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "refactor: remove bench grouping and status badge from plan UI"
```

---

## Task 6: Remove Bench CSS from styles.css

**Files:**
- Modify: `dashboard/styles.css` (lines 164–177)

- [ ] **Step 1: Delete the bench CSS block**

In `dashboard/styles.css`, delete lines 164–177:
```css
/* Bench — a vertical scroll shelf of candidate openings under the active cards.
   Both wrappers are direct .plan-grid children, so they span the full grid row. */
.plan-bench-label {
  grid-column: 1 / -1;
  margin: 0.5rem 0 0.25rem;
  font-size: 0.8rem; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--muted);
}
.plan-bench {
  grid-column: 1 / -1;
  max-height: 360px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 0.6rem;
  padding-right: 4px;   /* keep scrollbar off the card edges */
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/styles.css
git commit -m "style: remove .plan-bench CSS rules"
```

---

## Task 7: Full Test Suite + Regenerate Dashboard

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
uv run pytest -v
```

Expected: all tests pass, zero failures.

- [ ] **Step 2: Regenerate computed.json**

```bash
uv run refresh.py
```

Expected: runs successfully, outputs `data/computed.json` (dashboard data updated with Vienna Hybrid).

- [ ] **Step 3: Serve and verify dashboard**

```bash
python3 -m http.server 8000 --directory dashboard &
open http://localhost:8000
```

Verify in the browser:
- "As Black" section shows Pirc Defense (vs 1.e4) and Englund Gambit (vs 1.d4)
- "As White" section shows Colle–Zukertort System (vs 1.d4) and Vienna Hybrid (vs 1.e4)
- No "Bench — studying" section visible anywhere
- Each card's "Show moves & plan" expands correctly with the move board
- Vienna Hybrid board steps through `1.e4 e5 2.Bc4 Nf6 3.d3 Nc6 4.Nc3 Bc5...`

- [ ] **Step 4: Kill the local server and commit**

```bash
kill %1  # or lsof -ti:8000 | xargs kill
git add data/computed.json
git commit -m "chore: regenerate dashboard with Vienna Hybrid repertoire"
```

---

## Self-Review

**Spec coverage:**
- ✅ Remove bench system — Tasks 2, 3, 5, 6 cover data, backend, frontend, CSS
- ✅ Only Queen's Pawn and King's Pawn starters, two cards per side — Task 2 leaves exactly 4 entries: 2 as Black (Pirc vs e4, Englund vs d4), 2 as White (CZ vs d4, Vienna Hybrid vs e4)
- ✅ Replace Four Knights with Vienna Hybrid — Tasks 1, 4

**Placeholder scan:** None found — all steps include exact code.

**Type consistency:** `VH_RULE` defined once in Task 4 and used in all VH tests in the same file. `by_name["Vienna Hybrid"]` in Task 1 matches `"name": "Vienna Hybrid"` in the plan.json entry.

**`target_family` note:** `"Bishop's Opening"` is the expected Chess.com family name when playing `2.Bc4`. If the user's game history shows the Vienna Hybrid games are tracked under `"Vienna Game"` instead (because move order 2.Nc3 was more common historically), change `target_family` to `"Vienna Game"` in `plan.json` — no other files need changing.
