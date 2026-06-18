"""Tests for chess_tracker.trap_patterns."""
import pytest
from chess_tracker.pgn import GameRecord
from chess_tracker.trap_patterns import detect_traps, compute_trap_exposures


def _rec(side, result, opening_moves=None, end_time=1_700_000_000):
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
        opening=None,
        eco=None,
        opening_moves=opening_moves,
        play_signature=None,
    )


FRIED_LIVER = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7 Kxf7"
SCHOLARS_MATE = "1.e4 e5 2.Bc4 Nc6 3.Qh5 a6 4.Qxf7"
HALLOWEEN = "1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Nxe5 Nxe5"
BELGRADE = "1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.d4 exd4 5.Nd5"
BUDAPEST = "1.d4 Nf6 2.c4 e5 3.dxe5 Ne4 4.Nf3"
ENGLUND = "1.d4 e5 2.dxe5 Nc6 3.Nf3 Qe7"
FOOLS = "1.f3 e5 2.g4 Qh4"


# ---------------------------------------------------------------------------
# detect_traps
# ---------------------------------------------------------------------------

def test_fried_liver_fires_for_black_user():
    hits = detect_traps(FRIED_LIVER, "black", "checkmated")
    assert "fried_liver_attack" in hits


def test_fried_liver_does_not_fire_for_white_user():
    hits = detect_traps(FRIED_LIVER, "white", "checkmated")
    assert "fried_liver_attack" not in hits


def test_scholars_mate_fires_for_black_user():
    hits = detect_traps(SCHOLARS_MATE, "black", "checkmated")
    assert "scholars_mate" in hits


def test_scholars_mate_does_not_fire_for_white_user():
    hits = detect_traps(SCHOLARS_MATE, "white", "checkmated")
    assert "scholars_mate" not in hits


def test_halloween_gambit_fires():
    hits = detect_traps(HALLOWEEN, "black", "checkmated")
    assert "halloween_gambit" in hits


def test_belgrade_gambit_fires():
    hits = detect_traps(BELGRADE, "black", "checkmated")
    assert "belgrade_gambit" in hits


def test_budapest_gambit_fires_for_white_user():
    hits = detect_traps(BUDAPEST, "white", "checkmated")
    assert "budapest_gambit" in hits


def test_budapest_gambit_does_not_fire_for_black_user():
    hits = detect_traps(BUDAPEST, "black", "checkmated")
    assert "budapest_gambit" not in hits


def test_englund_gambit_fires_for_white_user():
    hits = detect_traps(ENGLUND, "white", "checkmated")
    assert "englund_gambit" in hits


def test_fools_mate_fires_only_on_win():
    assert "fools_mate" in detect_traps(FOOLS, "black", "win")
    assert "fools_mate" not in detect_traps(FOOLS, "black", "checkmated")


def test_null_opening_returns_empty():
    assert detect_traps(None, "black", "checkmated") == []


def test_empty_string_returns_empty():
    assert detect_traps("", "black", "checkmated") == []


def test_partial_sequence_does_not_fire():
    # Only Nf3 + Bc4, no Ng5 yet — Fried Liver should not fire
    partial = "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6"
    assert "fried_liver_attack" not in detect_traps(partial, "black", "checkmated")


def test_annotation_noise_stripped():
    # Checks and capture marks should be normalized away
    noisy = "1.e4 e5 2.Nf3+ Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5+ Nxd5 6.Nxf7# Kxf7"
    assert "fried_liver_attack" in detect_traps(noisy, "black", "checkmated")


def test_one_hit_per_pattern_per_game():
    # Even if line somehow matches twice, only one hit per pattern
    hits = detect_traps(FRIED_LIVER, "black", "checkmated")
    assert hits.count("fried_liver_attack") == 1


# ---------------------------------------------------------------------------
# compute_trap_exposures
# ---------------------------------------------------------------------------

def test_empty_records():
    result = compute_trap_exposures([])
    assert result["trap_exposures"] == []
    assert result["trap_exposure_audit"]["games_scanned"] == 0


def test_strong_cluster_fried_liver():
    records = [
        _rec("black", "checkmated", opening_moves=FRIED_LIVER,
             end_time=1_700_000_000 + i)
        for i in range(10)
    ]
    result = compute_trap_exposures(records)
    fl = next(r for r in result["trap_exposures"] if r["id"] == "fried_liver_attack")
    assert fl["hit_count"] == 10
    assert fl["loss_count"] == 10
    assert fl["confidence"] == "strong"


def test_hidden_below_threshold():
    # Only 2 hits — below N=3 threshold, should not appear in trap_exposures
    records = [
        _rec("black", "checkmated", opening_moves=SCHOLARS_MATE,
             end_time=1_700_000_000 + i)
        for i in range(2)
    ]
    result = compute_trap_exposures(records)
    ids = [r["id"] for r in result["trap_exposures"]]
    assert "scholars_mate" not in ids


def test_audit_games_scanned():
    records = [_rec("black", "checkmated", end_time=1_700_000_000 + i) for i in range(5)]
    result = compute_trap_exposures(records)
    assert result["trap_exposure_audit"]["games_scanned"] == 5


def test_loss_pct_correct():
    # 8 losses + 2 wins from Fried Liver
    records = (
        [_rec("black", "checkmated", opening_moves=FRIED_LIVER,
              end_time=1_700_000_000 + i) for i in range(8)]
        + [_rec("black", "win", opening_moves=FRIED_LIVER,
                end_time=1_700_001_000 + i) for i in range(2)]
    )
    result = compute_trap_exposures(records)
    fl = next(r for r in result["trap_exposures"] if r["id"] == "fried_liver_attack")
    assert fl["hit_count"] == 10
    assert fl["loss_count"] == 8
    assert abs(fl["loss_pct"] - 80.0) < 0.1


def test_sort_order_loss_count_desc():
    records = (
        [_rec("black", "checkmated", opening_moves=FRIED_LIVER,
              end_time=1_700_000_000 + i) for i in range(8)]
        + [_rec("black", "checkmated", opening_moves=SCHOLARS_MATE,
                end_time=1_700_001_000 + i) for i in range(5)]
    )
    result = compute_trap_exposures(records)
    rows = result["trap_exposures"]
    assert rows[0]["loss_count"] >= rows[1]["loss_count"]
