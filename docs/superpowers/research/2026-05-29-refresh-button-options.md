# Refresh button — re-exploration

**Date:** 2026-05-29
**Status:** Research / decision doc — supersedes the architecture in [2026-05-27-refresh-button-design.md](../specs/2026-05-27-refresh-button-design.md).
**Trigger:** Commit `21e30ae` ("ci: deploy dashboard to GitHub Pages on cron + push") landed a Pages auto-deploy after the original spec was written. The "`refresh.py --serve` on localhost" premise no longer matches how the dashboard is actually used.

## 1. Current reality

Refresh now happens in two places, neither of which is the user's terminal:

- **GitHub Actions — [`.github/workflows/deploy.yml`](../../../.github/workflows/deploy.yml)**
  - `schedule: cron "0 */6 * * *"` → runs four times a day (00:00, 06:00, 12:00, 18:00 UTC).
  - `push: branches: [main]` → runs on every push.
  - `workflow_dispatch` → manual trigger from the GitHub Actions UI.
  - Caches `data/raw` between runs (`actions/cache@v4`, keyed on `run_id` with `chess-archives-` restore prefix), so only the current month is re-fetched in steady state — same `force=current_month_url` shortcut that `refresh.py` uses locally.
  - Uploads `dashboard/` as a Pages artifact and deploys via `actions/deploy-pages@v4`.
- **Local CLI** — `uv run refresh.py` still works; the user can still serve locally via `python3 -m http.server 8000`.

What `refresh.py` does (unchanged): fetch archives → filter to rated 1+0 bullet → compute metrics → write `data/computed.json` → render the 6 templates in `chess_tracker/templates/` into `dashboard/*.html`. The full pipeline takes seconds against a warm archive cache, a minute-ish cold.

Published site: <https://madisonveldingvandam.github.io/chess-tracker/>. Per `.gitignore`, `data/` and `dashboard/*.html` are not committed — the deployed HTML only exists as a Pages artifact, never on `main`.

The user now lives on the published site. The original spec's `refresh.py --serve` mode would only be reachable from a localhost tab — exactly the workflow the user has moved away from.

## 2. Is the button still needed?

Short answer: **mostly no, narrowly yes.**

The cron + push triggers cover the two organic refresh events:

- **You played some games** → next 6h boundary picks them up automatically.
- **You changed the code** (a metric, a template, a leak rule) → push to main → deploy within ~1 minute.

Real-world scenarios where a manual refresh would matter:

1. **"I just finished a session and want to see the leaks now, not at the next 6h tick."** Genuine. Worst-case wait is ~6h, mean is ~3h. For someone using leaks to drive the *next* session, that's the gap between "playing now and learning now" vs "playing now and learning at breakfast." Real, but already solvable by `workflow_dispatch` from the Actions UI in two clicks.
2. **"I edited `data/annotations.json` and want the dashboard to reflect it."** This one is broken-by-design under the Pages model: `data/` is gitignored, so annotations only exist on the user's machine. The deployed site renders against whatever annotations were committed to the runner — which is *none*. Either annotations need to start being committed (changes the privacy story), or annotation editing stays a local-only workflow. A web button doesn't fix this.
3. **"I want to verify a code change before pushing."** Run `uv run refresh.py` locally and open `dashboard/index.html` over `python3 -m http.server`. The original CLI workflow. A web button on the published site can't help here.
4. **"I'm showing someone the dashboard and want fresh numbers."** The visible "Updated" KPI tile already tells them how stale the data is. If it's <6h, refreshing changes nothing. If it's >6h, something's wrong with the workflow and a button won't fix it.

Net read: scenario (1) is the only one where the *published-site* button delivers real value, and it's served adequately today by clicking "Run workflow" in the Actions UI. The original local-server design solves scenarios that no longer occur in the user's primary workflow.

## 3. Design options

Ranked from least to most work.

### Option A — Don't build it. Update the README.

