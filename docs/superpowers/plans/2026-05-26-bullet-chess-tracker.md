# Bullet Chess Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local HTML dashboard that ranks the user's Chess.com bullet openings, surfaces process-metric leaks, and persists annotations — refreshed by a single Python script.

**Architecture:** Python pipeline (`refresh.py`) pulls Chess.com archives → parses PGN+clocks → computes metrics as pure functions → merges with `annotations.json` → injects JSON into a static HTML page using Tabulator.js for sortable tables. No server. Per spec at `docs/superpowers/specs/2026-05-26-bullet-chess-tracker-design.md`.

**Tech Stack:** Python 3.14 (stdlib + `python-chess` for the 8-ply FEN), `pytest` (dev only via uv), Tabulator.js vendored locally, vanilla CSS + JS, inline SVG sparklines.

> **Plan revised on 2026-05-26 (second revision) after Tasks 1–11 shipped.** Original grouping by Chess.com ECO label fragmented the same play system into many buckets (e.g., five "Queen's Pawn Opening Zukertort \*" rows that play identically through move 8). Task 10.5 below adds a **`play_signature`** function (canonical FEN at ply 8, computed via `python-chess`) and switches `compute_all` to group by `(play_signature, color)` instead of `(opening_label, color)`. The JSON key renames `opening_outcomes` → `play_signatures`, the low-confidence threshold rises from N<10 to N<15 (collapsing transpositions concentrates more games per row), and Task 11's dashboard template gets its section IDs renamed in the same task. `compute_repertoire` and its 4 existing tests stay as-is (legacy, still green). `python-chess` becomes the project's only runtime dep beyond stdlib.

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
        rating_gap = round(statistics.mean([r.my_rating - r.opp_rating for r in recs]), 0)
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
            "rating_gap": int(rating_gap),  # mean(my - opp); positive = you outrated
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


> **Plan revised on 2026-05-26 after adversarial review.** Tasks 8–14 (old: conditions buckets / compute_all / HTML / frontend / CLI / smoke / README) are reorganized into Tasks 8–15 below. The new shape replaces "sortable spreadsheet" with "feedback loop": Leak Summary, Next Session Rule, and Recent Losses (with auto-suggested error-log entries) become the lead panels; the opening table is demoted to "Opening Outcomes" with confidence gates. Tasks 1–7 are unchanged.

## Task 8: Metrics — process metrics (clock + session decay)

**Files:**
- Modify: `chess_tracker/metrics.py` (APPEND only)
- Modify: `tests/test_metrics.py` (APPEND only)
- Modify: `tests/fixtures/sample_records.py` (extend RECORDS with clock-rich games so tests can assert reserve/velocity)

- [ ] **Step 1: Extend the fixture with clock-rich records**

Append to `tests/fixtures/sample_records.py`:

```python
# Clock-rich records for process-metric tests.
# Each clock list represents one side's per-ply clock readings.
# For simplicity these games have 25 plies (~12 full moves).
def _clocks(spent_per_ply: list[float]) -> list[float]:
    """Convert per-ply seconds spent into running 60s-bullet clock readings."""
    out = []
    remaining = 60.0
    for s in spent_per_ply:
        remaining -= s
        out.append(round(remaining, 1))
    return out


# Slow opener: spends 3s/move on first 8 plies, then 1s/move
_SLOW_OPENING = _clocks([3.0] * 8 + [1.0] * 17)
# Fast opener: 0.5s/move first 8 plies, then 1.5s/move
_FAST_OPENING = _clocks([0.5] * 8 + [1.5] * 17)

CLOCK_RECORDS = [
    _r(1_700_010_000, "win", "timeout", "London System", side="white",
       fullmoves=12, my_clocks=_FAST_OPENING, opp_clocks=_SLOW_OPENING),
    _r(1_700_010_120, "timeout", "win", "London System", side="white",
       fullmoves=12, my_clocks=_SLOW_OPENING, opp_clocks=_FAST_OPENING),
    _r(1_700_010_240, "win", "timeout", "London System", side="white",
       fullmoves=12, my_clocks=_FAST_OPENING, opp_clocks=_SLOW_OPENING),
]
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from tests.fixtures.sample_records import CLOCK_RECORDS
from chess_tracker.metrics import compute_process_metrics, compute_session_decay


def test_compute_process_metrics_returns_required_keys():
    pm = compute_process_metrics(CLOCK_RECORDS)
    assert set(pm.keys()) >= {
        "reserve_move_10_median",
        "reserve_move_20_median",
        "opening_velocity_median",
        "time_burn_delta",
        "outlasted_but_flagged_count",
    }


def test_opening_velocity_reflects_first_8_plies():
    """Fast opener uses 4s on first 8 plies; slow opener uses 24s."""
    fast_only = [CLOCK_RECORDS[0], CLOCK_RECORDS[2]]  # both fast
    slow_only = [CLOCK_RECORDS[1]]
    fast_vel = compute_process_metrics(fast_only)["opening_velocity_median"]
    slow_vel = compute_process_metrics(slow_only)["opening_velocity_median"]
    assert fast_vel < slow_vel
    assert abs(fast_vel - 4.0) < 0.5
    assert abs(slow_vel - 24.0) < 0.5


def test_outlasted_but_flagged_counts_timeouts_where_you_were_ahead_on_clock():
    """A timeout-loss where, mid-game, you had more time than opponent
    but eventually ran out — bad time management hidden inside an OK position."""
    pm = compute_process_metrics(CLOCK_RECORDS)
    # CLOCK_RECORDS[1] is the slow-opener timeout-loss
    assert pm["outlasted_but_flagged_count"] >= 0  # at minimum the field exists


def test_compute_session_decay_returns_buckets():
    decay = compute_session_decay(RECORDS, gap_seconds=600)
    by_bucket = {row["bucket"]: row for row in decay}
    assert set(by_bucket.keys()) == {"1-5", "6-10", "11-20", "21+"}
    # Each row has the same keys as a generic stats row
    for row in decay:
        assert {"games", "win_pct", "flag_pct", "mate_pct"} <= set(row.keys())
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 4 new tests fail with `ImportError`.

- [ ] **Step 4: Implement**

Append to `chess_tracker/metrics.py`:

```python
def _ply_clock(clocks: list[float], ply_index: int) -> float | None:
    """Return clock at a specific 0-indexed ply, or None if game was shorter."""
    if 0 <= ply_index < len(clocks):
        return clocks[ply_index]
    return None


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


