# Opening Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the opening families table from 74 rows to ~10–14 by merging known Chess.com taxonomy duplicates and collapsing sub-10-game families into an expandable "Rare Openings" basket.

**Architecture:** A static `FAMILY_ALIASES` dict in `metrics.py` rewrites donor `r.family` values to canonical names inside `compute_all()` before any aggregation. `compute_opening_families()` gains an `is_rare` boolean flag (`games < 10`) on every output row. `renderFamilyBlock()` in `app.js` splits on that flag: non-rare rows go to the Tabulator table; rare rows render in a native `<details>` basket below it.

**Tech Stack:** Python 3.11, pytest, vanilla JS, Tabulator 6.x, CSS custom properties.

---

## File map

| File | Change |
|---|---|
| `chess_tracker/metrics.py` | Add `FAMILY_ALIASES` constant; apply in `compute_all()`; add `is_rare` in `compute_opening_families()` |
| `dashboard/app.js` | `renderFamilyBlock()`: filter main rows to `!is_rare`; inject `<details>` rare basket |
| `dashboard/styles.css` | Add `.rare-basket` and `.rare-table` rules |
| `tests/test_metrics.py` | New tests: alias application via `compute_all()`, `is_rare` flag via `compute_opening_families()` |

---

## Task 1: `FAMILY_ALIASES` constant + apply in `compute_all()`

**Files:**
- Modify: `chess_tracker/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metrics.py`:

```python
def test_compute_all_applies_family_aliases_london_to_queens_pawn():
    """London System records must appear as Queens Pawn Opening in the payload."""
    from chess_tracker.metrics import compute_all
    annotations = {"openings": {}, "games": {}, "error_log": [], "blocked_dates": []}
    # RECORDS has 3 London System white games and no Queens Pawn Opening games
    payload = compute_all(RECORDS, annotations, username="x")
    families = payload["opening_families"]
    assert not any(f["family"] == "London System" for f in families), (
        "London System should be aliased away"
    )
    qp = next((f for f in families
               if f["family"] == "Queens Pawn Opening" and f["color"] == "white"), None)
    assert qp is not None, "Queens Pawn Opening white row should exist after alias"
    assert qp["games"] == 3


def test_compute_all_does_not_alias_when_calling_compute_opening_families_directly():
    """Alias only applies via compute_all(), not when calling compute_opening_families directly."""
    from chess_tracker.metrics import compute_opening_families
    from chess_tracker.enrich import enrich_with_deltas, enrich_with_sessions
    recs = list(RECORDS)
    enrich_with_deltas(recs)
    enrich_with_sessions(recs)
    families = compute_opening_families(recs)
    # Calling directly: London System still present, no Queens Pawn Opening white row
    assert any(f["family"] == "London System" for f in families)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/madisonvelding-vandam/Developer/chess-tracker
.venv/bin/python -m pytest tests/test_metrics.py::test_compute_all_applies_family_aliases_london_to_queens_pawn tests/test_metrics.py::test_compute_all_does_not_alias_when_calling_compute_opening_families_directly -v
```

Expected: both FAIL (AssertionError — London System still present in payload).

- [ ] **Step 3: Add `FAMILY_ALIASES` constant and apply in `compute_all()`**

In `chess_tracker/metrics.py`, add after line 21 (after `OUTLASTED_MIN_PLY_INDEX`):

```python
# Maps Chess.com family labels that fragment the same opening system into one
# canonical name. Applied in compute_all() before any aggregation so all
# downstream metrics (variations, plan compliance, sessions) see one name.
FAMILY_ALIASES: dict[str, str] = {
    "London System":   "Queens Pawn Opening",
    "Colle System":    "Queens Pawn Opening",
    "Modern Defense":  "Pirc Defense",
    "Bishops Opening": "Italian Game",
}
```

In `chess_tracker/metrics.py`, inside `compute_all()`, add three lines immediately after the blocked-dates filter block (after line 830, before `enrich_with_deltas`):

```python
    for r in records:
        if r.family in FAMILY_ALIASES:
            r.family = FAMILY_ALIASES[r.family]
```

The block in context:

```python
    blocked = set(annotations.get("blocked_dates", []))
    if blocked:
        records = [r for r in records
                   if datetime.fromtimestamp(r.end_time).astimezone().date().isoformat()
                   not in blocked]
    for r in records:
        if r.family in FAMILY_ALIASES:
            r.family = FAMILY_ALIASES[r.family]
    enrich_with_deltas(records)
    enrich_with_sessions(records)
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_metrics.py::test_compute_all_applies_family_aliases_london_to_queens_pawn tests/test_metrics.py::test_compute_all_does_not_alias_when_calling_compute_opening_families_directly -v
```

