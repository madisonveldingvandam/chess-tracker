# Opening Consolidation Design
**Date:** 2026-06-19
**Status:** Approved

## Problem

The opening families table currently shows 74 family-color rows. Many are 1–5 game entries (noise from Chess.com's granular ECO taxonomy) and several well-known opening systems are fragmented across multiple rows by Chess.com's position-based labeling (e.g. London System and Queens Pawn Opening are the same D02 system split into two rows). The result is an unreadable list that buries meaningful signal.

## Goal

Reduce the main opening table to ~10–14 rows of statistically meaningful data while keeping all variations fully drillable. Sub-threshold families remain accessible via an expandable "Rare Openings" basket.

---

## Design

### 1. Family Aliases (backend)

A static `FAMILY_ALIASES` dict in `metrics.py` maps donor family names to canonical names:

```python
FAMILY_ALIASES = {
    "London System":   "Queens Pawn Opening",
    "Colle System":    "Queens Pawn Opening",
    "Modern Defense":  "Pirc Defense",
    "Bishops Opening": "Italian Game",
}
```

**Rationale per alias:**
- `London System` → `Queens Pawn Opening`: identical ECO code D02; both are the user's 1.d4 system fragmented by move-order labeling (128 combined games)
- `Colle System` → `Queens Pawn Opening`: same d4 family; 3 games goes to Rare anyway but documents intent
- `Modern Defense` → `Pirc Defense`: both hypermodern ...g6 responses to 1.e4 (B06/B07); 58 combined games
- `Bishops Opening` → `Italian Game`: 2.Bc4 complex that transposes freely into Italian territory (27 combined games)

**Where applied:** In `compute_all()`, immediately after `blocked_dates` filtering and before any enrichment. One pass mutates `r.family` in place:

```python
for r in records:
    if r.family in FAMILY_ALIASES:
        r.family = FAMILY_ALIASES[r.family]
```

This ensures every downstream function — `enrich_with_sessions`, `compute_opening_families`, `compute_opening_variations`, `plan_compliance` — sees the canonical name consistently.

### 2. `is_rare` Flag (backend)

`compute_opening_families()` sets `is_rare: True` on any row where `games < 10`. No structural change to the `opening_families` array; it remains complete. The flag is the only addition.

**Threshold:** `games < 10`, consistent with the existing `sample_strength = "ignore"` tier.

### 3. Main Table Filtering (frontend)

When `app.js` populates the white and black opening family Tabulator tables, pre-filter the data to rows where `is_rare === false`. No other table logic changes.

### 4. Rare Openings Basket (frontend)

A native HTML `<details>`/`<summary>` element is added below each opening table (white and black separately):

```
▶ Rare Openings — 22 families with fewer than 10 games
```

When expanded, renders a compact list of the rare families: name, game count, Δ rating. Each entry links to its variation page (`opening.html?family=...&color=...`) — the full drill-down remains intact.

No changes to `opening.html` or the variation page. Rare families are fully navigable; they are only hidden from the main table surface.

---

## Data flow

```
raw ECOUrl slug
  → opening_family() → r.family (Chess.com label)
  → FAMILY_ALIASES applied in compute_all() → r.family (canonical)
  → compute_opening_families() → is_rare flag added
  → computed.json opening_families[]
  → app.js: is_rare=false → main table
           is_rare=true  → Rare Openings <details> basket
```

---

## Expected outcome

| | Before | After |
|---|---|---|
| Main table rows | ~74 | ~10–14 |
| Rare basket | — | ~22 families (expandable) |
| Variation drill-down | Unchanged | Unchanged (+ richer: London sub-lines appear under Queens Pawn Opening) |

---

## Files changed

| File | Change |
|---|---|
| `chess_tracker/metrics.py` | Add `FAMILY_ALIASES`; apply in `compute_all()`; add `is_rare` to `compute_opening_families()` |
| `dashboard/app.js` | Filter main table to `!is_rare`; add `<details>` rare basket below each table |
| `tests/test_metrics.py` | Cover alias application and `is_rare` flag |

---

## Known behaviour

**Bare alias games in the variation view:** A game labelled exactly "London System" (no sub-variation) has `r.variation = ""`. After aliasing, it shows in the Queens Pawn Opening variation drill-down as a "(main line)" row alongside other main-line QP games. Games with a Chess.com sub-variation label (e.g. "London System: Knight Variation") keep their variation suffix and show correctly. This is acceptable — the games are still present and drillable.

## Out of scope

- User-configurable aliases (annotations.json) — the current aliases are chess taxonomy facts, not preferences
- A third drill-down tier from variation → individual positions (play_signatures are computed but exposing them is a separate feature)
- Renaming the canonical family to something other than "Queens Pawn Opening" (user confirmed preference for Chess.com's label)
