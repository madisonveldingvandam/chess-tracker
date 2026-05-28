import json
from pathlib import Path
from chess_tracker.pgn import (
    parse_game,
    opening_family,
    opening_variation,
    _clean_opening_label,
)

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
    # Real bullet games are >= 8 plies so signature should populate
    if rec.plies >= 8:
        assert isinstance(rec.play_signature, str)
        assert "/" in rec.play_signature


def test_clean_opening_label_strips_move_suffix():
    """Private helper: just removes trailing move-number tokens."""
    assert _clean_opening_label("Queens-Pawn-Opening-Zukertort-Variation-3.Bf4") == \
        "Queens Pawn Opening Zukertort Variation"
    assert _clean_opening_label("Italian-Game-Knight-Attack") == "Italian Game Knight Attack"
    assert _clean_opening_label("Caro-Kann-Defense-2...d5") == "Caro Kann Defense"
    # Real-fixture form: move text glued to the family name with `...`
    assert _clean_opening_label("Scotch-Game...4.Nxd4-Nxd4-5.Qxd4-d6") == "Scotch Game"


def test_opening_family_cuts_at_category_keyword():
    """Tier-1 stem stops at the first variation-category keyword (inclusive).

    Note on Queens Gambit: 'Accepted' / 'Declined' / 'Slav' etc. are
    variations of 'Queens Gambit' (the family), so the stem stops at
    'Gambit'. Chess.com's game review groups them the same way.
    """
    assert opening_family("Queens Pawn Opening Zukertort Chigorin Variation") == \
        "Queens Pawn Opening"
    assert opening_family("Italian Game Knight Attack") == "Italian Game"
    assert opening_family("Caro Kann Defense") == "Caro Kann Defense"
    assert opening_family("Englund Gambit") == "Englund Gambit"
    assert opening_family("London System") == "London System"
    assert opening_family("Queens Gambit Accepted") == "Queens Gambit"
    assert opening_family("Queens Gambit Declined") == "Queens Gambit"


def test_opening_variation_distinguishes_queens_gambit_branches():
    """Accepted / Declined are variations of the Queens Gambit family."""
    assert opening_variation("Queens Gambit Accepted") == "Accepted"
    assert opening_variation("Queens Gambit Declined") == "Declined"


def test_opening_family_accepts_raw_slugs_idempotently():
    """Should work on chess.com slugs directly — equivalent to cleaning first."""
    assert opening_family("Queens-Pawn-Opening-Zukertort-Variation-3.Bf4") == \
        "Queens Pawn Opening"
    assert opening_family("Scotch-Game...4.Nxd4-Nxd4-5.Qxd4-d6") == "Scotch Game"


def test_opening_family_handles_edge_inputs():
    assert opening_family(None) is None
    assert opening_family("") == ""
    # No category keyword present — return cleaned input unchanged
    assert opening_family("Bird") == "Bird"


def test_opening_variation_returns_suffix_after_family_stem():
    assert opening_variation("Queens Pawn Opening Zukertort Chigorin Variation") == \
        "Zukertort Chigorin Variation"
    assert opening_variation("Italian Game Knight Attack") == "Knight Attack"
    # Main-line / no variation suffix → empty string
    assert opening_variation("Caro Kann Defense") == ""
    assert opening_variation("Englund Gambit") == ""
    assert opening_variation("London System") == ""


def test_opening_variation_accepts_raw_slugs():
    assert opening_variation("Queens-Pawn-Opening-Zukertort-Variation-3.Bf4") == \
        "Zukertort Variation"


def test_opening_variation_handles_edge_inputs():
    assert opening_variation(None) is None
    assert opening_variation("") == ""
    # No category keyword — no suffix can be extracted
    assert opening_variation("Bird") == ""


def test_game_record_auto_derives_family_and_variation_from_opening():
    """__post_init__ should populate family/variation from opening when not set."""
    from chess_tracker.pgn import GameRecord
    rec = GameRecord(
        url="x", end_time=0, time_class="bullet", side="white",
        my_rating=500, opp_rating=500, result="win", opp_result="checkmated",
        plies=20, fullmoves=10,
        opening="Queens Pawn Opening Zukertort Chigorin Variation",
        eco="A45",
    )
    assert rec.family == "Queens Pawn Opening"
    assert rec.variation == "Zukertort Chigorin Variation"


def test_game_record_family_and_variation_explicit_override():
    """Explicit family/variation should not be overwritten by __post_init__."""
    from chess_tracker.pgn import GameRecord
    rec = GameRecord(
        url="x", end_time=0, time_class="bullet", side="white",
        my_rating=500, opp_rating=500, result="win", opp_result="checkmated",
        plies=20, fullmoves=10,
        opening="Whatever",
        eco="A00",
        family="Explicit Family",
        variation="Explicit Variation",
    )
    assert rec.family == "Explicit Family"
    assert rec.variation == "Explicit Variation"


def test_parse_game_extracts_time_control_and_rated():
    g = {
        "url": "https://chess.com/game/1",
        "end_time": 1_700_000_000,
        "time_class": "bullet",
        "time_control": "60",
        "rated": True,
        "white": {"username": "me", "rating": 500, "result": "win"},
        "black": {"username": "opp", "rating": 500, "result": "checkmated"},
        "pgn": '[ECO "C20"]\n[ECOUrl "https://www.chess.com/openings/Kings-Pawn-Opening"]\n1. e4 {[%clk 0:01:00]} e5 {[%clk 0:01:00]} *',
    }
    rec = parse_game(g, username="me")
    assert rec.time_control == "60"
    assert rec.rated is True


def test_parse_game_move_count_from_pgn_tree_not_clocks():
    """If a [%clk] tag is missing on one move, plies/fullmoves still reflect actual move count."""
    g = {
        "url": "u", "end_time": 1, "time_class": "bullet",
        "time_control": "60", "rated": True,
        "white": {"username": "me", "rating": 500, "result": "win"},
        "black": {"username": "opp", "rating": 500, "result": "checkmated"},
        # 4 plies, only 3 clock annotations
        "pgn": "[ECO \"C20\"]\n1. e4 e5 2. Nf3 {[%clk 0:00:58]} Nc6 {[%clk 0:00:58]} *",
    }
    rec = parse_game(g, username="me")
    assert rec.plies == 4
    assert rec.fullmoves == 2
