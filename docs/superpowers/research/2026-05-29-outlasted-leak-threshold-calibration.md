# Outlasted-but-flagged — threshold calibration

**Date:** 2026-05-29
**Scope:** Read-only analysis. Empirically calibrate the `outlasted_but_flagged` leak rule (`chess_tracker/metrics.py::detect_leaks`) against the user's full bullet history (656 games, 627 rolling 30-game windows). No code changes — recommendation only.

## TL;DR

The current thresholds (`warn ≥ 50%`, `critical ≥ 70%`, `min_timeouts = 4`) were calibrated against a single anomalous 30-game window where 4 of 5 timeouts (80%) were outlasted. That snapshot is now historical: across **627 rolling 30-game windows in the user's full bullet history, exactly 0 windows would ever fire critical and only 4 would fire warn (0.6%)**. The rule is effectively dead at current thresholds.

The true distribution of outlasted-pct (in min-4-timeout windows) is: median 16.7%, P90 28.6%, P95 33.3%, P99 40.0%, **max 50.0%**. The critical threshold sits literally outside the entire observed sample space.

**Recommendation:** lower to `warn ≥ 30%`, `critical ≥ 45%`, keep `min_timeouts = 4`. This fires warn-or-above on 9.3% of historical windows (squarely in the 5-20% target band), critical on 0.6% (rare-but-possible), and does not fire on the current 30-game window (which sits at 12.5% — well below the user's typical 17% baseline, so it correctly stays quiet).

## 1. Current state

### Last 30 bullet games
- Timeout losses: **8**
- Outlasted-but-flagged: **1**
- Ratio: **12.5%**
- Rule fires today? **No.** Pct (12.5%) is below the 50% warn threshold. (The min-4 timeouts gate is satisfied; it's the percentage that doesn't clear.)

### All-time (656 bullet games)
- Total losses: 324
- Timeout losses: 160 (49.4% of all losses)
- Outlasted-but-flagged: 27
- Ratio: **16.9%** — this is the user's long-run baseline panic-conversion-failure rate.

Note: the spec doc dated 2026-05-27 cites "All-time 65.1%, last-30 80%" against a 586-game snapshot. Those numbers are not reproducible against the current `data/raw/`. Either the snapshot was a different filter (mixed time controls?), or the underlying `_is_loss`/`outlasted_but_flagged_count` logic has been refined since. Treat the numbers in *this* document as canonical for the current code path.

## 2. Historical sweep — rolling 30-game windows

Computed every 30-game rolling window across the 656-game bullet history (627 windows total). For each window, recomputed `compute_process_metrics(window)["outlasted_but_flagged_count"]` and the timeout count among losses in that window.

### Firing behavior at **current** thresholds (warn ≥ 50%, critical ≥ 70%, min_t = 4)

| Outcome | Windows | % of 627 |
|---|---:|---:|
| Critical | 0 | 0.0% |
| Warn | 4 | 0.6% |
| **Fires (warn-or-above)** | **4** | **0.6%** |
| Suppressed by min-N gate | 48 | 7.7% |
| Below 50% pct | 575 | 91.7% |

The current rule is essentially a null detector against this user's data.

### Distribution of outlasted-pct (windows with ≥ 4 timeouts — n=579)

```
   0- 10%: 114  ##########
  10- 20%: 206  ###################
  20- 30%: 201  ###################
  30- 40%:  47  ####
  40- 50%:   7
  50- 60%:   4
  60-100%:   0
```

| Statistic | Value |
|---|---:|
| Min | 0.0% |
| Median | 16.7% |
| Mean | 16.6% |
| **P75** | **22.2%** |
| **P80** | **25.0%** |
| **P85** | **27.3%** |
| **P90** | **28.6%** |
| **P95** | **33.3%** |
| P99 | 40.0% |
| Max | 50.0% |

Key takeaway: even the 99th-percentile-worst window across two years of bullet play tops out at 40%. The current `critical ≥ 70%` is calibrated against data the user does not produce.

### Timeout count distribution per window (n=627)

| Timeouts in window | Count |
|---:|---:|
| 2 | 19 |
| 3 | 29 |
| 4 | 62 |
| 5 | 83 |
| 6 | 91 |
| 7 | 58 |
| 8 | 73 |
| 9 | 78 |
| 10 | 57 |
| 11 | 38 |
| 12 | 19 |
| 13 | 16 |
| 14 | 4 |

Median 7 timeouts per 30-game window. The `min_t = 4` gate suppresses 7.7% of windows — those are noise-floor windows where the user mostly lost on mate/resign, not flag. Bumping min_t to 5 trims another ~10% of windows (12 percent of all windows total dropped); bumping to 3 only adds ~3% (3 → 4 timeouts is not a meaningful precision change). **min_t = 4 is well-tuned; leave it.**

## 3. Threshold sensitivity grid

10 interesting cells from the (warn × critical × min_t) grid. Skipped cells where critical ≤ warn or where the result duplicates a neighbor.

| min_t | warn % | crit % | Fires ≥ warn | Fires crit | Current 30-game fires? |
|---:|---:|---:|---|---|---|
| 4 | 50 | 70 | 4 (0.6%) | 0 (0.0%) | No  *(current rule)* |
| 4 | 35 | 50 | 16 (2.6%) | 4 (0.6%) | No |
| 4 | 30 | 45 | 58 (9.3%) | 4 (0.6%) | No  ← **recommended** |
| 4 | 30 | 40 | 58 (9.3%) | 11 (1.8%) | No |
| 4 | 25 | 40 | 141 (22.5%) | 11 (1.8%) | No |
| 4 | 25 | 35 | 141 (22.5%) | 16 (2.6%) | No |
| 4 | 20 | 35 | 259 (41.3%) | 16 (2.6%) | No |
| 5 | 30 | 45 | 54 (8.6%) | 0 (0.0%) | No |
| 5 | 25 | 40 | 120 (19.1%) | 7 (1.1%) | No |
| 3 | 30 | 45 | 63 (10.0%) | 4 (0.6%) | No |

Observations:

- The current 30-game window (12.5%) does not fire under any reasonable threshold pair — the user is currently *below* their own baseline of ~17%. This is good: the rule should stay quiet.
- The **target band of "fires 5-20% of windows" cleanly maps to `warn ∈ {25, 30}, critical ∈ {40, 45}` with min_t = 4 or 5**.
- The critical tier should NOT exceed ~45% — anything ≥ 50% would have fired zero criticals in two years and would be functionally indistinguishable from the current dead state.

## 4. Recommendation

**Use `warn ≥ 30%`, `critical ≥ 45%`, `min_timeouts = 4`.**

Justification:

1. **Warn rate 9.3%** — inside the 5-20% target band, leaning conservative. The user gets a warning roughly once per ten distinct 30-game contexts where this behavior is genuinely elevated relative to baseline.
2. **Critical rate 0.6%** — rare-but-non-zero. Critical fires only on the four worst windows in two years (the 50% tail). Severity escalation remains a real signal, not theatrical.
3. **30% warn = ~P90 of the distribution.** Triggering at the 90th percentile of the user's own historical behavior is the right semantic — "this is noticeably worse than your usual."
4. **45% critical = roughly P99.5.** It's slightly above the P99 mark (40%), so critical fires only on truly out-of-distribution windows.
5. **min_t = 4 stays.** Already well-calibrated; only suppresses 7.7% noise-floor windows where the rule shouldn't speak anyway.
6. **Current 30-game window does not fire** — correct behavior, since 12.5% is well below the user's 16.9% all-time baseline.

Why not the more aggressive `warn=25/crit=40`? Firing rate of 22.5% breaches the 20% ceiling — the rule starts adding noise rather than signal, and many "fires" would be windows at 25-29% which are within one standard deviation of the user's baseline.

Why not bump min_t to 5? Negligible behavioral difference (8.6% vs 9.3% firing) but the gate becomes harder to satisfy in low-timeout periods. Sticking with 4 keeps the rule live during normal play.

## 5. How to apply

In `chess_tracker/metrics.py`, lines 286 and 288 inside `detect_leaks()` (within the `if timeouts >= 4:` block):

```python
            if pct >= 70:        # line 286 — change to: if pct >= 45:
                sev = "critical"
            elif pct >= 50:      # line 288 — change to: elif pct >= 30:
                sev = "warn"
```

That is the entire change. The `timeouts >= 4` gate (line 283) is already correct and should stay. No test updates required for the *threshold* numerics if the existing fixture tests use exact-percentage construction (e.g., `test_outlasted_leak_fires_critical_at_70_percent`); those tests assert specific input ratios still produce specific severities — at 80% input, both old and new thresholds fire `critical`, so they remain green. Tests targeting the 50-69% band (warn under old, critical under new) and the 30-49% band (no-fire under old, warn under new) would need fixture-level reconsideration, but that is a test-design decision, not a code-change requirement of this calibration.