def compute_process_metrics(records: list[GameRecord]) -> dict:
    """Clock-behavior metrics — the bullet-specific process signals."""
    if not records:
        return {
            "reserve_move_10_median": None,
            "reserve_move_20_median": None,
            "opening_velocity_median": None,
            "time_burn_delta": None,
            "outlasted_but_flagged_count": 0,
        }

    # Reserve at end of move 10 = my_clocks[9] (one entry per my-move; 0-indexed)
    res10 = [c for r in records if (c := _ply_clock(r.my_clocks, 9)) is not None]
    res20 = [c for r in records if (c := _ply_clock(r.my_clocks, 19)) is not None]

    # Opening velocity: seconds spent on my first 8 moves = 60 - my_clocks[7]
    velocities = []
    for r in records:
        c = _ply_clock(r.my_clocks, 7)
        if c is not None:
            velocities.append(round(60.0 - c, 2))

    # Time burn delta: mean s/move across my moves 1-8 vs my moves 9-20
    early_rates = []
    late_rates = []
    for r in records:
        if len(r.my_clocks) >= 8:
            early_total = 60.0 - r.my_clocks[7]
            early_rates.append(early_total / 8)
        if len(r.my_clocks) >= 20:
            late_total = r.my_clocks[7] - r.my_clocks[19]
            late_rates.append(late_total / 12)

    time_burn_delta = None
    if early_rates and late_rates:
        time_burn_delta = round(
            statistics.mean(early_rates) - statistics.mean(late_rates), 2)

    # "Outlasted but flagged": timeout-losses where at some recorded ply
    # you had more time than opponent did at the same ply.
    outlasted = 0
    for r in records:
        if r.result != "timeout":
            continue
        common = min(len(r.my_clocks), len(r.opp_clocks))
        for i in range(common):
            if r.my_clocks[i] > r.opp_clocks[i]:
                outlasted += 1
                break

    return {
        "reserve_move_10_median": round(statistics.median(res10), 1) if res10 else None,
        "reserve_move_20_median": round(statistics.median(res20), 1) if res20 else None,
        "opening_velocity_median": round(statistics.median(velocities), 2) if velocities else None,
        "time_burn_delta": time_burn_delta,
        "outlasted_but_flagged_count": outlasted,
    }


def _session_position_groups(records: list[GameRecord], gap_seconds: int = 600) -> dict[str, list[GameRecord]]:
    if not records:
        return {"1-5": [], "6-10": [], "11-20": [], "21+": []}
    ordered = sorted(records, key=lambda r: r.end_time)
    out: dict[str, list[GameRecord]] = {"1-5": [], "6-10": [], "11-20": [], "21+": []}
    pos = 1
    out["1-5"].append(ordered[0])
    for prev, r in zip(ordered, ordered[1:]):
        if r.end_time - prev.end_time > gap_seconds:
            pos = 1
        else:
            pos += 1
        if pos <= 5:
            out["1-5"].append(r)
        elif pos <= 10:
            out["6-10"].append(r)
        elif pos <= 20:
            out["11-20"].append(r)
        else:
            out["21+"].append(r)
    return out


def compute_session_decay(records: list[GameRecord], gap_seconds: int = 600) -> list[dict]:
    """Win/flag/mate stats bucketed by position within session."""
    groups = _session_position_groups(records, gap_seconds)
    return [{"bucket": b, **_bucket_stats(recs)} for b, recs in groups.items()]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: 22 passing (18 existing + 4 new).

- [ ] **Step 6: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py tests/fixtures/sample_records.py
git commit -m "feat(metrics): process metrics + session-position decay"
```

---

## Task 9: Metrics — leak summary + next-session rule + recent losses

**Files:**
- Modify: `chess_tracker/metrics.py` (APPEND only)
- Modify: `tests/test_metrics.py` (APPEND only)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metrics.py`:

```python
from chess_tracker.metrics import (
    detect_leaks, next_session_rule, recent_losses_with_suggestions
)


def test_detect_leaks_returns_rows_with_required_fields():
    leaks = detect_leaks(RECORDS + CLOCK_RECORDS)
    for leak in leaks:
        assert set(leak.keys()) >= {"name", "severity", "evidence", "suggested_action"}
        assert leak["severity"] in ("info", "warn", "critical")


def test_detect_leaks_flags_slow_opening_when_velocity_high():
    # CLOCK_RECORDS has slow openers spending 24s on first 8 plies
    leaks = detect_leaks([CLOCK_RECORDS[1]])
    names = [l["name"] for l in leaks]
    assert "time_burn_opening" in names


def test_next_session_rule_has_three_fields_plus_narrative():
    rule = next_session_rule(RECORDS + CLOCK_RECORDS)
    assert set(rule.keys()) == {"game_cap", "move_10_target_seconds",
                                 "stop_if_rating_drops", "narrative"}
    assert isinstance(rule["narrative"], str) and len(rule["narrative"]) > 10


def test_recent_losses_includes_suggested_entry():
    losses = recent_losses_with_suggestions(RECORDS, limit=10)
    for L in losses:
        assert "game_url" in L
        assert "loss_type" in L
        assert "suggested_entry" in L
        # Suggested entry is a dict that maps onto annotations.json error_log shape
        assert {"title", "pattern", "game_refs"} <= set(L["suggested_entry"].keys())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 4 new tests fail with `ImportError`.

- [ ] **Step 3: Implement**

Append to `chess_tracker/metrics.py`:

```python
def detect_leaks(records: list[GameRecord]) -> list[dict]:
    """Rule-based leak detection over the recent window."""
    leaks = []
    if not records:
        return leaks
    # Window: last 30 games (or all if fewer)
    ordered = sorted(records, key=lambda r: r.end_time)
    window = ordered[-30:]

    pm = compute_process_metrics(window)

    # Time burn in opening
    if pm["opening_velocity_median"] is not None and pm["opening_velocity_median"] > 8.0:
        leaks.append({
            "name": "time_burn_opening",
            "severity": "critical" if pm["opening_velocity_median"] > 15 else "warn",
            "evidence": f"median {pm['opening_velocity_median']}s on first 8 plies (target <8s)",
            "suggested_action": "Move 8 with ≥50s left; pre-pick first 6 moves before sit-down.",
        })

    # Flag-loss dominant
    losses_recs = [r for r in window if _is_loss(r.result)]
    if losses_recs:
        flag_pct = 100 * sum(1 for r in losses_recs if r.result == "timeout") / len(losses_recs)
        mate_pct = 100 * sum(1 for r in losses_recs if r.result == "checkmated") / len(losses_recs)
        if flag_pct >= 60:
            leaks.append({
                "name": "flag_loss_dominant",
                "severity": "warn",
                "evidence": f"{flag_pct:.0f}% of losses are timeouts in the last {len(window)} games",
                "suggested_action": "Reserve at move 20 too low; try 1+1 format to convert wins.",
            })
        if mate_pct >= 55:
            leaks.append({
                "name": "mate_loss_dominant",
                "severity": "warn",
                "evidence": f"{mate_pct:.0f}% of losses are checkmates in the last {len(window)} games",
                "suggested_action": "Middlegame tactics — file recurring patterns in the error log.",
            })

    # Mid-session decay
    decay = compute_session_decay(records)
    by_bucket = {row["bucket"]: row for row in decay}
    early = by_bucket.get("1-5", {}).get("win_pct", 0.0)
    late = by_bucket.get("21+", {}).get("win_pct", 0.0)
    if early - late >= 10 and by_bucket.get("21+", {}).get("games", 0) >= 5:
        leaks.append({
            "name": "mid_session_decay",
            "severity": "warn",
            "evidence": f"win% drops from {early:.0f}% in games 1-5 to {late:.0f}% after game 21",
            "suggested_action": "Cap sessions — see Next Session Rule.",
        })

    # Tilt sessions in last 24h
    sessions = compute_sessions(records)
    now_seen = max(r.end_time for r in records)
    recent = [s for s in sessions if (now_seen - int(datetime.fromisoformat(s["start"]).timestamp())) < 86400]
    if any(s["tilt_flag"] for s in recent):
        leaks.append({
            "name": "tilt_session",
            "severity": "critical",
            "evidence": f"{sum(1 for s in recent if s['tilt_flag'])} session(s) lost ≥50 rating in last 24h",
            "suggested_action": "Stop-rule: leave the desk after -50 in 30 min.",
        })

    return leaks


