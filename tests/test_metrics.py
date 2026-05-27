"""Tests for metric computations."""
from tests.fixtures.sample_records import RECORDS, CLOCK_RECORDS, OUTLASTED_THEN_FLAG_RECORD
from chess_tracker.metrics import compute_kpis, compute_sessions, compute_repertoire, compute_process_metrics, compute_session_decay


def test_compute_kpis_current_rating_is_last_games():
    kpis = compute_kpis(RECORDS)
    assert kpis["current_rating"] == 485  # rating of last game


def test_compute_kpis_recent_form_counts_last_five():
    kpis = compute_kpis(RECORDS)
    # last 5: W=2 (games 0, 5 ... actually last 5 are records[1:6])
    # records[1]=L, [2]=W, [3]=L, [4]=L, [5]=W → 2W/3L → 40%
    assert kpis["recent_form_win_pct"] == 40.0
    assert kpis["tilt"] == "yellow"  # 40 ≤ win% < 60


def test_compute_sessions_detects_gaps():
    sessions = compute_sessions(RECORDS, gap_seconds=600)
    assert len(sessions) == 3
    assert sessions[0]["games"] == 3
    assert sessions[1]["games"] == 2
    assert sessions[2]["games"] == 1


def test_compute_sessions_tracks_rating_delta():
    sessions = compute_sessions(RECORDS, gap_seconds=600)
    # Session 1: started 500, ended 510
    assert sessions[0]["rating_start"] == 500
    assert sessions[0]["rating_end"] == 510
    assert sessions[0]["rating_delta"] == 10


def test_compute_sessions_flags_tilt_when_drop_50_or_more():
    sessions = compute_sessions(RECORDS, gap_seconds=600)
    # No session here has -50, but the flag must exist
    for s in sessions:
        assert "tilt_flag" in s
        assert s["tilt_flag"] == (s["rating_delta"] <= -50)


def test_compute_repertoire_groups_by_opening_and_color():
    rep = compute_repertoire(RECORDS)
    # 3 distinct (opening, color) keys: London/white, Petrovs/black, Italian/black
    # Actually: London(white) x3, Petrovs(black) x1, Italian(black) x2
    by_key = {(r["opening"], r["color"]): r for r in rep}
    assert by_key[("London System", "white")]["games"] == 3
    assert by_key[("Italian Game", "black")]["games"] == 2
    assert by_key[("Petrovs Defense", "black")]["games"] == 1


def test_compute_repertoire_calculates_win_pct():
    rep = compute_repertoire(RECORDS)
    by_key = {(r["opening"], r["color"]): r for r in rep}
    london = by_key[("London System", "white")]
    # London games: 1W, 1L (checkmated), 1W → 2W/3 = 66.7%
    assert london["wins"] == 2
    assert london["losses"] == 1
    assert london["win_pct"] == round(200/3, 1)


def test_compute_repertoire_includes_loss_type_breakdown():
    rep = compute_repertoire(RECORDS)
    by_key = {(r["opening"], r["color"]): r for r in rep}
    italian = by_key[("Italian Game", "black")]
    # 1 timeout, 1 checkmated → flag_pct 50%, mate_pct 50%
    assert italian["flag_pct"] == 50.0
    assert italian["mate_pct"] == 50.0


def test_compute_repertoire_includes_recent_form_sparkline():
    rep = compute_repertoire(RECORDS)
    by_key = {(r["opening"], r["color"]): r for r in rep}
    london = by_key[("London System", "white")]
    # form: oldest→newest, "W"|"L"|"D"
    assert london["form"] == ["W", "L", "W"]


def test_compute_process_metrics_returns_required_keys():
    pm = compute_process_metrics(CLOCK_RECORDS)
    assert set(pm.keys()) >= {
        "reserve_move_10_median",
        "reserve_move_20_median",
        "opening_velocity_median",
        "time_burn_delta",
        "outlasted_but_flagged_count",
    }


