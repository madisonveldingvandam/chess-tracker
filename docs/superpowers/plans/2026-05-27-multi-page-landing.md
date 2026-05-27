# Multi-page landing implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the chess-tracker dashboard into 5 separate HTML pages per [docs/superpowers/specs/2026-05-27-multi-page-landing-design.md](../specs/2026-05-27-multi-page-landing-design.md): a slim landing focused on the repertoire (table + sticky board) with 4 drill-in cards that link to dedicated `leaks.html` / `losses.html` / `process.html` / `sessions.html` pages.

**Architecture:** Add `render_all_pages()` to `chess_tracker/render.py` that iterates a fixed `PAGE_TEMPLATES` list and reuses the existing `render_dashboard()` per template. Switch `refresh.py` to call it. Split the current monolithic `chess_tracker/templates/index.html` into 5 self-contained templates. Add null-guards to every render function in `dashboard/app.js` so each function no-ops when its target element isn't on the page. Add a `renderDrillinCards()` function that derives the 4 card summaries inline from the existing payload.

**Tech Stack:** Python (additive change to `render.py`, one-line swap in `refresh.py`), pytest (two test updates), HTML/CSS/JS (4 new templates, slim `index.html`, app.js edits, CSS additions). No new dependencies.

---

## Files touched (overview)

- Modify: `dashboard/app.js` — null-guard all 9 render functions; switch `renderKPI` from `innerHTML` to `insertAdjacentHTML('beforeend', …)`; add "Last session" KPI field; rename "Games total" → "Games" and "Generated" → "Updated"; add `renderDrillinCards()` + `card()` helper + wire its call
- Modify: `dashboard/styles.css` — add `.home-link`, `.drillin-grid`, `.drillin-grid .card[.alert]` rules and one `<900px` breakpoint
- Modify: `chess_tracker/render.py` — add `DEFAULT_TEMPLATE_DIR` + `PAGE_TEMPLATES` constants + `render_all_pages()` function (keep `render_dashboard` unchanged)
- Modify: `refresh.py` — swap single-page call for `render_all_pages`; rename `--template-path` CLI arg to `--template-dir`
- Modify: `chess_tracker/templates/index.html` — slim to KPI + repertoire (renamed from "Play signatures") + drill-in cards placeholder
- Create: `chess_tracker/templates/leaks.html`, `losses.html`, `process.html`, `sessions.html`
- Modify: `tests/test_render.py` — add `test_render_all_pages_writes_one_file_per_template`
- Modify: `tests/test_refresh.py` — assert all 5 dashboard files exist after refresh

There are no metrics changes. There are no Tabulator vendoring changes.

---

## Task 1: app.js prep — null guards + KPI updates + drill-in cards

**Files:**
- Modify: `dashboard/app.js`

These changes are forward-compatible with the existing single-page setup: they don't break the current rendered dashboard.

- [ ] **Step 1.1: Add null guards to all 9 render functions**

Each function starts by looking up its target element; if it doesn't exist, return silently. In `dashboard/app.js`, modify the top of each function as follows.

Replace the `renderKPI` opening:

```javascript
  function renderKPI(d) {
    const k = d.kpis;
    document.getElementById("kpi-strip").innerHTML = `