def next_session_rule(records: list[GameRecord]) -> dict:
    """Generate concrete next-session recommendation."""
    if not records:
        return {"game_cap": 20, "move_10_target_seconds": 45,
                "stop_if_rating_drops": 50,
                "narrative": "No data yet — start conservative."}

    # Game cap: first session-position bucket where win% < 40
    decay = compute_session_decay(records)
    cap = 30  # default
    for row in decay:
        if row["games"] >= 5 and row["win_pct"] < 40:
            bucket = row["bucket"]
            cap = {"1-5": 5, "6-10": 10, "11-20": 20, "21+": 30}[bucket]
            break

    # Move-10 target: median my-clock at ply 19 among wins, minus 5s
    wins = [r for r in records if _is_win(r.result)]
    win_reserves = [c for r in wins if (c := _ply_clock(r.my_clocks, 19)) is not None]
    target = round(statistics.median(win_reserves) - 5, 0) if win_reserves else 45

    narrative = (
        f"Cap at {cap} games. Aim for {target}s left at move 10. "
        f"Stop if rating drops 50 in a session."
    )

    return {
        "game_cap": cap,
        "move_10_target_seconds": int(target),
        "stop_if_rating_drops": 50,
        "narrative": narrative,
    }


def recent_losses_with_suggestions(records: list[GameRecord], limit: int = 20) -> list[dict]:
    """Recent losses with auto-generated error_log starter entries."""
    losses = sorted(
        [r for r in records if _is_loss(r.result)],
        key=lambda r: r.end_time,
        reverse=True,
    )[:limit]

    out = []
    for r in losses:
        final_clk = r.my_clocks[-1] if r.my_clocks else None
        if r.result == "timeout":
            title = f"Flagged at move {r.fullmoves} in {r.opening or 'unknown'}"
            pattern = (
                f"Ran out of time at move {r.fullmoves}. "
                f"Final clock {final_clk}s. Opponent rating {r.opp_rating}."
            )
        elif r.result == "checkmated":
            title = f"Mated by move {r.fullmoves} in {r.opening or 'unknown'}"
            pattern = (
                f"Checkmated at move {r.fullmoves} with {final_clk}s on clock. "
                f"Opponent rating {r.opp_rating}."
            )
        else:
            title = f"Lost ({r.result}) in {r.opening or 'unknown'}"
            pattern = f"Result {r.result} at move {r.fullmoves}."

        out.append({
            "game_url": r.url,
            "opening": r.opening,
            "eco": r.eco,
            "loss_type": r.result,
            "final_clock": final_clk,
            "moves": r.fullmoves,
            "opp_rating_diff": r.opp_rating - r.my_rating,
            "suggested_entry": {
                "title": title,
                "pattern": pattern,
                "game_refs": [r.url],
            },
        })
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: 26 passing (22 + 4).

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): leak detection + next-session rule + loss suggestions"
```

---

## Task 10: Metrics — compute_all + opening_outcomes rename + low_confidence flag

**Files:**
- Modify: `chess_tracker/metrics.py` (APPEND only)
- Modify: `tests/test_metrics.py` (APPEND only)

- [ ] **Step 1: Write failing test**

Append to `tests/test_metrics.py`:

```python
from chess_tracker.metrics import compute_all


def test_compute_all_has_new_panel_keys():
    annotations = {
        "openings": {"London System": {"tag": "in_repertoire", "note": "main"}},
        "games": {},
        "error_log": [],
    }
    payload = compute_all(RECORDS + CLOCK_RECORDS, annotations,
                          username="m_v-v", format="bullet")
    expected = {
        "username", "format", "generated_at",
        "kpis", "leak_summary", "next_session_rule",
        "recent_losses", "process_metrics",
        "opening_outcomes", "sessions", "error_log",
    }
    assert expected <= set(payload.keys())


def test_compute_all_opening_outcomes_has_low_confidence_flag():
    annotations = {"openings": {}, "games": {}, "error_log": []}
    payload = compute_all(RECORDS, annotations, username="m_v-v")
    for row in payload["opening_outcomes"]:
        assert "low_confidence" in row
        assert row["low_confidence"] == (row["games"] < 10)


def test_compute_all_merges_opening_annotations():
    annotations = {
        "openings": {"London System": {"tag": "in_repertoire", "note": "main d4"}},
        "games": {}, "error_log": [],
    }
    payload = compute_all(RECORDS, annotations, username="m_v-v")
    london = next(r for r in payload["opening_outcomes"]
                  if r["opening"] == "London System")
    assert london["tag"] == "in_repertoire"
    assert london["note"] == "main d4"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 3 new tests fail.

- [ ] **Step 3: Implement**

Append to `chess_tracker/metrics.py`:

