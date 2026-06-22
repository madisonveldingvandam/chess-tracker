# Chessground Board Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all hand-rolled board rendering in the chess-tracker dashboard with Lichess's open-source Chessground library, getting CBurnett SVG pieces, Brown board theme, move dots, drawable arrows, check highlighting, and piece animation.

**Architecture:** Vendor a pre-built IIFE bundle of Chessground plus CBurnett SVG piece files. Add a `makeBoard(el, cfg)` factory to `app.js` that wraps Chessground with per-context defaults. Three board modes: view-only (family/opening/plan), puzzle-drill (locked dests + after-callback), hint-arrow (cg.setShapes). All existing puzzle logic and Python pipeline is unchanged except `puzzles.py` gains `legal_dests` computation.

**Tech Stack:** Chessground 9.x (GPL-3.0), esbuild (one-time bundle), CBurnett SVGs (CC BY-SA 3.0), python-chess (already installed), no ongoing build step.

---

### Task 1: Add `legal_dests` to `Puzzle` dataclass

**Files:**
- Modify: `chess_tracker/puzzles.py`
- Test: `tests/test_puzzles.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_puzzles.py` after the existing imports:

```python
def test_compute_legal_dests_starting_position():
    from chess_tracker.puzzles import _compute_legal_dests
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    dests = _compute_legal_dests(fen)
    # 20 legal moves from starting position
    total = sum(len(v) for v in dests.values())
    assert total == 20
    assert "e4" in dests.get("e2", [])
    assert "a3" in dests.get("a2", [])


def test_puzzle_dataclass_has_legal_dests():
    p = _puzzle(ply=0, cp_before=0, cp_loss=150)
    assert hasattr(p, "legal_dests")
    assert isinstance(p.legal_dests, dict)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
uv run pytest tests/test_puzzles.py::test_compute_legal_dests_starting_position tests/test_puzzles.py::test_puzzle_dataclass_has_legal_dests -v
```

Expected: `ImportError: cannot import name '_compute_legal_dests'` and `AttributeError`.

- [ ] **Step 3: Add `legal_dests` field and helper to `puzzles.py`**

In `chess_tracker/puzzles.py`, add the helper after the `_cp` function (around line 74) and update the `Puzzle` dataclass:

```python
# in the Puzzle dataclass, add legal_dests as the last field with a default:
from dataclasses import dataclass, asdict, field

@dataclass
class Puzzle:
    ply: int
    fullmove: int
    side: str
    fen_before: str
    my_move_uci: str
    my_move_san: str
    best_move_uci: str
    best_move_san: str
    cp_before: int
    cp_after: int
    cp_loss: int
    legal_dests: dict[str, list[str]] = field(default_factory=dict)
```

Then add the helper function after `_cp`:

```python
def _compute_legal_dests(fen: str) -> dict[str, list[str]]:
    """All legal moves from ``fen`` as {from_sq: [to_sq, ...]} with promotion deduped."""
    board = chess.Board(fen)
    dests: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for move in board.legal_moves:
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        key = (from_sq, to_sq)
        if key in seen:
            continue
        seen.add(key)
        dests.setdefault(from_sq, []).append(to_sq)
    return dests
```

In `analyse_game`, update the `Puzzle(...)` constructor call to pass `legal_dests`:

```python
candidates.append(Puzzle(
    ply=ply,
    fullmove=fullmove,
    side=side,
    fen_before=fen_before,
    my_move_uci=move.uci(),
    my_move_san=my_san,
    best_move_uci=best.uci(),
    best_move_san=best_san,
    cp_before=cp_before,
    cp_after=cp_after,
    cp_loss=cp_loss,
    legal_dests=_compute_legal_dests(fen_before),
))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_puzzles.py -v
```

