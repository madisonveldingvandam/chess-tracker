"""Parse a Chess.com game dict into a GameRecord."""
from dataclasses import dataclass, field
import re
from chess_tracker.play_signature import (
    play_signature as _compute_play_signature,
    first_moves_san as _compute_first_moves_san,
)

_CLOCK_RE = re.compile(r"\[%clk (\d+):(\d{2}):(\d{2}(?:\.\d+)?)\]")
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
    opening: str | None      # full opening label (no move-number suffix, retains variation)
    eco: str | None          # ECO code, e.g. "C42"
    my_clocks: list[float] = field(default_factory=list)
    opp_clocks: list[float] = field(default_factory=list)
    play_signature: str | None = None  # 8-ply canonical FEN signature
    first_moves: str | None = None     # SAN of first 8 plies, e.g. "1.d4 d5 …"
    family: str | None = None          # tier-1 stem (e.g. "Queens Pawn Opening"); auto-derived from opening
    variation: str | None = None       # tier-2 suffix (e.g. "Zukertort Chigorin Variation"); "" for main lines

    def __post_init__(self):
        # Derive family/variation from opening when not explicitly set.
        # Allows test fixtures to skip them and have them auto-populate.
        if self.opening and self.family is None:
            self.family = opening_family(self.opening)
        if self.opening and self.variation is None:
            self.variation = opening_variation(self.opening)


def _parse_clocks(pgn: str) -> list[float]:
    """Return clocks in move order: [W after move 1, B after move 1, ...]."""
    out = []
    for h, m, s in _CLOCK_RE.findall(pgn):
        out.append(int(h) * 3600 + int(m) * 60 + float(s))
    return out


def _clean_opening_label(slug: str) -> str:
    """Strip trailing move-number tokens from an ECOUrl slug.

    Chess.com slugs separate continuation move text with either a hyphen
    (becomes whitespace after replace) or a literal triple-dot (e.g.
    ``Scotch-Game...4.Nxd4-Nxd4``). Both separators must be honored so
    that the move-number token is reached and the family ends cleanly.

    Idempotent — calling on an already-cleaned label is a no-op.
    """
    name = slug.replace("-", " ")
    parts = []
    for tok in re.split(r"\s+|\.{3}", name):
        if not tok:
            continue
        if re.match(r"^\d", tok):  # token starts with a digit → move number
            break
        parts.append(tok)
    return " ".join(parts) if parts else name


# Category keywords that close out a family stem. After the first occurrence
# (at position > 0), the keyword is included in the family and everything
# after becomes the variation suffix.
_FAMILY_STOPS = {"Variation", "Defense", "Attack", "System", "Gambit",
                 "Game", "Opening", "Accepted", "Declined"}


def opening_family(label: str | None) -> str | None:
    """Tier-1 rollup: family stem of an opening label.

    Cuts at the first variation-category keyword (inclusive). E.g.:
      ``Queens Pawn Opening Zukertort Chigorin Variation`` → ``Queens Pawn Opening``
      ``Italian Game Knight Attack`` → ``Italian Game``
      ``Caro Kann Defense`` → ``Caro Kann Defense``
      ``Englund Gambit`` → ``Englund Gambit``

    If no category keyword is present, returns the cleaned input unchanged.
    Accepts raw chess.com slugs or already-cleaned labels — both work.
    """
    if not label:
        return label
    toks = _clean_opening_label(label).split()
    for i, t in enumerate(toks):
        if i > 0 and t in _FAMILY_STOPS:
            return " ".join(toks[: i + 1])
    return " ".join(toks)


def opening_variation(label: str | None) -> str | None:
    """Tier-2 suffix after the family stem. Empty string for main lines.

    Examples:
      ``Queens Pawn Opening Zukertort Chigorin Variation`` → ``Zukertort Chigorin Variation``
      ``Italian Game Knight Attack`` → ``Knight Attack``
      ``Caro Kann Defense`` → ``''``
      ``Englund Gambit`` → ``''``

    Returns ``None`` only when the input is ``None`` / empty.
    """
    if not label:
        return label
    toks = _clean_opening_label(label).split()
    for i, t in enumerate(toks):
        if i > 0 and t in _FAMILY_STOPS:
            return " ".join(toks[i + 1 :])
    return ""


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
    opening = _clean_opening_label(eco_url_m.group(1)) if eco_url_m else None
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
        play_signature=_compute_play_signature(pgn),
        first_moves=_compute_first_moves_san(pgn),
    )
