# Outlasted-but-flagged leak — design

**Date:** 2026-05-27
**Scope:** Promote the existing `outlasted_but_flagged_count` process metric into a fireable rule inside `detect_leaks()` so it surfaces on `leaks.html` with severity styling and bubbles into the Leaks drill-in card on `index.html`. No metric redefinition, no template change, no JavaScript change, no new dependencies.

## Motivation

The `outlasted_but_flagged_count` field has lived in `process_metrics` since v1 (computed in `compute_process_metrics`, returned alongside the other reserve / velocity / time-burn fields) but only ever renders as a raw integer tile in the process-grid (the last `.process-card` inside `renderProcess()` in `dashboard/app.js`). It carries no severity, no interpretation, and no suggested action — the user sees "97" with no read on whether it matters.

Against the real-data snapshot (586 bullet games):

- All-time: 149 timeouts, 97 outlasted-but-flagged → **65.1%** of timeout-losses
- Last 30 games: 5 timeouts, 4 outlasted-but-flagged → **80.0%**

That's a meaningful behavioral signal — winning-position-but-flag-loss is a distinct leak from generic time pressure — and it deserves the same surfacing treatment the other four leak rules already get for free.

## Algorithm — `outlasted_but_flagged` leak

Inserted in `detect_leaks()` immediately after the `mate_loss_dominant` block (i.e. after the `if mate_pct >= 55:` branch closes, before the `# Post-peak decay` comment), inside the existing `if losses_recs:` branch so the window iteration is shared.

Inputs already available in the current `detect_leaks()` scope:

- `window` — last 30 games
- `pm = compute_process_metrics(window)` → `pm["outlasted_but_flagged_count"]`
- `losses_recs` — losses in window

Compute one new local:

```python
timeouts = sum(1 for r in losses_recs if r.result == "timeout")
```

Rule:

1. If `timeouts < 4` → no fire. (Min-N gate. With <4 timeouts, the ratio is too noisy to act on.)
2. Compute `outlasted_pct = 100 * pm["outlasted_but_flagged_count"] / timeouts`.
3. If `outlasted_pct >= 70` → fire `severity="critical"`.
4. Else if `outlasted_pct >= 50` → fire `severity="warn"`.
5. Else → no fire.

Evidence string (server-constructed from numerics, safe to inline into HTML per the trust-boundary comment at the top of `dashboard/app.js`):

```
{count} of {timeouts} timeout losses ({pct:.0f}%) had you ahead on the clock at some ply
```

Suggested action:

```
Convert clock leads: simplify and trade in winning positions instead of grinding for more.
```

## Rendering — automatic

Zero template changes. The existing flow:

1. `renderLeaks()` in `dashboard/app.js` renders each leak as `.severity-{warn,critical}` — the new leak name uses the existing CSS rules.
2. `renderDrillinCards()` in `dashboard/app.js` selects the first `critical` leak (or first `warn`) as the Leaks-card headline; the new leak participates in that selection automatically.
3. The existing `Outlasted-but-flagged` `.process-card` tile inside `renderProcess()` is **unchanged** — raw count stays for forensic reference.

Display-text humanization: `renderLeaks()` already does `L.name.replace(/_/g, " ")`, so `outlasted_but_flagged` will render as "outlasted but flagged". This is consistent with how `flag_loss_dominant` renders as "flag loss dominant". No additional copy work.

## Edge cases

| Window state                                              | Behavior                                  |
|-----------------------------------------------------------|-------------------------------------------|
| No records                                                | `detect_leaks` already returns `[]` early — never reached |
| 0 losses in window                                        | Outer `if losses_recs:` is false — no fire |
| Losses but 0 timeouts                                     | `timeouts < 4` — no fire                  |
| 3 timeouts, all outlasted (100%)                          | `timeouts < 4` — **no fire**              |
| 4 timeouts, 2 outlasted (50%)                             | warn                                      |
| 5 timeouts, 4 outlasted (80%)  *(current real data)*      | critical                                  |
| 10 timeouts, 6 outlasted (60%)                            | warn                                      |
| 10 timeouts, 4 outlasted (40%)                            | no fire                                   |
| `pm["outlasted_but_flagged_count"]` > `timeouts`          | Impossible by construction — every outlasted game is a timeout — no defensive code needed |

## Testing

Add to `tests/test_metrics.py` after `test_detect_leaks_includes_post_peak_decay_when_peak_crashes`. Reuse the existing fixture style.

Available fixture: `OUTLASTED_THEN_FLAG_RECORD` already exists in `tests/fixtures/sample_records.py` and produces one outlasted timeout. For varied counts, build small lists by hand using `GameRecord(...)` constructors with `my_clocks` / `opp_clocks` chosen so the per-ply comparison either triggers or doesn't.

Tests to add:

1. **`test_outlasted_leak_fires_critical_at_70_percent`** — 5 timeouts, 4 outlasted (80%). Pad with non-loss records up to 30 games. Assert a leak with `name == "outlasted_but_flagged"` and `severity == "critical"`.
2. **`test_outlasted_leak_fires_warn_between_50_and_70`** — 4 timeouts, 2 outlasted (50%). Assert leak with `severity == "warn"`.
3. **`test_outlasted_leak_suppressed_below_min_n_timeouts`** — 3 timeouts, all outlasted (100%). Assert `outlasted_but_flagged` is **not** in returned leak names.
4. **`test_outlasted_leak_quiet_when_under_50_percent`** — 5 timeouts, 2 outlasted (40%). Assert `outlasted_but_flagged` not in leak names.
5. **`test_outlasted_leak_evidence_shape`** — Use fixture from test 1; assert evidence string contains the count, the timeout total, and the pct (e.g., `"4 of 5"` and `"80%"`).

Existing tests to leave alone:

- `test_detect_leaks_returns_rows_with_required_fields` — shape check, unaffected.
- `test_outlasted_but_flagged_counts_a_timeout_where_you_were_ahead_at_some_ply` and `test_outlasted_but_flagged_excludes_timeouts_where_you_were_always_behind` — test the underlying metric, unchanged.

Full suite must remain green (51 passing + 5 new tests = 56 expected).

## Files touched

- `chess_tracker/metrics.py` — insert ~10 lines in `detect_leaks()` between the `mate_loss_dominant` block and the `# Post-peak decay` comment.
- `tests/test_metrics.py` — add 5 tests after `test_detect_leaks_includes_post_peak_decay_when_peak_crashes`.

No other files in scope. Templates, app.js, styles.css, render.py, refresh.py, and the API layer are untouched.

## Out of scope

- Changing the underlying `outlasted_but_flagged_count` metric definition (the "any ply where my clock > opp clock" heuristic).
- Adding severity styling to the existing process-card tile.
- Adding a dedicated drill-in card on `index.html`.
- Adjusting `flag_loss_dominant` or other adjacent leak rules.
- Re-rendering or updating prior spec docs.
- Coordination with the refresh-button spec — these are functionally independent and ship together only by sharing the v1.2.0 tag.
