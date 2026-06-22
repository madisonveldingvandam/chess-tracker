# Lichess Stats Band + Quick Links — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch the user's Lichess ratings and puzzle score via the public Lichess API and display them as a new stats band below the existing Chess.com band on the dashboard, with quick-links to both Chess.com and Lichess profiles in every page header.

**Architecture:** Add `fetch_lichess_user()` to `chess_tracker/api.py`, call it in `refresh.py` after the Chess.com fetch, store the result under `computed["lichess"]` in `data/computed.json`, render the band from the template + `app.js`. Band hides gracefully when `lichess` is null (network failure at refresh time). Quick links are static anchor tags added to all template headers.

**Tech Stack:** Lichess public API (no auth), Python `urllib` (already in project), same render pipeline as Chess.com stats.

---

### Task 1: Add `fetch_lichess_user()` to `api.py`

**Files:**
- Modify: `chess_tracker/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/test_api.py` and add at the end:

```python
import json
from unittest.mock import patch, MagicMock


def _mock_urlopen(response_data: dict):
    """Return a context-manager mock that yields a response with JSON body."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_fetch_lichess_user_returns_perfs():
    from chess_tracker.api import fetch_lichess_user
    payload = {
        "perfs": {
            "bullet": {"rating": 1234, "games": 50},
            "blitz":  {"rating": 1345, "games": 200},
            "rapid":  {"rating": 1456, "games": 30},
            "classical": {"rating": 1567, "games": 5},
            "puzzle": {"score": 1678, "runs": 400},
        },
        "count": {"all": 285},
    }
    with patch("chess_tracker.api.urlopen", return_value=_mock_urlopen(payload)):
        result = fetch_lichess_user("M_V-v")
    assert result["perfs"]["bullet"]["rating"] == 1234
    assert result["perfs"]["puzzle"]["score"] == 1678
    assert result["count"]["all"] == 285


def test_fetch_lichess_user_returns_empty_dict_on_error():
    from chess_tracker.api import fetch_lichess_user
    with patch("chess_tracker.api.urlopen", side_effect=Exception("network error")):
        result = fetch_lichess_user("M_V-v")
    assert result == {}
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/madisonvelding-vandam/Developer/chess-tracker
uv run pytest tests/test_api.py::test_fetch_lichess_user_returns_perfs tests/test_api.py::test_fetch_lichess_user_returns_empty_dict_on_error -v
```

Expected: `ImportError: cannot import name 'fetch_lichess_user'`.

- [ ] **Step 3: Implement `fetch_lichess_user()` in `api.py`**

Add to `chess_tracker/api.py` after the existing `fetch_player_stats` function:

```python
LICHESS_BASE = "https://lichess.org/api"


def fetch_lichess_user(username: str) -> dict:
    """Fetch public profile + perfs for a Lichess user. Returns {} on any error."""
    url = f"{LICHESS_BASE}/user/{username.lower()}"
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/test_api.py -v
```

Expected: all pass including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/api.py tests/test_api.py
git commit -m "feat(api): add fetch_lichess_user() for Lichess public profile"
```

---

### Task 2: Wire Lichess fetch into `refresh.py` and extend the smoke test

**Files:**
- Modify: `refresh.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Extend the smoke test to assert the `lichess` key exists**

In `tests/test_smoke.py`, find `test_render_dashboard_required_keys_present_in_embedded_data` (around line 89). Add `"lichess"` to the keys list:

```python
    for key in ("kpis", "leak_summary", "recent_losses",
                "process_metrics", "opening_families", "sessions",
                "opponent_openings", "trap_exposures", "blunder_phases",
                "ratings_by_format", "lichess"):   # <-- add "lichess"
        assert key in data, f"Missing required key: {key}"
```

Also add `"lichess": None` to `_MINIMAL_PAYLOAD` in the same file:

```python
_MINIMAL_PAYLOAD = {
    # ... existing keys ...
    "engine_coverage": None,
    "lichess": None,          # <-- add this
}
```

- [ ] **Step 2: Run the smoke test to confirm it fails**

```bash
uv run pytest tests/test_smoke.py::test_render_dashboard_required_keys_present_in_embedded_data -v
```

Expected: `AssertionError: Missing required key: lichess`.

- [ ] **Step 3: Add the Lichess fetch to `refresh.py`**

In `refresh.py`, add the import at the top with the other api imports:

```python
from chess_tracker.api import fetch_archives_index, fetch_archive, fetch_player_stats, fetch_lichess_user
```

Then find the section where `computed` dict is built (look for where `computed["kpis"]` or similar keys are set). After the Chess.com stats fetch, add:

```python
    # Lichess stats (public API, no auth — null on network failure)
    print("[X/5] Fetching Lichess profile...")
    raw_lichess = fetch_lichess_user("M_V-v")
    if raw_lichess:
        perfs = raw_lichess.get("perfs", {})
        computed["lichess"] = {
            "bullet":       perfs.get("bullet",    {}).get("rating"),
            "blitz":        perfs.get("blitz",     {}).get("rating"),
            "rapid":        perfs.get("rapid",     {}).get("rating"),
            "classical":    perfs.get("classical", {}).get("rating"),
            "puzzle_score": perfs.get("puzzle",    {}).get("score"),
            "game_count":   raw_lichess.get("count", {}).get("all"),
        }
    else:
        computed["lichess"] = None
```

Adjust the print step number to fit the existing step sequence.

- [ ] **Step 4: Run the smoke test to confirm it passes**

```bash
uv run pytest tests/test_smoke.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add refresh.py tests/test_smoke.py
git commit -m "feat(refresh): add Lichess stats fetch to computed.json"
```

---

