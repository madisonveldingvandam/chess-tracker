# Bullet Chess Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local HTML dashboard that ranks the user's Chess.com bullet openings, surfaces process-metric leaks, and persists annotations — refreshed by a single Python script.

**Architecture:** Python pipeline (`refresh.py`) pulls Chess.com archives → parses PGN+clocks → computes metrics as pure functions → merges with `annotations.json` → injects JSON into a static HTML page using Tabulator.js for sortable tables. No server. Per spec at `docs/superpowers/specs/2026-05-26-bullet-chess-tracker-design.md`.

**Tech Stack:** Python 3.14 (stdlib only for runtime), `pytest` (dev only via uv), Tabulator.js (CDN), vanilla CSS + JS, inline SVG sparklines.

---

## Conventions

- **TDD where it makes sense:** all Python modules are pure functions with unit tests written first. Frontend (HTML/JS/CSS) is verified by opening in a browser — no headless DOM testing in v1.
- **Commit after every passing task.** Use Conventional Commits prefixes: `feat:`, `test:`, `fix:`, `chore:`, `docs:`.
- **Run from project root:** `/Users/madisonvelding-vandam/Developer/chess-tracker`.
- **Working dataset for tests:** real games from username `M_V-V`, trimmed to ≤5 games per fixture for speed.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `chess_tracker/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/__init__.py` (empty; makes fixtures importable)

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "chess-tracker"
version = "0.1.0"
description = "Local Chess.com bullet repertoire dashboard"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Write `.gitignore`**

```
# Python
__pycache__/
*.pyc
.pytest_cache/
.venv/

# Project data (regenerable / private)
data/
dashboard/index.html

# OS
.DS_Store
```

- [ ] **Step 3: Write `README.md`**

```markdown
# Chess Tracker

Local Chess.com bullet repertoire dashboard for user `M_V-V`.

## Setup

    uv sync --group dev

## Refresh

    uv run refresh.py

Opens dashboard at `dashboard/index.html`.

## Test

    uv run pytest
```

- [ ] **Step 4: Create empty package + tests stubs**

```bash
mkdir -p tests/fixtures
touch chess_tracker/__init__.py tests/__init__.py tests/fixtures/__init__.py
```

- [ ] **Step 5: Verify `uv` can resolve the project**

Run: `uv sync --group dev`
Expected: `Resolved N packages`, `.venv/` created, pytest installed.

- [ ] **Step 6: Verify pytest discovers no tests yet (sanity check)**

Run: `uv run pytest`
Expected: `no tests ran` exit 5, NOT an import error.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore README.md chess_tracker/ tests/
git commit -m "chore: scaffold python package and test harness"
```

---

## Task 2: API client — archives index

**Files:**
- Create: `chess_tracker/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_api.py
from unittest.mock import patch, MagicMock
import json
from chess_tracker.api import fetch_archives_index


