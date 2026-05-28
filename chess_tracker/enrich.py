"""Single-pass enrichment of GameRecord lists with derived fields.

Each function mutates records in place and returns the same list.
Centralising this here lets downstream metrics consume prev_rating /
rating_delta / session_id / game_index_in_session without re-deriving
adjacency or session boundaries.
"""
from chess_tracker.pgn import GameRecord


def enrich_with_deltas(records: list[GameRecord]) -> list[GameRecord]:
    """Attach prev_rating and rating_delta to each record.

    Sorts a copy by end_time to determine adjacency, then mutates the
    original records. First chronological record has prev_rating=None
    and rating_delta=None.
    """
    if not records:
        return records
    ordered = sorted(records, key=lambda r: r.end_time)
    prev = None
    for r in ordered:
        if prev is None:
            r.prev_rating = None
            r.rating_delta = None
        else:
            r.prev_rating = prev.my_rating
            r.rating_delta = r.my_rating - prev.my_rating
        prev = r
    return records


def enrich_with_sessions(records: list[GameRecord], gap_seconds: int = 600) -> list[GameRecord]:
    """Attach session_id (0-indexed) and game_index_in_session (1-indexed).

    Session boundaries: a gap >gap_seconds between consecutive end_times
    starts a new session.
    """
    if not records:
        return records
    ordered = sorted(records, key=lambda r: r.end_time)
    session_id = 0
    idx = 1
    ordered[0].session_id = 0
    ordered[0].game_index_in_session = 1
    for prev, r in zip(ordered, ordered[1:]):
        if r.end_time - prev.end_time > gap_seconds:
            session_id += 1
            idx = 1
        else:
            idx += 1
        r.session_id = session_id
        r.game_index_in_session = idx
    return records
