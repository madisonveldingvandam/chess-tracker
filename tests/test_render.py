# tests/test_render.py
from pathlib import Path
from chess_tracker.render import render_dashboard


def test_render_dashboard_injects_data_and_substitutes_username(tmp_path):
    template = tmp_path / "index.html"
    template.write_text(
        "<title>Chess Tracker — {{USERNAME}}</title>"
        "<script>/* DATA_INJECTION_POINT */</script>"
    )
    out = tmp_path / "out.html"
    payload = {"username": "alice", "kpis": {"current_rating": 444}}
    render_dashboard(template_path=template, output_path=out, payload=payload)
    html = out.read_text()
    assert "Chess Tracker — alice" in html
    assert "window.DATA =" in html
    assert "/* DATA_INJECTION_POINT */" not in html
    assert "alice" in html


def test_render_escapes_closing_script_in_payload(tmp_path):
    template = tmp_path / "index.html"
    template.write_text("<script>/* DATA_INJECTION_POINT */</script>")
    out = tmp_path / "out.html"
    # Payload contains "</script>" which would break out of the tag if unescaped
    payload = {"username": "x", "evil": "</script><b>oh no</b>"}
    render_dashboard(template_path=template, output_path=out, payload=payload)
    html = out.read_text()
    assert "</script><b>oh no</b>" not in html  # the literal substring is escaped