Expected: all existing tests pass (the new `legal_dests` field has `default_factory=dict` so existing `_puzzle()` helper calls still work), plus the two new tests pass.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/puzzles.py tests/test_puzzles.py
git commit -m "feat(puzzles): add legal_dests field to Puzzle dataclass"
```

---

### Task 2: Download and vendor Chessground assets

**Files:**
- Create: `dashboard/vendor/chessground.min.js`
- Create: `dashboard/vendor/chessground.base.css`
- Create: `dashboard/vendor/pieces/cburnett/` (12 SVG files)

- [ ] **Step 1: Bundle Chessground into a browser-ready IIFE**

```bash
cd /tmp
mkdir cg-build && cd cg-build
npm init -y
npm install chessground esbuild
```

Inspect the installed package to find the entry point:
```bash
ls node_modules/chessground/
cat node_modules/chessground/package.json | grep -E '"main"|"module"|"exports"'
```

Then bundle (the entry is typically `src/chessground.ts` or `dist/chessground.js` — adjust based on what you see):
```bash
# If entry is src/chessground.ts:
./node_modules/.bin/esbuild node_modules/chessground/src/chessground.ts \
  --bundle --format=iife --global-name=ChessgroundLib \
  --minify \
  --outfile=/Users/madisonvelding-vandam/Developer/chess-tracker/dashboard/vendor/chessground.min.js

# If entry is dist/chessground.js (no TS):
./node_modules/.bin/esbuild node_modules/chessground/dist/chessground.js \
  --bundle --format=iife --global-name=ChessgroundLib \
  --minify \
  --outfile=/Users/madisonvelding-vandam/Developer/chess-tracker/dashboard/vendor/chessground.min.js
```

Verify: `wc -c /Users/madisonvelding-vandam/Developer/chess-tracker/dashboard/vendor/chessground.min.js` should be ~30–50KB.

- [ ] **Step 2: Copy the base CSS**

```bash
# Find the CSS in the package:
find /tmp/cg-build/node_modules/chessground -name "*.css"

# Copy whichever base/layout CSS file you find (likely chessground.base.css):
cp /tmp/cg-build/node_modules/chessground/assets/chessground.base.css \
  /Users/madisonvelding-vandam/Developer/chess-tracker/dashboard/vendor/chessground.base.css
# OR:
cp /tmp/cg-build/node_modules/chessground/css/chessground.base.css \
  /Users/madisonvelding-vandam/Developer/chess-tracker/dashboard/vendor/chessground.base.css
```

- [ ] **Step 3: Download CBurnett SVG piece files**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
mkdir -p dashboard/vendor/pieces/cburnett
for piece in wK wQ wR wB wN wP bK bQ bR bB bN bP; do
  curl -sL \
    "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece/cburnett/${piece}.svg" \
    -o "dashboard/vendor/pieces/cburnett/${piece}.svg"
  echo "Downloaded ${piece}.svg ($(wc -c < dashboard/vendor/pieces/cburnett/${piece}.svg) bytes)"
done
```

Verify all 12 files are present and non-empty:
```bash
ls -la dashboard/vendor/pieces/cburnett/
```

Expected: 12 .svg files, each ~2–10KB.

- [ ] **Step 4: Quick sanity-check in browser**

Open `dashboard/vendor/pieces/cburnett/wK.svg` in a browser. You should see the white king CBurnett piece SVG render correctly.

- [ ] **Step 5: Commit assets**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
git add dashboard/vendor/chessground.min.js dashboard/vendor/chessground.base.css dashboard/vendor/pieces/
git commit -m "feat: vendor Chessground library and CBurnett SVG pieces"
```

---

### Task 3: Write Chessground theme CSS

**Files:**
- Create: `dashboard/chessground-theme.css`

- [ ] **Step 1: Create the theme CSS file**

Create `dashboard/chessground-theme.css`:

```css
/* Chessground Brown board theme + CBurnett piece images */

/* Board sizing — cg-wrap fills its container.
   Container divs set the actual size via existing CSS classes. */
.cg-wrap {
  position: relative;
  display: block;
}