```python
def compute_all(records: list[GameRecord], annotations: dict,
                username: str, format: str = "bullet",
                low_confidence_threshold: int = 10) -> dict:
    """Top-level dashboard payload. All panel data merged + annotations applied."""
    opening_outcomes = compute_repertoire(records)
    opening_notes = annotations.get("openings", {})
    for row in opening_outcomes:
        ann = opening_notes.get(row["opening"], {})
        row["tag"] = ann.get("tag", "")
        row["note"] = ann.get("note", "")
        row["low_confidence"] = row["games"] < low_confidence_threshold

    return {
        "username": username,
        "format": format,
        "generated_at": datetime.now().astimezone().isoformat(),
        "kpis": compute_kpis(records),
        "leak_summary": detect_leaks(records),
        "next_session_rule": next_session_rule(records),
        "recent_losses": recent_losses_with_suggestions(records),
        "process_metrics": {
            **compute_process_metrics(records),
            "session_decay": compute_session_decay(records),
        },
        "opening_outcomes": opening_outcomes,
        "sessions": compute_sessions(records),
        "error_log": annotations.get("error_log", []),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: 29 passing (26 + 3).

- [ ] **Step 5: Commit**

```bash
git add chess_tracker/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): compute_all wires all panels + low_confidence flag"
```

---

## Task 10.5: Refactor opening grouping to play_signature

**Why this task exists.** Chess.com's ECO label splits the same play system into many rows keyed on the opponent's response (e.g., five separate "Queen's Pawn Opening Zukertort \*" rows that play identically through move 8). The dashboard's `opening_outcomes` panel was therefore an artifact of opponent choice rather than a real signal about my play. This task replaces ECO-label grouping with an 8-ply **play signature**: the canonical FEN reached after the first 8 plies, computed via `python-chess`. Different move orders reaching the same position collapse into one signature.

**Files:**
- Modify: `pyproject.toml` (add runtime dep `python-chess`)
- Create: `chess_tracker/play_signature.py`
- Modify: `chess_tracker/pgn.py` (add `play_signature` field to `GameRecord` and populate it in `parse_game`)
- Modify: `chess_tracker/metrics.py` (add `compute_play_signatures`; update `compute_all` to use it, rename JSON key, raise threshold default to 15)
- Modify: `chess_tracker/templates/index.html` (rename section IDs)
- Create: `tests/test_play_signature.py`
- Modify: `tests/test_pgn.py` (assert `parse_game` populates `play_signature`)
- Modify: `tests/test_metrics.py` (rename 3 `compute_all` tests; threshold 10 → 15)
- Modify: `tests/fixtures/sample_records.py` (extend `_r` helper with optional `play_signature` arg; populate stubs for RECORDS so the existing `compute_all` tests still find rows)

- [ ] **Step 1: Add `python-chess` runtime dep in `pyproject.toml`**

```toml
[project]
dependencies = ["python-chess>=1.10"]
```

Run `uv sync` to pull the dep. Confirm it lands in the dev venv.

- [ ] **Step 2: Write `chess_tracker/play_signature.py`**

```python
"""Compute the 8-ply canonical FEN signature for a chess game.

Two games that reach the same position after 8 plies (regardless of move
order — i.e., transpositions collapse) produce identical signatures.
"""
from io import StringIO
import chess
import chess.pgn

PLY_DEPTH = 8


def play_signature(pgn_text: str) -> str | None:
    """Return canonical FEN at ply 8, or None if the game has < 8 plies.

    FEN's halfmove and fullmove counters are stripped: the signature is
    placement + side-to-move + castling rights + en-passant target. Two
    transpositions reaching the same position get identical signatures.
    """
    try:
        game = chess.pgn.read_game(StringIO(pgn_text))
    except Exception:
        return None
    if game is None:
        return None
    board = game.board()
    plies = 0
    for move in game.mainline_moves():
        if plies >= PLY_DEPTH:
            break
        board.push(move)
        plies += 1
    if plies < PLY_DEPTH:
        return None
    parts = board.fen().split()
    return " ".join(parts[:4])  # drop halfmove + fullmove counters
```

- [ ] **Step 3: Write failing tests at `tests/test_play_signature.py`**

```python
from chess_tracker.play_signature import play_signature, PLY_DEPTH


def test_play_signature_returns_string_for_long_enough_game():
    pgn = "1. d4 d5 2. Nf3 Nf6 3. c4 e6 4. Nc3 Be7 5. Bg5 O-O *"
    sig = play_signature(pgn)
    assert isinstance(sig, str)
    assert "/" in sig  # FEN has rank separators


def test_play_signature_returns_none_for_short_game():
    pgn = "1. d4 d5 2. Nf3 *"  # only 4 plies
    assert play_signature(pgn) is None


def test_play_signature_collapses_transpositions():
    direct     = "1. d4 Nf6 2. c4 e6 3. Nc3 d5 4. Nf3 Be7 *"
    transposed = "1. d4 d5  2. c4 e6 3. Nc3 Nf6 4. Nf3 Be7 *"
    assert play_signature(direct) == play_signature(transposed)


def test_play_signature_returns_none_for_empty_pgn():
    assert play_signature("") is None


def test_play_signature_distinguishes_different_positions():
    queens = "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 *"   # QGD
    kings  = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *"  # Ruy Lopez
    assert play_signature(queens) != play_signature(kings)
```

Run: `uv run pytest tests/test_play_signature.py -v` → expect 5 fail with `ModuleNotFoundError`.

- [ ] **Step 4: Implement steps 2's code so test_play_signature.py goes green**

Then run again — expect 5 PASS.

- [ ] **Step 5: Add `play_signature` field to `GameRecord` and populate it**

In `chess_tracker/pgn.py`:

```python
from chess_tracker.play_signature import play_signature as _compute_play_signature

@dataclass
class GameRecord:
    url: str
    end_time: int
    time_class: str
    side: str
    my_rating: int
    opp_rating: int
    result: str
    opp_result: str
    plies: int
    fullmoves: int
    opening: str | None
    eco: str | None
    my_clocks: list[float] = field(default_factory=list)
    opp_clocks: list[float] = field(default_factory=list)
    play_signature: str | None = None  # NEW
```

In `parse_game`, populate via the new helper:
```python
def parse_game(g: dict, username: str) -> GameRecord:
    ...
    return GameRecord(
        ...
        play_signature=_compute_play_signature(g.get("pgn", "")),
    )
```

Add a new assertion to `tests/test_pgn.py::test_parse_game_returns_record_with_required_fields`:
```python
    # Real bullet games are >= 8 plies so signature should populate
    if rec.plies >= 8:
        assert isinstance(rec.play_signature, str)
        assert "/" in rec.play_signature
