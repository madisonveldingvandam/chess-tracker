# Refresh button — design

> **SUPERSEDED (2026-05-29).** The `refresh.py --serve` localhost design below
> assumes a local-server reading workflow that no longer applies after GitHub
> Pages auto-deploy landed (`21e30ae`). Replaced by Option B in
> [../../research/2026-05-29-refresh-button-options.md](../../research/2026-05-29-refresh-button-options.md):
> a ↻ Refresh link in the KPI strip pointing at the Actions deploy workflow.
> Kept for reference only.

**Date:** 2026-05-27
**Scope:** Add a "Refresh" affordance to the dashboard that triggers `refresh.py`'s pipeline on demand, without leaving the browser. Requires a small stdlib HTTP server mode in `refresh.py` because the static-file-only workflow (`python3 -m http.server 8000`) cannot run Python. No new dependencies.

## Motivation

Today, getting new game data into the dashboard requires:

1. Stop watching the browser.
2. `Ctrl-C` the `python3 -m http.server`.
3. `uv run refresh.py` in the terminal.
4. Restart `python3 -m http.server 8000`.
5. Reload the browser tab.

A button reduces that to one click. The CLI flow remains the default; the server mode is purely additive for the interactive use case.

## Architecture

The browser cannot run `refresh.py` directly. Something on localhost must accept a POST and run the pipeline. Two changes:

1. **`refresh.py --serve`** — new flag that starts a `http.server.ThreadingHTTPServer` bound to `127.0.0.1:8000` (port configurable via `--port`). The server both serves `dashboard/` as static files **and** exposes `POST /refresh`. Replaces the user's habit of running `python3 -m http.server 8000` separately. The default behavior of `refresh.py` (one-shot fetch + render + exit) is unchanged.

2. **Refresh button + handler** in the shared KPI strip on every page. Clicking it POSTs to `/refresh` on the same origin and reloads on success.

Binding to `127.0.0.1` (not `0.0.0.0`) keeps the endpoint off the LAN. No auth, no HTTPS — local-only.

## Server side

### `refresh.py` changes

Add to the existing `argparse` block:

```python
ap.add_argument("--serve", action="store_true",
                help="Serve dashboard/ on http://127.0.0.1:<port> with a POST /refresh endpoint.")
ap.add_argument("--port", type=int, default=8000)
```

After existing `args = ap.parse_args(argv)`:

```python
if args.serve:
    return _serve(args)
```

`_serve(args)` (new function, ~25 lines, same file):

1. Construct a `RefreshHandler` class — `SimpleHTTPRequestHandler` subclass rooted at `args.dashboard_dir`.
2. Override `do_POST`: if `self.path == "/refresh"`, run the same pipeline as `main()` minus the argparse plumbing (factor the fetch + parse + compute + render block into a helper `_run_refresh(args)` so both `main` and the POST handler share one source of truth), then respond `200 application/json` with `{"status":"ok","generated_at":<payload.generated_at>}`. On exception, respond `500 application/json` with `{"status":"error","detail":<str(exc)>}`. Any other POST path → `404`.
3. `ThreadingHTTPServer(("127.0.0.1", args.port), RefreshHandler)` — threading so a slow refresh doesn't block parallel `GET styles.css` requests.
4. Print `Serving http://127.0.0.1:{port}/dashboard/index.html — Ctrl-C to stop.` and `serve_forever()`.

The current `main()` body is refactored: everything after `args = ap.parse_args(argv)` — the fetch / parse / compute-metrics / render block — moves into `_run_refresh(args)`. `main()` parses args, then either calls `_serve(args)` (if `--serve`) or `_run_refresh(args)` (default). This keeps the existing CLI behavior bit-for-bit and gives the POST handler one canonical call.

### `--force` semantics

The button POST does **not** pass `--force`. Force semantics (re-fetch every archive) stays a CLI-only flag for explicit recovery. Button click maps to a normal refresh — re-fetches the current month only, which is what someone clicking "give me the latest" actually wants. No second "Force refresh" button.

### Error contract

| Condition                                  | Status | Body                                              |
|--------------------------------------------|--------|---------------------------------------------------|
| Refresh succeeds                           | 200    | `{"status":"ok","generated_at":"<iso8601>"}`      |
| Chess.com fetch raises (HTTPError, etc.)   | 500    | `{"status":"error","detail":"<exception message>"}` |
| `POST` to any path other than `/refresh`   | 404    | empty                                             |
| `GET /anything.{html,css,js}`              | 200/404| served from `dashboard/` via SimpleHTTPRequestHandler default |

## Client side

### Template change

In each of the five templates (`chess_tracker/templates/{index,leaks,losses,process,sessions}.html`), insert one line into the `<header id="kpi-strip">`:

```html
<button id="refresh-btn" type="button">↻ Refresh</button>
```

For `index.html` the header is currently `<header id="kpi-strip"></header>` — the button is the only child until `renderKPI()` appends the KPI tiles. The detail pages currently have `<header id="kpi-strip"><a class="home-link" href="index.html">← repertoire</a></header>` — the button goes after the home link so the order reads "← back / KPIs… / Refresh".