/* Brown board colors */
cg-board square.light       { background: #f0d9b5; }
cg-board square.dark        { background: #b58863; }
cg-board square.last-move   { background: rgba(155, 199, 0, 0.41); }
cg-board square.selected    { background: rgba(20, 85, 30, 0.5); }
cg-board square.check       {
  background: radial-gradient(ellipse at center,
    rgba(255,0,0,1) 0%, rgba(231,0,0,1) 25%,
    rgba(169,0,0,0) 89%, rgba(158,0,0,0) 100%);
}
cg-board square.move-dest   { background: rgba(20, 85, 30, 0.5); }

/* CBurnett piece images — paths relative to dashboard/chessground-theme.css */
.cg-wrap piece.pawn.white   { background-image: url('vendor/pieces/cburnett/wP.svg'); }
.cg-wrap piece.knight.white { background-image: url('vendor/pieces/cburnett/wN.svg'); }
.cg-wrap piece.bishop.white { background-image: url('vendor/pieces/cburnett/wB.svg'); }
.cg-wrap piece.rook.white   { background-image: url('vendor/pieces/cburnett/wR.svg'); }
.cg-wrap piece.queen.white  { background-image: url('vendor/pieces/cburnett/wQ.svg'); }
.cg-wrap piece.king.white   { background-image: url('vendor/pieces/cburnett/wK.svg'); }
.cg-wrap piece.pawn.black   { background-image: url('vendor/pieces/cburnett/bP.svg'); }
.cg-wrap piece.knight.black { background-image: url('vendor/pieces/cburnett/bN.svg'); }
.cg-wrap piece.bishop.black { background-image: url('vendor/pieces/cburnett/bB.svg'); }
.cg-wrap piece.rook.black   { background-image: url('vendor/pieces/cburnett/bR.svg'); }
.cg-wrap piece.queen.black  { background-image: url('vendor/pieces/cburnett/bQ.svg'); }
.cg-wrap piece.king.black   { background-image: url('vendor/pieces/cburnett/bK.svg'); }
```

**Note:** If the browser dev tools show that Chessground uses different selectors (e.g., `.cg-wrap piece` without the compound selector, or square colors handled differently in the base CSS), open the rendered DOM and adjust accordingly. The Brown color values and CBurnett file references are the constants; the selector paths may need tuning.

- [ ] **Step 2: Update board container CSS in `dashboard/styles.css`**

Find the `.board-large` and `.puzzle-board` CSS rules and replace the `display: grid` / `grid-template-columns` declarations with simple width/height so Chessground can fill them. Open `dashboard/styles.css` and locate these rules:

```css
/* BEFORE — find and replace these */
.board-large {
  display: grid;
  grid-template-columns: repeat(8, 40px);
  /* ... other rules ... */
}
.puzzle-board {
  display: grid;
  grid-template-columns: repeat(8, 44px);
  /* ... other rules ... */
}
.plan-board {
  display: grid;
  grid-template-columns: repeat(8, 30px);
  /* ... other rules ... */
}
```

Replace with:
```css
/* AFTER — Chessground fills its container */
.board-large { width: 320px; height: 320px; }
.puzzle-board { width: 400px; height: 400px; }
.plan-board   { width: 240px; height: 240px; }
```

(Puzzle board is bumped to 400×400 / 50px per square as requested.)

- [ ] **Step 3: Commit**

```bash
git add dashboard/chessground-theme.css dashboard/styles.css
git commit -m "feat: add Chessground Brown theme CSS and resize board containers"
```

---

### Task 4: Load Chessground in all HTML templates

**Files:**
- Modify: `chess_tracker/templates/index.html`
- Modify: `chess_tracker/templates/losses.html`
- Modify: `chess_tracker/templates/opening.html`
- Modify: `chess_tracker/templates/leaks.html`
- Modify: `chess_tracker/templates/process.html`
- Modify: `chess_tracker/templates/sessions.html`

Each template that shows a board needs Chessground. In practice: index.html (family boards), losses.html (puzzle drill), opening.html (variation board). The others (leaks, process, sessions) have no boards but should still load consistently — add to all for simplicity.

- [ ] **Step 1: Add Chessground `<link>` and `<script>` to each template's `<head>` / before `app.js`**

In every template's `<head>`, add after the existing `<link>` tags:
```html
  <link rel="stylesheet" href="vendor/chessground.base.css">
  <link rel="stylesheet" href="chessground-theme.css">
```

In every template, add before `<script src="app.js">`:
```html
  <script src="vendor/chessground.min.js"></script>
```

Example — `chess_tracker/templates/losses.html` (before/after):

```html
<!-- BEFORE -->
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — Losses — {{USERNAME}}</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
...
  <script src="vendor/tabulator.min.js"></script>
  <script>/* DATA_INJECTION_POINT */</script>
  <script src="app.js"></script>

<!-- AFTER -->
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — Losses — {{USERNAME}}</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="vendor/chessground.base.css">
  <link rel="stylesheet" href="chessground-theme.css">
  <link rel="stylesheet" href="styles.css">
</head>
...
  <script src="vendor/tabulator.min.js"></script>
  <script src="vendor/chessground.min.js"></script>
  <script>/* DATA_INJECTION_POINT */</script>
  <script src="app.js"></script>
```

Apply this same change to all 6 templates.

- [ ] **Step 2: Run refresh to regenerate dashboard HTML**

```bash
uv run python refresh.py --no-puzzles 2>&1 | tail -5
```

Open `dashboard/index.html` in a browser. No visual change expected yet — we just need to confirm no JS errors in the console related to Chessground loading. Open browser dev tools → Console. Should see no errors. If `ChessgroundLib is not defined` appears, check that the `<script>` tag was added before `app.js` and that the `.min.js` bundle was built correctly (Task 2, Step 1).

- [ ] **Step 3: Commit**

```bash
git add chess_tracker/templates/
git commit -m "feat: load Chessground in all dashboard templates"
```

---

### Task 5: Add `makeBoard()` factory to `app.js`

**Files:**
- Modify: `dashboard/app.js`

- [ ] **Step 1: Add the `makeBoard` factory near the top of the IIFE**

In `dashboard/app.js`, add `makeBoard` after the `escapeAttr` helper (around line 8), before the `const D = window.DATA` line:

```javascript
  function makeBoard(el, cfg) {
    const factory = (window.ChessgroundLib || {}).Chessground;
    if (!factory) { console.error("Chessground not loaded"); return null; }
    const defaults = {
      coordinates: true,
      animation: { enabled: true, duration: 150 },
      highlight: { lastMove: true, check: true },
      drawable: { enabled: false, visible: false },
    };
    return factory(el, Object.assign({}, defaults, cfg));
  }
```

- [ ] **Step 2: Run refresh and open the browser**

```bash
uv run python refresh.py --no-puzzles 2>&1 | tail -5
```

Open browser console on `dashboard/index.html`. No errors expected. `makeBoard` is defined but not called yet.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app.js
git commit -m "feat(app): add makeBoard() Chessground factory"
```

---

### Task 6: Replace view-only boards (family, opening, plan step)

**Files:**
- Modify: `dashboard/app.js`

There are three call sites for `boardSquaresHTML`:
1. `updateFamilyBoard()` — family boards on index.html
2. `updateOpeningBoard()` — variation board on opening.html
3. `paint()` inside `renderPlanBlock()` — plan move stepper

- [ ] **Step 1: Initialize family boards on page load**

In `renderFamilyBlock()`, find the block that calls `table.on("tableBuilt", ...)` (around line 580). Before it, add initialization of the Chessground board:

```javascript
  // Initialize the Chessground board for this side (view-only)
  const boardEl = document.getElementById(boardId);
  if (boardEl) boardEl._cg = makeBoard(boardEl, {
    viewOnly: true,
    orientation: flip ? 'black' : 'white',
  });
```

- [ ] **Step 2: Update `updateFamilyBoard()` to use Chessground**

Find `updateFamilyBoard()` (around line 601). Replace the `board.innerHTML = boardSquaresHTML(...)` line:

```javascript
  // REMOVE:
  board.innerHTML = boardSquaresHTML(data.canonical_play_signature, flip);

  // REPLACE WITH:
  if (board._cg) board._cg.set({ fen: data.canonical_play_signature });
```

- [ ] **Step 3: Initialize and update the opening board**

In `renderOpeningDetail()`, find where the table is initialized for variations. Before the `table.on("tableBuilt", ...)` call, add:

```javascript
  const openingBoardEl = document.getElementById("opening-board");
  if (openingBoardEl) openingBoardEl._cg = makeBoard(openingBoardEl, {
    viewOnly: true,
    orientation: flip ? 'black' : 'white',
  });
```

In `updateOpeningBoard()`, replace `board.innerHTML = boardSquaresHTML(...)`:

```javascript
  // REMOVE:
  board.innerHTML = boardSquaresHTML(data.canonical_play_signature, flip);

  // REPLACE WITH:
  if (board._cg) board._cg.set({ fen: data.canonical_play_signature });
```

Also update `selectRareFamilyRow` → calls `updateFamilyBoard` which already uses Chessground, so no change needed there.

- [ ] **Step 4: Update the plan move stepper**

In `renderPlanBlock()`, find the `paint()` function (around line 228):

```javascript
          const paint = () => {
            boardEl.innerHTML = boardSquaresHTML(fens[idx], flip);  // REMOVE THIS LINE
            // ...
          };
```

Replace it with:

```javascript
          // Initialize Chessground for this board on first paint
          if (!boardEl._cg) {
            boardEl._cg = makeBoard(boardEl, {
              viewOnly: true,
              orientation: flip ? 'black' : 'white',
            });
          }
          const paint = () => {
            if (boardEl._cg) boardEl._cg.set({ fen: fens[idx] });
            capEl.textContent = idx === 0
              ? "Start position"
              : `after ${labels[idx - 1]} · move ${idx} of ${fens.length - 1}`;
            prevEl.disabled = idx === 0;
            nextEl.disabled = idx === fens.length - 1;
          };
```

- [ ] **Step 5: Run refresh and verify in browser**

```bash
uv run python refresh.py --no-puzzles 2>&1 | tail -5
```

Open `dashboard/index.html`. Click a row in the White or Black opening table — the board panel on the right should show a Chessground board with CBurnett pieces on a Brown background. Check:
- Pieces look like Lichess pieces (detailed SVGs, not unicode)
- Brown board colours (buff light squares, sienna dark squares)
- Coordinates on board edges
- Plan stepper (expand an opening card, use ◀ ▶ buttons): board updates correctly

If the board appears but has no pieces (just an empty board), the piece SVG URLs in the CSS are wrong — open browser DevTools → Network → filter by `.svg` to see what's being fetched and where it's 404ing.

- [ ] **Step 6: Remove `boardSquaresHTML` and `GLYPH` (now dead code)**

`boardSquaresHTML` and `GLYPH` are no longer called. Remove them from `app.js`:

```javascript
// REMOVE the following constant and function:
const GLYPH = { K:"♚", Q:"♛", ... };
function boardSquaresHTML(fen, flip = false) { ... }
```

Run `grep -n "boardSquaresHTML\|GLYPH" dashboard/app.js` to confirm both are gone and no remaining callsites exist.

- [ ] **Step 7: Run the full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/app.js
git commit -m "feat(app): replace view-only boards with Chessground (family, opening, plan)"
```

---

### Task 7: Replace puzzle drill board with Chessground

**Files:**
- Modify: `dashboard/app.js`

This is the main interaction board. It replaces the click-based `boardEl.addEventListener` handler with Chessground's `movable.events.after` callback.

- [ ] **Step 1: Rewrite `renderPuzzleDrill()` to initialize Chessground**

Find `renderPuzzleDrill()` (around line 299). The outer structure (root, puzzles list, stage layout, listEl/promptEl/fbEl references) stays. The `state` object, `select()`, and board interaction logic change.

Replace from the `const state = {};` line (≈line 333) through the end of `renderPuzzleDrill()` (≈line 441) with:

```javascript
    const state = { puzzle: null, solved: false };

    // Initialize puzzle board once
    boardEl._cg = makeBoard(boardEl, {
      viewOnly: false,
      drawable: { enabled: true, visible: true },
      movable: {
        free: false,
        events: { after: handleMove },
      },
    });

    function handleMove(orig, dest) {
      if (state.solved || !state.puzzle) return;
      const best = state.puzzle.best_move_uci;
      const uci = orig + dest;
      if (uci === best || uci === best.slice(0, 4)) {
        // Correct: Chessground already moved the piece visually
        state.solved = true;
        fbEl.innerHTML = `<span class="ok">✓ Correct — ${escapeAttr(state.puzzle.best_move_san)} holds the position.</span>`;
      } else {
        // Wrong: reset board to pre-move FEN, draw answer arrow
        boardEl._cg.set({ fen: state.puzzle.fen_before });
        boardEl._cg.setShapes([{
          orig: best.slice(0, 2),
          dest: best.slice(2, 4),
          brush: 'green',
        }]);
        fbEl.innerHTML =
          `<span class="bad">✗ That's the kind of move that lost the game.</span> ` +
          `The move that holds was <strong>${escapeAttr(state.puzzle.best_move_san)}</strong>.`;
      }
    }

    function select(i) {
      const p = puzzles[i].puzzle;
      state.puzzle = p;
      state.solved = false;
      listEl.querySelectorAll(".puzzle-item").forEach(b =>
        b.classList.toggle("active", +b.dataset.idx === i));
      promptEl.innerHTML =
        `<strong>${p.side === "white" ? "White" : "Black"} to move.</strong> ` +
        `You played <span class="bad">${escapeAttr(p.my_move_san)}</span> here — find the move that holds.`;
      fbEl.innerHTML = "";
      boardEl._cg.set({
        fen: p.fen_before,
        orientation: p.side === "black" ? "black" : "white",
        movable: {
          color: p.side,
          dests: new Map(Object.entries(p.legal_dests || {})),
        },
        lastMove: undefined,
        check: false,
      });
      boardEl._cg.setShapes([]);
    }

    function currentIdx() {
      const active = listEl.querySelector(".puzzle-item.active");
      return active ? +active.dataset.idx : 0;
    }

    listEl.addEventListener("click", (e) => {
      const b = e.target.closest(".puzzle-item");
      if (b) select(+b.dataset.idx);
    });
    document.getElementById("puzzle-show").onclick = () => {
      if (!state.solved && state.puzzle) {
        const best = state.puzzle.best_move_uci;
        boardEl._cg.setShapes([{
          orig: best.slice(0, 2),
          dest: best.slice(2, 4),
          brush: 'green',
        }]);
      }
      if (state.puzzle) {
        fbEl.innerHTML = `Best move: <strong>${escapeAttr(state.puzzle.best_move_san)}</strong>.`;
      }
    };
    document.getElementById("puzzle-reset").onclick = () => select(currentIdx());

    queueMicrotask(() => select(0));
```

- [ ] **Step 2: Remove dead code no longer needed by the puzzle drill**

After this change, `drawBoard`, `reveal`, `placementToGrid`, `gridToPlacement`, `sqToRC`, `applyUci`, `FILES` are dead. Remove them from `app.js`:

```javascript
// REMOVE:
const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];
function placementToGrid(placement) { ... }
function gridToPlacement(grid) { ... }
function sqToRC(sq) { ... }
function applyUci(fen, uci) { ... }
// (drawBoard and reveal were inline inside renderPuzzleDrill and are already gone)
```

Run `grep -n "FILES\|placementToGrid\|gridToPlacement\|sqToRC\|applyUci" dashboard/app.js` to confirm no remaining references.

- [ ] **Step 3: Run refresh with puzzles enabled and verify in browser**

```bash
uv run python refresh.py 2>&1 | tail -10
```

Open `dashboard/losses.html`. Check:
- Puzzle drill section shows a Chessground board with CBurnett pieces, Brown theme
- Board is oriented correctly for the puzzle's side to move
- Click a puzzle in the list → board updates to new position
- Try to make a wrong move: board resets to original FEN, green arrow points to correct move
- Try the correct move: move stays applied, success message appears
- "Show answer" button: draws green arrow, shows move text
- "Reset" button: reloads position, clears arrows

If `legal_dests` is missing from puzzle JSON (i.e., refresh.py was run before Task 1), re-run `refresh.py` to regenerate `data/computed.json` with the new field.

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "feat(app): replace puzzle drill board with Chessground"
```

---

### Task 8: Verify and final cleanup

- [ ] **Step 1: Run `refresh.py` end-to-end**

```bash
uv run python refresh.py 2>&1 | tail -20
```

Expected: completes without errors, `data/computed.json` generated, `dashboard/*.html` files regenerated.

- [ ] **Step 2: Open each dashboard page and spot-check boards**

- `dashboard/index.html`: White + Black family boards (click a row to see board)
- `dashboard/index.html` plan section: expand an opening card, step through moves with ◀ ▶
- `dashboard/opening.html?family=London+System&color=white` (substitute a real family from your data): variation board
- `dashboard/losses.html`: puzzle drill

- [ ] **Step 3: Confirm no `boardSquaresHTML`, `GLYPH`, `applyUci`, `FILES`, `placementToGrid`, `sqToRC`, `gridToPlacement` remain**

```bash
grep -n "boardSquaresHTML\|GLYPH\|applyUci\|const FILES\|placementToGrid\|sqToRC\|gridToPlacement" dashboard/app.js
```

Expected: no output.

- [ ] **Step 4: Run full test suite one final time**

```bash
uv run pytest tests/ -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: Chessground board integration complete — CBurnett pieces, Brown theme, puzzle drill"
```
