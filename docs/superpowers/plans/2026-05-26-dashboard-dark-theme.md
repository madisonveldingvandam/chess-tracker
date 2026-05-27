# Dashboard dark theme implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's chess-green / amber / red palette with the minimal warm-dark theme specified in [docs/superpowers/specs/2026-05-26-dashboard-dark-theme-design.md](../specs/2026-05-26-dashboard-dark-theme-design.md): two-color base (`#262624` / `#f0eee6`) + one accent (`#c9a574`).

**Architecture:** Pure styling change. Rewrites `dashboard/styles.css`, swaps the vendored Tabulator theme CSS for its base CSS, removes color-bearing emojis from `dashboard/app.js` in favor of CSS-styled text glyphs, and tags the "recent form" KPI with an accent class when the value is ≥ 50. No metrics, no Python, no template structure changes.

**Tech Stack:** CSS, Tabulator (already vendored), vanilla JS in `dashboard/app.js`. No new dependencies.

---

## Files touched (overview)

- Delete: `dashboard/vendor/tabulator_midnight.min.css`
- Create: `dashboard/vendor/tabulator.min.css` (different file, same vendor)
- Modify: `chess_tracker/templates/index.html` (one `<link>` href)
- Modify: `dashboard/styles.css` (full rewrite, ~140 lines)
- Modify: `dashboard/app.js` (3 small edits: KPI accent class, board column width, emoji→glyph swaps)

There are no Python changes and no unit tests — frontend verification is visual per the existing Task 12 convention.

---

## Task 1: Re-vendor Tabulator base CSS

**Files:**
- Delete: `dashboard/vendor/tabulator_midnight.min.css`
- Create: `dashboard/vendor/tabulator.min.css`
- Modify: `chess_tracker/templates/index.html` (line 7)

- [ ] **Step 1: Remove the midnight theme CSS**

Run:
```bash
rm dashboard/vendor/tabulator_midnight.min.css
```

- [ ] **Step 2: Download the base Tabulator CSS**

Run:
```bash
curl -sLo dashboard/vendor/tabulator.min.css \
  https://unpkg.com/tabulator-tables@6.2.5/dist/css/tabulator.min.css
test -s dashboard/vendor/tabulator.min.css && echo "OK $(wc -c < dashboard/vendor/tabulator.min.css) bytes"
```

Expected: prints "OK <bytes>" with bytes > 30000.

- [ ] **Step 3: Update the template stylesheet link**

In `chess_tracker/templates/index.html`, change line 7 from:

```html
  <link rel="stylesheet" href="vendor/tabulator_midnight.min.css">
```

to:

```html
  <link rel="stylesheet" href="vendor/tabulator.min.css">
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/vendor/ chess_tracker/templates/index.html
git commit -m "chore(dashboard): swap Tabulator midnight theme for base CSS"
```

---

## Task 2: Rewrite `dashboard/styles.css`

**Files:**
- Modify: `dashboard/styles.css` (full rewrite)

- [ ] **Step 1: Replace `dashboard/styles.css` with the following content**