```

with:

```javascript
  function renderKPI(d) {
    const strip = document.getElementById("kpi-strip");
    if (!strip) return;
    const k = d.kpis;
    const lastDelta = (d.sessions && d.sessions.length > 0) ? d.sessions[0].rating_delta : null;
    const lastStr = lastDelta == null ? "—" : (lastDelta >= 0 ? "+" : "") + lastDelta;
    strip.insertAdjacentHTML('beforeend', `
```

And change the closing `\`;` line from:

```javascript
    `;
  }
```

to:

```javascript
    `);
  }
```

(The opening backtick now follows `insertAdjacentHTML('beforeend',` so the closing must include the matching `)`.)

For `renderLeaks`, `renderRule`, `renderRecentLosses`, `renderErrorLog`, `renderProcess`, `renderSessionDecay`, `renderPlaySignatures`, `renderSessions`: insert a guard as the **first line** of the function body (before any other code).

Specific guards to add (insert each immediately after `function NAME(...) {`):

| Function               | Insert at top                                       |
|------------------------|-----------------------------------------------------|
| `renderLeaks`          | `if (!document.getElementById("leak-list")) return;` |
| `renderRule`           | `if (!document.getElementById("next-rule")) return;` |
| `renderRecentLosses`   | `if (!document.getElementById("losses-table")) return;` |
| `renderErrorLog`       | `if (!document.getElementById("error-log-table")) return;` |
| `renderProcess`        | `if (!document.getElementById("process-block")) return;` |
| `renderSessionDecay`   | `if (!document.getElementById("session-decay-table")) return;` |
| `renderPlaySignatures` | `if (!document.getElementById("play-signatures-table")) return;` |
| `renderSessions`       | `if (!document.getElementById("sessions-table")) return;` |

For `renderRecentLosses` specifically, also wrap the `copy-suggestions` button handler. Replace:

```javascript
    document.getElementById("copy-suggestions").onclick = () => {
      const entries = losses.map(L => L.suggested_entry);
      navigator.clipboard.writeText(JSON.stringify(entries, null, 2));
    };
```

with:

```javascript
    const copyBtn = document.getElementById("copy-suggestions");
    if (copyBtn) copyBtn.onclick = () => {
      const entries = losses.map(L => L.suggested_entry);
      navigator.clipboard.writeText(JSON.stringify(entries, null, 2));
    };
```

- [ ] **Step 1.2: Update the KPI strip labels and add the "Last session" field**

In the `renderKPI` body, the inline template string currently is:

```javascript
      <div class="kpi"><span class="kpi-label">Rating</span>
        <span class="kpi-value">${k.current_rating ?? "—"}</span></div>
      <div class="kpi"><span class="kpi-label">Games total</span>
        <span class="kpi-value">${k.games_total}</span></div>
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value${k.recent_form_win_pct >= 50 ? " accent" : ""}">${k.recent_form_win_pct}%</span></div>
      <div class="kpi"><span class="kpi-label">Generated</span>
        <span class="kpi-value" style="font-size:0.9rem">${new Date(d.generated_at).toLocaleString()}</span></div>
```

Replace it with:

```javascript
      <div class="kpi"><span class="kpi-label">Rating</span>
        <span class="kpi-value">${k.current_rating ?? "—"}</span></div>
      <div class="kpi"><span class="kpi-label">Games</span>
        <span class="kpi-value">${k.games_total}</span></div>
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value${k.recent_form_win_pct >= 50 ? " accent" : ""}">${k.recent_form_win_pct}%</span></div>
      <div class="kpi"><span class="kpi-label">Last session</span>
        <span class="kpi-value">${lastStr}</span></div>
      <div class="kpi"><span class="kpi-label">Updated</span>
        <span class="kpi-value" style="font-size:0.9rem">${new Date(d.generated_at).toLocaleString()}</span></div>
```

(The `lastStr` variable was added in Step 1.1's `renderKPI` opening rewrite. "Games total" → "Games"; "Generated" → "Updated"; new "Last session" between Recent form and Updated.)

- [ ] **Step 1.3: Add `renderDrillinCards` and `card` helper**

Add the following two functions inside the IIFE in `dashboard/app.js`, after `renderSessions` and before `function sparkline(cell)`:

```javascript
  function renderDrillinCards(D) {
    const root = document.getElementById("drillin-cards");
    if (!root) return;
    const leaks = D.leak_summary || [];
    const losses = D.recent_losses || [];
    const sessions = D.sessions || [];
    const pm = D.process_metrics || {};

    // Leaks card: alert when any critical leak exists
    const critical = leaks.find(L => L.severity === "critical");
    const firstWarn = leaks.find(L => L.severity === "warn");
    const worstName = critical ? critical.name : (firstWarn ? firstWarn.name : null);
    const leaksAlert = critical != null;
    const leaksSub = leaks.length === 0 ? "all clear"
      : worstName ? `Worst: ${worstName.replace(/_/g, " ")}`
      : `${leaks.length} active`;

    // Recent losses card: alert when count >= 10
    const lossCounts = {};
    losses.forEach(L => { lossCounts[L.loss_type] = (lossCounts[L.loss_type] || 0) + 1; });
    const topLossTypes = Object.entries(lossCounts).sort((a, b) => b[1] - a[1]).slice(0, 2);
    const lossesSub = losses.length === 0 ? "none in last 30"
      : topLossTypes.map(([t, n]) => `${n} ${t}`).join(", ");
    const lossesAlert = losses.length >= 10;

    // Process card: alert when opening_velocity_median < 18
    const velocity = pm.opening_velocity_median;
    const processHeadline = velocity == null ? "—" : `${velocity}s @ 8`;
    const processSub = velocity == null ? "insufficient data" : "Target ≥ 18s";
    const processAlert = velocity != null && velocity < 18;

    // Sessions card: alert when last session was tilted
    const sessionCount = sessions.length;
    const last5 = sessions.slice(0, 5);
    const tiltedCount = last5.filter(s => s.tilt_flag).length;
    const sessionsSub = sessionCount === 0 ? "no sessions"
      : `${tiltedCount} tilted of last 5`;
    const sessionsAlert = sessions.length > 0 && sessions[0].tilt_flag === true;

    root.innerHTML = [
      card("Leaks", `${leaks.length} active`, leaksSub, "leaks.html", leaksAlert),
      card("Recent losses", `${losses.length}`, lossesSub, "losses.html", lossesAlert),
      card("Process", processHeadline, processSub, "process.html", processAlert),
      card("Sessions", `${sessionCount} total`, sessionsSub, "sessions.html", sessionsAlert),
    ].join("");
  }

  function card(label, headline, sub, href, alert) {
    return `<a class="card${alert ? " alert" : ""}" href="${href}">
      <div class="label">${label}</div>
      <div class="headline">${headline}</div>
      <div class="sub">${sub}</div>
    </a>`;
  }
```

- [ ] **Step 1.4: Wire `renderDrillinCards` into the init block**

Find the init sequence near the top of the IIFE:

```javascript
  renderKPI(D);
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics.session_decay);
  renderPlaySignatures(D.play_signatures);
  renderSessions(D.sessions);
```

Add `renderDrillinCards(D);` as the new last line so the block becomes:

```javascript
  renderKPI(D);
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics.session_decay);
  renderPlaySignatures(D.play_signatures);
  renderSessions(D.sessions);
  renderDrillinCards(D);
```

- [ ] **Step 1.5: Run pytest to confirm no regression**

```bash
uv run pytest -q
```

Expected: 40 tests pass.

- [ ] **Step 1.6: Commit**

```bash
git add dashboard/app.js
git commit -m "feat(dashboard): null-guard render fns + add Last session KPI + drill-in card renderer

Forward-compatible refactor before splitting the dashboard into multiple
pages. Every render function now no-ops if its target element isn't on
the page. KPI strip switched from innerHTML to insertAdjacentHTML so a
static home-link can live in the same element on detail pages. Added a
new Last session KPI (derived from D.sessions[0].rating_delta) and
renderDrillinCards() that builds 4 anchor cards from the existing
payload."
```

---

## Task 2: CSS — drill-in cards + home link

**Files:**
- Modify: `dashboard/styles.css`

- [ ] **Step 2.1: Add the new CSS rules at the end of `dashboard/styles.css`**

Append the following block to the file:

```css

/* Home link in detail-page KPI strips */
.home-link {
  font-size: 0.75rem;
  color: var(--muted);
  text-decoration: none;
  padding: 0.3rem 0.6rem;
  margin-right: 0.5rem;
  border-right: 1px solid var(--border);
}
.home-link:hover { color: var(--accent); }

/* Drill-in cards (landing only) */
.drillin-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.6rem;
}
.drillin-grid .card {
  background: var(--surface);
  padding: 0.7rem 0.85rem;
  border-radius: 4px;
  border-left: 2px solid var(--border);
  text-decoration: none;
  color: var(--text);
  display: block;
  transition: background 0.1s ease;
}
.drillin-grid .card:hover { background: #34342f; }
.drillin-grid .card.alert { border-left-color: var(--accent); }
.drillin-grid .card .label {
  font-size: 0.6rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.05em;
}
.drillin-grid .card .headline {
  font-size: 1rem; font-weight: 600;
  margin: 0.15rem 0;
}
.drillin-grid .card.alert .headline { color: var(--accent); }
.drillin-grid .card .sub {
  font-size: 0.7rem; color: var(--muted);
  line-height: 1.3;
}

@media (max-width: 900px) {
  .drillin-grid { grid-template-columns: repeat(2, 1fr); }
}
```

- [ ] **Step 2.2: Commit**

```bash
git add dashboard/styles.css
git commit -m "feat(dashboard): styles for drill-in cards + home-link in detail pages"
```

---

## Task 3: TDD `render_all_pages` in `chess_tracker/render.py`

**Files:**
- Modify: `chess_tracker/render.py`
- Modify: `tests/test_render.py`

- [ ] **Step 3.1: Write the failing test**

Append the following test to `tests/test_render.py`:

```python


def test_render_all_pages_writes_one_file_per_template(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    output_dir = tmp_path / "out"
    page_names = ["index", "leaks", "losses", "process", "sessions"]
    for name in page_names:
        (template_dir / f"{name}.html").write_text(
            f"<title>{{{{USERNAME}}}}</title>"
            f"<section id='{name}-section'></section>"
            f"<script>/* DATA_INJECTION_POINT */</script>"
        )
    from chess_tracker.render import render_all_pages
    payload = {"username": "alice", "kpis": {"current_rating": 444}}
    render_all_pages(template_dir, output_dir, payload)
    for name in page_names:
        out = output_dir / f"{name}.html"
        assert out.exists(), f"missing {name}.html"
        html = out.read_text()
        assert "alice" in html
        assert "window.DATA" in html
        assert f"id='{name}-section'" in html
```

- [ ] **Step 3.2: Run the test to verify it fails**

```bash
uv run pytest tests/test_render.py::test_render_all_pages_writes_one_file_per_template -v
```

Expected: FAIL with `ImportError: cannot import name 'render_all_pages' from 'chess_tracker.render'` (or similar).

- [ ] **Step 3.3: Implement `render_all_pages`**

Add the following to `chess_tracker/render.py`. After the existing `DEFAULT_TEMPLATE_PATH` line, add a `DEFAULT_TEMPLATE_DIR` constant and a `PAGE_TEMPLATES` list:

Replace:

```python
INJECT_MARKER = "/* DATA_INJECTION_POINT */"
DEFAULT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"
```

with:

```python
INJECT_MARKER = "/* DATA_INJECTION_POINT */"
DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"
DEFAULT_TEMPLATE_PATH = DEFAULT_TEMPLATE_DIR / "index.html"
PAGE_TEMPLATES = ["index", "leaks", "losses", "process", "sessions"]
```

Append the following function at the end of the file:

```python


def render_all_pages(template_dir: Path, output_dir: Path, payload: dict) -> None:
    """Render each template in PAGE_TEMPLATES to <output_dir>/<name>.html.

    Each output file is produced by calling render_dashboard with the matching
    template at <template_dir>/<name>.html.
    """
    template_dir = Path(template_dir)
    output_dir = Path(output_dir)
    for name in PAGE_TEMPLATES:
        render_dashboard(
            template_path=template_dir / f"{name}.html",
            output_path=output_dir / f"{name}.html",
            payload=payload,
        )
```

- [ ] **Step 3.4: Run the test to verify it passes**

```bash
uv run pytest tests/test_render.py::test_render_all_pages_writes_one_file_per_template -v
```

Expected: PASS.

- [ ] **Step 3.5: Run the full suite to confirm no regressions**

```bash
uv run pytest -q
```

Expected: 41 tests pass (was 40; the new test is the +1).

- [ ] **Step 3.6: Commit**

```bash
git add chess_tracker/render.py tests/test_render.py
git commit -m "feat(render): add render_all_pages() + PAGE_TEMPLATES + DEFAULT_TEMPLATE_DIR

Iterates a fixed list of page names and calls the existing
render_dashboard() per template. Keeps render_dashboard unchanged so
existing tests stay green."
```

---

## Task 4: Create the 4 detail templates

**Files:**
- Create: `chess_tracker/templates/leaks.html`
- Create: `chess_tracker/templates/losses.html`
- Create: `chess_tracker/templates/process.html`
- Create: `chess_tracker/templates/sessions.html`

All four templates share the same outer structure. The only differences are the `<title>`, the section IDs in `<main>`, and the section copy. Every detail page includes a `home-link` inside its KPI strip.

- [ ] **Step 4.1: Create `chess_tracker/templates/leaks.html`**

```html
<!-- chess_tracker/templates/leaks.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — Leaks — {{USERNAME}}</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="kpi-strip"><a class="home-link" href="index.html">← repertoire</a></header>
  <main>
    <section id="leak-section"><h2>Leak summary</h2><div id="leak-list"></div></section>
    <section id="rule-section"><h2>Next session rule</h2><div id="next-rule"></div></section>
  </main>
  <script src="vendor/tabulator.min.js"></script>
  <script>
    /* DATA_INJECTION_POINT */
  </script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4.2: Create `chess_tracker/templates/losses.html`**

```html
<!-- chess_tracker/templates/losses.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — Losses — {{USERNAME}}</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="kpi-strip"><a class="home-link" href="index.html">← repertoire</a></header>
  <main>
    <section id="losses-section">
      <h2>Recent losses → error log</h2>
      <div id="losses-table"></div>
      <button id="copy-suggestions">Copy starter entries</button>
      <h3>Error log</h3>
      <div id="error-log-table"></div>
    </section>
  </main>
  <script src="vendor/tabulator.min.js"></script>
  <script>
    /* DATA_INJECTION_POINT */
  </script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4.3: Create `chess_tracker/templates/process.html`**

```html
<!-- chess_tracker/templates/process.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — Process — {{USERNAME}}</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="kpi-strip"><a class="home-link" href="index.html">← repertoire</a></header>
  <main>
    <section id="process-section"><h2>Process metrics</h2>
      <div id="process-block"></div>
      <h3>Session-position decay</h3>
      <div id="session-decay-table"></div>
    </section>
  </main>
  <script src="vendor/tabulator.min.js"></script>
  <script>
    /* DATA_INJECTION_POINT */
  </script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4.4: Create `chess_tracker/templates/sessions.html`**

```html
<!-- chess_tracker/templates/sessions.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — Sessions — {{USERNAME}}</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="kpi-strip"><a class="home-link" href="index.html">← repertoire</a></header>
  <main>
    <section id="sessions-section"><h2>Sessions</h2><div id="sessions-table"></div></section>
  </main>
  <script src="vendor/tabulator.min.js"></script>
  <script>
    /* DATA_INJECTION_POINT */
  </script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4.5: Commit**

```bash
git add chess_tracker/templates/leaks.html chess_tracker/templates/losses.html chess_tracker/templates/process.html chess_tracker/templates/sessions.html
git commit -m "feat(templates): add leaks/losses/process/sessions detail page templates

Each is a self-contained HTML file with a home-link in the KPI strip
and the section markup migrated from the current monolithic index.html.
Not yet rendered by refresh.py; that swap is the next task."
```

---

## Task 5: Slim down `index.html` + switch `refresh.py` to render_all_pages

**Files:**
- Modify: `chess_tracker/templates/index.html`
- Modify: `refresh.py`
- Modify: `tests/test_refresh.py`

This is the cut-over task. After this commit the dashboard works as the new multi-page experience.

- [ ] **Step 5.1: Replace `chess_tracker/templates/index.html` with the slim landing**

The current `chess_tracker/templates/index.html` contains 7 sections. Replace its entire contents with:

```html
<!-- chess_tracker/templates/index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — {{USERNAME}}</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="kpi-strip"></header>
  <main>
    <section id="signatures-section">
      <h2>Repertoire <small>sortable · click a row to see the position</small></h2>
      <div class="sig-split">
        <div id="play-signatures-table"></div>
        <aside class="board-panel">
          <div class="board-large" id="board-large"></div>
          <div class="board-meta" id="board-meta"></div>
        </aside>
      </div>
    </section>
    <section id="drillin-section">
      <h2>Drill in</h2>
      <div id="drillin-cards" class="drillin-grid"></div>
    </section>
  </main>
  <script src="vendor/tabulator.min.js"></script>
  <script>
    /* DATA_INJECTION_POINT */
  </script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 5.2: Update `tests/test_refresh.py` to assert all 5 output files exist**

Find this assertion block at the end of `test_refresh_main_writes_computed_and_dashboard`:

```python
    assert (tmp_path / "data" / "computed.json").exists()
    out_html = (tmp_path / "dashboard" / "index.html").read_text()
    assert "window.DATA" in out_html
```

Replace it with:

```python
    assert (tmp_path / "data" / "computed.json").exists()
    for name in ["index", "leaks", "losses", "process", "sessions"]:
        out = tmp_path / "dashboard" / f"{name}.html"
        assert out.exists(), f"missing {name}.html"
        html = out.read_text()
        assert "window.DATA" in html
```

- [ ] **Step 5.3: Run the refresh test to verify it fails**

```bash
uv run pytest tests/test_refresh.py -v
```

Expected: FAIL with an `AssertionError: missing leaks.html` (or similar) — `refresh.py` still calls `render_dashboard`, which only writes `index.html`.

- [ ] **Step 5.4: Modify `refresh.py` to call `render_all_pages` and rename the CLI arg**

In `refresh.py`, find this block at the top of `main()`:

```python
    ap.add_argument("--template-path", default=str(DEFAULT_TEMPLATE_PATH))
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw"
    dashboard_dir = Path(args.dashboard_dir)
    template = Path(args.template_path)
    output = dashboard_dir / "index.html"
    annotations_path = data_dir / "annotations.json"
```

Replace it with:

```python
    ap.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR))
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw"
    dashboard_dir = Path(args.dashboard_dir)
    template_dir = Path(args.template_dir)
    annotations_path = data_dir / "annotations.json"