def test_fetch_archives_index_returns_list_of_urls():
    fake_response = json.dumps({
        "archives": [
            "https://api.chess.com/pub/player/m_v-v/games/2026/04",
            "https://api.chess.com/pub/player/m_v-v/games/2026/05",
        ]
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response
    mock_resp.__enter__.return_value = mock_resp

    with patch("chess_tracker.api.urlopen", return_value=mock_resp):
        urls = fetch_archives_index("m_v-v")

    assert len(urls) == 2
    assert urls[0].endswith("/2026/04")
    assert urls[1].endswith("/2026/05")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: chess_tracker.api`.

- [ ] **Step 3: Implement minimally**

```python
# chess_tracker/api.py
"""Chess.com Published Data API client with simple disk cache."""
from urllib.request import Request, urlopen
import json

USER_AGENT = "ChessTracker/0.1 (madisonveldingvandam.artist@gmail.com)"
BASE = "https://api.chess.com/pub/player"


def _get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_archives_index(username: str) -> list[str]:
    """Return list of monthly archive URLs for the user, oldest first."""
    data = _get_json(f"{BASE}/{username.lower()}/games/archives")
    return list(data.get("archives", []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/api.py tests/test_api.py
git commit -m "feat(api): fetch archives index for a chess.com user"
```

---

## Task 3: API client — monthly archive fetch with disk cache

**Files:**
- Modify: `chess_tracker/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_api.py`:

```python
import tempfile
from pathlib import Path


def test_fetch_archive_caches_to_disk(tmp_path):
    url = "https://api.chess.com/pub/player/m_v-v/games/2025/01"
    payload = {"games": [{"uuid": "abc", "time_class": "bullet"}]}

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__.return_value = mock_resp

    from chess_tracker.api import fetch_archive

    with patch("chess_tracker.api.urlopen", return_value=mock_resp) as m:
        result1 = fetch_archive(url, cache_dir=tmp_path)
        result2 = fetch_archive(url, cache_dir=tmp_path)  # second call: cached

    assert result1 == payload
    assert result2 == payload
    assert m.call_count == 1  # only fetched once

    cache_file = tmp_path / "2025-01.json"
    assert cache_file.exists()


def test_fetch_archive_force_bypasses_cache(tmp_path):
    url = "https://api.chess.com/pub/player/m_v-v/games/2025/01"
    payload = {"games": []}

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__.return_value = mock_resp

    from chess_tracker.api import fetch_archive

    with patch("chess_tracker.api.urlopen", return_value=mock_resp) as m:
        fetch_archive(url, cache_dir=tmp_path)
        fetch_archive(url, cache_dir=tmp_path, force=True)

    assert m.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_archive'`.

- [ ] **Step 3: Implement**

Append to `chess_tracker/api.py`:

```python
import re
from pathlib import Path


_ARCHIVE_URL_RE = re.compile(r"/games/(\d{4})/(\d{2})$")


def _cache_filename(url: str) -> str:
    m = _ARCHIVE_URL_RE.search(url)
    if not m:
        raise ValueError(f"Not a monthly archive URL: {url}")
    yyyy, mm = m.groups()
    return f"{yyyy}-{mm}.json"


def fetch_archive(url: str, cache_dir: Path, force: bool = False) -> dict:
    """Fetch a monthly archive, caching to {cache_dir}/{YYYY-MM}.json."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / _cache_filename(url)

    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text())

    data = _get_json(url)
    cache_path.write_text(json.dumps(data))
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/api.py tests/test_api.py
git commit -m "feat(api): fetch and cache monthly archive with force flag"
```

---

## Task 4: PGN parser — GameRecord dataclass + parse_game

**Files:**
- Create: `chess_tracker/pgn.py`
- Create: `tests/test_pgn.py`
- Create: `tests/fixtures/sample_game.json`

- [ ] **Step 1: Save fixture**

Create `tests/fixtures/sample_game.json` containing one real bullet game from the existing data dump. Run this once to produce it:

```bash
python3 -c "
import json
with open('/tmp/chess/2026-05.json') as f:
    games = json.load(f)['games']
bullet = [g for g in games if g.get('time_class') == 'bullet']
with open('tests/fixtures/sample_game.json', 'w') as f:
    json.dump(bullet[0], f, indent=2)
"
```

If `/tmp/chess/2026-05.json` is not available (fresh machine), substitute by running a one-off `curl` against the API to pull May 2026 archive first.

- [ ] **Step 2: Write failing tests**

```python
# tests/test_pgn.py
import json
from pathlib import Path
from chess_tracker.pgn import parse_game, opening_family

FIXTURE = json.loads((Path(__file__).parent / "fixtures/sample_game.json").read_text())


def test_parse_game_returns_record_with_required_fields():
    rec = parse_game(FIXTURE, username="m_v-v")
    assert rec.side in ("white", "black")
    assert rec.result in ("win", "timeout", "checkmated", "resigned",
                          "agreed", "repetition", "stalemate", "insufficient",
                          "50move", "timevsinsufficient", "abandoned")
    assert rec.opp_result in ("win", "timeout", "checkmated", "resigned",
                              "agreed", "repetition", "stalemate", "insufficient",
                              "50move", "timevsinsufficient", "abandoned")
    assert rec.my_rating > 0
    assert rec.opp_rating > 0
    assert rec.plies > 0
    assert rec.fullmoves > 0
    assert rec.end_time > 0
    assert rec.time_class == "bullet"
    assert isinstance(rec.my_clocks, list)
    assert isinstance(rec.opp_clocks, list)
    # Final clocks should be non-negative
    if rec.my_clocks:
        assert rec.my_clocks[-1] >= 0


def test_opening_family_strips_move_suffix():
    assert opening_family("Queens-Pawn-Opening-Zukertort-Variation-3.Bf4") == \
        "Queens Pawn Opening Zukertort Variation"
    assert opening_family("Italian-Game-Knight-Attack") == "Italian Game Knight Attack"
    assert opening_family("Caro-Kann-Defense-2...d5") == "Caro Kann Defense"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_pgn.py -v`
Expected: FAIL — `ModuleNotFoundError: chess_tracker.pgn`.

- [ ] **Step 4: Implement**

```python
# chess_tracker/pgn.py
"""Parse a Chess.com game dict into a GameRecord."""
from dataclasses import dataclass, field
import re

_CLOCK_RE = re.compile(r"\[%clk (\d):(\d{2}):(\d{2}(?:\.\d+)?)\]")
_ECO_URL_RE = re.compile(r'\[ECOUrl "https://www\.chess\.com/openings/([^"]+)"\]')
_ECO_RE = re.compile(r'\[ECO "([^"]+)"\]')


@dataclass
class GameRecord:
    url: str
    end_time: int
    time_class: str
    side: str                # "white" | "black"
    my_rating: int
    opp_rating: int
    result: str              # me['result']
    opp_result: str
    plies: int
    fullmoves: int
    opening: str | None      # opening family (no move-number suffix)
    eco: str | None          # ECO code, e.g. "C42"
    my_clocks: list[float] = field(default_factory=list)
    opp_clocks: list[float] = field(default_factory=list)


def _parse_clocks(pgn: str) -> list[float]:
    """Return clocks in move order: [W after move 1, B after move 1, ...]."""
    out = []
    for h, m, s in _CLOCK_RE.findall(pgn):
        out.append(int(h) * 3600 + int(m) * 60 + float(s))
    return out


def opening_family(slug: str) -> str:
    """Strip trailing move-number tokens from an ECOUrl slug."""
    name = slug.replace("-", " ")
    parts = []
    for tok in name.split():
        if re.match(r"^\d", tok):  # token starts with a digit → move number
            break
        parts.append(tok)
    return " ".join(parts) if parts else name


def parse_game(g: dict, username: str) -> GameRecord:
    me_white = g["white"]["username"].lower() == username.lower()
    me = g["white"] if me_white else g["black"]
    opp = g["black"] if me_white else g["white"]
    side = "white" if me_white else "black"

    pgn = g.get("pgn", "")
    all_clocks = _parse_clocks(pgn)
    w_clocks = all_clocks[0::2]
    b_clocks = all_clocks[1::2]

    plies = len(all_clocks)
    fullmoves = (plies + 1) // 2

    eco_url_m = _ECO_URL_RE.search(pgn)
    opening = opening_family(eco_url_m.group(1)) if eco_url_m else None
    eco_m = _ECO_RE.search(pgn)
    eco = eco_m.group(1) if eco_m else None

    return GameRecord(
        url=g.get("url", ""),
        end_time=g["end_time"],
        time_class=g.get("time_class", ""),
        side=side,
        my_rating=me["rating"],
        opp_rating=opp["rating"],
        result=me["result"],
        opp_result=opp["result"],
        plies=plies,
        fullmoves=fullmoves,
        opening=opening,
        eco=eco,
        my_clocks=w_clocks if me_white else b_clocks,
        opp_clocks=b_clocks if me_white else w_clocks,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_pgn.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/pgn.py tests/test_pgn.py tests/fixtures/sample_game.json
git commit -m "feat(pgn): parse Chess.com game dict into GameRecord"
```

---

## Task 5: Annotations I/O

**Files:**
- Create: `chess_tracker/annotations.py`
- Create: `tests/test_annotations.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_annotations.py
import json
from chess_tracker.annotations import load_annotations, save_annotations, default_annotations


def test_default_annotations_has_three_sections():
    d = default_annotations()
    assert set(d.keys()) == {"openings", "games", "error_log"}
    assert d["openings"] == {}
    assert d["games"] == {}
    assert d["error_log"] == []


def test_load_creates_default_when_missing(tmp_path):
    path = tmp_path / "annotations.json"
    data = load_annotations(path)
    assert data == default_annotations()


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "annotations.json"
    payload = {
        "openings": {"Petrovs Defense": {"tag": "in_repertoire", "note": "main"}},
        "games": {},
        "error_log": [{"id": "err-001", "title": "queen blunders"}],
    }
    save_annotations(path, payload)
    assert load_annotations(path) == payload


def test_load_validates_structure(tmp_path):
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps({"openings": {}}))  # missing keys
    data = load_annotations(path)
    # Missing sections must be backfilled with defaults
    assert "games" in data
    assert "error_log" in data
    assert data["error_log"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_annotations.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# chess_tracker/annotations.py
"""Read/write the user-owned annotations.json sidecar."""
import json
from pathlib import Path


def default_annotations() -> dict:
    return {"openings": {}, "games": {}, "error_log": []}


def load_annotations(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return default_annotations()
    data = json.loads(path.read_text())
    # Backfill missing sections
    for k, v in default_annotations().items():
        data.setdefault(k, v)
    return data


def save_annotations(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_annotations.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/annotations.py tests/test_annotations.py
git commit -m "feat(annotations): load/save annotations.json with default backfill"
```

---

## Task 6: Metrics — KPI strip and sessions

**Files:**
- Create: `chess_tracker/metrics.py`
- Create: `tests/test_metrics.py`
- Create: `tests/fixtures/sample_records.py`

- [ ] **Step 1: Write a small set of fixture records**

```python
# tests/fixtures/sample_records.py
"""Hand-crafted GameRecord instances for metric tests."""
from chess_tracker.pgn import GameRecord

# Helper to keep fixtures terse
def _r(end_time, result, opp_result, opening, my_rating=500, opp_rating=500,
       side="white", fullmoves=30, my_clocks=None, opp_clocks=None, eco="A00"):
    return GameRecord(
        url=f"https://chess.com/game/{end_time}",
        end_time=end_time, time_class="bullet",
        side=side, my_rating=my_rating, opp_rating=opp_rating,
        result=result, opp_result=opp_result,
        plies=fullmoves * 2, fullmoves=fullmoves,
        opening=opening, eco=eco,
        my_clocks=my_clocks or [60.0, 30.0, 10.0],
        opp_clocks=opp_clocks or [60.0, 30.0, 5.0],
    )


# Three sessions: clear boundaries (>10min gap)
RECORDS = [
    # Session 1: 3 games, 2W 1L, ratings 500→510
    _r(1_700_000_000, "win", "timeout", "London System", my_rating=500),
    _r(1_700_000_060, "checkmated", "win", "London System", my_rating=505),
    _r(1_700_000_120, "win", "timeout", "Petrovs Defense", my_rating=510, side="black"),
    # Gap of 30 min
    # Session 2: 2 games, 0W 2L, ratings 510→480
    _r(1_700_002_000, "timeout", "win", "Italian Game", my_rating=505, side="black"),
    _r(1_700_002_060, "checkmated", "win", "Italian Game", my_rating=490, side="black"),
    # Gap of 1 hour
    # Session 3: 1 game, 1W
    _r(1_700_006_000, "win", "timeout", "London System", my_rating=485),
]
```

- [ ] **Step 2: Write failing tests for KPIs and sessions**

```python
# tests/test_metrics.py
from tests.fixtures.sample_records import RECORDS
from chess_tracker.metrics import compute_kpis, compute_sessions


def test_compute_kpis_current_rating_is_last_games():
    kpis = compute_kpis(RECORDS)
    assert kpis["current_rating"] == 485  # rating of last game

def test_compute_kpis_recent_form_counts_last_five():
    kpis = compute_kpis(RECORDS)
    # last 5: W=2 (games 0, 5 ... actually last 5 are records[1:6])
    # records[1]=L, [2]=W, [3]=L, [4]=L, [5]=W → 2W/3L → 40%
    assert kpis["recent_form_win_pct"] == 40.0
    assert kpis["tilt"] == "yellow"  # 40 ≤ win% < 60

def test_compute_sessions_detects_gaps():
    sessions = compute_sessions(RECORDS, gap_seconds=600)
    assert len(sessions) == 3
    assert sessions[0]["games"] == 3
    assert sessions[1]["games"] == 2
    assert sessions[2]["games"] == 1

def test_compute_sessions_tracks_rating_delta():
    sessions = compute_sessions(RECORDS, gap_seconds=600)
    # Session 1: started 500, ended 510
    assert sessions[0]["rating_start"] == 500
    assert sessions[0]["rating_end"] == 510
    assert sessions[0]["rating_delta"] == 10

def test_compute_sessions_flags_tilt_when_drop_50_or_more():
    sessions = compute_sessions(RECORDS, gap_seconds=600)
    # No session here has -50, but the flag must exist
    for s in sessions:
        assert "tilt_flag" in s
        assert s["tilt_flag"] == (s["rating_delta"] <= -50)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

```python
# chess_tracker/metrics.py
"""Pure-function metric computations over a list of GameRecord."""
from collections import Counter
from datetime import datetime
import statistics
from chess_tracker.pgn import GameRecord


_DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient",
                 "50move", "timevsinsufficient"}


def _is_win(r: str) -> bool:
    return r == "win"


def _is_draw(r: str) -> bool:
    return r in _DRAW_RESULTS


def _is_loss(r: str) -> bool:
    return not _is_win(r) and not _is_draw(r)


def _tilt_color(win_pct: float) -> str:
    if win_pct >= 60:
        return "green"
    if win_pct >= 40:
        return "yellow"
    return "red"


def compute_kpis(records: list[GameRecord]) -> dict:
    if not records:
        return {"current_rating": None, "games_total": 0,
                "recent_form_win_pct": 0.0, "tilt": "yellow"}
    last = max(records, key=lambda r: r.end_time)
    last_5 = sorted(records, key=lambda r: r.end_time)[-5:]
    wins5 = sum(1 for r in last_5 if _is_win(r.result))
    form_pct = 100.0 * wins5 / len(last_5)
    return {
        "current_rating": last.my_rating,
        "games_total": len(records),
        "recent_form_win_pct": round(form_pct, 1),
        "tilt": _tilt_color(form_pct),
    }


def compute_sessions(records: list[GameRecord], gap_seconds: int = 600) -> list[dict]:
    if not records:
        return []
    ordered = sorted(records, key=lambda r: r.end_time)
    sessions = []
    current = [ordered[0]]
    for r in ordered[1:]:
        if r.end_time - current[-1].end_time > gap_seconds:
            sessions.append(current)
            current = []
        current.append(r)
    sessions.append(current)

    out = []
    for s in sessions:
        wins = sum(1 for r in s if _is_win(r.result))
        losses = sum(1 for r in s if _is_loss(r.result))
        draws = sum(1 for r in s if _is_draw(r.result))
        rating_start = s[0].my_rating
        rating_end = s[-1].my_rating
        delta = rating_end - rating_start
        out.append({
            "start": datetime.fromtimestamp(s[0].end_time).isoformat(),
            "games": len(s),
            "duration_minutes": round((s[-1].end_time - s[0].end_time) / 60, 1),
            "wins": wins, "losses": losses, "draws": draws,
            "rating_start": rating_start,
            "rating_end": rating_end,
            "rating_delta": delta,
            "tilt_flag": delta <= -50,
        })
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py tests/fixtures/sample_records.py
git commit -m "feat(metrics): KPI strip and session detection"
```

---

## Task 7: Metrics — repertoire aggregation per opening

**Files:**
- Modify: `chess_tracker/metrics.py`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from chess_tracker.metrics import compute_repertoire


def test_compute_repertoire_groups_by_opening_and_color():
    rep = compute_repertoire(RECORDS)
    # 3 distinct (opening, color) keys: London/white, Petrovs/black, Italian/black, London/white
    # Actually: London(white) x3, Petrovs(black) x1, Italian(black) x2
    by_key = {(r["opening"], r["color"]): r for r in rep}
    assert by_key[("London System", "white")]["games"] == 3
    assert by_key[("Italian Game", "black")]["games"] == 2
    assert by_key[("Petrovs Defense", "black")]["games"] == 1


def test_compute_repertoire_calculates_win_pct():
    rep = compute_repertoire(RECORDS)
    by_key = {(r["opening"], r["color"]): r for r in rep}
    london = by_key[("London System", "white")]
    # London games: 1W, 1L (checkmated), 1W → 2W/3 = 66.7%
    assert london["wins"] == 2
    assert london["losses"] == 1
    assert london["win_pct"] == round(200/3, 1)


def test_compute_repertoire_includes_loss_type_breakdown():
    rep = compute_repertoire(RECORDS)
    by_key = {(r["opening"], r["color"]): r for r in rep}
    italian = by_key[("Italian Game", "black")]
    # 1 timeout, 1 checkmated → flag_pct 50%, mate_pct 50%
    assert italian["flag_pct"] == 50.0
    assert italian["mate_pct"] == 50.0


def test_compute_repertoire_includes_recent_form_sparkline():
    rep = compute_repertoire(RECORDS)
    by_key = {(r["opening"], r["color"]): r for r in rep}
    london = by_key[("London System", "white")]
    # form: oldest→newest, "W"|"L"|"D"
    assert london["form"] == ["W", "L", "W"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 4 new tests FAIL — `ImportError: cannot import name 'compute_repertoire'`.

- [ ] **Step 3: Implement**

Append to `chess_tracker/metrics.py`:

```python
def _result_letter(r: GameRecord) -> str:
    if _is_win(r.result): return "W"
    if _is_draw(r.result): return "D"
    return "L"


def compute_repertoire(records: list[GameRecord]) -> list[dict]:
    groups: dict[tuple[str, str], list[GameRecord]] = {}
    for r in records:
        if r.opening is None:
            continue
        key = (r.opening, r.side)
        groups.setdefault(key, []).append(r)

    out = []
    for (opening, color), recs in groups.items():
        recs = sorted(recs, key=lambda r: r.end_time)
        n = len(recs)
        wins = sum(1 for r in recs if _is_win(r.result))
        losses_recs = [r for r in recs if _is_loss(r.result)]
        losses = len(losses_recs)
        draws = n - wins - losses
        flag = sum(1 for r in losses_recs if r.result == "timeout")
        mate = sum(1 for r in losses_recs if r.result == "checkmated")
        med_len = statistics.median([r.fullmoves for r in recs])
        avg_opp = round(statistics.mean([r.opp_rating for r in recs]), 0)
        delta_yours = round(statistics.mean([r.my_rating - r.opp_rating for r in recs]), 0)
        # ECO mode
        eco_counts = Counter(r.eco for r in recs if r.eco)
        eco_top = eco_counts.most_common(1)[0][0] if eco_counts else None
        out.append({
            "opening": opening,
            "color": color,
            "eco": eco_top,
            "games": n,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_pct": round(100 * wins / n, 1),
            "flag_pct": round(100 * flag / losses, 1) if losses else 0.0,
            "mate_pct": round(100 * mate / losses, 1) if losses else 0.0,
            "med_len": med_len,
            "avg_opp_rating": int(avg_opp),
            "rating_delta": int(delta_yours),
            "form": [_result_letter(r) for r in recs[-10:]],
        })
    out.sort(key=lambda x: (-x["games"], -x["win_pct"]))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: all metrics tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): per-opening repertoire aggregation"
```

---

## Task 8: Metrics — conditions buckets (hour, session pos, opp delta)

**Files:**
- Modify: `chess_tracker/metrics.py`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from chess_tracker.metrics import compute_conditions


def test_compute_conditions_returns_three_axes():
    cond = compute_conditions(RECORDS, gap_seconds=600)
    assert set(cond.keys()) == {"hour_of_day", "session_position", "opp_rating_bucket"}


def test_compute_conditions_hour_of_day_buckets_have_win_pct():
    cond = compute_conditions(RECORDS, gap_seconds=600)
    hours = cond["hour_of_day"]
    # Each row: {"bucket": "HH", "games": N, "win_pct": float, "flag_pct": float, "mate_pct": float}
    for row in hours:
        assert "bucket" in row
        assert "games" in row
        assert "win_pct" in row
        assert "flag_pct" in row
        assert "mate_pct" in row


def test_compute_conditions_session_position_groups_games_correctly():
    cond = compute_conditions(RECORDS, gap_seconds=600)
    sp = {row["bucket"]: row for row in cond["session_position"]}
    # Game indices within session: session1 has 3 games (pos 1,2,3), session2 has 2 (pos 1,2), session3 has 1 (pos 1)
    # Bucket "1-5": all 6 games
    assert sp["1-5"]["games"] == 6


def test_compute_conditions_opp_bucket_uses_my_current_rating_as_anchor():
    cond = compute_conditions(RECORDS, gap_seconds=600)
    # Each row exists with games >= 0
    buckets = [row["bucket"] for row in cond["opp_rating_bucket"]]
    expected = ["< -150", "-150 to -50", "-50 to +50", "+50 to +150", "> +150"]
    assert buckets == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 4 new tests FAIL — `ImportError: cannot import name 'compute_conditions'`.

- [ ] **Step 3: Implement**

Append to `chess_tracker/metrics.py`:

```python
def _bucket_stats(recs: list[GameRecord]) -> dict:
    n = len(recs)
    if n == 0:
        return {"games": 0, "win_pct": 0.0, "flag_pct": 0.0, "mate_pct": 0.0}
    wins = sum(1 for r in recs if _is_win(r.result))
    losses_recs = [r for r in recs if _is_loss(r.result)]
    losses = len(losses_recs)
    flag = sum(1 for r in losses_recs if r.result == "timeout")
    mate = sum(1 for r in losses_recs if r.result == "checkmated")
    return {
        "games": n,
        "win_pct": round(100 * wins / n, 1),
        "flag_pct": round(100 * flag / losses, 1) if losses else 0.0,
        "mate_pct": round(100 * mate / losses, 1) if losses else 0.0,
    }


def _session_position(records: list[GameRecord], gap_seconds: int) -> dict[int, list[GameRecord]]:
    """Return {position_within_session: [records]}."""
    if not records:
        return {}
    ordered = sorted(records, key=lambda r: r.end_time)
    out: dict[int, list[GameRecord]] = {}
    pos = 1
    out.setdefault(pos, []).append(ordered[0])
    for prev, r in zip(ordered, ordered[1:]):
        if r.end_time - prev.end_time > gap_seconds:
            pos = 1
        else:
            pos += 1
        out.setdefault(pos, []).append(r)
    return out


def compute_conditions(records: list[GameRecord], gap_seconds: int = 600) -> dict:
    # 1. Hour of day
    by_hour: dict[int, list[GameRecord]] = {}
    for r in records:
        hr = datetime.fromtimestamp(r.end_time).hour
        by_hour.setdefault(hr, []).append(r)
    hour_rows = [
        {"bucket": f"{h:02d}", **_bucket_stats(by_hour[h])}
        for h in sorted(by_hour)
    ]

    # 2. Session position
    pos_groups = _session_position(records, gap_seconds)
    pos_buckets = {"1-5": [], "6-10": [], "11-20": [], "21+": []}
    for pos, recs in pos_groups.items():
        if pos <= 5: pos_buckets["1-5"].extend(recs)
        elif pos <= 10: pos_buckets["6-10"].extend(recs)
        elif pos <= 20: pos_buckets["11-20"].extend(recs)
        else: pos_buckets["21+"].extend(recs)
    pos_rows = [
        {"bucket": b, **_bucket_stats(recs)}
        for b, recs in pos_buckets.items()
    ]

    # 3. Opp rating delta (anchor: my current rating from last game)
    if records:
        anchor = max(records, key=lambda r: r.end_time).my_rating
    else:
        anchor = 0
    bucket_defs = [
        ("< -150", lambda d: d < -150),
        ("-150 to -50", lambda d: -150 <= d < -50),
        ("-50 to +50", lambda d: -50 <= d <= 50),
        ("+50 to +150", lambda d: 50 < d <= 150),
        ("> +150", lambda d: d > 150),
    ]
    opp_rows = []
    for label, pred in bucket_defs:
        in_bucket = [r for r in records if pred(r.opp_rating - anchor)]
        opp_rows.append({"bucket": label, **_bucket_stats(in_bucket)})

    return {
        "hour_of_day": hour_rows,
        "session_position": pos_rows,
        "opp_rating_bucket": opp_rows,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: all metrics tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): hour-of-day, session-position, opp-rating buckets"
```

---

## Task 9: Top-level compute_all + merge with annotations

**Files:**
- Modify: `chess_tracker/metrics.py`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_metrics.py`:

```python
from chess_tracker.metrics import compute_all


def test_compute_all_returns_full_dashboard_payload():
    annotations = {
        "openings": {"London System": {"tag": "in_repertoire", "note": "main"}},
        "games": {},
        "error_log": [{"id": "err-001", "title": "queen blunders"}],
    }
    payload = compute_all(RECORDS, annotations, username="m_v-v", format="bullet")
    assert payload["username"] == "m_v-v"
    assert payload["format"] == "bullet"
    assert "generated_at" in payload
    assert "kpis" in payload
    assert "repertoire" in payload
    assert "conditions" in payload
    assert "sessions" in payload
    assert payload["error_log"] == annotations["error_log"]
    # Annotation tag must be merged into repertoire rows
    london = next(r for r in payload["repertoire"] if r["opening"] == "London System")
    assert london["tag"] == "in_repertoire"
    assert london["note"] == "main"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py::test_compute_all_returns_full_dashboard_payload -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `chess_tracker/metrics.py`:

```python
def compute_all(records: list[GameRecord], annotations: dict,
                username: str, format: str = "bullet") -> dict:
    rep = compute_repertoire(records)
    # Merge per-opening annotations
    opening_notes = annotations.get("openings", {})
    for row in rep:
        ann = opening_notes.get(row["opening"], {})
        row["tag"] = ann.get("tag", "")
        row["note"] = ann.get("note", "")
    return {
        "username": username,
        "format": format,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "kpis": compute_kpis(records),
        "repertoire": rep,
        "conditions": compute_conditions(records),
        "sessions": compute_sessions(records),
        "error_log": annotations.get("error_log", []),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): compute_all merges annotations into dashboard payload"
```

---

## Task 10: HTML renderer (Python side)

**Files:**
- Create: `chess_tracker/render.py`
- Create: `tests/test_render.py`
- Create: `dashboard/index.html` (template)

- [ ] **Step 1: Write the template**

```html
<!-- dashboard/index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Chess Tracker — {{USERNAME}}</title>
  <link rel="stylesheet" href="https://unpkg.com/tabulator-tables@6.2.5/dist/css/tabulator_midnight.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="kpi-strip"></header>
  <main>
    <section><h2>Repertoire</h2><div id="repertoire-table"></div></section>
    <section>
      <h2>Conditions</h2>
      <div class="conditions-grid">
        <div><h3>Hour of day</h3><div id="hour-table"></div></div>
        <div><h3>Session position</h3><div id="session-pos-table"></div></div>
        <div><h3>Opponent rating delta</h3><div id="opp-bucket-table"></div></div>
      </div>
    </section>
    <section><h2>Sessions</h2><div id="sessions-table"></div></section>
    <section><h2>Error log</h2><div id="error-log-table"></div></section>
  </main>
  <script src="https://unpkg.com/tabulator-tables@6.2.5/dist/js/tabulator.min.js"></script>
  <script>
    /* DATA_INJECTION_POINT */
  </script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_render.py
import json
from pathlib import Path
from chess_tracker.render import render_dashboard


def test_render_dashboard_writes_html_with_injected_data(tmp_path):
    template = tmp_path / "index.html"
    template.write_text(
        "<html><body><script>/* DATA_INJECTION_POINT */</script></body></html>"
    )
    out = tmp_path / "out.html"
    payload = {"username": "m_v-v", "kpis": {"current_rating": 444}}

    render_dashboard(template_path=template, output_path=out, payload=payload)

    html = out.read_text()
    assert "const DATA =" in html
    assert "m_v-v" in html
    # JSON should be safely embedded (no closing </script> in payload)
    assert "/* DATA_INJECTION_POINT */" not in html


def test_render_dashboard_substitutes_username_in_title(tmp_path):
    template = tmp_path / "index.html"
    template.write_text("<title>Chess Tracker — {{USERNAME}}</title>")
    out = tmp_path / "out.html"
    render_dashboard(template_path=template, output_path=out,
                     payload={"username": "alice"})
    assert "Chess Tracker — alice" in out.read_text()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

```python
# chess_tracker/render.py
"""Render dashboard HTML by injecting computed JSON into a template."""
import json
from pathlib import Path

INJECT_MARKER = "/* DATA_INJECTION_POINT */"


def _safe_json(payload: dict) -> str:
    """Serialize for inline <script> embedding.

    Escapes </script> sequences which would otherwise break out of the tag.
    """
    raw = json.dumps(payload, indent=2)
    return raw.replace("</", "<\\/")


def render_dashboard(template_path: Path, output_path: Path, payload: dict) -> None:
    template_path = Path(template_path)
    output_path = Path(output_path)
    html = template_path.read_text()

    # Substitute simple placeholders
    username = payload.get("username", "")
    html = html.replace("{{USERNAME}}", username)

    # Inject data
    embed = f"const DATA = {_safe_json(payload)};"
    html = html.replace(INJECT_MARKER, embed)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_render.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/render.py tests/test_render.py dashboard/index.html
git commit -m "feat(render): inject computed payload into dashboard template"
```

---

## Task 11: Frontend — styles + KPI strip + app.js bootstrap

**Files:**
- Create: `dashboard/styles.css`
- Create: `dashboard/app.js`

> Verification for frontend tasks is visual: open `dashboard/index.html` in a browser after running `refresh.py` (Task 13). No automated test in this task.

- [ ] **Step 1: Write `dashboard/styles.css`**

```css
:root {
  --bg: #1a1a1a;
  --panel: #232323;
  --text: #e7e7e7;
  --muted: #8a8a8a;
  --accent: #769656;
  --warn: #c4a01e;
  --bad: #b54a3f;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
}

header#kpi-strip {
  position: sticky; top: 0; z-index: 10;
  display: flex; gap: 1.5rem; align-items: center;
  padding: 1rem 1.5rem;
  background: var(--panel);
  border-bottom: 1px solid #333;
}

.kpi {
  display: flex; flex-direction: column;
}
.kpi-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; }
.kpi-value { font-size: 1.5rem; font-weight: 600; }

.tilt-green { color: var(--accent); }
.tilt-yellow { color: var(--warn); }
.tilt-red { color: var(--bad); }

main { padding: 1.5rem; }
section { margin-bottom: 2.5rem; }
section h2 { margin: 0 0 0.75rem; font-size: 1.25rem; }
section h3 { margin: 0 0 0.5rem; font-size: 0.95rem; color: var(--muted); }

.conditions-grid {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

/* Sparkline */
.sparkline { display: inline-flex; gap: 2px; align-items: end; height: 16px; }
.spark-bar { width: 4px; }
.spark-W { background: var(--accent); height: 100%; }
.spark-L { background: var(--bad); height: 100%; }
.spark-D { background: var(--muted); height: 60%; }

/* Win% cell heatmap */
.cell-strong { color: var(--accent); font-weight: 600; }
.cell-weak { color: var(--bad); font-weight: 600; }
```

- [ ] **Step 2: Write `dashboard/app.js`**

```javascript
// dashboard/app.js
// Reads window.DATA (injected by render.py) and builds the dashboard.

(function() {
  const D = window.DATA;
  if (!D) {
    document.body.innerHTML = "<p style='padding:2rem'>No data. Run refresh.py.</p>";
    return;
  }

  renderKPIStrip(D);
  renderRepertoire(D.repertoire);
  renderConditions(D.conditions);
  renderSessions(D.sessions);
  renderErrorLog(D.error_log);

  // ---------- KPI strip ----------
  function renderKPIStrip(d) {
    const k = d.kpis;
    const strip = document.getElementById("kpi-strip");
    strip.innerHTML = `
      <div class="kpi"><span class="kpi-label">Rating</span>
        <span class="kpi-value">${k.current_rating ?? "—"}</span></div>
      <div class="kpi"><span class="kpi-label">Games total</span>
        <span class="kpi-value">${k.games_total}</span></div>
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value tilt-${k.tilt}">${k.recent_form_win_pct}%</span></div>
      <div class="kpi"><span class="kpi-label">Generated</span>
        <span class="kpi-value" style="font-size:0.9rem">${new Date(d.generated_at).toLocaleString()}</span></div>
    `;
  }

  // ---------- Sparkline formatter ----------
  function sparkline(cell) {
    const arr = cell.getValue() || [];
    return `<span class="sparkline">${
      arr.map(r => `<span class="spark-bar spark-${r}"></span>`).join("")
    }</span>`;
  }

  function winPctCell(cell) {
    const v = cell.getValue();
    const cls = v >= 60 ? "cell-strong" : v <= 35 ? "cell-weak" : "";
    return `<span class="${cls}">${v}%</span>`;
  }

  // ---------- Repertoire ----------
  function renderRepertoire(rows) {
    new Tabulator("#repertoire-table", {
      data: rows,
      layout: "fitDataStretch",
      pagination: false,
      columns: [
        {title: "Opening", field: "opening", widthGrow: 3, headerFilter: "input"},
        {title: "ECO", field: "eco", width: 70},
        {title: "Color", field: "color", width: 80, headerFilter: "list",
         headerFilterParams: {values: {"":"All", "white":"White", "black":"Black"}}},
        {title: "N", field: "games", width: 60, sorter: "number"},
        {title: "Win%", field: "win_pct", width: 80, sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", width: 80, sorter: "number"},
        {title: "Mate%", field: "mate_pct", width: 80, sorter: "number"},
        {title: "MedLen", field: "med_len", width: 80, sorter: "number"},
        {title: "Form", field: "form", width: 120, formatter: sparkline, headerSort: false},
        {title: "AvgOpp", field: "avg_opp_rating", width: 90, sorter: "number"},
        {title: "Δ", field: "rating_delta", width: 70, sorter: "number"},
        {title: "Tag", field: "tag", width: 120, headerFilter: "input"},
        {title: "Note", field: "note", widthGrow: 2},
      ],
      initialSort: [{column: "games", dir: "desc"}],
    });
  }

  // ---------- Conditions (3 tables) ----------
  function renderConditions(c) {
    const cols = [
      {title: "Bucket", field: "bucket"},
      {title: "N", field: "games", sorter: "number"},
      {title: "Win%", field: "win_pct", sorter: "number", formatter: winPctCell},
      {title: "Flag%", field: "flag_pct", sorter: "number"},
      {title: "Mate%", field: "mate_pct", sorter: "number"},
    ];
    new Tabulator("#hour-table", {data: c.hour_of_day, layout: "fitColumns", columns: cols});
    new Tabulator("#session-pos-table", {data: c.session_position, layout: "fitColumns", columns: cols});
    new Tabulator("#opp-bucket-table", {data: c.opp_rating_bucket, layout: "fitColumns", columns: cols});
  }

  // ---------- Sessions ----------
  function renderSessions(rows) {
    new Tabulator("#sessions-table", {
      data: rows,
      layout: "fitDataStretch",
      columns: [
        {title: "Start", field: "start"},
        {title: "Games", field: "games", sorter: "number"},
        {title: "Duration (min)", field: "duration_minutes", sorter: "number"},
        {title: "W", field: "wins", sorter: "number"},
        {title: "L", field: "losses", sorter: "number"},
        {title: "D", field: "draws", sorter: "number"},
        {title: "Δ Rating", field: "rating_delta", sorter: "number",
         formatter: c => {
           const v = c.getValue();
           const cls = v <= -50 ? "cell-weak" : v >= 30 ? "cell-strong" : "";
           return `<span class="${cls}">${v >= 0 ? "+" : ""}${v}</span>`;
         }},
        {title: "Tilt", field: "tilt_flag", width: 80,
         formatter: c => c.getValue() ? "🔴" : ""},
      ],
      initialSort: [{column: "start", dir: "desc"}],
    });
  }

  // ---------- Error log ----------
  function renderErrorLog(rows) {
    new Tabulator("#error-log-table", {
      data: rows,
      layout: "fitDataStretch",
      placeholder: "No entries yet. Add via annotations.json.",
      columns: [
        {title: "Title", field: "title"},
        {title: "Pattern", field: "pattern"},
        {title: "# Linked games", field: "game_refs",
         formatter: c => (c.getValue() || []).length, sorter: "number"},
        {title: "Created", field: "created"},
      ],
    });
  }
})();
```

- [ ] **Step 3: Commit (no test run — frontend will be verified in Task 13)**

```bash
git add dashboard/styles.css dashboard/app.js
git commit -m "feat(dashboard): styles + Tabulator wiring for all tables"
```

---

## Task 12: CLI entrypoint — refresh.py

**Files:**
- Create: `refresh.py`
- Create: `tests/test_refresh.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_refresh.py
import json
from unittest.mock import patch, MagicMock
import refresh  # the script


def test_refresh_main_orchestrates_pipeline(tmp_path, monkeypatch):
    """Smoke test: refresh.main writes computed.json and dashboard/index.html."""
    # Arrange: fake API responses
    archives_index = {"archives": [
        "https://api.chess.com/pub/player/m_v-v/games/2026/05"
    ]}
    sample_game = json.loads(
        (tmp_path.parent.parent / "tests/fixtures/sample_game.json").read_text()
    ) if (tmp_path.parent.parent / "tests/fixtures/sample_game.json").exists() else \
        {"url": "x", "end_time": 1_700_000_000, "time_class": "bullet",
         "white": {"username": "m_v-v", "rating": 500, "result": "win"},
         "black": {"username": "opp", "rating": 500, "result": "timeout"},
         "pgn": "[ECO \"A00\"]\n1. e4 {[%clk 0:00:59]} e5 {[%clk 0:00:59]}"}
    archive = {"games": [sample_game]}

    def fake_urlopen(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else req
        mock = MagicMock()
        if "archives" in url and url.endswith("/archives"):
            mock.read.return_value = json.dumps(archives_index).encode()
        else:
            mock.read.return_value = json.dumps(archive).encode()
        mock.__enter__.return_value = mock
        return mock

    monkeypatch.chdir(tmp_path)
    (tmp_path / "dashboard").mkdir()
    # Minimal template
    (tmp_path / "dashboard" / "index.html").write_text(
        "<html><body><script>/* DATA_INJECTION_POINT */</script></body></html>"
    )

    with patch("chess_tracker.api.urlopen", side_effect=fake_urlopen):
        refresh.main(["--username", "m_v-v"])

    assert (tmp_path / "data" / "computed.json").exists()
    assert (tmp_path / "dashboard" / "index.html").read_text().count("const DATA") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_refresh.py -v`
Expected: FAIL — `ModuleNotFoundError: refresh`.

- [ ] **Step 3: Implement**

```python
# refresh.py
"""CLI: pull Chess.com archives → compute metrics → render dashboard."""
import argparse
import json
import sys
from pathlib import Path

from chess_tracker.api import fetch_archives_index, fetch_archive
from chess_tracker.pgn import parse_game
from chess_tracker.metrics import compute_all
from chess_tracker.annotations import load_annotations
from chess_tracker.render import render_dashboard


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh chess tracker dashboard.")
    ap.add_argument("--username", default="M_V-V")
    ap.add_argument("--format", default="bullet",
                    choices=["bullet", "blitz", "rapid", "daily"])
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch all archives, not just current month.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--dashboard-dir", default="dashboard")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw"
    dashboard_dir = Path(args.dashboard_dir)
    template = dashboard_dir / "index.html"
    output = dashboard_dir / "index.html"
    annotations_path = data_dir / "annotations.json"

    print(f"[1/5] Loading archives index for {args.username}...")
    archives = fetch_archives_index(args.username)
    print(f"      {len(archives)} archive(s)")

    print(f"[2/5] Fetching archives (force={args.force})...")
    all_games = []
    current_month_url = archives[-1] if archives else None
    for url in archives:
        # Always re-fetch the current (latest) month; cache the rest
        force_this = args.force or (url == current_month_url)
        data = fetch_archive(url, cache_dir=raw_dir, force=force_this)
        all_games.extend(data.get("games", []))
    print(f"      {len(all_games)} games total")

    print(f"[3/5] Filtering to {args.format} and parsing PGNs...")
    in_format = [g for g in all_games if g.get("time_class") == args.format]
    records = [parse_game(g, username=args.username) for g in in_format]
    print(f"      {len(records)} {args.format} games parsed")

    print("[4/5] Computing metrics + merging annotations...")
    annotations = load_annotations(annotations_path)
    payload = compute_all(records, annotations,
                          username=args.username, format=args.format)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "computed.json").write_text(json.dumps(payload, indent=2))

    print("[5/5] Rendering dashboard...")
    render_dashboard(template_path=template, output_path=output, payload=payload)

    print(f"\nDone. Open: file://{output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_refresh.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (api: 3, pgn: 2, annotations: 4, metrics: 14, render: 2, refresh: 1 = 26).

- [ ] **Step 6: Commit**

```bash
git add refresh.py tests/test_refresh.py
git commit -m "feat: CLI orchestrator that runs the full refresh pipeline"
```

---

## Task 13: End-to-end smoke test (real API hit) + visual verification

**Files:** None (manual verification step)

- [ ] **Step 1: Run a real refresh against Chess.com**

Run: `uv run refresh.py --username M_V-V --format bullet`
Expected output (approximate):
```
[1/5] Loading archives index for M_V-V... 12 archive(s)
[2/5] Fetching archives (force=False)... ~500+ games total
[3/5] Filtering to bullet and parsing PGNs... ~520 bullet games parsed
[4/5] Computing metrics + merging annotations...
[5/5] Rendering dashboard...

Done. Open: file:///Users/madisonvelding-vandam/Developer/chess-tracker/dashboard/index.html
```

- [ ] **Step 2: Open the dashboard in a browser**

Run: `open /Users/madisonvelding-vandam/Developer/chess-tracker/dashboard/index.html`

Visual checklist:
- [ ] KPI strip shows current rating, games total, recent form % with tilt color
- [ ] Repertoire table renders with all expected columns
- [ ] Sorting by any column works (click headers)
- [ ] Header filters (input boxes under column headers) filter rows
- [ ] Sparklines render in the Form column as colored bars
- [ ] Win% cells are green/red based on threshold
- [ ] Three Conditions sub-tables render side-by-side and are sortable
- [ ] Sessions table shows latest first, with red tilt flags where applicable
- [ ] Error log shows placeholder text (no entries yet)

- [ ] **Step 3: Verify computed.json is well-formed**

Run: `uv run python -c "import json; d=json.load(open('data/computed.json')); print(list(d.keys()), 'rep rows:', len(d['repertoire']))"`
Expected: `['username', 'format', 'generated_at', 'kpis', 'repertoire', 'conditions', 'sessions', 'error_log'] rep rows: <some number ≥ 10>`

- [ ] **Step 4: Sanity-check annotations workflow**

Manually create `data/annotations.json`:
```bash
cat > data/annotations.json <<'EOF'
{
  "openings": {
    "Queens Pawn Opening Zukertort Chigorin Variation": {
      "tag": "in_repertoire",
      "note": "main d4 weapon"
    }
  },
  "games": {},
  "error_log": [
    {"id": "err-001", "created": "2026-05-26", "title": "test entry", "pattern": "wired up correctly"}
  ]
}
EOF
```

Re-run: `uv run refresh.py`
Reload dashboard. Verify:
- [ ] Queens Pawn row shows tag `in_repertoire` and note `main d4 weapon`
- [ ] Error log table shows the test entry

- [ ] **Step 5: Commit (smoke test passed marker)**

No code changed — this is a verification gate. If anything failed, fix in a follow-up task before continuing.

---

## Task 14: README polish + done

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Expand `README.md`**

```markdown
# Chess Tracker

Local Chess.com bullet repertoire dashboard. Pulls your games via the
public API, computes per-opening stats and process metrics, and
renders an interactive HTML dashboard.

## Setup

    uv sync --group dev

## Refresh

    uv run refresh.py                       # default: bullet, user M_V-V
    uv run refresh.py --format blitz        # other format
    uv run refresh.py --force               # re-fetch all months

Then open `dashboard/index.html` in your browser.

## Annotations

Edit `data/annotations.json` to tag openings, write notes, and add
error-log entries. Schema:

```json
{
  "openings": {
    "<opening name>": {"tag": "in_repertoire|experimenting|drop", "note": "..."}
  },
  "games": { "<game_url>": {"tags": ["..."], "note": "..."} },
  "error_log": [{"id": "...", "title": "...", "pattern": "...", "game_refs": []}]
}
```

Annotations are preserved across refreshes — they're a separate file
the pipeline only reads.

## Testing

    uv run pytest

## Layout

- `refresh.py` — CLI entrypoint
- `chess_tracker/` — pipeline modules (api, pgn, metrics, annotations, render)
- `dashboard/` — HTML/JS/CSS frontend
- `data/` — generated (cached archives, computed.json, annotations.json)
- `docs/superpowers/` — spec + plan

## Design

See `docs/superpowers/specs/2026-05-26-bullet-chess-tracker-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: expand README with setup, refresh, annotations, layout"
```

---

## Done criteria

After all 14 tasks:

- [ ] `uv run pytest` — all 26+ tests pass
- [ ] `uv run refresh.py` — runs without error against real Chess.com API
- [ ] `dashboard/index.html` — opens in browser, all 4 tables render and sort
- [ ] Annotations roundtrip — edit `data/annotations.json`, re-refresh, see changes
- [ ] Git log — ~14 commits, one per task, conventional commit format

## Out of scope (per spec)

- Engine analysis / ACPL / CAPS
- Daily / Rapid as first-class (only via `--format` flag, no UI tabs yet)
- Browser-side annotation editing (manual JSON edits for v1)
- Multi-user support
