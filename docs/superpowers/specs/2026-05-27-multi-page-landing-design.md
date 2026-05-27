# Multi-page landing redesign — design

**Date:** 2026-05-27
**Scope:** Restructure the chess-tracker dashboard from one stuffed single-page view into a landing page focused on the repertoire (table + sticky board) plus four detail pages reachable from drill-in cards. Pure structural / IA change. No metrics, no Python pipeline, no Tabulator vendoring changes.

## Goal

The landing answers one question — "what does my repertoire look like and which positions need work" — by promoting the play-signatures table + sticky board to the top of `index.html`. Everything secondary (leaks, losses, process, sessions) moves to its own HTML page reachable from a card grid at the bottom of the landing. The browser handles navigation; real URLs, real back button, no JS routing.

## Pages

Five HTML files in `dashboard/`:

| File              | Headline content                                             |
|-------------------|--------------------------------------------------------------|
| `index.html`      | KPI strip · Repertoire (table + sticky board) · 4 drill-in cards |
| `leaks.html`      | KPI strip · Leak summary · Next-session rule                 |
| `losses.html`     | KPI strip · Recent losses · Copy starter entries · Error log |
| `process.html`    | KPI strip · Process metric cards · Session-position decay table |
| `sessions.html`   | KPI strip · Sessions table                                   |

Every page is independent — open `losses.html` directly and it works.

## Shared layout

Every page has:

1. **Sticky KPI strip** with 5 fields:
   - Rating
   - Games (total)
   - Recent form (win %)
   - Last session Δ rating
   - Updated (timestamp)
2. **Back-home affordance** on every detail page: a small "← repertoire" link in the top-left of the header, before the KPIs.
3. **Main content** specific to the page.
4. **Same `vendor/tabulator.min.js` + `vendor/tabulator.min.css` + `styles.css` + `app.js`** loaded by every page. No per-page bundles.

## Drill-in cards (landing only)

Four cards in a single row at the bottom of `index.html`. Each card is an `<a href="…">` to the corresponding detail page. Each card shows: label, headline value, sub-line.

| Card           | Headline             | Sub-line                                  | Links to        |
|----------------|----------------------|-------------------------------------------|-----------------|
| Leaks          | `N active`           | `Worst: <name of first critical leak, then first warn leak, else "none">` | `leaks.html`    |
| Recent losses  | `N`                  | `<top 2 loss_type counts, e.g. "5 timeout, 7 checkmated">` | `losses.html`   |
| Process        | `<velocity>s @ 8`    | `Target ≥ 18s`                            | `process.html`  |
| Sessions       | `N total`            | `<K tilted of last 5 sessions>`           | `sessions.html` |

Card accent-bg / accent-border treatment:

- **Leaks**: accent treatment when any leak has `severity == "critical"`.
- **Recent losses**: accent treatment when count ≥ 10.
- **Process**: accent treatment when `opening_velocity_median < 18` (below target).
- **Sessions**: accent treatment when last session had `tilt_flag == true`.
- Otherwise: neutral `--border` left border, no accent text.

If a card's data is empty: leaks card shows headline `0 active` / sub `"all clear"`; losses card shows `0` / `"none in last 30"`; process card shows `—` / `"insufficient data"`; sessions card shows `0` / `"no sessions"`. The cards still render — never hidden.

## Data flow

- `refresh.py` builds the payload once (no change to metrics pipeline).
- `chess_tracker/render.py` gets a new function `render_all_pages(template_dir, output_dir, payload)` that iterates over the 5 template names and calls the existing `render_dashboard()` for each, writing each to `output_dir/<name>.html`.
- Every page injects the **full** `window.DATA` payload. Yes, `sessions.html` doesn't strictly need the play-signatures slice — but the payload is ~100KB JSON, costs ~10ms to parse, and shipping it everywhere keeps the renderer trivial. (We can split per-page payloads later if it ever matters.)

## JS behavior

`app.js` runs on every page. It tries to render every section; each render function gains a top-of-function guard:

```js
function renderLeaks(leaks) {
  const root = document.getElementById("leak-list");
  if (!root) return;       // not on this page; skip silently
  // ...existing body
}
```