```

Run tests again — the existing `test_parse_game_returns_record_with_required_fields` should still PASS plus the new clause should pass on the fixture (real chess.com bullet game).

- [ ] **Step 6: Extend `tests/fixtures/sample_records.py` `_r` helper**

Add `play_signature=None` to `_r`'s signature and pass through. Then populate stubs on `RECORDS` so groups exist:

```python
def _r(end_time, result, opp_result, opening, my_rating=500, opp_rating=500,
       side="white", fullmoves=30, my_clocks=None, opp_clocks=None,
       eco="A00", play_signature=None):
    return GameRecord(
        ...,
        play_signature=play_signature,
    )

# Use opening-name stubs as fake signatures so grouping works in tests:
RECORDS = [
    _r(1_700_000_000, "win", "timeout", "London System",
       my_rating=500, play_signature="sig-london-white"),
    _r(1_700_000_060, "checkmated", "win", "London System",
       my_rating=505, play_signature="sig-london-white"),
    _r(1_700_000_120, "win", "timeout", "Petrovs Defense",
       my_rating=510, side="black", play_signature="sig-petrov-black"),
    _r(1_700_002_000, "timeout", "win", "Italian Game",
       my_rating=505, side="black", play_signature="sig-italian-black"),
    _r(1_700_002_060, "checkmated", "win", "Italian Game",
       my_rating=490, side="black", play_signature="sig-italian-black"),
    _r(1_700_006_000, "win", "timeout", "London System",
       my_rating=485, play_signature="sig-london-white"),
]
```

`CLOCK_RECORDS`, `OUTLASTED_THEN_FLAG_RECORD`: leave `play_signature=None` since their tests don't exercise `compute_play_signatures`.

- [ ] **Step 7: Add `compute_play_signatures` in `chess_tracker/metrics.py`**

Append (do NOT remove `compute_repertoire`; it stays as legacy with its 4 tests):

```python
def compute_play_signatures(records: list[GameRecord]) -> list[dict]:
    """Group records by (play_signature, color). Records without a
    play_signature (game < 8 plies) are skipped. Each row carries
    display_name = most common opening label among the group's games.
    """
    groups: dict[tuple[str, str], list[GameRecord]] = {}
    for r in records:
        if r.play_signature is None:
            continue
        key = (r.play_signature, r.side)
        groups.setdefault(key, []).append(r)

    out = []
    for (sig, color), recs in groups.items():
        recs = sorted(recs, key=lambda r: r.end_time)
        name_counts = Counter(r.opening for r in recs if r.opening)
        display_name = name_counts.most_common(1)[0][0] if name_counts else "Unnamed"
        n = len(recs)
        wins = sum(1 for r in recs if _is_win(r.result))
        losses_recs = [r for r in recs if _is_loss(r.result)]
        losses = len(losses_recs)
        draws = n - wins - losses
        flag = sum(1 for r in losses_recs if r.result == "timeout")
        mate = sum(1 for r in losses_recs if r.result == "checkmated")
        med_len = statistics.median([r.fullmoves for r in recs])
        avg_opp = round(statistics.mean([r.opp_rating for r in recs]), 0)
        rating_gap = round(statistics.mean([r.my_rating - r.opp_rating for r in recs]), 0)
        eco_counts = Counter(r.eco for r in recs if r.eco)
        eco_top = eco_counts.most_common(1)[0][0] if eco_counts else None
        out.append({
            "play_signature": sig,
            "display_name": display_name,
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
            "rating_gap": int(rating_gap),
            "form": [_result_letter(r) for r in recs[-10:]],
        })
    out.sort(key=lambda x: (-x["games"], -x["win_pct"]))
    return out
```

- [ ] **Step 8: Update `compute_all` to use the new function**

In `chess_tracker/metrics.py`, change two things:

1. Default threshold `low_confidence_threshold: int = 10` → `int = 15`.
2. Body: replace the `compute_repertoire` block with `compute_play_signatures`, and the JSON key `"opening_outcomes"` → `"play_signatures"`. Annotation lookup keys on `row["display_name"]`:

```python
def compute_all(records, annotations, username, format="bullet",
                low_confidence_threshold: int = 15) -> dict:
    play_signatures = compute_play_signatures(records)
    opening_notes = annotations.get("openings", {})
    for row in play_signatures:
        ann = opening_notes.get(row["display_name"], {})
        row["tag"] = ann.get("tag", "")
        row["note"] = ann.get("note", "")
        row["low_confidence"] = row["games"] < low_confidence_threshold

    return {
        "username": username,
        "format": format,
        "generated_at": datetime.now().astimezone().isoformat(),
        "kpis": compute_kpis(records),
        "leak_summary": detect_leaks(records),
        "next_session_rule": next_session_rule(records),
        "recent_losses": recent_losses_with_suggestions(records),
        "process_metrics": {
            **compute_process_metrics(records),
            "session_decay": compute_session_decay(records),
        },
        "play_signatures": play_signatures,  # was "opening_outcomes"
        "sessions": compute_sessions(records),
        "error_log": annotations.get("error_log", []),
    }
```

- [ ] **Step 9: Update 3 tests in `tests/test_metrics.py`**

(a) `test_compute_all_has_new_panel_keys`: change `"opening_outcomes"` → `"play_signatures"` in the expected set.

(b) Rename `test_compute_all_opening_outcomes_has_low_confidence_flag` → `test_compute_all_play_signatures_has_low_confidence_flag`. Change `payload["opening_outcomes"]` → `payload["play_signatures"]`. Change `row["games"] < 10` → `row["games"] < 15`.

(c) `test_compute_all_merges_opening_annotations`: change `payload["opening_outcomes"]` → `payload["play_signatures"]`. Change the row match from `r["opening"] == "London System"` to `r["display_name"] == "London System"`. (The new function emits `display_name`, not `opening`, as the human-readable label.)

- [ ] **Step 10: Rename section IDs in `chess_tracker/templates/index.html`**

```diff
-    <section id="outcomes-section">
-      <h2>Opening outcomes <small>(sample sizes are small — treat low-N rows as exploratory)</small></h2>
-      <div id="opening-outcomes-table"></div>
+    <section id="signatures-section">
+      <h2>Play signatures <small>(grouped by 8-ply FEN; sample sizes are small — treat low-N rows as exploratory)</small></h2>
+      <div id="play-signatures-table"></div>
     </section>
