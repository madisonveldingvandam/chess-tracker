# Opponent Analysis + Training Prescription Design

**Date:** 2026-06-17
**Status:** Locked — pending adversarial review before writing-plans

---

## Goals

1. **Priority 1 — Opponent opening patterns:** identify what opening sequences (first 8+ actual moves, not Chess.com labels) opponents use to beat the user. Both sides (user as White and as Black).
2. **Priority 2 — Early blunder analysis + named trap exposure:** identify where in the opening/early middlegame the user blunders, and which named traps/systems appear in their losses.
3. **Training prescription:** surface one clear next action per session derived from the above data.

---

## Section 1: Architecture + Caching

**Core principle:** One Stockfish scan per game, results cached. All downstream features read from the cache — the engine never scans the same game twice.

### `data/analysis_cache.json` — internal, not frontend-facing

```json
{
  "_meta": {
    "schema_version": 1,
    "analysis_version": "2026-06-17",
    "engine": "stockfish",
    "depth": 12,
    "ply_limit": 40
  },
  "games": {
    "<game_url>": {
      "game_hash": "<hash>",
      "analyzed_at": "<timestamp>",
      "plies": [
        {
          "ply": 0,
          "phase": "opening",
          "is_user_move": true,
          "fen_before": "...",
          "played_uci": "e2e4",
          "played_san": "e4",
          "best_uci": "d2d4",
          "best_san": "d4",
          "best_reply_uci": "e7e5",
          "score_before_user_cp": 20,
          "score_after_user_cp": -40,
          "loss_cp_from_user_perspective": 60,
          "is_user_blunder": false
        }
      ]
    }
  }
}
```

**Ply indexing:** zero-indexed. ply 0 = first played move, ply 39 = 40th ply.

**Centipawn perspective:** all scores from the user's perspective (positive = user is better). `loss_cp_from_user_perspective = max(0, score_before_user_cp - score_after_user_cp)` for user moves; `null` for opponent moves. Mate scores clamped to ±2000cp before arithmetic.

**`best_reply_uci`:** engine's best move for the opponent after the user's played move (used for material-loss proxy).

**`is_user_blunder`:** only meaningful when `is_user_move = true`. Threshold defined in the cache module.

**Phase ranges:**
- `opening` = plies 0–15 (moves 1–8)
- `early_middlegame` = plies 16–39 (moves 9–20)

**Cache invalidation:** if `schema_version`, `depth`, `ply_limit`, or `analysis_version` changes, cached entries are stale and re-analyzed.

**Atomic writes:** write to `analysis_cache.json.tmp`, then rename.

**`game_hash`:** stored per entry for stale/corrupt detection.

### CI persistence

`analysis_cache.json` is gitignored and not deployed. GitHub Actions saves/restores it via `actions/cache`:

```yaml
key: analysis-cache-v1-${{ hashFiles('data/raw/**') }}
restore-keys:
  analysis-cache-v1-
```

If cache is missing, the run rebuilds from scratch (expensive but correct). Deploy never publishes the cache.

### `computed.json` — frontend-facing only

Summaries, counts, labels, puzzle references only. No per-ply engine data. Pipeline warns if file grows unexpectedly.

### Incremental analysis

Only games absent from the cache get analyzed. First full run is expensive; subsequent refreshes are near-instant.

**Runtime budget — benchmark-driven:**

```
Benchmark first 25 games before locking depth/ply_limit.
Per-game target: < 5s average at depth 12, ply_limit 40.
CI budget: 15 min total refresh.
If projected full-run exceeds CI budget:
  → analyze only new/recent games in scheduled CI
  → keep full rebuild as manual command (--full-scan flag)
Depth is configurable; 12 is the default.
```

Cache trimming: if cache exceeds 5MB, trim games outside the active analysis window (not by age alone).

### Graceful degradation

If Stockfish unavailable or times out on a game: skip, log to `error_log`, continue. Dashboard still builds. Engine-dependent cards show "analysis unavailable." Dashboard shows:

```
Engine analysis available for 184 / 200 recent games.
```

### Integration in `refresh.py`

```
fetch raw games
→ parse GameRecords
→ analyze_new_games(records, cache)   ← one Stockfish scan per new game
→ compute_all(records, cache)         ← all features read from cache
→ attach_puzzles(records, cache)      ← reads best_uci/fen from cache, no second scan
→ render
```

---

## Section 2: Opponent Opening Patterns

