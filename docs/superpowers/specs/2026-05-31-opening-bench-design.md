# Browsable opening bench on the landing page

**Date:** 2026-05-31
**Status:** Approved (design)

## Goal

On `index.html`, keep each side's committed openings prominent, and add a
scrollable "bench" of candidate openings being studied but not yet committed.
Bench lines carry the same adherence/win-rate stats and steppable board as
active ones — they are a display tier, not a separate data path.

## Motivation

The Plan & adherence block currently shows exactly the committed repertoire
(2 per side: one vs e4, one vs d4) straight from `plan.json`, with no cap. The
user wants to browse a few more candidate openings they're considering —
without burying the committed picks. A bench gives a place to park and study
candidates while still seeing how often they've already drifted into them.

## Design

### 1. Data model — `plan.json`

Each opening gains an optional `"status"`:

- `"active"` (or omitted) → committed repertoire, rendered prominently. The
  existing 4 entries need no edits — absent status defaults to active, so the
  change is backward compatible.
- `"bench"` → candidate, rendered in the scrollable shelf.

A bench entry is otherwise structurally identical (`name`, `side`,
`vs_first_move`, `target_family`, `moves`, `plan`, optional `match` / `lines`),
so it flows through the existing pipeline unchanged.

### 2. Metrics — `compute_plan_compliance` (metrics.py)

Add `"status": op.get("status", "active")` to the output opening dict
(`out_openings.append({...})`, ~line 779). No changes to adherence math: bench
lines compute exactly like active ones, including gambit breakdown when a
`match` rule is present. This satisfies the "stats too" requirement.

### 3. Rendering — `renderPlanBlock` (app.js)

Per side (As Black, then As White):

1. Render `status === "active"` cards first, in the current look.
2. If that side has any bench entries, render a `.plan-bench` container labeled
   *"Bench — studying"* holding the bench cards in the **same** `.plan-card`
   markup.

**Critical constraint:** board element IDs (`plan-board-${i}-${j}`,
`plan-prev/next/cap-${i}-${j}`) must stay on a **single global index `i`**
across active + bench cards so the existing board-wiring loop (which iterates
`ordered.forEach((o, i) => ...)`) keeps matching IDs without collisions. The
sort/grouping changes to interleave active-then-bench within each side, but the
flat index used for board IDs remains unique and shared between the markup pass
and the wiring pass.

### 4. Styles — `styles.css`

- `.plan-bench { max-height: 360px; overflow-y: auto; }` — vertical capped
  shelf (Approach A).
- `.plan-bench-label` — a muted sublabel ("Bench — studying").
- Reuse all existing `.plan-card` / `.plan-board` / severity styling unchanged.

### 5. Testing

- `test_metrics.py`: extend the plan-compliance test to assert `status` passes
  through — defaults to `"active"` when the plan entry omits it, and is
  `"bench"` when set.
- Manual: add one bench entry per side to `plan.json`, run `refresh.py`, and
  verify in the preview that active cards render as before and the bench shelf
  scrolls with working move-by-move boards.

## Out of scope (YAGNI)

- Promote/demote UI or drag-ordering between active and bench.
- Bench-only or candidate-specific metrics.
- Any cap or pagination beyond the scroll container.

Bench is purely a display tier over the existing adherence pipeline.