The KPI strip already exists on every page; the button is the only new DOM.

### `app.js` change

Add `renderRefreshButton()` called once during the IIFE setup, mirroring the other `render*` calls at the top:

```js
renderRefreshButton();
// existing render calls...
```

```js
function renderRefreshButton() {
  const btn = document.getElementById("refresh-btn");
  if (!btn) return;
  const originalText = btn.textContent;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Refreshing…";
    try {
      const res = await fetch("/refresh", {method: "POST"});
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      window.location.reload();
    } catch (e) {
      console.error("Refresh failed:", e);
      btn.textContent = e.message.startsWith("HTTP")
        ? "Refresh failed — see console"
        : "No refresh server — run \"uv run refresh.py --serve\"";
      setTimeout(() => {
        btn.textContent = originalText;
        btn.disabled = false;
      }, 4000);
    }
  });
}
```

Notes:

- No spinner image — the label change IS the visual feedback.
- `fetch` throwing (TypeError) means the dashboard was opened over `file://` or via a static server with no `/refresh` endpoint. The error message distinguishes this case so the user knows to switch entry points.
- Success path reloads the whole page rather than re-rendering in place — simpler, picks up the new `window.DATA` payload via the freshly rendered HTML.

### `styles.css` change

Add ~10 lines to `dashboard/styles.css`:

```css
#refresh-btn {
  /* muted by default — uses the same --muted / --border tokens as KPI labels
     so the button blends with the rest of the strip until interacted with. */
  background: transparent;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.25rem 0.6rem;
  font-size: 0.85rem;
  cursor: pointer;
  margin-left: auto;  /* push to far right of the strip */
}
#refresh-btn:hover:not(:disabled) { color: var(--text); border-color: var(--text); }
#refresh-btn:disabled { cursor: wait; opacity: 0.6; }
```

The `margin-left: auto` keeps the button visually anchored to the right while the home-link and KPIs flow naturally on the left.

## Testing

`tests/test_refresh.py` already exists (currently [tests/test_refresh.py](../../tests/test_refresh.py), 40 lines, one test). Extend it with four new tests using the same `monkeypatch.chdir(tmp_path)` + `patch("chess_tracker.api.urlopen", ...)` pattern.

To avoid blocking on `serve_forever()`, tests instantiate the handler against a `ThreadingHTTPServer` on port `0` (ephemeral) in a daemon thread, then issue requests via `urllib.request.urlopen` against the bound address. Use `server.shutdown()` in a try/finally to tear down.

Tests to add:

1. **`test_serve_mode_serves_dashboard_html`** — Pre-seed `tmp_path/dashboard/index.html` with known content. Start server in thread. `GET /index.html`. Assert 200 + body matches.
2. **`test_post_refresh_runs_pipeline_and_returns_ok`** — `monkeypatch.chdir(tmp_path)`, patch `urlopen` per the existing fixture, start server in thread. `POST /refresh`. Assert 200 + JSON body with `"status":"ok"` and an ISO `generated_at`. Assert `tmp_path/data/computed.json` was written by the POST (the handler runs the same `_run_refresh` helper as the CLI).
3. **`test_post_refresh_returns_500_on_fetcher_exception`** — Same setup, but `patch("chess_tracker.api.urlopen", side_effect=URLError("boom"))`. `POST /refresh`. Assert 500 + JSON body with `"status":"error"` and `detail` containing `"boom"`.
4. **`test_post_unknown_path_returns_404`** — Start server. `POST /not-a-route`. Assert 404.

The existing `test_refresh_main_writes_computed_and_dashboard` is unchanged — it tests CLI one-shot mode, which the refactor preserves.

Full suite must remain green (51 + 5 from leak spec + 4 here = 60 expected, assuming both specs land).

## Files touched

- `refresh.py` — refactor `main` body into `_run_refresh(args)` helper; add `--serve` / `--port` flags and `_serve(args)` function with handler class. ~50 lines added net.
- `chess_tracker/templates/index.html` — add `<button>` line.
- `chess_tracker/templates/leaks.html` — add `<button>` line.
- `chess_tracker/templates/losses.html` — add `<button>` line.
- `chess_tracker/templates/process.html` — add `<button>` line.
- `chess_tracker/templates/sessions.html` — add `<button>` line.
- `dashboard/app.js` — add `renderRefreshButton()` (~25 lines).
- `dashboard/styles.css` — add `#refresh-btn` rules (~10 lines).
- `tests/test_refresh.py` — add 4 tests (~60 lines).

No other files in scope. Metrics, render layer, API, and annotation modules are untouched.

## Out of scope

- Auth / HTTPS / non-localhost binding.
- CORS — same-origin only.
- Async refresh with progress streaming (SSE, WebSockets).
- In-place re-render after refresh (vs full page reload).
- A second "Force full refresh" button (the `--force` CLI flag remains the only way to re-fetch every archive).
- Coexistence with `python3 -m http.server 8000` on the same port (the user is expected to stop the static server when running `--serve`).
- Coordination with the outlasted-but-flagged leak spec — these are functionally independent and ship together only by sharing the v1.2.0 tag.