**New module:** `chess_tracker/opponent_openings.py`

### `extract_opp_moves(game_record, parsed_move_list)`

Uses the parsed move list from the PGN tree — not string-splitting `opening_moves`. Extracts the opponent's first 4 SAN moves:
- `my_side == "black"` → opponent is White (even-indexed plies)
- `my_side == "white"` → opponent is Black (odd-indexed plies)

**SAN normalization:** strip `!`, `?`, `!?`, `?!`, `+`, `#`. Keep captures, promotions, disambiguation, castling. `Nf3+` → `Nf3`, `Bxf7+` → `Bxf7`, `O-O` → `O-O`, `Nbd2` → `Nbd2`.

**Move count handling:**
- Fewer than 2 opponent moves → skip as `too_short`
- 2–3 opponent moves → return shorter prefix, include `opp_move_count` field
- 4+ opponent moves → use first 4

Returns `None` with skip reason if data is null, unparseable, or too short.

**Tests required:** White user, Black user, short game, null `opening_moves`, castling, captures/checks, fewer-than-4-opponent-moves.

**4 opponent moves is a deliberate anti-fragmentation choice** — a 12-ply window contains up to 6 moves per side; 4 is chosen to keep clusters trainable.

### `compute_opponent_opening_stats(records)`

Takes **all games** (not only losses). Per game:
- Determine user side and opponent side
- Extract opponent's first 4 moves (or skip with reason)
- Record result from user perspective (win/loss/draw)
- Attach grouping keys: `exact_line`, `play_signature` (skip level if unavailable), `opening_family`, `broad_side`

Per group, compute: `game_count`, `win_count`, `draw_count`, `loss_count`, `loss_pct = loss_count / game_count`.

**Grouping fallback — backend selects one level globally:**

```
1. exact_line      — use if N ≥ 5 for at least one group
2. play_signature  — fallback if N ≥ 5 (skip if play_signature unavailable)
3. opening_family  — fallback if N ≥ 3
4. broad_side      — always available
```

Backend picks the most specific level that produces at least one medium-or-strong group. Frontend renders prepared rows only.

**`play_signature`** is the canonical FEN/position key after 8 plies, if available. Skip this fallback level if not available rather than failing.

**`broad_side`** values: `opponent_as_white` / `opponent_as_black`. Display as "Opponent White openings" / "Opponent Black openings".

**Confidence thresholds:**

```
N < 3:   hidden
N 3–4:   weak
N 5–9:   medium
N >= 10: strong
```

**Kill criterion:** if `exact_line` and `play_signature` both produce no N≥5 groups, do not show a line-specific opponent-openings table. Fall back to existing `opening_family` rollup.

**Audit counters** in `computed.json`:

```json
"opponent_openings_audit": {
  "total_groups_before_filter": 42,
  "groups_hidden_low_sample": 31,
  "groups_shown": 11,
  "games_excluded_null_opening": 8,
  "games_excluded_too_short": 3
}
```

**Sort:** loss_count desc → confidence desc → loss_pct desc → game_count desc.

### `computed.json` shape

```json
"opponent_openings": [
  {
    "opponent_side": "white",
    "opp_moves": ["e4", "Nf3", "Bc4", "Ng5"],
    "opp_line": "White: e4 Nf3 Bc4 Ng5",
    "opp_move_count": 4,
    "game_count": 18,
    "win_count": 3,
    "draw_count": 1,
    "loss_count": 14,
    "loss_pct": 77.8,
    "confidence": "strong",
    "grouping_level": "exact_line"
  }
]
```

**Dashboard:** new subsection in `opening.html` — flat table sorted by loss count, confidence tag shown, audit summary visible. No boards in V1.

---

## Section 3: Early Blunder Phase Analysis

**Covers plies 0–39 only.** Answers where early-game user blunders cluster: opening vs early middlegame. Does not diagnose endgames or late middlegame.

Reads `is_user_blunder = true` entries from `analysis_cache.json`. Opponent blunders ignored. Blunder threshold defined in the cache module (Section 1).

Phase ranges:
- `opening` = plies 0–15
- `early_middlegame` = plies 16–39

`avg_loss_cp` and `worst_single_loss_cp` are computed over `is_user_blunder = true` entries only.

**Format note:** analysis matches the active dashboard dataset. Do not silently mix bullet/blitz/rapid unless the dashboard explicitly aggregates all formats.

### `computed.json` shape

