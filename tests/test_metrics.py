"""Tests for metric computations."""
from tests.fixtures.sample_records import RECORDS
from chess_tracker.metrics import compute_kpis, compute_sessions, compute_repertoire


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
