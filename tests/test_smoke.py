"""Smoke tests: render pipeline produces valid HTML with required fields."""
import json
import tempfile
from pathlib import Path

from chess_tracker.render import render_dashboard, DEFAULT_TEMPLATE_PATH

_MINIMAL_PAYLOAD = {
    "username": "test_user",
    "format": "bullet",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "kpis": {
        "current_rating": 500,
        "games_total": 10,
        "recent_form_win_pct": 40.0,
        "tilt": "yellow",
    },
    "leak_summary": [],
    "recent_losses": [],
    "review_picks": [],
    "process_metrics": {
        "reserve_move_10_median": None,
        "reserve_move_20_median": None,
        "opening_velocity_median": None,
        "time_burn_delta": None,
        "outlasted_but_flagged_count": 0,
        "session_decay": [],
    },
    "opening_families": [],
    "opening_variations": [],
    "play_signatures": [],
    "sessions": [],
    "behavior": {
        "loss_streaks": {},
        "revenge_gap": {},
        "daily_drawdown": [],
        "time_of_day": [],
        "mate_loss_buckets": [],
    },
    "error_log": [],
    "plan_compliance": {"openings": [], "window": 30},
    "move_quality": None,
    "move_quality_by_format": None,
}


def test_render_dashboard_produces_html_file():
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out = Path(f.name)
    render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
    assert out.exists()
    content = out.read_text()
    assert len(content) > 100
    out.unlink()


def test_render_dashboard_injects_window_data():
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out = Path(f.name)
    render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
    content = out.read_text()
    assert "window.DATA" in content
    out.unlink()


def test_render_dashboard_username_substituted():
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out = Path(f.name)
    render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
    content = out.read_text()
    assert "test_user" in content
    assert "{{USERNAME}}" not in content
    out.unlink()


def test_render_dashboard_required_keys_present_in_embedded_data():
    """All dashboard panels depend on these top-level keys existing."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out = Path(f.name)
    render_dashboard(DEFAULT_TEMPLATE_PATH, out, _MINIMAL_PAYLOAD)
    content = out.read_text()
    # Extract the embedded JSON by finding window.DATA = {...};
    start = content.index("window.DATA = ") + len("window.DATA = ")
    end = content.index(";\n", start)
    raw = content[start:end].replace("\\/", "/")
    data = json.loads(raw)
    for key in ("kpis", "leak_summary", "recent_losses",
                "process_metrics", "opening_families", "sessions"):
        assert key in data, f"Missing required key: {key}"
    out.unlink()