```

Update the import line at the top of `refresh.py`:

```python
from chess_tracker.render import render_dashboard, DEFAULT_TEMPLATE_PATH
```

becomes:

```python
from chess_tracker.render import render_all_pages, DEFAULT_TEMPLATE_DIR
```

Find the render call near the end of `main()`:

```python
    render_dashboard(template_path=template, output_path=output, payload=payload)
```

Replace it with:

```python
    render_all_pages(template_dir=template_dir, output_dir=dashboard_dir, payload=payload)
```

Find the final `print(f"Done. Rendered to: ...")` line — it probably references `output`. Change the reference to use `dashboard_dir / "index.html"` so the user gets the landing URL. If the line reads:

```python
    print(f"Done. Rendered to: {output.resolve()}")
```

change to:

```python
    print(f"Done. Rendered to: {(dashboard_dir / 'index.html').resolve()}")
```

(If the existing print uses a different format, preserve that format — just swap the variable.)

- [ ] **Step 5.5: Run the refresh test to verify it passes**

```bash
uv run pytest tests/test_refresh.py -v
```

Expected: PASS — all 5 dashboard files now written.

- [ ] **Step 5.6: Run the full suite to confirm no regressions**

```bash
uv run pytest -q
```

Expected: 41 tests pass.

- [ ] **Step 5.7: Commit**

```bash
git add chess_tracker/templates/index.html refresh.py tests/test_refresh.py
git commit -m "feat(dashboard): switch refresh.py to multi-page render; slim index.html