def test_opening_velocity_reflects_first_8_plies():
    """Fast opener uses 4s on first 8 of-my-moves; slow opener uses 24s."""
    fast_only = [CLOCK_RECORDS[0], CLOCK_RECORDS[2]]  # both fast
    slow_only = [CLOCK_RECORDS[1]]
    fast_vel = compute_process_metrics(fast_only)["opening_velocity_median"]
    slow_vel = compute_process_metrics(slow_only)["opening_velocity_median"]
    assert fast_vel < slow_vel
    assert abs(fast_vel - 4.0) < 0.5
    assert abs(slow_vel - 24.0) < 0.5


def test_outlasted_but_flagged_counts_a_timeout_where_you_were_ahead_at_some_ply():
    """Timeout-loss where you had more time than opponent at some recorded ply."""
    pm = compute_process_metrics([OUTLASTED_THEN_FLAG_RECORD])
    assert pm["outlasted_but_flagged_count"] == 1


def test_outlasted_but_flagged_excludes_timeouts_where_you_were_always_behind():
    """Slow-opener timeout where opp had more time at every ply — not outlasted."""
    # CLOCK_RECORDS[1] is the slow-opener-mine vs fast-opener-opp timeout
    pm = compute_process_metrics([CLOCK_RECORDS[1]])
    assert pm["outlasted_but_flagged_count"] == 0


def test_time_burn_delta_is_positive_when_slow_opening():
    """Slow opener: 3s/move early, 1s/move late → delta = +2.0 exactly."""
    pm = compute_process_metrics([CLOCK_RECORDS[1]])
    assert pm["time_burn_delta"] is not None
    assert abs(pm["time_burn_delta"] - 2.0) < 0.1


def test_time_burn_delta_is_negative_when_fast_opening():
    """Fast opener: 0.5s/move early, 1.5s/move late → delta = -1.0 exactly."""
    pm = compute_process_metrics([CLOCK_RECORDS[0]])
    assert pm["time_burn_delta"] is not None
    assert abs(pm["time_burn_delta"] - (-1.0)) < 0.1


def test_compute_session_decay_returns_buckets():
    decay = compute_session_decay(RECORDS, gap_seconds=600)
    by_bucket = {row["bucket"]: row for row in decay}
    assert set(by_bucket.keys()) == {"1-5", "6-10", "11-20", "21+"}
    # Each row has the same keys as a generic stats row
    for row in decay:
        assert {"games", "win_pct", "flag_pct", "mate_pct"} <= set(row.keys())


from chess_tracker.metrics import _post_peak_decay


def _decay(rows):
    """Build a decay-bucket list from terse (bucket, games, win_pct) triples."""
    return [{"bucket": b, "games": g, "win_pct": w,
             "flag_pct": 0.0, "mate_pct": 0.0} for b, g, w in rows]


def test_post_peak_decay_fires_when_peak_crashes_to_last():
    decay = _decay([
        ("1-5",   5, 40.0),
        ("6-10",  5, 50.0),
        ("11-20", 10, 80.0),
        ("21+",   5, 20.0),
    ])
    fired, peak, last = _post_peak_decay(decay)
    assert fired is True
    assert peak["bucket"] == "11-20"
    assert last["bucket"] == "21+"


def test_post_peak_decay_does_not_fire_on_monotonic_increase():
    decay = _decay([
        ("1-5",   5, 20.0),
        ("6-10",  5, 40.0),
        ("11-20", 5, 60.0),
        ("21+",   5, 80.0),
    ])
    fired, _peak, _last = _post_peak_decay(decay)
    assert fired is False


def test_post_peak_decay_does_not_fire_when_drop_below_threshold():
    decay = _decay([
        ("1-5",   5, 60.0),
        ("6-10",  5, 70.0),
        ("11-20", 5, 80.0),
        ("21+",   5, 75.0),  # peak=80, last=75, drop=5pp < 10pp
    ])
    fired, _peak, _last = _post_peak_decay(decay)
    assert fired is False


def test_post_peak_decay_excludes_peak_bucket_with_too_few_games():
    # 11-20 would be the peak by win_pct, but has only 4 games -> ineligible.
    # Eligible buckets: 1-5 (60%) and 21+ (20%). Peak=1-5, last=21+, drop=40pp.
    decay = _decay([
        ("1-5",   5, 60.0),
        ("6-10",  4, 55.0),
        ("11-20", 4, 95.0),  # ineligible
        ("21+",   5, 20.0),
    ])
    fired, peak, last = _post_peak_decay(decay)
    assert fired is True  # still fires, but with a different peak
    assert peak["bucket"] == "1-5"
    assert last["bucket"] == "21+"


