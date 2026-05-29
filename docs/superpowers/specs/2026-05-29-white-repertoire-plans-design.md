# White Repertoire Plans + Adherence — Design

**Date:** 2026-05-29
**Status:** Approved (design), pending implementation plan

## Problem

The plan/adherence block (`compute_plan_compliance`, `plan.json`) currently
holds only the two Black openings (Modern Defense vs e4, Englund Gambit vs d4).
The user also wants to track their **White** repertoire and, crucially, treat it
as an *aspirational behavior-change* plan rather than a record of what they
already do:

- **vs ...as White after 1.d4:** they currently play the **London System** but
  want to switch to the **Colle–Zukertort System**. Adherence must measure
  whether they actually played the new system or drifted back into the London.
- **as White after 1.e4:** their strongest *chosen* lines are the knights
  complex (Three/Four Knights, ~65% over 31 games; the Scotch is their *worst*
  chosen line at 33%). The target is the **Four Knights** with two tactical
  surprise branches both treated as on-plan: **Halloween Gambit** (`4.Nxe5`)
  and **Belgrade Gambit** (`4.d4 exd4 5.Nd5`).

## Why ECO-family matching is insufficient

The existing model matches `GameRecord.family == target_family` exactly. The
rolled-up family stems smear the systems that matter here:

| Chess.com label | rolled-up `family` |
|---|---|
| `London System` | `London System` |
| `Queens Pawn Opening Zukertort Variation` | `Queens Pawn Opening` |
| `…Zukertort Chigorin Variation 3.Bf4` (London-via-Bf4) | `Queens Pawn Opening` |
| `Colle-Zukertort System` | `Colle Zukertort System` |

Real Colle–Zukertort games are frequently mislabeled `Queens Pawn Opening`, and
London-via-`Bf4` games land in the same bucket. So the family label cannot
answer the one question that matters: *did I play the Colle setup (e3 + b3 +
Bb2, no early Bf4) or the London (early Bf4)?* The distinguishing signal is the
**moves themselves**.

## Design

### 1. Move-pattern matcher (new)

A small, pure function that classifies a game from its early SAN moves:

- Input: the game's opening SAN (move-number string, e.g.
  `"1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6"`) and a `match` rule.
- It tokenizes into White plies (even ply index, 0-based) and Black plies, then
  evaluates the rule's `requires` / `requires_any` / `forbids` token-sets
  against White's moves, and an `applicable_if_black_plays` guard against
  Black's reply.
- Token matching is on SAN piece+square tokens (`e3`, `b3`, `Bb2`, `Bf4`,
  `Nf3`, `Nc3`, `Nxe5`, `Nd5`). Capture/check decorations are normalized so
  `Bxb2` matches a `Bb2` requirement and `Nd5+` matches `Nd5`.

Rule schema (added to a `plan.json` opening entry, optional — entries without
it keep using exact-`family` matching):

```jsonc
"match": {
  "applicable_if_black_plays": "e5",        // optional: ply-2 guard
  "white_requires": ["Nf3", "Nc3"],          // all must be present
  "white_requires_any": [["e3","b3"], ["e3","Bb2"]], // at least one group fully present
  "white_forbids": ["Bf4"],                  // none may be present
  "gambit_flags": { "Halloween": ["Nxe5"], "Belgrade": ["Nd5"] }, // optional sub-tags
  "window_plies": 12                          // how deep to read
}
```

### 2. Deeper move window

`first_moves_san(game, count)` already takes a ply count; today only the 8-ply
form is stored on `GameRecord.first_moves`. The Zukertort-defining `b3`/`Bb2`
lands around plies 9–11, just past 8. Add a field
`GameRecord.opening_moves` holding up to 12 plies of SAN — as many as the game
has when it is shorter (so very short games still expose what was played, and
the matcher reads whatever is present). This needs a "best-effort" SAN helper
rather than `first_moves_san`'s all-or-nothing `None`. `first_moves` (8 plies)
and `play_signature` are unchanged — the existing
8-ply display and transposition grouping keep working.

### 3. `compute_plan_compliance` changes

