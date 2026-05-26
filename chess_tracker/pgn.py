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
