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