Branch per opening entry:

- **Entry has `match`** → use the move-pattern matcher. Applicability =
  `r.side == side` AND `first_moves` starts with `1.<vs_first_move>` AND (if
  present) the `applicable_if_black_plays` guard. On-plan = matcher verdict on
  `r.opening_moves`. When `gambit_flags` is set, also count games per flag and
  surface them (e.g. `{"Halloween": 3, "Belgrade": 1}`) for the dashboard.
- **Entry has no `match`** → today's exact-`family` path, unchanged. The two
  Black entries are untouched.

Severity thresholds (green ≥60, yellow ≥40, red <40, neutral when no applicable
games) are reused as-is.

### 4. `plan.json` — two new White entries

```jsonc
{
  "name": "Colle–Zukertort System",
  "side": "white",
  "vs_first_move": "d4",
  "target_family": "Colle Zukertort System",
  "moves": "1.d4 d5  2.Nf3 Nf6  3.e3 e6  4.Bd3 c5  5.b3 Nc6  6.Bb2 Bd6",
  "plan": "e3 + b3 + Bb2 fianchetto, dark bishop stays home (NO early Bf4). Aim the e4 break and kingside attack.",
  "match": {
    "white_requires_any": [["e3","b3"], ["e3","Bb2"]],
    "white_forbids": ["Bf4"],
    "window_plies": 12
  }
},
{
  "name": "Four Knights (Belgrade / Halloween)",
  "side": "white",
  "vs_first_move": "e4",
  "target_family": "Four Knights Game",
  "moves": "1.e4 e5  2.Nf3 Nc6  3.Nc3 Nf6  4.Nxe5 (Halloween)  /  4.d4 exd4 5.Nd5 (Belgrade)",
  "plan": "Develop both knights (Four Knights). Spring Halloween 4.Nxe5 or Belgrade 4.d4 exd4 5.Nd5 for bullet surprise.",
  "match": {
    "applicable_if_black_plays": "e5",
    "white_requires": ["Nf3", "Nc3"],
    "gambit_flags": { "Halloween": ["Nxe5"], "Belgrade": ["Nd5"] },
    "window_plies": 8
  }
}
```

### 5. Dashboard

`renderPlanBlock` in `dashboard/app.js`: group the plan cards under **Black**
and **White** sub-headers (there are now 4). On an entry carrying gambit flags,
render a small breakdown line ("of N on-plan: 3 Halloween, 1 Belgrade"). No
other panels change. The existing move-stepper board renders the new entries'
`moves` lines unchanged.

## Out of scope (YAGNI)

- Distinguishing Colle-Zukertort (`b3`) from Colle-Koltanowski (`c3`) as
  separate adherence buckets — the `b3`/`Bb2` requirement already excludes
  Koltanowski from on-plan, which is the user's intent.
- Any change to the Black entries, leaks, sessions, puzzles, or refresh flow.
- Engine-based "was this objectively the best system" judgement — adherence is
  purely "did I play my chosen system."

## Testing

PGN/record fixtures, asserting on-plan vs deviated:

- Real **Colle–Zukertort** (e3 + b3 + Bb2, no Bf4) → on-plan.
- **London via Bf4** (labeled Zukertort/Queens Pawn) → **deviated** (the key
  discriminator test).
- **Four Knights** (Nf3 + Nc3 after 1.e4 e5) → on-plan.
- **Halloween** (`4.Nxe5`) → on-plan + `Halloween` flag.
- **Belgrade** (`4.d4 exd4 5.Nd5`) → on-plan + `Belgrade` flag.
- **Scotch** (`3.d4`, no Nc3) after 1.e4 e5 → deviated.
- d4 game where Black avoids ...d5 → CZ still applicable (system vs anything).
- 1.e4 vs a non-...e5 reply (Scandinavian) → **not applicable** (no Four
  Knights possible), severity neutral, not punished.
- Token normalization: `Bxb2` satisfies `Bb2`; `Nd5+` satisfies `Nd5`.
- Backward-compat: the two Black entries still compute via the family path.