- **One-liner:** Document `workflow_dispatch` as the manual-refresh path. Delete the local-serve spec.
- **How it works:** Add ~5 lines to `README.md` pointing at <https://github.com/madisonveldingvandam/chess-tracker/actions/workflows/deploy.yml> with instructions to click "Run workflow." Archive [2026-05-27-refresh-button-design.md](../specs/2026-05-27-refresh-button-design.md) as superseded.
- **Pros:** Zero code. Zero new surface area. Zero new failure modes. Honest about the actual frequency of need (rare). The Actions UI already shows run history, logs, and failure states for free.
- **Cons:** Two extra clicks vs. one. No in-dashboard affordance. User has to leave the page.
- **When right:** If the answer to "how often do you actually want to refresh between 6h ticks?" is "less than once a week."
- **Effort:** ~5 LOC in `README.md`. 1 file touched. Plus moving the old spec to `docs/superpowers/specs/archived/` or adding a "Superseded by …" header.

### Option B — Static "Refresh" link in the KPI strip pointing at the Actions UI.

- **One-liner:** Anchor tag styled like a button, `href` points at the workflow page.
- **How it works:** In each of the 5 templates with a `#kpi-strip`, add `<a class="refresh-link" href="https://github.com/madisonveldingvandam/chess-tracker/actions/workflows/deploy.yml" target="_blank" rel="noopener">↻ Refresh</a>`. Add ~8 lines of CSS mirroring the `#refresh-btn` styling from the original spec (margin-left: auto, muted border, hover state). No JS.
- **Pros:** Stupid simple. Discoverable from any page. No new Python, no new endpoint, no new tests. Works identically on the published site and locally. Honest about the underlying mechanic (you're triggering a workflow, not refreshing a server).
- **Cons:** Still two clicks (link → "Run workflow" button on GitHub). User has to be signed into GitHub. Doesn't auto-reload the dashboard when the workflow finishes — user has to come back ~60s later and hard-refresh.
- **When right:** If discoverability is the actual blocker and the user wouldn't think to bookmark the Actions URL.
- **Effort:** ~5 templates × 1 line + ~8 CSS lines = ~15 LOC. 6 files touched. No tests needed.

### Option C — Button → `repository_dispatch` via GitHub REST API.

- **One-liner:** In-page button POSTs to the GitHub API to fire the deploy workflow, polls until the artifact updates, then reloads.
- **How it works:** `fetch("https://api.github.com/repos/madisonveldingvandam/chess-tracker/actions/workflows/deploy.yml/dispatches", {method:"POST", headers:{Authorization: "Bearer "+token, ...}, body: JSON.stringify({ref:"main"})})`. The token is a fine-grained PAT with `actions: write` on this single repo, stored in `localStorage` after a one-time prompt. Poll `actions/runs?event=workflow_dispatch&per_page=1` every 5s until `status==="completed"`, then reload.
- **Pros:** One click from the dashboard. Works from the published site. Real status feedback (queued → in_progress → completed). Same trigger path the cron uses, so no new pipeline.
- **Cons:** Token in `localStorage` is the kind of thing that ages badly — PATs expire (max 1y), get revoked, leak in screen recordings. Even a fine-grained PAT scoped to this one repo with `actions:write` lets anyone with the token nuke the Actions history. A token-prompt modal is non-trivial UI. The "1-minute deploy wait" makes the button feel broken even when it works. Adds ~80 LOC of JS for what amounts to a fancier link.
- **When right:** Never, for this project. The threat model isn't right and the UX gain is marginal.
- **Effort:** ~80 LOC in `dashboard/app.js`, ~15 LOC styling, plus a small "paste your PAT" modal. ~100 LOC total. 2-3 files touched. No Python changes.

### Option D — Original spec: `refresh.py --serve` localhost mode + in-dashboard button.

- **One-liner:** Run `refresh.py --serve` locally; the button POSTs to `127.0.0.1:8000/refresh`.
- **How it works:** As described in [2026-05-27-refresh-button-design.md](../specs/2026-05-27-refresh-button-design.md) — refactor `main()` body into `_run_refresh(args)`, add `--serve` + `--port`, subclass `SimpleHTTPRequestHandler` for `POST /refresh`. Button in the KPI strip POSTs, reloads on success.
- **Pros:** Self-contained — no GitHub round-trip, no token, no API rate limits, no network dependency. Works offline. The pipeline is fast against cached archives.
- **Cons:** Solves the wrong problem. User primarily reads the published site; the button only works from the local-server entry point. Adds ~50 LOC of Python + a new server process + 4 tests for a workflow that's no longer primary. The button's error message ("No refresh server — run `uv run refresh.py --serve`") will fire for the user's actual reading session every time.
- **When right:** Only if the user reverts to a local-first workflow (stops relying on the Pages site). Or if local annotation editing becomes the dominant loop and they want to see annotation edits reflected without a manual re-render.
- **Effort:** ~150 LOC total per the original spec. 9 files touched (refresh.py, 5 templates, app.js, styles.css, tests). 4 new tests.

### Option E — Hybrid: published-site link to Actions + optional `refresh.py --serve` for local annotation editors.

- **One-liner:** Ship Option B today; add Option D later only if local annotation editing becomes a real workflow.
- **How it works:** Just Option B for now. Defer D behind a "do I actually need this?" gate.
- **Pros:** Ships value immediately at near-zero cost. Keeps Option D on the table without paying for it. Matches the project's "subtractive over additive" instinct.
- **Cons:** None vs. doing each piece individually. Worth listing as the deliberate sequencing choice.
- **When right:** Default unless the user has a strong reason for Option A (don't even add the link) or D (full local-serve mode).
- **Effort:** ~15 LOC today, plus a flagged "may add later" note in the README. Same files as Option B.

## 4. Recommendation

**Ship Option B (static link to the Actions UI from the KPI strip), with a one-line README note. Archive the original spec as superseded.**

Three reasons:

1. **The button's job changed.** In a localhost-only world, a button saved a context switch (terminal → browser → terminal → browser). In a Pages world, the user is already in the browser — the only thing the button can save is a tab switch to GitHub. A link does that.
2. **Cron covers the common case.** 6-hour ticks plus push-on-edit covers ~95% of the "I want fresh data" moments. Manual refresh is a thin remainder. Spending 150 LOC + a new server mode on a thin remainder violates the project's stated minimalism (cf. `feedback_airwindows_minimalism` — every change should be subtractive or near-zero cost).
3. **Option D is reversible later.** If local annotation editing becomes the primary loop, the original spec is still there. Building it now is speculative; deferring it costs nothing.

Explicitly NOT recommended: Option C. The PAT-in-localStorage threat model is wrong for a single-user, otherwise-tokenless project, and the UX gain (one click vs. two) doesn't earn the complexity.

Implementation sketch (Option B):

- `chess_tracker/templates/{index,leaks,losses,process,sessions,opening}.html` — add one `<a>` line inside `#kpi-strip` after the home-link (where present).
- `dashboard/styles.css` — add `#refresh-link` rules mirroring the `#refresh-btn` block from the old spec (transparent bg, `var(--muted)` color, `margin-left: auto`).
- `README.md` — mention `workflow_dispatch` as the manual-refresh path.
- No `refresh.py` change. No `app.js` change. No new tests (it's an `<a>` tag).

## 5. Open questions

Answers to any of these would shift the recommendation:

1. **How often do you actually want fresh data between the 6h cron ticks?** If the honest answer is "less than weekly," collapse to Option A (no UI, README only). If "after every session," Option B is correct. If "every time I edit `annotations.json` locally," Option D becomes necessary because no remote workflow can see your local annotations.
2. **Should `data/annotations.json` start being committed?** Today it's gitignored, which means the deployed dashboard renders with zero annotations — the error-log and tag panels on the published site are empty. If annotations should appear in the deployed dashboard, that's its own decision (privacy story changes), and it would make the published site the primary annotation surface — strengthening the case for Option B and weakening Option D. If annotations stay private/local, Option D regains weight as the only way to see them in a dashboard.
3. **Are you OK with the GitHub Actions UI as the "manual refresh" surface, or does leaving the dashboard tab feel like friction worth eliminating?** If the Actions UI is acceptable, Option A or B. If not, the only way to keep the user inside the dashboard is Option C (with its token-in-browser tax) or Option D (with its local-only constraint).
