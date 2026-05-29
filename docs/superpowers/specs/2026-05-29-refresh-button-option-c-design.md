# Refresh button — Option C (in-page workflow dispatch)

**Date:** 2026-05-29
**Status:** Approved design — supersedes the Option B link shipped in `a9e03a8`.
**Context:** [../research/2026-05-29-refresh-button-options.md](../research/2026-05-29-refresh-button-options.md) laid out Options A–E and recommended B (a static link to the Actions UI). B shipped, but the user wants a "real" in-page button that refreshes without leaving the dashboard. This spec is Option C from that doc, chosen deliberately with eyes open about the token tradeoff.

## Goal

Turn the KPI-strip `↻ Refresh` control from a link-to-GitHub into an **in-page button** that triggers the `deploy.yml` workflow via the GitHub REST API, shows live build status, and reloads the dashboard when the rebuild finishes — all without leaving the page.

## Non-goals

- No faster data. The rebuild still runs on GitHub Actions (~60s). This changes *where* you wait (in-page) not *how long*.
- No server, no Python changes, no new workflow. `deploy.yml` already exposes `workflow_dispatch:`.
- No JS test runner. `app.js` is currently untested; this spec does not introduce a framework (see Testing).

## Decisions (locked during brainstorming)

1. **No-token behavior — Pure C.** The button always attempts a dispatch. If no token is stored, it prompts for one inline; a visitor without a token simply can't satisfy the prompt. We do *not* fall back to the old link, and we do *not* hide the button.
2. **Token storage — `localStorage`.** Paste once; persists across sessions. Accepted tradeoff: the key is readable by JS on any `madisonveldingvandam.github.io` project (shared origin), and persists on disk.
3. **Progress/completion — live status, then auto-reload.** Button disables and shows `Triggering… → Building m:ss → ` then `location.reload()` on success.

## Security model

The whole risk is bounded by **token scope**, so the design forces the safe choice through UX rather than relying on the user to know better.

- The token prompt text instructs, verbatim: create a **fine-grained** token, **repository access: `chess-tracker` only**, **permissions: Actions → Read and write**, short expiry — and links to <https://github.com/settings/personal-access-tokens/new>.
- A correctly-scoped token's worst-case-if-leaked is: spam/cancel/re-run this one public repo's workflow, and delete its logs/artifacts/caches. Recoverable by revoking the token. It cannot read private repos, push code, change the workflow, or touch the account.
- The danger case is a **classic PAT** (account-wide `repo`/`workflow` scopes). The prompt explicitly steers away from classic tokens.
- The token is **never inlined into HTML** — it is only ever sent as a `fetch` `Authorization` header. This preserves the existing XSS trust boundary documented at the top of `app.js`.
- A **clear-token** affordance (see UI) lets the user wipe the key without opening devtools.

## Architecture

All client-side. Two files touched: `dashboard/app.js`, `dashboard/styles.css`.

### Constants
```
const REPO = "madisonveldingvandam/chess-tracker";
const WORKFLOW = "deploy.yml";
const TOKEN_KEY = "ct_gh_token";
const POLL_MS = 5000;
const POLL_TIMEOUT_MS = 180000;   // 3 min, then stop polling
const GH_API = "https://api.github.com";
```

### The element
`renderKPI()` currently appends an `<a class="refresh-link">`. Replace with a `<button class="refresh-btn" id="refresh-btn">↻ Refresh</button>` at the same position (last flex child of `#kpi-strip`, so `margin-left:auto` still right-aligns it). A small `<button class="refresh-clear" title="Forget saved token">✕</button>` renders immediately after it, only when a token is present.

### Pure, unit-testable seams (extracted as module-level functions)
- `formatElapsed(ms) -> "m:ss"` — display helper.
- `pickRun(runs, sinceIso) -> run | null` — given the `workflow_runs` array and the dispatch timestamp, return the newest run with `created_at >= sinceIso` and `event === "workflow_dispatch"`. This is the one piece of real logic worth testing in isolation.

