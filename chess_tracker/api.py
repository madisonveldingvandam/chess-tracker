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