### Task 3: Add Lichess stats band to the dashboard

**Files:**
- Modify: `chess_tracker/templates/index.html`
- Modify: `dashboard/app.js`
- Modify: `dashboard/styles.css`

The band sits directly below the Chess.com KPI strip (`#kpi-strip`) and uses the same visual rhythm.

- [ ] **Step 1: Add the Lichess band container to `chess_tracker/templates/index.html`**

Find the `<header id="kpi-strip">` line and add a second header div immediately after it:

```html
  <header id="kpi-strip"></header>
  <div id="lichess-strip" style="display:none"></div>   <!-- hidden until data loads -->
```

- [ ] **Step 2: Add `renderLichessKPI()` to `app.js`**

In `app.js`, add this function after `renderKPI()` (around line 76), and call it from the main init block:

In the main block near the top, add the call:
```javascript
  renderLichessKPI(D);
```

And the function:

```javascript
  function renderLichessKPI(d) {
    const strip = document.getElementById("lichess-strip");
    if (!strip || !d.lichess) return;
    const L = d.lichess;
    const FMT_ORDER  = ["bullet", "blitz", "rapid", "classical"];
    const FMT_LABELS = { bullet: "Bullet", blitz: "Blitz", rapid: "Rapid", classical: "Classical" };
    const ratingHtml = FMT_ORDER
      .filter(f => L[f] != null)
      .map(f =>
        `<div class="kpi">` +
        `<span class="kpi-label">${FMT_LABELS[f]}</span>` +
        `<span class="kpi-value">${L[f]}</span></div>`
      ).join("");
    const puzzleHtml = L.puzzle_score != null
      ? `<div class="kpi"><span class="kpi-label">Puzzles</span>` +
        `<span class="kpi-value">${L.puzzle_score}</span></div>`
      : "";
    const gamesHtml = L.game_count != null
      ? `<div class="kpi"><span class="kpi-label">Games</span>` +
        `<span class="kpi-value">${L.game_count}</span></div>`
      : "";
    strip.insertAdjacentHTML("beforeend",
      `<span class="lichess-label">Lichess</span>` +
      ratingHtml + puzzleHtml + gamesHtml
    );
    strip.style.display = "";
  }
```

- [ ] **Step 3: Add CSS for the Lichess strip in `dashboard/styles.css`**

Add after the existing `#kpi-strip` styles (search for `kpi-strip` to find the block):

```css
#lichess-strip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 1rem;
  background: rgba(0, 0, 0, 0.15);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  font-size: 0.82rem;
  flex-wrap: wrap;
}
.lichess-label {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.5;
  margin-right: 0.25rem;
}
```

- [ ] **Step 4: Run refresh and verify in browser**

```bash
uv run python refresh.py --no-puzzles 2>&1 | tail -5
```

Open `dashboard/index.html`. Below the Chess.com rating strip you should see a second strip labeled "Lichess" with your Lichess ratings (Bullet, Blitz, Rapid, Classical, Puzzles, Games). If the strip is absent, check the browser console — `D.lichess` might be null if the Lichess API was unreachable at refresh time. Run `python refresh.py` again with a network connection.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/templates/index.html dashboard/app.js dashboard/styles.css
git commit -m "feat(dashboard): add Lichess stats band below Chess.com ratings"
```

---

### Task 4: Add quick links to all page headers

**Files:**
- Modify: `chess_tracker/templates/index.html`
- Modify: `chess_tracker/templates/losses.html`
- Modify: `chess_tracker/templates/opening.html`
- Modify: `chess_tracker/templates/leaks.html`
- Modify: `chess_tracker/templates/process.html`
- Modify: `chess_tracker/templates/sessions.html`

- [ ] **Step 1: Add CSS for the header links in `dashboard/styles.css`**

```css
.platform-links {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-left: auto;
}
.platform-link {
  font-size: 0.78rem;
  font-weight: 600;
  opacity: 0.6;
  text-decoration: none;
  color: inherit;
  letter-spacing: 0.03em;
  transition: opacity 0.15s;
}
.platform-link:hover { opacity: 1; }
```

- [ ] **Step 2: Add the links to every template's `<header>` tag**

Every template currently has `<header id="kpi-strip">` or `<header id="kpi-strip"><a class="home-link" href="index.html">← repertoire</a></header>`.

On `index.html` (which has no home link, just `<header id="kpi-strip"></header>`):

```html
<header id="kpi-strip">
  <div class="platform-links">
    <a class="platform-link" href="https://www.chess.com/member/M_V-V" target="_blank" rel="noopener">Chess.com</a>
    <a class="platform-link" href="https://lichess.org/@/M_V-v" target="_blank" rel="noopener">Lichess</a>
  </div>
</header>
```

On all other templates (which already have the `← repertoire` link):

```html
<header id="kpi-strip">
  <a class="home-link" href="index.html">← repertoire</a>
  <div class="platform-links">
    <a class="platform-link" href="https://www.chess.com/member/M_V-V" target="_blank" rel="noopener">Chess.com</a>
    <a class="platform-link" href="https://lichess.org/@/M_V-v" target="_blank" rel="noopener">Lichess</a>
  </div>
</header>
```

Apply this to all 6 templates.

- [ ] **Step 3: Run refresh and verify**

```bash
uv run python refresh.py --no-puzzles 2>&1 | tail -5
```

Open each generated dashboard page. Each header should show "Chess.com" and "Lichess" links on the right side. Clicking each should open the respective profile in a new tab.

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all green.

- [ ] **Step 5: Commit and push**

```bash
git add chess_tracker/templates/ dashboard/styles.css
git commit -m "feat(dashboard): add Chess.com + Lichess profile links to all page headers"
git push
```