### Click handler (`onRefreshClick`)
1. `token = localStorage.getItem(TOKEN_KEY)`. If falsy → `promptForToken()` (see below); if still falsy after prompt, abort (re-enable button).
2. Disable button, label `Triggering…`.
3. `POST {GH_API}/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches` with headers `Authorization: Bearer {token}`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, body `{"ref":"main"}`.
4. Record `dispatchedAt = <response Date header or client time>`. (Client time is fine; `pickRun` tolerates a few seconds of skew by matching the newest dispatch-event run.)
5. On `204` → `startPolling(token, dispatchedAt)`.
6. On `401`/`403` → `clearToken()`, `alert("Token rejected — please re-enter.")`, re-enable.
7. On other failure → `alert("Couldn't trigger the rebuild — try again.")`, re-enable.

### Polling (`startPolling`)
- Every `POLL_MS`: `GET …/runs?event=workflow_dispatch&per_page=5`, `pickRun(...)`.
- While run is `queued`/`in_progress`: label `Building m:ss` (elapsed since dispatch).
- On `completed` + `conclusion==="success"` → `location.reload()`.
- On `completed` + other conclusion → `alert("Build finished with: <conclusion>")`, re-enable, label back to `↻ Refresh`.
- If `Date.now() - dispatchedAt > POLL_TIMEOUT_MS` → stop, `alert("Still building — reload the page manually in a moment.")`, re-enable. (Never hangs forever.)

### Token prompt (`promptForToken`)
- `window.prompt(<multi-line instruction with fine-grained scope guidance + settings URL>)`.
- Trim; if non-empty, `localStorage.setItem(TOKEN_KEY, value)` and re-render the clear-token ✕.
- No validation beyond non-empty; a bad token surfaces as a `401` on dispatch, which clears it.

### Clear token (`clearToken`)
- `localStorage.removeItem(TOKEN_KEY)`, hide the ✕, label button back to `↻ Refresh`.

## Styling (`dashboard/styles.css`)
- Rename/extend the existing `.refresh-link` rules into `.refresh-btn` (same look: `margin-left:auto`, muted border, `border-radius:4px`, hover brighten). Reset native button styles (`background:transparent; font:inherit; cursor:pointer`).
- `.refresh-btn:disabled { opacity:0.6; cursor:default; }`.
- `.refresh-clear { color:var(--muted); background:transparent; border:0; cursor:pointer; font-size:0.7rem; margin-left:0.3rem; }` with hover brighten.

## Testing

- **Pure functions:** `formatElapsed` and `pickRun` are the only logic with branching worth testing. Because the repo has no JS test runner and adding one is out of scope, these are documented as the testable seams; if/when a runner is introduced they get unit tests. They are written as pure, side-effect-free functions to keep that door open.
- **Manual verification (preview browser)** is the acceptance gate for this change, matching how the rest of `app.js` is verified today:
  1. **No-token path:** clear `localStorage`, click → prompt appears with fine-grained guidance.
  2. **Dispatch path:** paste a real fine-grained token, click → button shows `Triggering…` then `Building m:ss`; a new run appears in the repo's Actions; on completion the page reloads with a newer `Updated` KPI.
  3. **Bad-token path:** store a garbage token, click → `401` → token cleared, alert shown, button re-enabled.
  4. **Clear-token path:** with a token stored, the ✕ shows; clicking it removes the key and hides the ✕.

## Files touched
- `dashboard/app.js` — replace `.refresh-link` markup with the button + clear control; add `onRefreshClick`, `startPolling`, `promptForToken`, `clearToken`, `formatElapsed`, `pickRun`.
- `dashboard/styles.css` — `.refresh-link` → `.refresh-btn` + `.refresh-clear`.
- `README.md` — update the refresh paragraph: the published dashboard's `↻ Refresh` is now a one-click in-page trigger (needs a fine-grained token, scope guidance), with the Actions UI still available as the manual path.

## Rollback
Pure client-side; reverting the two `dashboard/` files restores the Option B link. No data or server state involved.
