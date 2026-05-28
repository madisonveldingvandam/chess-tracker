"""Hand-crafted GameRecord instances for metric tests."""
from chess_tracker.pgn import GameRecord

# Helper to keep fixtures terse
def _r(end_time, result, opp_result, opening, my_rating=500, opp_rating=500,
       side="white", fullmoves=30, my_clocks=None, opp_clocks=None, eco="A00",
       play_signature=None, time_control: str = "60", rated: bool = True):
    return GameRecord(
        url=f"https://chess.com/game/{end_time}",
        end_time=end_time, time_class="bullet",
        side=side, my_rating=my_rating, opp_rating=opp_rating,
        result=result, opp_result=opp_result,
        plies=fullmoves * 2, fullmoves=fullmoves,
        opening=opening, eco=eco,
        my_clocks=my_clocks or [60.0, 30.0, 10.0],
        opp_clocks=opp_clocks or [60.0, 30.0, 5.0],
        play_signature=play_signature,
        time_control=time_control,
        rated=rated,
    )


# Three sessions: clear boundaries (>10min gap).
# play_signature values below are synthetic grouping keys, not real FENs;
# compute_play_signatures only uses them as opaque group identifiers.
RECORDS = [
    # Session 1: 3 games, 2W 1L, ratings 500→510
    _r(1_700_000_000, "win", "timeout", "London System", my_rating=500,
       play_signature="sig-london-white"),
    _r(1_700_000_060, "checkmated", "win", "London System", my_rating=505,
       play_signature="sig-london-white"),
    _r(1_700_000_120, "win", "timeout", "Petrovs Defense", my_rating=510, side="black",
       play_signature="sig-petrov-black"),
    # Gap of 30 min
    # Session 2: 2 games, 0W 2L, ratings 510→480
    _r(1_700_002_000, "timeout", "win", "Italian Game", my_rating=505, side="black",
       play_signature="sig-italian-black"),
    _r(1_700_002_060, "checkmated", "win", "Italian Game", my_rating=490, side="black",
       play_signature="sig-italian-black"),
    # Gap of 1 hour
    # Session 3: 1 game, 1W
    _r(1_700_006_000, "win", "timeout", "London System", my_rating=485,
       play_signature="sig-london-white"),
]


# Clock-rich records for process-metric tests.
# Each clock list represents ONE side's per-MY-MOVE clock readings.
# (i.e. my_clocks[i] is my clock after MY (i+1)-th move; opp_clocks similar.)
# For simplicity these games have 25 of-my-moves each (~25 fullmoves of game).
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


# Designed for outlasted-but-flagged test: I was ahead on time in the opening,
# burned hard mid-game, and ran out. Opp paced steadily and survives.
_OUTLASTED_THEN_FLAG_MINE = [55.0, 50.0, 45.0, 35.0, 25.0, 15.0, 5.0, 0.0]
_OPP_STEADY_PACER = [50.0, 45.0, 40.0, 35.0, 30.0, 25.0, 20.0, 15.0]

OUTLASTED_THEN_FLAG_RECORD = _r(
    1_700_011_000, "timeout", "win", "London System", side="white",
    fullmoves=8,
    my_clocks=_OUTLASTED_THEN_FLAG_MINE,
    opp_clocks=_OPP_STEADY_PACER,
)

# Designed for the tightened outlasted-but-flagged test: I held a 7-second
# clock lead through move 10, then collapsed and flagged. 12 plies of clock
# data per side.
_LONG_OUTLAST_MINE = [55.0, 50.0, 45.0, 40.0, 35.0, 30.0, 25.0, 20.0, 15.0,
                       12.0, 5.0, 0.0]
_LONG_OUTLAST_OPP =  [50.0, 45.0, 40.0, 35.0, 30.0, 25.0, 20.0, 15.0, 10.0,
                       5.0, 4.0, 3.0]

LONG_OUTLAST_RECORD = _r(
    1_700_011_200, "timeout", "win", "London System", side="white",
    fullmoves=12,
    my_clocks=_LONG_OUTLAST_MINE,
    opp_clocks=_LONG_OUTLAST_OPP,
)