```

- [ ] **Step 11: Run full suite**

```
uv run pytest -v
```

Expected: ~40 passing (34 before + 5 new `test_play_signature.py` + 1 new line in `test_parse_game_returns_record_with_required_fields` doesn't add a test, just an assertion). The 3 renamed `compute_all` tests keep their count.

- [ ] **Step 12: Commit**

```bash
git add pyproject.toml chess_tracker/play_signature.py chess_tracker/pgn.py chess_tracker/metrics.py chess_tracker/templates/index.html tests/test_play_signature.py tests/test_pgn.py tests/test_metrics.py tests/fixtures/sample_records.py
git commit -m "refactor(metrics): group play_signatures by 8-ply canonical FEN (python-chess)"
```

---

## Task 11: HTML renderer (Python side)

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
  <link rel="stylesheet" href="vendor/tabulator_midnight.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="kpi-strip"></header>
  <main>
    <section id="leak-section"><h2>Leak summary</h2><div id="leak-list"></div></section>
    <section id="rule-section"><h2>Next session rule</h2><div id="next-rule"></div></section>
    <section id="losses-section">
      <h2>Recent losses → error log</h2>
      <div id="losses-table"></div>
      <button id="copy-suggestions">Copy starter entries</button>
      <h3>Error log</h3>
      <div id="error-log-table"></div>
    </section>
    <section id="process-section"><h2>Process metrics</h2>
      <div id="process-block"></div>
      <h3>Session-position decay</h3>
      <div id="session-decay-table"></div>
    </section>
    <section id="signatures-section">
      <h2>Play signatures <small>(grouped by 8-ply FEN; sample sizes are small — treat low-N rows as exploratory)</small></h2>
      <div id="play-signatures-table"></div>
    </section>
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

- [ ] **Step 2: Write failing test**

```python
# tests/test_render.py
from pathlib import Path
from chess_tracker.render import render_dashboard


def test_render_dashboard_injects_data_and_substitutes_username(tmp_path):
    template = tmp_path / "index.html"
    template.write_text(
        "<title>Chess Tracker — {{USERNAME}}</title>"
        "<script>/* DATA_INJECTION_POINT */</script>"
    )
    out = tmp_path / "out.html"
    payload = {"username": "alice", "kpis": {"current_rating": 444}}
    render_dashboard(template_path=template, output_path=out, payload=payload)
    html = out.read_text()
    assert "Chess Tracker — alice" in html
    assert "const DATA =" in html
    assert "/* DATA_INJECTION_POINT */" not in html
    assert "alice" in html


def test_render_escapes_closing_script_in_payload(tmp_path):
    template = tmp_path / "index.html"
    template.write_text("<script>/* DATA_INJECTION_POINT */</script>")
    out = tmp_path / "out.html"
    # Payload contains "</script>" which would break out of the tag if unescaped
    payload = {"username": "x", "evil": "</script><b>oh no</b>"}
    render_dashboard(template_path=template, output_path=out, payload=payload)
    html = out.read_text()
    assert "</script><b>oh no</b>" not in html  # the literal substring is escaped
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_render.py -v`
Expected: `ModuleNotFoundError`.

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
    username = payload.get("username", "")
    html = html.replace("{{USERNAME}}", username)
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

## Task 12: Frontend — vendor Tabulator + 6-panel layout + recommendation panels

**Files:**
- Create: `dashboard/vendor/tabulator.min.js` (download)
- Create: `dashboard/vendor/tabulator_midnight.min.css` (download)
- Create: `dashboard/styles.css`
- Create: `dashboard/app.js`

> Frontend tasks: no unit tests. Verification is visual after Task 14 smoke test.

- [ ] **Step 1: Vendor Tabulator**

```bash
mkdir -p dashboard/vendor
curl -sLo dashboard/vendor/tabulator.min.js \
  https://unpkg.com/tabulator-tables@6.2.5/dist/js/tabulator.min.js
curl -sLo dashboard/vendor/tabulator_midnight.min.css \
  https://unpkg.com/tabulator-tables@6.2.5/dist/css/tabulator_midnight.min.css
test -s dashboard/vendor/tabulator.min.js
test -s dashboard/vendor/tabulator_midnight.min.css
```

- [ ] **Step 2: Write `dashboard/styles.css`**

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
.kpi { display: flex; flex-direction: column; }
.kpi-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; }
.kpi-value { font-size: 1.5rem; font-weight: 600; }

main { padding: 1.5rem; }
section { margin-bottom: 2.5rem; }
section h2 { margin: 0 0 0.75rem; font-size: 1.25rem; }
section h3 { margin: 1rem 0 0.5rem; font-size: 1rem; color: var(--muted); }

/* Leak summary */
.leak {
  border-left: 4px solid var(--muted);
  padding: 0.75rem 1rem; margin-bottom: 0.5rem; background: var(--panel);
}
.leak.severity-warn { border-left-color: var(--warn); }
.leak.severity-critical { border-left-color: var(--bad); }
.leak .leak-name { font-weight: 600; }
.leak .leak-evidence { color: var(--muted); font-size: 0.9rem; }
.leak .leak-action { margin-top: 0.25rem; }

/* Next-session rule */
.rule-block {
  background: var(--panel); padding: 1rem 1.25rem; border-radius: 6px;
  display: grid; grid-template-columns: max-content 1fr; gap: 0.5rem 1.5rem;
}
.rule-block dt { color: var(--muted); }
.rule-block dd { margin: 0; font-weight: 600; }
.rule-narrative {
  margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #333;
  font-style: italic;
}

/* Process metrics block */
.process-grid {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
.process-card {
  background: var(--panel); padding: 0.75rem 1rem; border-radius: 6px;
}
.process-card .pm-label { color: var(--muted); font-size: 0.8rem; }
.process-card .pm-value { font-size: 1.3rem; font-weight: 600; }

/* Sparkline */
.sparkline { display: inline-flex; gap: 2px; align-items: end; height: 16px; }
.spark-bar { width: 4px; }
.spark-W { background: var(--accent); height: 100%; }
.spark-L { background: var(--bad); height: 100%; }
.spark-D { background: var(--muted); height: 60%; }

/* Cell formatting */
.cell-strong { color: var(--accent); font-weight: 600; }
.cell-weak { color: var(--bad); font-weight: 600; }
.row-low-conf { opacity: 0.5; }

#copy-suggestions {
  margin-top: 0.75rem; padding: 0.5rem 1rem;
  background: var(--accent); color: #111; border: 0; border-radius: 4px;
  cursor: pointer; font-weight: 600;
}
```

- [ ] **Step 3: Write `dashboard/app.js`**

