"""Tests for chess_tracker.blunder_phases."""
import pytest
from chess_tracker.blunder_phases import compute_blunder_phases


def _summary(opening_blunders=0, middlegame_blunders=0,
             opening_moves=10, middlegame_moves=15,
             opening_cp_sum=0, middlegame_cp_sum=0,
             opening_worst=0, middlegame_worst=0):
    """Build a minimal per-game summary dict."""
    mbp = {}
    if opening_moves:
        mbp["opening"] = opening_moves
    if middlegame_moves:
        mbp["middlegame"] = middlegame_moves

    bbp = {}
    cs = {}
    cw = {}
    if opening_blunders:
        bbp["opening"] = opening_blunders
        cs["opening"] = opening_cp_sum
        cw["opening"] = opening_worst
    if middlegame_blunders:
        bbp["middlegame"] = middlegame_blunders
        cs["middlegame"] = middlegame_cp_sum
        cw["middlegame"] = middlegame_worst

    return {
        "moves_analyzed": opening_moves + middlegame_moves,
        "moves_by_phase": mbp,
        "blunders_by_phase": bbp,
        "blunder_cp_sum_by_phase": cs,
        "blunder_worst_cp_by_phase": cw,
    }


def test_empty_summaries():
    result = compute_blunder_phases([], total_eligible=100)
    bp = result["blunder_phases"]
    assert bp["opening"]["blunder_count"] == 0
    assert bp["early_middlegame"]["blunder_count"] == 0
    assert result["engine_coverage"]["analyzed_games"] == 0
    assert result["engine_coverage"]["eligible_games"] == 100


def test_blunder_counts_aggregate():
    summaries = [
        _summary(opening_blunders=2, middlegame_blunders=3,
                 opening_cp_sum=400, middlegame_cp_sum=600,
                 opening_worst=250, middlegame_worst=300),
        _summary(opening_blunders=1, middlegame_blunders=0,
                 opening_cp_sum=180, opening_worst=180),
    ]
    result = compute_blunder_phases(summaries, total_eligible=50)
    bp = result["blunder_phases"]
    assert bp["opening"]["blunder_count"] == 3
    assert bp["early_middlegame"]["blunder_count"] == 3
    assert bp["opening"]["affected_games"] == 2
    assert bp["early_middlegame"]["affected_games"] == 1


def test_phase_eligible_games():
    # Game 1: has opening + middlegame moves
    # Game 2: only opening moves (too short for middlegame)
    summaries = [
        _summary(opening_moves=10, middlegame_moves=15),
        _summary(opening_moves=8, middlegame_moves=0),
    ]
    result = compute_blunder_phases(summaries, total_eligible=5)
    bp = result["blunder_phases"]
    assert bp["opening"]["phase_eligible_games"] == 2
    assert bp["early_middlegame"]["phase_eligible_games"] == 1


def test_blunder_rate_computed():
    summaries = [_summary(opening_blunders=1, opening_moves=20,
                          opening_cp_sum=200, opening_worst=200)]
    result = compute_blunder_phases(summaries, total_eligible=10)
    bp = result["blunder_phases"]
    assert abs(bp["opening"]["blunder_rate"] - 1 / 20) < 0.001


def test_avg_loss_cp():
    # 2 blunders, cp_sum = 300 → avg = 150
    summaries = [_summary(opening_blunders=2, opening_moves=10,
                          opening_cp_sum=300, opening_worst=200)]
    bp = compute_blunder_phases(summaries, total_eligible=10)["blunder_phases"]
    assert bp["opening"]["avg_loss_cp"] == 150


def test_worst_single_loss_cp():
    summaries = [
        _summary(opening_blunders=1, opening_moves=10,
                 opening_cp_sum=300, opening_worst=300),
        _summary(opening_blunders=1, opening_moves=10,
                 opening_cp_sum=500, opening_worst=500),
    ]
    bp = compute_blunder_phases(summaries, total_eligible=10)["blunder_phases"]
    assert bp["opening"]["worst_single_loss_cp"] == 500


def test_no_blunders_null_avg():
    summaries = [_summary(opening_moves=10, middlegame_moves=15)]
    bp = compute_blunder_phases(summaries, total_eligible=5)["blunder_phases"]
    assert bp["opening"]["avg_loss_cp"] is None
    assert bp["opening"]["worst_single_loss_cp"] is None


def test_engine_coverage():
    summaries = [_summary() for _ in range(7)]
    result = compute_blunder_phases(summaries, total_eligible=20)
    assert result["engine_coverage"]["analyzed_games"] == 7
    assert result["engine_coverage"]["eligible_games"] == 20


def test_missing_blunder_fields_graceful():
    # Old-format summary without blunder_by_phase keys
    summary = {"moves_analyzed": 10, "moves_by_phase": {"opening": 10}}
    result = compute_blunder_phases([summary], total_eligible=5)
    bp = result["blunder_phases"]
    assert bp["opening"]["blunder_count"] == 0
