"""Chess.com Published Data API client with simple disk cache."""
from urllib.request import Request, urlopen
import json
import re
from pathlib import Path

USER_AGENT = "ChessTracker/0.1 (madisonveldingvandam.artist@gmail.com)"
BASE = "https://api.chess.com/pub/player"
LICHESS_BASE = "https://lichess.org/api"


def _get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_archives_index(username: str) -> list[str]:
    """Return list of monthly archive URLs for the user, oldest first."""
    data = _get_json(f"{BASE}/{username.lower()}/games/archives")
    return list(data.get("archives", []))


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


def fetch_player_stats(username: str) -> dict:
    """Return the /stats dict for a player (current ratings across all time classes)."""
    return _get_json(f"{BASE}/{username.lower()}/stats")


def fetch_lichess_user(username: str) -> dict:
    """Fetch public profile + perfs for a Lichess user. Returns {} on any error."""
    url = f"{LICHESS_BASE}/user/{username.lower()}"
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}
