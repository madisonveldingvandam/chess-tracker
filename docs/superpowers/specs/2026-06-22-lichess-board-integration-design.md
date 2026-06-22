# Lichess Board Integration + Lichess Stats Band

**Date:** 2026-06-22
**Status:** Approved

---

## Overview

Two independent features added to the chess-tracker dashboard:

1. **Chessground board integration** — replace all hand-rolled board rendering with Lichess's open-source `chessground` library. Gets CBurnett SVG pieces, Brown board theme, move dots/rings, user-drawable arrows, red check highlight, gold last-move, and piece slide animation.
2. **Lichess stats band + quick links** — fetch the user's Lichess ratings and puzzle score via the public Lichess API; display as a new band below the Chess.com band; add Chess.com and Lichess profile links to the header.

These two features are independent and can be implemented in sequence.

---

## Feature 1: Chessground Board Integration

### Assets to add

```
dashboard/vendor/chessground.min.js     — Chessground library (GPL-3.0, ~10KB gzipped)
dashboard/chessground.css               — Board + piece theme CSS from Chessground package
dashboard/vendor/pieces/cburnett/       — 12 CBurnett SVG piece files
  wK.svg  wQ.svg  wR.svg  wB.svg  wN.svg  wP.svg
  bK.svg  bQ.svg  bR.svg  bB.svg  bN.svg  bP.svg
```

CBurnett pieces are CC BY-SA 3.0 (original Wikimedia Commons set). Download from the Lichess GitHub repo at `public/piece/cburnett/` or Wikimedia Commons.

Chessground loads pieces via CSS `background-image` paths. The exact mechanism (class on `.cg-wrap`, CSS custom property, or path override) must be confirmed from the downloaded package's CSS — point it at `vendor/pieces/cburnett/`.

### Board factory

Add a `makeBoard(el, cfg)` helper in `app.js` that wraps `Chessground(el, config)` with shared defaults:

```
defaults: {
  coordinates: true,
  orientation: 'white',    // overridable
  viewOnly: false,         // overridable
  animation: { enabled: true, duration: 200 },
  highlight: { lastMove: true, check: true },
  drawable: { enabled: false }   // overridden per mode
}
```

### Board modes

**View-only** (opening family boards, plan move boards):
```
viewOnly: true
drawable: { enabled: false }
```
Pass a FEN and optional `lastMove: [from, to]`. No interaction.

**Puzzle drill** (losses page):
```
viewOnly: false
movable: {
  free: false,
  color: <side to move from FEN>,
  dests: <all legal moves as Map<from, to[]>>   // user can pick up any piece
},
movable.events.after: (orig, dest) => {
  const uci = orig + dest   // + promotion char if applicable
  if (uci === puzzle.best_move_uci) {
    // Chessground already moved the piece visually — just show success state
  } else {
    // Wrong move: reset board to pre-move FEN, reveal answer arrow
    cg.set({ fen: puzzle.fen_before })
    cg.setShapes([{ orig: bestFrom, dest: bestTo, brush: 'green' }])
  }
}
drawable: { enabled: true }   // user can draw arrows/circles
```

Legal move generation for `movable.dests`: compute with `python-chess` at refresh time and embed in each puzzle's JSON, OR compute in-browser with a minimal legal-move function. Recommended: embed in JSON (one extra field per puzzle, computed offline — consistent with the existing offline-engine philosophy).

**Hint arrow** (existing "Get a Hint" button):
```
cg.setShapes([{ orig: bestFrom, dest: bestTo, brush: 'green' }])
```

### What changes minimally

- `chess_tracker/puzzles.py` — one addition: after computing `best_move`, also compute `legal_dests` (all legal moves from the position as a dict `{from: [to, ...]}`) using python-chess and attach to the `Puzzle` dataclass
- `data/computed.json` — one new field per puzzle entry: `legal_dests`

### What does NOT change

- `chess_tracker/refresh.py` — pipeline untouched
- All Python tests
- Page layout, CSS outside the board, Tabulator tables

### Migration path

Replace board-rendering call sites one at a time:
1. Puzzle drill board (losses.html / `renderPuzzleDrill`)
2. Opening family boards
3. Plan move boards

Each is self-contained. The factory handles all three with different config.

---

## Feature 2: Lichess Stats Band + Quick Links

### Python: new API fetch

Add to `chess_tracker/api.py`:

```python
LICHESS_BASE = "https://lichess.org/api"

def fetch_lichess_user(username: str) -> dict:
    """Fetch public profile + perfs for a Lichess user. Returns {} on error."""
    url = f"{LICHESS_BASE}/user/{username.lower()}"
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}
```

Add to `refresh.py` after the Chess.com stats fetch:

```python
raw_lichess = fetch_lichess_user("M_V-v")
perfs = raw_lichess.get("perfs", {})
computed["lichess"] = {
    "bullet":       perfs.get("bullet",    {}).get("rating"),
    "blitz":        perfs.get("blitz",     {}).get("rating"),
    "rapid":        perfs.get("rapid",     {}).get("rating"),
    "classical":    perfs.get("classical", {}).get("rating"),
    "puzzle_score": perfs.get("puzzle",    {}).get("score"),
    "game_count":   raw_lichess.get("count", {}).get("all"),
} if raw_lichess else None
```

If `raw_lichess` is empty (network error, rate limit), `computed["lichess"]` is `null` and the band hides.

### Dashboard: Lichess stats band

New band in `templates/index.html` (regenerated to `dashboard/index.html`) directly below the existing Chess.com rating band. Same visual structure — a row of stat chips. Label: "Lichess" with a small inline SVG Lichess logo (the knight icon, ~16px).

Display fields: Bullet · Blitz · Rapid · Classical · Puzzles · Games played

If `data.lichess` is null, render nothing (band hidden with `display:none` or conditional template).

### Dashboard: quick links

Two small icon links added to the page `<header>`:
- Chess.com: links to `https://www.chess.com/member/M_V-V`
- Lichess: links to `https://lichess.org/@/M_V-v`

Both `target="_blank" rel="noopener"`. Implemented as styled anchor tags, no JS.

---

## Error handling

| Scenario | Behavior |
|---|---|
| Lichess API down at refresh | `computed.lichess = null`, band hidden, Chess.com data unaffected |
| CBurnett SVG fails to load | Browser shows blank square (piece image missing), board still functional |
| Chessground init fails | Wrap in try/catch, fall back to existing unicode board render |
| Legal dests missing from JSON | Fall back to `movable.free: true` (user can attempt any move) |

---

## Testing

- **Python:** add `test_fetch_lichess_user` to `tests/` — mock the HTTP call, verify field extraction and null-on-error behavior
- **Board:** manual browser verification (same approach as existing puzzle drill tests — no JS unit tests in this project)
- **Smoke test:** extend `tests/test_smoke.py` to assert `computed["lichess"]` key present (can be null)

---

## Out of scope

- Lichess game import for loss analysis / puzzle generation (fast-follow, separate spec)
- Multiple piece set options (CBurnett only)
- Mobile arrow drawing (touch support is in Chessground but not explicitly tested here)
- Lichess opening analysis from Lichess games