This pattern goes on `renderKPI`, `renderLeaks`, `renderRule`, `renderRecentLosses`, `renderErrorLog`, `renderProcess`, `renderSessionDecay`, `renderPlaySignatures`, `renderSessions`. The drill-in card renderer is new:

```js
function renderDrillinCards(D) {
  const root = document.getElementById("drillin-cards");
  if (!root) return;
  // build 4 <a> cards from summary computations
}
```

The four summary computations (worst leak name, loss-type counts, tilted-session count) are derived inline from the existing payload — no new metrics in Python.

## Template structure

Five self-contained templates in `chess_tracker/templates/`, one per page. No partials, no includes — each template is the full HTML for its page. They share copy-paste-identical boilerplate (`<head>`, KPI strip markup, vendor `<script>` tags, data injection point, `app.js`), which is fine: five small files are easier to reason about than a fragile templating layer.

The only structural difference between the landing template and the four detail templates: detail templates have `<a class="home-link" href="index.html">← repertoire</a>` inside the KPI strip, before the JS-populated KPIs. The landing template doesn't. The home link is just HTML — no Python substitution needed.

Each template carries its own `<title>` (`Chess Tracker — Repertoire — {{USERNAME}}`, `... — Leaks — ...`, etc.) so browser tabs are distinguishable.

## CSS additions

- `.drillin-grid` — 4-column card grid, gap 0.6rem.
- `.card` (drill-in card) — `--surface` background, left border 2px `--border`, padding 0.7rem 0.85rem.
- `.card.alert` — left border `--accent`; headline text `--accent`.
- `.card .label` / `.headline` / `.sub` — type scale matching the mockup.
- `.home-link` — small muted link inside the KPI strip, before the KPIs.

No changes to the existing repertoire / table / board CSS. The signatures section just moves up.

## What is removed from the current landing

- "Leak summary" section in `index.html` → moves to `leaks.html`.
- "Next session rule" section in `index.html` → moves to `leaks.html` (paired with leaks: same decision).
- "Recent losses → error log" section in `index.html` → moves to `losses.html`.
- "Process metrics" + "Session-position decay" sections in `index.html` → both move to `process.html`.
- "Sessions" section in `index.html` → moves to `sessions.html`.

## What is kept on the landing

- KPI strip (with the 5 fields listed above; "Last session" is new — derived inline from `D.sessions[0].rating_delta`).
- The entire "Play signatures" section, including the sticky board panel built in the previous feature. Promoted to be the main content.
- A new "Drill in" row of 4 cards beneath the signatures section.

## Test changes

- `tests/test_render.py`: existing two tests stay (they exercise the single-file `render_dashboard`). Add one new test for `render_all_pages` that verifies all five output files are written and each contains `window.DATA` + its expected section ID (e.g. `losses.html` contains `id="losses-table"`).
- `tests/test_refresh.py`: existing test currently asserts `window.DATA` in `dashboard/index.html`. It should also verify the four other files exist after a successful refresh.

## Implementation notes

- Render.py changes are additive: keep `render_dashboard()` as-is so existing tests stay green; add `render_all_pages()` that calls it five times.
- The four-template list is a Python constant (`PAGE_TEMPLATES = ["index", "leaks", "losses", "process", "sessions"]`), iterated by `render_all_pages`. To add a sixth page later: add to the list and create one template file.
- `refresh.py` switches from calling `render_dashboard(...)` to `render_all_pages(...)`. The CLI behavior (writes to `dashboard/`) is unchanged.
- The KPI strip's "Last session Δ" is computed inline in `renderKPI()` from `D.sessions[0].rating_delta` if present, falls back to `"—"`.

## Non-goals

- No data-loading-once optimization (no separate `data.js`). Each page injects the full payload inline.
- No client-side routing, no hash URLs, no SPA framework.
- No new metrics. All card sub-lines derive from the existing payload.
- No new vendor dependencies.
- No mobile-specific responsive behavior beyond the existing `<900px` stack for the repertoire split.
- No "next session rule" banner on the landing — the rule lives only on `leaks.html`.

## Open questions

None — every decision above is concrete. If anything in the next-step implementation plan needs to revisit a choice, the choice should be flagged and brought back here.
