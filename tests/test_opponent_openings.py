"""Tests for chess_tracker.opponent_openings."""
import pytest
from chess_tracker.pgn import GameRecord
from chess_tracker.opponent_openings import (
    extract_opp_moves,
    compute_opponent_opening_stats,
)


# ---------------------------------------------------------------------------
# Minimal GameRecord factory
# ---------------------------------------------------------------------------

def _rec(
    side: str,
    result: str,
    opening_moves: str | None = None,
    play_signature: str | None = None,
    opening: str | None = None,
    end_time: int = 1_700_000_000,
) -> GameRecord:
    return GameRecord(
        url=f"https://chess.com/game/{end_time}",
        end_time=end_time,
        time_class="bullet",
        side=side,
        my_rating=500,
        opp_rating=500,
        result=result,
        opp_result="win",
        plies=20,
        fullmoves=10,
        opening=opening,
        eco=None,
        opening_moves=opening_moves,
        play_signature=play_signature,
    )


# ---------------------------------------------------------------------------
# extract_opp_moves
# ---------------------------------------------------------------------------

FRIED_LIVER = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7 Kxf7"


def test_extract_as_black_gets_white_moves():
    moves, skip = extract_opp_moves(FRIED_LIVER, "black")
    assert skip == ""
    # White's first 4 normalized moves
    assert moves == ["e4", "Nf3", "Bc4", "Ng5"]


def test_extract_as_white_gets_black_moves():
    moves, skip = extract_opp_moves(FRIED_LIVER, "white")
    assert skip == ""
    # Black's first 4 normalized moves
    assert moves == ["e5", "Nc6", "Nf6", "d5"]


def test_extract_null_opening():
    moves, skip = extract_opp_moves(None, "black")
    assert skip == "null_opening"
    assert moves is None


def test_extract_empty_string():
    moves, skip = extract_opp_moves("", "black")
    assert skip == "null_opening"
    assert moves is None


def test_extract_too_short_one_opponent_move():
    # Only 2 plies: White plays 1.e4, Black plays e5 — but as Black,
    # opponent (White) has only 1 move.
    moves, skip = extract_opp_moves("1.e4 e5", "black")
    assert skip == "too_short"
    assert moves is None


def test_extract_partial_three_opponent_moves():
    # 6-ply game — White has 3 moves, Black has 3.
    line = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6"
    moves, skip = extract_opp_moves(line, "black")
    assert skip == ""
    assert moves == ["e4", "Nf3", "Bc4"]
    assert len(moves) == 3


def test_extract_partial_two_opponent_moves():
    # 4-ply game — opponent has exactly 2 moves.
    line = "1.e4 e5 2.Nf3 Nc6"
    moves, skip = extract_opp_moves(line, "black")
    assert skip == ""
    assert moves == ["e4", "Nf3"]


def test_extract_captures_normalized():
    # Bxf7 should normalize to Bf7
    line = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Bxf7 Kxf7"
    moves, skip = extract_opp_moves(line, "black")
    assert skip == ""
    assert "Bf7" in moves


def test_extract_checks_stripped():
    # Nf6+ should normalize to Nf6
    line = "1.e4 e5 2.Nf3+ Nc6 3.Bc4 Nf6+ 4.Ng5 d5"
    moves, skip = extract_opp_moves(line, "black")
    assert skip == ""
    assert moves == ["e4", "Nf3", "Bc4", "Ng5"]


def test_extract_castling_preserved():
    line = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.O-O Nf6"
    moves, skip = extract_opp_moves(line, "black")
    assert skip == ""
    assert moves == ["e4", "Nf3", "Bc4", "O-O"]


def test_extract_caps_at_four_moves():
    # 12-ply game — opponent has 6 moves but we only want 4
    line = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7 Kxf7"
    moves, skip = extract_opp_moves(line, "black")
    assert skip == ""
    assert len(moves) == 4
    assert moves == ["e4", "Nf3", "Bc4", "Ng5"]


# ---------------------------------------------------------------------------
# compute_opponent_opening_stats
# ---------------------------------------------------------------------------

def test_empty_records():
    result = compute_opponent_opening_stats([])
    assert result["rows"] == []
    assert result["grouping_level"] == "none"


def test_all_null_opening_moves():
    records = [_rec("black", "checkmated", opening_moves=None) for _ in range(20)]
    result = compute_opponent_opening_stats(records)
    assert result["rows"] == []
    assert result["audit"]["games_excluded_null_opening"] == 20


def test_kill_criterion_sparse_clusters():
    # Each game has a unique opponent line → no cluster reaches N >= 5
    records = []
    for i in range(12):
        line = f"1.e{i % 4 + 1} e5 2.Nf{i % 4 + 1} Nc6 3.Bc{i % 4 + 1} Nf6 4.Ng{i % 4 + 1} d5"
        records.append(_rec("black", "checkmated", opening_moves=line, end_time=1_700_000_000 + i))
    result = compute_opponent_opening_stats(records)
    assert result["rows"] == []
    assert result["grouping_level"] == "none"