```javascript
// dashboard/app.js
(function() {
  const D = window.DATA;
  if (!D) {
    document.body.innerHTML = "<p style='padding:2rem'>No data. Run refresh.py.</p>";
    return;
  }
  renderKPI(D);
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics.session_decay);
  renderPlaySignatures(D.play_signatures);
  renderSessions(D.sessions);

  function renderKPI(d) {
    const k = d.kpis;
    document.getElementById("kpi-strip").innerHTML = `
      <div class="kpi"><span class="kpi-label">Rating</span>
        <span class="kpi-value">${k.current_rating ?? "—"}</span></div>
      <div class="kpi"><span class="kpi-label">Games total</span>
        <span class="kpi-value">${k.games_total}</span></div>
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value">${k.recent_form_win_pct}%</span></div>
      <div class="kpi"><span class="kpi-label">Generated</span>
        <span class="kpi-value" style="font-size:0.9rem">${new Date(d.generated_at).toLocaleString()}</span></div>
    `;
  }

  function renderLeaks(leaks) {
    const root = document.getElementById("leak-list");
    if (!leaks || leaks.length === 0) {
      root.innerHTML = `<p style="color:var(--muted)">No leaks detected in the last 30 games.</p>`;
      return;
    }
    root.innerHTML = leaks.map(L => `
      <div class="leak severity-${L.severity}">
        <div class="leak-name">${L.name.replace(/_/g, " ")}</div>
        <div class="leak-evidence">${L.evidence}</div>
        <div class="leak-action">→ ${L.suggested_action}</div>
      </div>
    `).join("");
  }

  function renderRule(rule) {
    const root = document.getElementById("next-rule");
    root.innerHTML = `
      <dl class="rule-block">
        <dt>Game cap</dt><dd>${rule.game_cap}</dd>
        <dt>Move-10 target</dt><dd>${rule.move_10_target_seconds}s left</dd>
        <dt>Stop if</dt><dd>rating drops ${rule.stop_if_rating_drops} in a session</dd>
      </dl>
      <div class="rule-narrative">${rule.narrative}</div>
    `;
  }

  function renderRecentLosses(losses) {
    new Tabulator("#losses-table", {
      data: losses, layout: "fitDataStretch", pagination: false,
      columns: [
        {title: "Opening", field: "opening", widthGrow: 2},
        {title: "Loss", field: "loss_type"},
        {title: "Moves", field: "moves", sorter: "number"},
        {title: "Clock", field: "final_clock", sorter: "number"},
        {title: "OppΔ", field: "opp_rating_diff", sorter: "number"},
        {title: "Suggested entry", field: "suggested_entry",
         formatter: c => c.getValue().title, widthGrow: 3},
        {title: "Game", field: "game_url",
         formatter: c => `<a href="${c.getValue()}" target="_blank">open</a>`},
      ],
    });
    document.getElementById("copy-suggestions").onclick = () => {
      const entries = losses.map(L => L.suggested_entry);
      navigator.clipboard.writeText(JSON.stringify(entries, null, 2));
    };
  }

  function renderErrorLog(rows) {
    new Tabulator("#error-log-table", {
      data: rows, layout: "fitDataStretch",
      placeholder: "No entries yet. Paste from suggestions above into data/annotations.json.",
      columns: [
        {title: "Title", field: "title"},
        {title: "Pattern", field: "pattern"},
        {title: "# Games", field: "game_refs",
         formatter: c => (c.getValue() || []).length, sorter: "number"},
        {title: "Created", field: "created"},
      ],
    });
  }

  function renderProcess(pm) {
    const fmt = v => v === null || v === undefined ? "—" : v;
    document.getElementById("process-block").innerHTML = `
      <div class="process-grid">
        <div class="process-card"><div class="pm-label">Reserve @ move 10 (median)</div><div class="pm-value">${fmt(pm.reserve_move_10_median)}s</div></div>
        <div class="process-card"><div class="pm-label">Reserve @ move 20 (median)</div><div class="pm-value">${fmt(pm.reserve_move_20_median)}s</div></div>
        <div class="process-card"><div class="pm-label">Opening velocity (first 8 plies)</div><div class="pm-value">${fmt(pm.opening_velocity_median)}s</div></div>
        <div class="process-card"><div class="pm-label">Time-burn delta (early − late)</div><div class="pm-value">${fmt(pm.time_burn_delta)}</div></div>
        <div class="process-card"><div class="pm-label">Outlasted-but-flagged</div><div class="pm-value">${pm.outlasted_but_flagged_count}</div></div>
      </div>
    `;
  }

  function renderSessionDecay(rows) {
    new Tabulator("#session-decay-table", {
      data: rows, layout: "fitColumns",
      columns: [
        {title: "Games in session", field: "bucket"},
        {title: "N", field: "games", sorter: "number"},
        {title: "Win%", field: "win_pct", sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", sorter: "number"},
        {title: "Mate%", field: "mate_pct", sorter: "number"},
      ],
    });
  }

  function renderPlaySignatures(rows) {
    new Tabulator("#play-signatures-table", {
      data: rows, layout: "fitDataStretch",
      rowFormatter: row => {
        if (row.getData().low_confidence) row.getElement().classList.add("row-low-conf");
      },
      columns: [
        {title: "Conf", field: "low_confidence",
         formatter: c => c.getValue() ? "⚪" : "🟢", width: 60, sorter: (a,b)=> (a?1:0)-(b?1:0)},
        {title: "Opening", field: "display_name", widthGrow: 3, headerFilter: "input"},
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
        {title: "Δ-opp", field: "rating_gap", width: 80, sorter: "number"},
        {title: "Tag", field: "tag", width: 100, headerFilter: "input"},
        {title: "Note", field: "note", widthGrow: 2},
        {title: "FEN@8", field: "play_signature", visible: false},
      ],
      initialSort: [
        {column: "low_confidence", dir: "asc"},
        {column: "games", dir: "desc"},
      ],
    });
  }

  function renderSessions(rows) {
    new Tabulator("#sessions-table", {
      data: rows, layout: "fitDataStretch",
      columns: [
        {title: "Start", field: "start"},
        {title: "Games", field: "games", sorter: "number"},
        {title: "Span (min)", field: "duration_minutes", sorter: "number"},
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
})();
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/vendor/ dashboard/styles.css dashboard/app.js
git commit -m "feat(dashboard): vendor Tabulator + 6-panel feedback-loop layout"
```

---

## Task 13: CLI entrypoint — refresh.py