index.html now hosts only the repertoire (table + sticky board) and the
drill-in card grid. Leaks/losses/process/sessions live on their own
pages, written alongside index.html by render_all_pages. CLI arg
renamed --template-path → --template-dir to match the new shape."
```

---

## Task 6: Visual verification

**Files:** none modified — manual verification only.

- [ ] **Step 6.1: Regenerate the dashboard against live data**

```bash
uv run refresh.py
ls dashboard/
```

Expected: `dashboard/` now contains `index.html`, `leaks.html`, `losses.html`, `process.html`, `sessions.html`, plus the existing `app.js`, `styles.css`, `vendor/`.

- [ ] **Step 6.2: Ensure the local HTTP server is up**

```bash
lsof -ti :8765 > /dev/null && echo "server running" || { python3 -m http.server 8765 > /tmp/chess-dash-server.log 2>&1 & disown; sleep 1; echo "started"; }
```

- [ ] **Step 6.3: Walk the visual checklist**

Open `http://localhost:8765/dashboard/index.html` in the browser, hard-refresh (Cmd+Shift+R), and confirm each item:

- [ ] Landing page renders: KPI strip (5 fields including "Last session"), the Repertoire section with the sortable table + sticky 320×320 board, and a 4-card "Drill in" grid at the bottom.
- [ ] Each drill-in card shows: label (uppercase muted), headline (1rem semibold), sub-line (muted). The cards link with normal text colour, not accent — unless the alert rules fire.
- [ ] Leaks card is accent-treated whenever any leak has severity `critical`.
- [ ] Losses card is accent-treated when there are ≥ 10 recent losses.
- [ ] Process card is accent-treated when `opening_velocity_median < 18`.
- [ ] Sessions card is accent-treated when the most-recent session was tilted.
- [ ] Cards have hover affordance (slight background change).
- [ ] Click each card → navigates to the corresponding detail page; URL bar updates; browser back returns to landing.
- [ ] `leaks.html` shows: KPI strip with "← repertoire" home-link before the KPIs; Leak summary section; Next session rule section.
- [ ] `losses.html` shows: KPI strip with home-link; recent losses table; "Copy starter entries" button (clicking it copies JSON to clipboard); error log table.
- [ ] `process.html` shows: KPI strip with home-link; process metric cards; session-position decay table.
- [ ] `sessions.html` shows: KPI strip with home-link; sessions table.
- [ ] Clicking the home-link on any detail page returns to `index.html` cleanly.
- [ ] No console errors in DevTools on any of the 5 pages.
- [ ] At a viewport narrower than 900px: drill-in grid becomes 2 columns; repertoire layout stacks (board above table).