def test_post_peak_decay_does_not_fire_when_last_bucket_has_too_few_games():
    # 21+ has only 4 games -> ineligible. With 1-5, 6-10, 11-20 all eligible
    # at >=5 games and 11-20 having the highest win%, peak == last == 11-20
    # -> no fire even though 21+ visibly crashed.
    decay = _decay([
        ("1-5",   5, 40.0),
        ("6-10",  10, 60.0),
        ("11-20", 10, 80.0),
        ("21+",   4, 10.0),
    ])
    fired, _peak, _last = _post_peak_decay(decay)
    assert fired is False


def test_post_peak_decay_tie_break_picks_later_bucket():
    # 6-10 and 11-20 tied at 70%. Tie-break: later (11-20) wins as peak.
    decay = _decay([
        ("1-5",   5, 40.0),
        ("6-10",  5, 70.0),
        ("11-20", 5, 70.0),
        ("21+",   5, 30.0),
    ])
    fired, peak, last = _post_peak_decay(decay)
    assert fired is True
    assert peak["bucket"] == "11-20"
    assert last["bucket"] == "21+"


from chess_tracker.metrics import (
    detect_leaks, next_session_rule, recent_losses_with_suggestions
)


def test_detect_leaks_returns_rows_with_required_fields():
    leaks = detect_leaks(RECORDS + CLOCK_RECORDS)
    for leak in leaks:
        assert set(leak.keys()) >= {"name", "severity", "evidence", "suggested_action"}
        assert leak["severity"] in ("info", "warn", "critical")


def test_detect_leaks_flags_slow_opening_when_velocity_high():
    # CLOCK_RECORDS has slow openers spending 24s on first 8 of-my-moves
    leaks = detect_leaks([CLOCK_RECORDS[1]])
    names = [l["name"] for l in leaks]
    assert "time_burn_opening" in names


def test_next_session_rule_has_three_fields_plus_narrative():
    rule = next_session_rule(RECORDS + CLOCK_RECORDS)
    assert set(rule.keys()) == {"game_cap", "move_10_target_seconds",
                                 "stop_if_rating_drops", "narrative"}
    assert isinstance(rule["narrative"], str) and len(rule["narrative"]) > 10


def test_recent_losses_includes_suggested_entry():
    losses = recent_losses_with_suggestions(RECORDS, limit=10)
    for L in losses:
        assert "game_url" in L
        assert "loss_type" in L
        assert "suggested_entry" in L
        # Suggested entry is a dict that maps onto annotations.json error_log shape
        assert {"title", "pattern", "game_refs"} <= set(L["suggested_entry"].keys())


from chess_tracker.metrics import compute_all


def test_compute_all_has_new_panel_keys():
    annotations = {
        "openings": {"London System": {"tag": "in_repertoire", "note": "main"}},
        "games": {},
        "error_log": [],
    }
    payload = compute_all(RECORDS + CLOCK_RECORDS, annotations,
                          username="m_v-v", format="bullet")
    expected = {
        "username", "format", "generated_at",
        "kpis", "leak_summary", "next_session_rule",
        "recent_losses", "process_metrics",
        "play_signatures", "sessions", "error_log",
    }
    assert expected <= set(payload.keys())


def test_compute_all_play_signatures_has_low_confidence_flag():
    annotations = {"openings": {}, "games": {}, "error_log": []}
    payload = compute_all(RECORDS, annotations, username="m_v-v")
    for row in payload["play_signatures"]:
        assert "low_confidence" in row
        assert row["low_confidence"] == (row["games"] < 15)


def test_compute_all_merges_opening_annotations():
    annotations = {
        "openings": {"London System": {"tag": "in_repertoire", "note": "main d4"}},
        "games": {}, "error_log": [],
    }
    payload = compute_all(RECORDS, annotations, username="m_v-v")
    london = next(r for r in payload["play_signatures"]
                  if r["display_name"] == "London System")
    assert london["tag"] == "in_repertoire"
    assert london["note"] == "main d4"