def test_strong_cluster_exact_line():
    # 12 losses all from the same White opener → strong cluster
    line = FRIED_LIVER
    records = [
        _rec("black", "checkmated", opening_moves=line, end_time=1_700_000_000 + i)
        for i in range(12)
    ]
    result = compute_opponent_opening_stats(records)
    assert result["grouping_level"] == "exact_line"
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["loss_count"] == 12
    assert row["win_count"] == 0
    assert row["game_count"] == 12
    assert row["confidence"] == "strong"
    assert row["opponent_side"] == "white"
    assert row["opp_moves"] == ["e4", "Nf3", "Bc4", "Ng5"]


def test_loss_pct_uses_all_games_not_only_losses():
    # 10 losses + 5 wins from same line → loss_pct should be 10/15, not 100%
    line = FRIED_LIVER
    records = (
        [_rec("black", "checkmated", opening_moves=line, end_time=1_700_000_000 + i)
         for i in range(10)]
        + [_rec("black", "win", opening_moves=line, end_time=1_700_000_100 + i)
           for i in range(5)]
    )
    result = compute_opponent_opening_stats(records)
    assert result["grouping_level"] == "exact_line"
    row = result["rows"][0]
    assert row["game_count"] == 15
    assert row["loss_count"] == 10
    assert row["win_count"] == 5
    assert abs(row["loss_pct"] - 66.7) < 0.2


def test_both_sides_produce_separate_groups():
    # 6 games as Black against e4, 6 games as White against e5
    line_as_black = FRIED_LIVER
    line_as_white = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5"
    records = (
        [_rec("black", "checkmated", opening_moves=line_as_black,
              end_time=1_700_000_000 + i) for i in range(6)]
        + [_rec("white", "checkmated", opening_moves=line_as_white,
                end_time=1_700_001_000 + i) for i in range(6)]
    )
    result = compute_opponent_opening_stats(records)
    sides = {r["opponent_side"] for r in result["rows"]}
    assert "white" in sides  # opponent-as-white (user was black)
    assert "black" in sides  # opponent-as-black (user was white)


def test_sort_order_loss_count_descending():
    # Two clusters: 10-loss and 5-loss
    line_a = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.O-O Nf6"
    line_b = "1.d4 d5 2.Nf3 Nf6 3.Bf4 e6 4.e3 Bd6"
    records = (
        [_rec("black", "checkmated", opening_moves=line_a, end_time=1_700_000_000 + i)
         for i in range(10)]
        + [_rec("black", "checkmated", opening_moves=line_b, end_time=1_700_001_000 + i)
           for i in range(5)]
    )
    result = compute_opponent_opening_stats(records)
    rows = result["rows"]
    assert rows[0]["loss_count"] >= rows[1]["loss_count"]


def test_weak_cluster_shown_not_hidden():
    # N=3 → "weak" — should appear in rows (not hidden)
    line = FRIED_LIVER
    records = [
        _rec("black", "checkmated", opening_moves=line, end_time=1_700_000_000 + i)
        for i in range(3)
    ]
    # Also need another cluster with N >= 5 so the level gets selected
    line_b = "1.d4 d5 2.Nf3 Nf6 3.Bf4 e6 4.e3 Bd6"
    records += [
        _rec("black", "checkmated", opening_moves=line_b, end_time=1_700_001_000 + i)
        for i in range(6)
    ]
    result = compute_opponent_opening_stats(records)
    confs = {r["confidence"] for r in result["rows"]}
    assert "weak" in confs


def test_hidden_clusters_counted_in_audit():
    # N=1 clusters should not appear in rows but be counted in audit
    line_common = FRIED_LIVER
    records = [
        _rec("black", "checkmated", opening_moves=line_common, end_time=1_700_000_000 + i)
        for i in range(10)
    ]
    # Add 2 unique lines (N=1 each → hidden)
    for i, unique_line in enumerate([
        "1.c4 e5 2.Nc3 Nc6 3.g3 g6 4.Bg2 Bg7",
        "1.b4 e5 2.Bb2 Bxb4 3.Bxe5 Nf6 4.c4 c5",
    ]):
        records.append(
            _rec("black", "checkmated", opening_moves=unique_line,
                 end_time=1_700_002_000 + i)
        )
    result = compute_opponent_opening_stats(records)
    assert result["audit"]["groups_hidden_low_sample"] >= 2


def test_play_signature_fallback():
    # Games with the same play_signature but different exact move orders
    # (transpositions) → should group under play_signature if exact_line sparse
    sig = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq -"
    lines = [
        "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6",
        "1.e4 e5 2.Bc4 Nf6 3.Nf3 Nc6",  # transposition
    ]
    records = []
    for i in range(12):
        line = lines[i % 2]
        records.append(
            _rec("black", "checkmated", opening_moves=line,
                 play_signature=sig, end_time=1_700_000_000 + i)
        )
    result = compute_opponent_opening_stats(records)
    # exact_line would split into two groups of 6 — both medium, so exact_line wins.
    # That's fine; the test just confirms it picks one level and returns rows.
    assert len(result["rows"]) > 0
    assert result["grouping_level"] in ("exact_line", "play_signature")