- [ ] **Step 6.4: If any item failed, return to the relevant task**

For each FAIL, identify the task whose code change drove the behavior, fix it, re-commit, and re-render with `uv run refresh.py`.

- [ ] **Step 6.5: Done — no commit needed**

If all checklist items pass, Tasks 1–5 already committed the work. End the implementation.

---

## Self-review

**Spec coverage** — every section of the spec maps to a task:

- "5 HTML pages" → Tasks 4 (create detail templates) and 5 (slim index.html, switch refresh.py).
- "Shared layout: KPI strip + home-link on detail pages" → Task 1 (insertAdjacentHTML refactor lets the home-link stay) + Task 4 (each detail template includes the home-link element) + Task 2 (CSS rule).
- "5 KPI fields including 'Last session Δ'" → Task 1, Step 1.2.
- "Drill-in cards (4) with explicit headline/sub/alert rules" → Task 1, Step 1.3 (function logic implements the exact rules from the spec table).
- "Card data derived from existing payload (no new metrics)" → Task 1, Step 1.3 (computes everything from `D.leak_summary`, `D.recent_losses`, `D.process_metrics`, `D.sessions`).
- "Render.py changes are additive (keep render_dashboard)" → Task 3 (adds `render_all_pages` alongside existing function).
- "refresh.py one-line swap" → Task 5, Step 5.4 (plus the CLI arg rename, which is the only other refresh.py change).
- "Tests extended" → Task 3 (render_all_pages test), Task 5 (refresh test extended).
- "Detail templates carry distinct `<title>` for browser tabs" → Task 4 (each template's `<title>` is page-specific).

**Type / name consistency:**

- `PAGE_TEMPLATES` is `["index", "leaks", "losses", "process", "sessions"]` in three places: render.py constant (Task 3), test_render.py loop (Task 3), test_refresh.py loop (Task 5). All match.
- `render_all_pages(template_dir, output_dir, payload)` signature is consistent: defined in Task 3, called in Task 5 with matching kwargs.
- `DEFAULT_TEMPLATE_DIR` is introduced in Task 3 and imported / used in Task 5.
- `id="drillin-cards"` is set in Task 5 (index.html) and queried in Task 1 (`renderDrillinCards`). Matches.
- `class="home-link"` is set in Task 4 (each detail template) and styled in Task 2. Matches.
- `class="drillin-grid"` and `class="card[.alert]"` are set in Task 5 (index.html) and Task 1 (`card()` helper) and styled in Task 2. Matches.

**Placeholder scan:** No "TBD", "TODO", "etc." in code blocks. Every step shows the actual code to write or the actual command to run with its expected output. The visual checklist in Task 6 is exhaustive, not a "verify it works" stub.