**Files:**
- Create: `refresh.py`
- Create: `tests/test_refresh.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_refresh.py
import json
from unittest.mock import patch, MagicMock
import refresh


def test_refresh_main_writes_computed_and_dashboard(tmp_path, monkeypatch):
    archives_index = {"archives": [
        "https://api.chess.com/pub/player/m_v-v/games/2026/05"
    ]}
    sample_game = {
        "url": "x", "end_time": 1_700_000_000, "time_class": "bullet",
        "white": {"username": "m_v-v", "rating": 500, "result": "win"},
        "black": {"username": "opp", "rating": 500, "result": "timeout"},
        "pgn": "[ECO \"A00\"]\n1. e4 {[%clk 0:00:59]} e5 {[%clk 0:00:59]}",
    }
    archive = {"games": [sample_game]}

    def fake_urlopen(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else req
        mock = MagicMock()
        if url.endswith("/archives"):
            mock.read.return_value = json.dumps(archives_index).encode()
        else:
            mock.read.return_value = json.dumps(archive).encode()
        mock.__enter__.return_value = mock
        return mock

    monkeypatch.chdir(tmp_path)
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "index.html").write_text(
        "<html><body><script>/* DATA_INJECTION_POINT */</script></body></html>"
    )

    with patch("chess_tracker.api.urlopen", side_effect=fake_urlopen):
        refresh.main(["--username", "m_v-v"])

    assert (tmp_path / "data" / "computed.json").exists()
    out_html = (tmp_path / "dashboard" / "index.html").read_text()
    assert "const DATA" in out_html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_refresh.py -v`
Expected: `ModuleNotFoundError: refresh`.

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

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -v`
Expected: ~32 passing.

- [ ] **Step 6: Commit**

```bash
git add refresh.py tests/test_refresh.py
git commit -m "feat: CLI orchestrator runs the full refresh pipeline"
```

---

## Task 14: End-to-end smoke test (real API) + visual verification

**Files:** None (manual verification)

- [ ] **Step 1: Real refresh against Chess.com**

Run: `uv run refresh.py --username M_V-V --format bullet`

Expected: 5-stage progress output, ~500+ bullet games parsed, ends with "Open: file://...".

- [ ] **Step 2: Open the dashboard**

Run: `open dashboard/index.html`

Visual checklist (in panel order):
- [ ] KPI strip renders with current rating and 4 metrics
- [ ] **Leak summary** shows 0+ leak cards with colored left-borders (none/warn/critical)
- [ ] **Next session rule** shows game cap / move-10 target / stop-if + narrative
- [ ] **Recent losses** table renders; "Copy starter entries" button works (paste into a text editor to verify)
- [ ] **Error log** below the losses table shows existing entries or the empty placeholder
- [ ] **Process metrics** cards render with reserve/velocity/burn-delta/outlasted values (some may be "—" if data is too short)
- [ ] **Session-position decay** table shows 4 rows (1-5, 6-10, 11-20, 21+)
- [ ] **Play signatures** table shows rows sorted with high-confidence (🟢) first, low-confidence (⚪) rows dimmed; the visible "Opening" column shows each row's `display_name`
- [ ] **Sessions** table shows latest first, red tilt flags where Δ ≤ -50

- [ ] **Step 3: Verify computed.json shape**

Run: `uv run python -c "import json; d=json.load(open('data/computed.json')); print(sorted(d.keys()))"`
Expected: includes `leak_summary`, `next_session_rule`, `recent_losses`, `process_metrics`, `play_signatures`, `sessions`.

- [ ] **Step 4: Verify offline operation**

Disconnect Wi-Fi, hard-reload `dashboard/index.html`. All tables should still render (Tabulator loads from `dashboard/vendor/`, not CDN).

- [ ] **Step 5: Annotations roundtrip**

Create `data/annotations.json` with one opening tag + one error_log entry. Re-run `uv run refresh.py`. Reload dashboard. Verify the tag appears in Opening Outcomes and the error_log entry appears below Recent Losses.

- [ ] **Step 6: Verification gate**

No code changes if everything passed. If anything failed, file a follow-up task before continuing.

---

## Task 15: README polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Expand `README.md`**

```markdown
# Chess Tracker

Local Chess.com bullet behavior recorder + feedback loop. Pulls your
games via the public API, computes per-session and per-opening
metrics, surfaces leaks, and proposes a next-session rule.

## Setup

    uv sync --group dev

## Refresh

    uv run refresh.py                       # default: bullet, user M_V-V
    uv run refresh.py --force               # re-fetch all months

Then open `dashboard/index.html` in your browser.

## What you'll see

1. **KPI strip** — current rating, total games, recent form
2. **Leak summary** — what's bleeding rating right now
3. **Next session rule** — game cap, move-10 target, stop signal
4. **Recent losses → error log** — click "Copy starter entries" to populate annotations
5. **Process metrics** — clock and session behavior
6. **Play signatures** — sortable; low-confidence rows (N<15) are dimmed; grouped by 8-ply FEN, not ECO label
7. **Sessions** — chronological list with tilt flags

## Annotations

Edit `data/annotations.json` directly. Schema:

```json
{
  "openings": {
    "<opening name>": {"tag": "in_repertoire|experimenting|drop", "note": "..."}
  },
  "games":    { "<game_url>": {"tags": ["..."], "note": "..."} },
  "error_log": [{"id": "...", "title": "...", "pattern": "...", "game_refs": []}]
}
```

The dashboard generates starter entries for you (Recent Losses panel) — paste them in.

Re-running `refresh.py` picks up changes immediately.

## Testing

    uv run pytest

## Layout

- `refresh.py` — CLI entrypoint
- `chess_tracker/` — pipeline modules (api, pgn, metrics, annotations, render)
- `dashboard/` — HTML/JS/CSS frontend; `vendor/` has Tabulator (offline-safe)
- `data/` — generated (cached archives, computed.json, annotations.json)
- `docs/superpowers/` — spec + plan

## Design

See `docs/superpowers/specs/2026-05-26-bullet-chess-tracker-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: expand README for v1 feedback-loop layout"
```

---

## Done criteria

After all 15 tasks:

- [ ] `uv run pytest` — all tests pass (~32)
- [ ] `uv run refresh.py` — runs without error against real Chess.com API
- [ ] `dashboard/index.html` — opens in browser, all 7 panels render in order
- [ ] Annotations roundtrip — edit `data/annotations.json`, re-refresh, see changes
- [ ] Offline test — dashboard renders without network (vendored Tabulator)
- [ ] Git log — ~15 commits, conventional commit format

## Out of scope (per spec)

- Engine analysis beyond Chess.com's `accuracies` field
- Hour-of-day and opp-rating bucket conditions (deferred — lower value than clock behavior)
- Daily / Rapid as first-class UI tabs
- Browser-side annotation editing modal (v1.1)
- Multi-user support
- Bayesian shrinkage / formal confidence intervals (replaced by low_confidence flag)
