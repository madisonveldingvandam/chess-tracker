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
