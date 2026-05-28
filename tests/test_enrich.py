"""Tests for the enrichment pass that attaches per-game derived fields."""
from chess_tracker.pgn import GameRecord
from chess_tracker.enrich import enrich_with_deltas


def _mk(t, rating, result="win"):
    return GameRecord(
        url=f"u{t}", end_time=t, time_class="bullet",
        side="white", my_rating=rating, opp_rating=500,
        result=result, opp_result="checkmated",
        plies=20, fullmoves=10, opening="x", eco="A00",
    )


def test_enrich_with_deltas_first_record_is_none():
    records = [_mk(1, 500)]
    enrich_with_deltas(records)
    assert records[0].prev_rating is None
    assert records[0].rating_delta is None


def test_enrich_with_deltas_computes_adjacent_swing():
    records = [_mk(3, 510), _mk(1, 500), _mk(2, 495)]  # deliberately out-of-order input
    enrich_with_deltas(records)
    # Sort by end_time before reading: chronological order is t=1 (500), t=2 (495), t=3 (510)
    by_time = sorted(records, key=lambda r: r.end_time)
    assert by_time[0].prev_rating is None
    assert by_time[0].rating_delta is None
    assert by_time[1].prev_rating == 500
    assert by_time[1].rating_delta == -5
    assert by_time[2].prev_rating == 495
    assert by_time[2].rating_delta == 15


def test_enrich_with_deltas_mutates_in_place():
    """Enrichment mutates the GameRecord objects directly (no new list returned)."""
    records = [_mk(1, 500), _mk(2, 510)]
    ret = enrich_with_deltas(records)
    assert ret is records  # same list object
    assert records[1].rating_delta == 10


from chess_tracker.enrich import enrich_with_sessions


def test_enrich_with_sessions_assigns_id_and_index():
    """Session boundary = >gap_seconds idle. session_id is 0-indexed by start time;
    game_index_in_session is 1-indexed within each session."""
    records = [
        _mk(1_700_000_000, 500),
        _mk(1_700_000_060, 505),
        # >10 min gap
        _mk(1_700_002_000, 510),
        _mk(1_700_002_060, 515),
        _mk(1_700_002_120, 520),
    ]
    enrich_with_sessions(records, gap_seconds=600)
    by_time = sorted(records, key=lambda r: r.end_time)
    assert [r.session_id for r in by_time] == [0, 0, 1, 1, 1]
    assert [r.game_index_in_session for r in by_time] == [1, 2, 1, 2, 3]
