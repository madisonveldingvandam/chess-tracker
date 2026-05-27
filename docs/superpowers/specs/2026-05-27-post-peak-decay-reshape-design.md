# Post-peak decay reshape — design

**Date:** 2026-05-27
**Scope:** Replace the v1 `mid_session_decay` leak rule with a peak-aware
`post_peak_decay` rule, and re-derive the `next_session_rule` game cap from the
same peak signal. No dashboard changes, no new dependencies.

## Motivation

Real bullet data peaks at games 11-20 within a session, then decays. The v1
rule (`chess_tracker/metrics.py:287-295`) compares only the `1-5` bucket to the
`21+` bucket and fires when the start is ≥10pp higher than the end. That misses
the peak-then-crash shape entirely.

The companion next-session game cap (`chess_tracker/metrics.py:319-326`)
inherits the same defect: it picks the *first* bucket where win% < 40, which
fires on cold-start dips even when the player is best mid-session. A player who
goes 35% / 55% / 65% / 45% gets capped at 5 games when their actual sweet spot
is games 11-20.

This reshape aligns both signals around the empirically observed shape.

## Algorithm — `post_peak_decay` leak

Inputs: the existing `decay = compute_session_decay(records)` output —
four rows for buckets `{1-5, 6-10, 11-20, 21+}`, each with `games` and `win_pct`.

1. Filter to buckets with `games ≥ 5` — call this set *eligible*.
2. If *eligible* has fewer than 2 buckets → no fire.
3. `peak` = eligible bucket with highest `win_pct`. **Tie-break: if two or more
   buckets are tied at the highest `win_pct`, pick the one with the highest
   position** (`1-5 < 6-10 < 11-20 < 21+`). This honors the "longest interval
   still at peak" framing and produces the more permissive cap.
4. `last` = eligible bucket with the highest position.
5. If `peak == last` → no fire (player is best at end of session; no decay).
6. If `peak.win_pct − last.win_pct ≥ 10` → fire `post_peak_decay`.

Severity: `warn` (tier-by-magnitude is deferred — keeps parity with the v1 rule).

Evidence string:

```
win% drops from {peak.win_pct:.0f}% in games {peak.bucket} to {last.win_pct:.0f}% in games {last.bucket}
```

Suggested action (unchanged in spirit): `"Cap sessions — see Next Session Rule."`

## Game cap derivation

In `next_session_rule`:

1. Compute the same `(peak, last, fired)` tuple. Extract a small helper
   `_post_peak_decay(decay)` returning that tuple so `detect_leaks` and
   `next_session_rule` share one source of truth.
2. If `fired` → `cap = {"1-5": 5, "6-10": 10, "11-20": 20}[peak.bucket]`.
   Peak can never be `"21+"` here because that would mean `peak == last` and
   the rule wouldn't have fired.
3. Otherwise → `cap = 30` (the current default).

The "first bucket where win% < 40" fallback is removed entirely. The cap is now
tied 1:1 to the leak signal.

## Edge cases

| Situation                                | Leak | Cap        |
|------------------------------------------|------|------------|
| No records                               | n/a  | 20 (existing empty-input default) |
| All buckets have <5 games                | no   | 30         |
| Only one bucket has ≥5 games             | no   | 30         |
| Monotonic increase (peak == last)        | no   | 30         |
| Monotonic decrease (peak = 1-5, last = 21+, drop ≥10pp) | yes | 5 |
| Peak at 11-20, drop to 21+ ≥10pp         | yes  | 20         |
| Peak at 11-20, drop to 21+ < 10pp        | no   | 30         |
| Tie at top win% between 6-10 and 11-20   | peak resolves to 11-20 | 20 (if rule fires) |

## Naming & backward compatibility

- Leak `name`: `"mid_session_decay"` → `"post_peak_decay"`.
- The dashboard (`dashboard/app.js`, `dashboard/styles.css`) renders leaks
  generically by `severity` and the `evidence` / `suggested_action` strings —
  no JavaScript or CSS change is required. Verified by grep: the only
  in-repo references to the old name are `chess_tracker/metrics.py:291`
  (definition) and the historical implementation-plan doc.
- `data/` is gitignored, so persisted JSON is not migrated.
- The original spec
  `docs/superpowers/specs/2026-05-26-bullet-chess-tracker-design.md` line 156
  documents the v1 rule. Treat the v1 spec as historical; this v1.1 spec
  supersedes it for the decay row. No edit to the v1 spec is required.

## Testing

Add the following tests to `tests/test_metrics.py`. Each uses a small synthetic
record list constructed to land games in the intended buckets (mirror the
fixture pattern already used by `test_compute_session_decay_returns_buckets`).

1. **Fires on peak-then-crash.** Construct a session whose `11-20` win% is ≥10pp
   above `21+` (both with ≥5 games). Assert a leak with `name == "post_peak_decay"`
   appears in `detect_leaks` output.
2. **Does not fire on monotonic increase.** Win% rises 1-5 → 21+. Assert no
   `post_peak_decay` leak.
3. **Does not fire below threshold.** Drop from peak to last is 9pp. Assert no
   leak.
4. **Does not fire when peak bucket has <5 games.** Strip the peak bucket to 4
   records. Assert no leak.
5. **Does not fire when last bucket has <5 games.** Strip the trailing bucket
   to 4 records. Assert no leak.
6. **Tie-break picks the later bucket.** Construct equal win% in `6-10` and
   `11-20`, with a steep drop to `21+`. Assert evidence string mentions
   `games 11-20` (not `6-10`) and the resulting cap is 20.
7. **`next_session_rule` caps at peak bucket end when leak fires.** Same
   fixture as test 1, assert `rule["game_cap"] == 20`.
8. **`next_session_rule` keeps default cap when no leak fires.** Monotonic
   increase fixture, assert `rule["game_cap"] == 30`.

Existing tests to leave alone unless they break:

- `test_compute_session_decay_returns_buckets` — bucket logic is unchanged.
- `test_detect_leaks_returns_rows_with_required_fields` — checks shape, not
  names.
- `test_next_session_rule_has_three_fields_plus_narrative` — checks keyset,
  not values.

Full suite must remain green (40 passing + new tests).

## Files touched

- `chess_tracker/metrics.py` — replace the `mid_session_decay` block at
  `metrics.py:284-295` and the cap loop at `metrics.py:319-326`. Add a
  private helper `_post_peak_decay(decay)` near `compute_session_decay` that
  returns `(fired: bool, peak_row: dict | None, last_row: dict | None)`.
- `tests/test_metrics.py` — add the eight tests above.

No other files are in scope. The dashboard, render layer, API, and spec
documents are untouched.

## Out of scope

- Tiered severity by drop magnitude (deferred).
- Approach B/C variants from brainstorming (any-after / pooled-after).
- Bucket boundary changes (the `{1-5, 6-10, 11-20, 21+}` bins remain).
- Re-rendering the v1 leak table in the original spec doc.