```css
/* dashboard/styles.css — minimal warm-dark theme
 * Spec: docs/superpowers/specs/2026-05-26-dashboard-dark-theme-design.md
 */

:root {
  --bg: #262624;
  --surface: #2d2d2a;
  --surface-2: #34342f;
  --accent-bg: #332e26;
  --text: #f0eee6;
  --muted: #8a8a82;
  --border: #3a3a37;
  --accent: #c9a574;
  --board-light: #d8c9a8;
  --board-dark: #5a5852;
  --piece-fg: #111111;
}

* { box-sizing: border-box; }
html, body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
}

/* KPI strip */
header#kpi-strip {
  position: sticky; top: 0; z-index: 10;
  display: flex; gap: 2rem; align-items: center;
  padding: 1.1rem 1.5rem;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.kpi { display: flex; flex-direction: column; }
.kpi-label {
  font-size: 0.7rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.05em;
}
.kpi-value { font-size: 1.5rem; font-weight: 600; margin-top: 0.2rem; }
.kpi-value.accent { color: var(--accent); }

main { padding: 1.5rem; max-width: 1200px; margin: 0 auto; }
section { margin-bottom: 2.5rem; }
section h2 {
  margin: 0 0 0.75rem;
  font-size: 1.1rem; font-weight: 600; letter-spacing: -0.01em;
}
section h2 small {
  color: var(--muted); font-weight: 400; font-size: 0.8rem;
  margin-left: 0.5rem;
}
section h3 {
  margin: 1rem 0 0.5rem;
  font-size: 0.85rem; font-weight: 500;
  color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.05em;
}

/* Leak summary */
.leak {
  padding: 0.7rem 1rem; margin-bottom: 0.4rem;
  background: var(--surface);
  border-left: 2px solid var(--border);
}
.leak.severity-warn { border-left-color: var(--accent); }
.leak.severity-critical {
  border-left-color: var(--accent); border-left-width: 3px;
  background: var(--accent-bg);
}
.leak .leak-name { font-weight: 600; }
.leak .leak-evidence { color: var(--muted); font-size: 0.85rem; margin-top: 0.15rem; }
.leak .leak-action { font-size: 0.85rem; margin-top: 0.3rem; }

/* Next-session rule */
.rule-block {
  background: var(--surface);
  padding: 1rem 1.25rem; border-radius: 4px;
  display: grid; grid-template-columns: max-content 1fr;
  gap: 0.4rem 1.5rem;
}
.rule-block dt { color: var(--muted); font-size: 0.85rem; }
.rule-block dd { margin: 0; font-weight: 600; font-size: 0.85rem; }
.rule-narrative {
  margin-top: 0.8rem; padding-top: 0.8rem;
  border-top: 1px solid var(--border);
  font-style: italic; color: var(--muted); font-size: 0.85rem;
}

/* Process metrics */
.process-grid {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
.process-card {
  background: var(--surface);
  padding: 0.75rem 1rem; border-radius: 4px;
}
.process-card .pm-label {
  color: var(--muted); font-size: 0.7rem;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.process-card .pm-value { font-size: 1.3rem; font-weight: 600; margin-top: 0.2rem; }

/* Sparkline */
.sparkline { display: inline-flex; gap: 2px; align-items: end; height: 14px; }
.spark-bar { width: 4px; }
.spark-W { background: var(--accent); height: 100%; }
.spark-L { background: var(--border); height: 100%; }
.spark-D { background: var(--muted); height: 60%; }

/* Cell formatting */
.cell-strong { color: var(--accent); font-weight: 600; }
.cell-weak { /* spec: no color on weak cells */ }
.row-low-conf { opacity: 0.45; }

/* Confidence / tilt indicator glyphs */
.ind-on  { color: var(--accent); }
.ind-off { color: var(--muted); }

/* Primary button */
#copy-suggestions {
  margin-top: 0.75rem; padding: 0.5rem 1rem;
  background: var(--accent); color: #1a1a18;
  border: 0; border-radius: 3px;
  cursor: pointer; font-weight: 600; font-size: 0.85rem;
}

/* Mini FEN board (play-signatures table cell) */
.board {
  display: grid;
  grid-template-columns: repeat(8, 14px);
  grid-auto-rows: 14px;
  width: 112px; height: 112px;
}
.board > div {
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; line-height: 14px;
  color: var(--piece-fg);
  user-select: none;
}
.board .light { background: var(--board-light); }
.board .dark  { background: var(--board-dark); }

/* ===== Tabulator overrides (base CSS handles structure) ===== */
.tabulator {
  background: transparent;
  border: 0;
  font-size: 0.85rem;
  color: var(--text);
}
.tabulator-header,
.tabulator .tabulator-header {
  background: transparent !important;
  border-bottom: 1px solid var(--border) !important;
  border-top: 0 !important;
  color: var(--muted);
}
.tabulator .tabulator-header .tabulator-col {
  background: transparent !important;
  border-right: 0 !important;
}
.tabulator .tabulator-header .tabulator-col .tabulator-col-content .tabulator-col-title {
  color: var(--muted);
  font-size: 0.72rem; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.tabulator-row,
.tabulator .tabulator-row {
  background: transparent !important;
  border-bottom: 1px solid var(--border) !important;
  color: var(--text);
}
.tabulator .tabulator-row.tabulator-row-even {
  background: transparent !important;
}
.tabulator .tabulator-row:hover {
  background: var(--surface) !important;
}
.tabulator .tabulator-cell {
  border-right: 0 !important;
  padding: 0.6rem 0.75rem;
}
.tabulator .tabulator-row.row-low-conf {
  opacity: 0.45;
}
.tabulator .tabulator-header-filter input {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 0.2rem 0.4rem;
  font-size: 0.8rem;
}
.tabulator a {
  color: var(--accent);
  text-decoration: none;
}
.tabulator a:hover { text-decoration: underline; }
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/styles.css
git commit -m "feat(dashboard): minimal warm-dark theme per spec"
```

---

## Task 3: Update `dashboard/app.js` (KPI accent + board width + emoji swaps)

**Files:**
- Modify: `dashboard/app.js:32` (KPI accent class)
- Modify: `dashboard/app.js:141` (Conf column emoji → glyph)
- Modify: `dashboard/app.js:157` (board column width 144 → 128)
- Modify: `dashboard/app.js:183` (Tilt column emoji → glyph)

- [ ] **Step 1: Add accent class to recent-form KPI value**

Find this line in `dashboard/app.js` (around line 32, inside `renderKPI`):

```javascript
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value">${k.recent_form_win_pct}%</span></div>
```

Replace with:

```javascript
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value${k.recent_form_win_pct >= 50 ? " accent" : ""}">${k.recent_form_win_pct}%</span></div>
```

- [ ] **Step 2: Swap the Conf column emojis for styled glyphs**

Find this column definition (around line 140–141, inside `renderPlaySignatures`):

```javascript
        {title: "Conf", field: "low_confidence",
         formatter: c => c.getValue() ? "⚪" : "🟢", width: 60, sorter: (a,b)=> (a?1:0)-(b?1:0)},
```

Replace with:

```javascript
        {title: "Conf", field: "low_confidence",
         formatter: c => c.getValue()
           ? `<span class="ind-off">○</span>`
           : `<span class="ind-on">●</span>`,
         width: 60, sorter: (a,b)=> (a?1:0)-(b?1:0)},
```

- [ ] **Step 3: Change the board column width from 144 to 128**

Find this column definition (around line 156–157):

```javascript
        {title: "Board@8", field: "play_signature", formatter: boardCell,
         width: 144, headerSort: false},
```

Replace with:

```javascript
        {title: "Board@8", field: "play_signature", formatter: boardCell,
         width: 128, headerSort: false},
```

- [ ] **Step 4: Swap the Tilt column emoji for a styled glyph**

Find this column definition (around line 182–183, inside `renderSessions`):

```javascript
        {title: "Tilt", field: "tilt_flag", width: 80,
         formatter: c => c.getValue() ? "🔴" : ""},
```

Replace with:

```javascript
        {title: "Tilt", field: "tilt_flag", width: 80,
         formatter: c => c.getValue() ? `<span class="ind-on">●</span>` : ""},
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.js
git commit -m "feat(dashboard): style indicators as text glyphs; accent on recent-form KPI"
```

---

## Task 4: Verify visually

**Files:** none modified — manual verification only.

- [ ] **Step 1: Render the dashboard against live data**

Run:
```bash
uv run refresh.py
```

Expected: completes without error and writes `dashboard/index.html`.

If the Chess.com API is unreachable in this environment, skip to Step 2 with the previously rendered `dashboard/index.html` if one exists; otherwise note the blocker and stop here.

- [ ] **Step 2: Open the dashboard in a browser**

Run:
```bash
open dashboard/index.html
```

- [ ] **Step 3: Visual checklist**

Walk through the page and confirm each of these. Mark FAIL next to any that don't match — a FAIL means returning to the relevant task to adjust.

- [ ] Page background is warm dark gray (`#262624`), not chess-green / amber / red anywhere.
- [ ] Body text is warm off-white (`#f0eee6`), readable against the background.
- [ ] KPI strip is sticky at the top with the slightly-lighter surface color.
- [ ] The "Recent form" KPI value is accent-tan (`#c9a574`) when win% ≥ 50; otherwise primary text color.
- [ ] Leak rows: regular leaks have a thin gray border-left; warn leaks have a 2px tan border-left; critical leaks have a 3px tan border-left AND a tan-tinted background.
- [ ] Sparkline: win bars are tan, loss bars are gray (the border color), draw bars are muted at 60% height.
- [ ] Strong stat cells (win% ≥ 60) are tan and bold; weak cells (win% ≤ 35) are NOT colored.
- [ ] Confidence column shows ● (tan) for high confidence and ○ (muted) for low — no emoji squares.
- [ ] Tilt column shows ● (tan) on tilt sessions — no red emoji circle.
- [ ] Low-confidence rows render at ~45% opacity.
- [ ] Mini chess board: 112×112px, light squares warm tan, dark squares warm gray, piece glyphs near-black.
- [ ] "Copy starter entries" button is solid tan background with near-black text.
- [ ] Section headings are smaller (1.1rem) than they were before; sub-labels in headings appear muted next to the title.
- [ ] Table headers are uppercase, small, muted, with letter-spacing.
- [ ] Hover on a table row shows a subtle surface-color highlight.

- [ ] **Step 4: If any item failed, return to the relevant task**

For each FAIL, identify the task that touches the relevant CSS rule or JS line, adjust it, re-commit, and re-render.

- [ ] **Step 5: Final commit checkpoint**

If all checklist items pass, no further commit needed — Tasks 1-3 have already committed the work. End the implementation.

---

## Self-review (already performed during plan writing)

- **Spec coverage:** Every accent-usage rule in the spec maps to a task step:
  - Critical leak / warn leak → Task 2 CSS `.leak.severity-*` rules.
  - Win bars sparkline → Task 2 CSS `.spark-W` / `.spark-L` / `.spark-D`.
  - Strong cells ≥ 60% → unchanged (existing `cell-strong` formatter in `winPctCell`); CSS in Task 2 styles it.
  - Confidence dot → Task 3 Step 2.
  - Board light squares → Task 2 CSS `.board .light`.
  - Primary button → Task 2 CSS `#copy-suggestions`.
  - Recent form KPI accent → Task 3 Step 1.
- **Removed Task-12 items confirmed:**
  - `tabulator_midnight.min.css` removed → Task 1 Step 1.
  - Emojis `🟢`/`⚪`/`🔴` removed → Task 3 Steps 2 and 4.
  - `--accent: #769656`, `--warn: #c4a01e`, `--bad: #b54a3f` tokens gone → Task 2 full CSS rewrite.
- **Type consistency:** Class names `.spark-W` / `.spark-L` / `.spark-D` match the `sparkline()` formatter in `app.js`. `.cell-strong` / `.cell-weak` match the `winPctCell` and `rating_delta` formatters. `.row-low-conf` matches the `rowFormatter` in `renderPlaySignatures`. `.ind-on` / `.ind-off` are introduced in both Task 2 (CSS) and Task 3 (JS) consistently.
- **No placeholders.**