```json
"blunder_phases": {
  "opening": {
    "user_move_count": 812,
    "blunder_count": 34,
    "blunder_rate": 0.042,
    "affected_games": 28,
    "phase_eligible_games": 192,
    "affected_game_pct": 14.6,
    "avg_loss_cp": 180,
    "worst_single_loss_cp": 620
  },
  "early_middlegame": {
    "user_move_count": 1190,
    "blunder_count": 51,
    "blunder_rate": 0.043,
    "affected_games": 39,
    "phase_eligible_games": 200,
    "affected_game_pct": 19.5,
    "avg_loss_cp": 220,
    "worst_single_loss_cp": 800
  }
},
"engine_coverage": {
  "analyzed_games": 184,
  "eligible_games": 200
}
```

`phase_eligible_games` = games long enough to have moves in that phase range; used as denominator for `affected_game_pct` (prevents short games from distorting the metric).

**Dashboard:** "Early blunders by phase" table in `losses.html`.

---

## Section 4: Named Opening/Trap Exposure

**Informational only in V1.** Does not drive the main puzzle prescription. Answers: "What named traps/systems have I repeatedly seen?"

Main training prescription derives from blunder phase + loss type + material-loss proxy + personal-loss puzzles.

**New module:** `chess_tracker/trap_patterns.py`

Detection runs against the normalized parsed SAN move list from the PGN tree — not `opening_moves` display string. May reuse `_norm()` from `opening_match.py`.

### Pattern definition

```json
{
  "id": "fried_liver_attack",
  "name": "Fried Liver Attack",
  "target_user_side": "black",
  "signature": ["e4", "Nf3", "Bc4", "Ng5", "exd5", "Nxf7"],
  "detection_note": "Nxf7 sac on move 6; opponent must be White"
}
```

**Signatures are ordered subsequence matches** (not contiguous — intervening moves allowed). Side-aware: each pattern specifies which side is the attacker. One hit per pattern per game maximum. `hit_count = win_count + draw_count + loss_count`.

**Fool's Mate note:** strip `#` for normalization but verify mate occurred; do not fire on partial sequences ending in `Qh4` without mate confirmation.

### V1 library — move-sequence detectable only

Patterns that require board-state or mate-pattern recognition are deferred to V2.

| ID | Name | Target user side |
|---|---|---|
| `scholars_mate` | Scholar's Mate | black |
| `fried_liver_attack` | Fried Liver Attack | black |
| `fools_mate` | Fool's Mate | black |
| `halloween_gambit` | Halloween Gambit | black |
| `belgrade_gambit` | Belgrade Gambit | black |
| `budapest_gambit` | Budapest Gambit | white |
| `englund_gambit` | Englund Gambit | white |

**Deferred pending precise tested signatures:** Legal's Trap, Elephant Trap, Noah's Ark Trap.

**Deferred to V2 (require board-state detection):** Back-Rank Mate, Smothered Mate, Opera Mate.

### Tests required per pattern

Positive detection, negative detection, wrong side does not count, partial sequence does not count, annotation noise does not fragment detection.

### Confidence thresholds

Same as Section 2: N<3 hidden, 3–4 weak, 5–9 medium, ≥10 strong.

### `computed.json` shape

```json
"trap_exposures": [
  {
    "id": "fried_liver_attack",
    "name": "Fried Liver Attack",
    "hit_count": 8,
    "win_count": 1,
    "draw_count": 0,
    "loss_count": 7,
    "loss_pct": 87.5,
    "confidence": "strong"
  }
],
"trap_exposure_audit": {
  "games_scanned": 200,
  "hits_before_filter": 45,
  "patterns_deferred": 3
}
```

**Sort:** loss_count desc → confidence desc → loss_pct desc → hit_count desc → name asc.

**Dashboard:** "Known opening traps encountered" — flat table in `opening.html`.

---

## Section 5: UX / Prescription Clarity

**Core rule:** The dashboard must produce one clear next action within 10 seconds of loading. Every new card either supports that action or is secondary.

### Prescription hierarchy

If `next_session_rule` exists (user-set): show it as the primary top action. Data-derived prescription appears directly below it, labeled "Suggested prep for that rule."

If no `next_session_rule` exists: data-derived prescription is the primary top action.

### Prescription derivation

Assembled from available signals only — never infer tactic types from phase data alone:

```
Phase     → tells WHEN the blunder happened (opening vs early middlegame)
Material-loss proxy → tells WHETHER to recommend hanging-piece / capture-defender puzzles
Loss type → tells clock vs mate-defense vs material work
```

Phase tie-breaking: blunder_rate desc → affected_games desc → avg_loss_cp desc → early_middlegame before opening if still tied.

**Minimum data thresholds** to show engine-derived prescription:
- `engine_coverage.analyzed_games >= 20`
- phase `user_move_count >= 50`
- `blunder_count >= 3`

Below threshold: fall back to loss_type only.

**Fundamentals-first training order:**
```
1. 10 basic tactics
2. 5 hanging-piece checks  (only if material-loss proxy is dominant)
3. 2 personal-loss puzzles from the worst phase
```

### Loss-type fallback map

```
timeout:     "Use a clock rule this session: no move longer than X seconds before move 20."
checkmate:   "Do basic mate-in-1, mate-in-2, and back-rank recognition before playing."
resignation: "Review 2 recent resignation losses before playing; identify the first material drop."
other:       (no prescription shown)
```

### Backend outputs `training_prescription` object

Frontend renders, does not reason:

```json
"training_prescription": {
  "title": "Early middlegame blunders",
  "why": "51 blunders across 39 games; 4.3% of analyzed user moves.",
  "do": [
    "10 basic tactics",
    "5 hanging-piece checks",
    "2 personal-loss puzzles from early middlegame positions"
  ],
  "avoid": "Do not start a long blitz session before completing the prep.",
  "confidence": "medium",
  "source": ["blunder_phases", "engine_coverage"]
}
```

### Kill criteria

- If prescription cannot be expressed in one sentence from available data, show nothing.
- Do not generate motivational filler.
- Do not show more than one primary prescription.

### Page placement

```
index.html:   prescription card + engine coverage note
losses.html:  early blunder phase table + personal-loss puzzle queue
opening.html: opponent openings + trap exposures
```

---

## Adversarial Review Plan

Four subagents, run in parallel after spec is written, before writing-plans:

### 1. Data Reality Check (most critical)

Reads raw game files and `computed.json`. Required outputs:

```
Total games analyzed
Total losses
Losses with usable opening_moves
Losses with null/short opening data (broken down by: too_short / parse_fail / extraction_bug)
Number of opponent-line clusters
Median cluster size
Clusters N=1 / N=2–4 / N=5–9 / N>=10
Top 10 clusters by loss count
Top 10 clusters by blunder count
Comparison of grouping keys: exact_line / play_signature / opening_family
Grouping recommendation: simplest key with enough repeated clusters
```

Kill signal: if no grouping key produces N≥5 groups, defer line-specific recommendations.

### 2. Architecture Stress Test

Required outputs:

```
Current refresh runtime
Estimated refresh runtime after new analysis (10 / 100 / all games)
Whether analysis is incremental and cache-based
Whether old games are skipped correctly
Whether CI can finish within 15 min budget
computed.json size before / estimated after
Whether attach_puzzles reuses cache (no second scan)
Graceful degradation behavior confirmed
```

Kill signal: if full refresh exceeds CI budget, move to incremental-only + manual --full-scan.

### 3. Scope/Value Auditor

Every feature judged by: "Does this produce a clearer next action?"

Required outputs:

```
Does prescription rely only on blunder_phase + loss_type + material-loss proxy?
Does prescription avoid inferred tactic labels unsupported by data?
Does the dashboard show one recommendation or multiple competing ones?
Is fundamentals-first order preserved?
Which features produce an action; which only produce a chart?
```

Kill signal: any feature that produces a chart but no action is deferred.

### 4. UX / Prescription Clarity Check

Required outputs:

```
Can the top recommendation be understood in 10 seconds?
Is there exactly one primary next-session rule?
Is the prescription derived from the data, not generated as filler?
Does engine_coverage note make partial analysis visible?
Does the prescription card render cleanly when next_session_rule is absent?
Does it render cleanly when next_session_rule is present?
```

Kill signal: if prescription is vague or multi-headed, simplify or remove it.

### Kill/defer criteria (applies to all subagents)

```
Clusters mostly N=1 → defer line-specific recommendations
Full refresh too slow → incremental-only + manual flag
computed.json too large → split summaries from cache
Feature produces chart but no action → defer
Tactic classification unreliable → reduce to material-loss proxy
Recommendation cannot be expressed in one sentence → simplify or remove
```