Expected: both PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

```
.venv/bin/python -m pytest tests/ -q
```

Expected: all pass. The existing `test_compute_opening_families_plan_status_active` still sees "London System" because it calls `compute_opening_families` directly.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): add FAMILY_ALIASES to consolidate Chess.com taxonomy duplicates"
```

---

## Task 2: `is_rare` flag in `compute_opening_families()`

**Files:**
- Modify: `chess_tracker/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_metrics.py`:

```python
def test_compute_opening_families_is_rare_flag():
    """is_rare=True when games < 10; False when games >= 10."""
    from chess_tracker.pgn import GameRecord
    from chess_tracker.metrics import compute_opening_families
    from chess_tracker.enrich import enrich_with_deltas, enrich_with_sessions

    def _mk(n, family, result="win"):
        recs = [GameRecord(
            url=f"u{i}", end_time=i, time_class="bullet",
            side="white", my_rating=500, opp_rating=500,
            result=result, opp_result="checkmated",
            plies=20, fullmoves=10, opening=f"{family} Test Variation", eco="A00",
            family=family, variation="Test Variation",
        ) for i in range(n)]
        enrich_with_deltas(recs)
        enrich_with_sessions(recs)
        return recs

    # 5 games → rare
    rows = compute_opening_families(_mk(5, "Small Family"))
    assert rows[0]["is_rare"] is True

    # 9 games → rare (boundary: < 10)
    rows = compute_opening_families(_mk(9, "Almost Family"))
    assert rows[0]["is_rare"] is True

    # 10 games → not rare
    rows = compute_opening_families(_mk(10, "Big Family"))
    assert rows[0]["is_rare"] is False

    # 50 games → not rare
    rows = compute_opening_families(_mk(50, "Strong Family"))
    assert rows[0]["is_rare"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv/bin/python -m pytest tests/test_metrics.py::test_compute_opening_families_is_rare_flag -v
```

Expected: FAIL with `KeyError: 'is_rare'`.

- [ ] **Step 3: Add `is_rare` to `compute_opening_families()` output**

In `chess_tracker/metrics.py`, inside `compute_opening_families()`, find the `out.append({...})` block (around line 547). Add `"is_rare": n < 10,` after `"sample_strength": sample_strength,`:

```python
        out.append({
            "family": family,
            "color": color,
            "eco": eco_top,
            "games": n,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_pct": round(100 * wins / n, 1),
            "flag_pct": round(100 * flag / losses, 1) if losses else 0.0,
            "mate_pct": round(100 * mate / losses, 1) if losses else 0.0,
            "sum_rating_delta": sum_delta,
            "avg_rating_delta": avg_delta,
            "timeout_rating_delta": timeout_delta,
            "checkmate_rating_delta": mate_delta,
            "med_len": med_len,
            "avg_opp_rating": int(avg_opp),
            "rating_gap": int(rating_gap),
            "variation_count": len(sig_keys.get((family, color), set())),
            "canonical_play_signature": canonical_sig,
            "form": [_result_letter(r) for r in recs[-10:]],
            "plan_status": plan_status,
            "smoothed_win_rate": smoothed_win_rate,
            "sample_strength": sample_strength,
            "is_rare": n < 10,
            "priority": priority,
        })
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv/bin/python -m pytest tests/test_metrics.py::test_compute_opening_families_is_rare_flag -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```
.venv/bin/python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): add is_rare flag to opening_families (games < 10)"
```

---

## Task 3: Frontend — filter main table, inject rare basket

**Files:**
- Modify: `dashboard/app.js`
- Modify: `dashboard/styles.css`

No automated tests — verify manually by regenerating `computed.json` and loading in browser.

- [ ] **Step 1: Update `renderFamilyBlock()` in `dashboard/app.js`**

Replace the existing `renderFamilyBlock` function (lines 491–521) with:

```javascript
  function renderFamilyBlock(families, color, tableSelector, boardId, metaId, flip) {
    if (!document.querySelector(tableSelector)) return;
    const all = (families || []).filter(r => r.color === color);
    const rows = all.filter(r => !r.is_rare);
    const rare = all.filter(r => r.is_rare);
    const table = new Tabulator(tableSelector, {
      data: rows, layout: "fitColumns", height: "540px",
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
        {title: "Δ Rating", field: "sum_rating_delta", width: 90, sorter: "number", formatter: ratingDeltaCell},
        {title: "Win%", field: "win_pct", width: 75, sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", width: 75, sorter: "number"},
        {title: "Mate%", field: "mate_pct", width: 75, sorter: "number"},
        {title: "#Vars", field: "variation_count", width: 70, sorter: "number"},
        {title: "Form", field: "form", width: 110, formatter: sparkline, headerSort: false},
      ],
      initialSort: [{column: "sum_rating_delta", dir: "asc"}],
    });
    table.on("rowClick", (e, row) => selectFamilyRow(row, boardId, metaId, flip));
    table.on("rowDblClick", (e, row) => drillIntoFamily(row.getData()));
    table.on("tableBuilt", () => {
      const first = table.getRows()[0];
      if (first) selectFamilyRow(first, boardId, metaId, flip);
    });
    if (rare.length > 0) {
      const sigSplit = document.querySelector(tableSelector).closest(".sig-split");
      const det = document.createElement("details");
      det.className = "rare-basket";
      const label = rare.length === 1 ? "1 family" : `${rare.length} families`;
      const rareSorted = rare.slice().sort((a, b) => b.games - a.games);
      det.innerHTML = `<summary>Rare Openings — ${label} with fewer than 10 games</summary>` +
        `<table class="rare-table"><thead><tr><th>Opening</th><th>Games</th><th>Δ Rating</th></tr></thead><tbody>` +
        rareSorted.map(r => {
          const delta = r.sum_rating_delta >= 0 ? "+" + r.sum_rating_delta : String(r.sum_rating_delta);
          const qs = `family=${encodeURIComponent(r.family)}&color=${encodeURIComponent(r.color)}`;
          return `<tr><td><a href="opening.html?${qs}">${r.family}</a></td><td>${r.games}</td><td>${delta}</td></tr>`;
        }).join("") +
        `</tbody></table>`;
      sigSplit.after(det);
    }
  }
```

- [ ] **Step 2: Add CSS rules to `dashboard/styles.css`**

Append to the end of `dashboard/styles.css`:

```css
/* Rare Openings basket */
.rare-basket { margin-top: 0.75rem; }
.rare-basket > summary { cursor: pointer; color: var(--muted); font-size: 0.85rem; user-select: none; }
.rare-basket > summary:hover { color: var(--text); }
.rare-table { border-collapse: collapse; margin-top: 0.5rem; font-size: 0.82rem; }
.rare-table th { text-align: left; padding: 0.15rem 1.5rem 0.15rem 0; color: var(--muted); font-weight: 400; }
.rare-table td { padding: 0.15rem 1.5rem 0.15rem 0; }
.rare-table td:nth-child(2), .rare-table td:nth-child(3) { font-variant-numeric: tabular-nums; }
.rare-table a { color: var(--text); text-decoration: none; }
.rare-table a:hover { text-decoration: underline; }
```

- [ ] **Step 3: Regenerate `computed.json` and templates**

```
cd /Users/madisonvelding-vandam/Developer/chess-tracker
.venv/bin/python refresh.py --no-puzzles --no-analysis
```

- [ ] **Step 4: Verify `computed.json` reflects aliases and `is_rare` flag**

```
.venv/bin/python -c "
import json
with open('data/computed.json') as f:
    d = json.load(f)
fams = d['opening_families']
rare = [f for f in fams if f['is_rare']]
main = [f for f in fams if not f['is_rare']]
london = [f for f in fams if f['family'] == 'London System']
qp_w = [f for f in fams if f['family'] == 'Queens Pawn Opening' and f['color'] == 'white']
print(f'Total families: {len(fams)}')
print(f'Main (not rare): {len(main)}')
print(f'Rare: {len(rare)}')
print(f'London System rows remaining: {len(london)} (should be 0)')
print(f'Queens Pawn Opening white games: {qp_w[0][\"games\"] if qp_w else \"MISSING\"}')
print()
print('Main table families:')
for f in sorted(main, key=lambda x: x[\"sum_rating_delta\"]):
    print(f'  {f[\"color\"]:5} {f[\"games\"]:3}g  {f[\"sum_rating_delta\"]:+4}  {f[\"family\"]}')
"
```

Expected output: 0 London System rows, Queens Pawn Opening white with 128+ games, ~10–14 main rows, ~20+ rare rows.

- [ ] **Step 5: Run full test suite**

```
.venv/bin/python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.js dashboard/styles.css
git commit -m "feat(dashboard): filter opening table to non-rare rows; add Rare Openings basket"
```

---

## Task 4: Push and verify CI

- [ ] **Step 1: Push to origin**

```bash
git push
```

- [ ] **Step 2: Confirm CI passes**

```bash
gh run watch --exit-status
```

Expected: all steps green.
