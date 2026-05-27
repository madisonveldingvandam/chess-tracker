# tests/test_refresh.py
import json
from unittest.mock import patch, MagicMock
import refresh


def test_refresh_main_writes_computed_and_dashboard(tmp_path, monkeypatch):
    archives_index = {"archives": [
        "https://api.chess.com/pub/player/m_v-v/games/2026/05"
    ]}
    sample_game = {
        "url": "x", "end_time": 1_700_000_000, "time_class": "bullet",
        "white": {"username": "m_v-v", "rating": 500, "result": "win"},
        "black": {"username": "opp", "rating": 500, "result": "timeout"},
        "pgn": "[ECO \"A00\"]\n1. e4 {[%clk 0:00:59]} e5 {[%clk 0:00:59]}",
    }
    archive = {"games": [sample_game]}

    def fake_urlopen(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else req
        mock = MagicMock()
        if url.endswith("/archives"):
            mock.read.return_value = json.dumps(archives_index).encode()
        else:
            mock.read.return_value = json.dumps(archive).encode()
        mock.__enter__.return_value = mock
        return mock

    monkeypatch.chdir(tmp_path)

    with patch("chess_tracker.api.urlopen", side_effect=fake_urlopen):
        refresh.main(["--username", "m_v-v"])

    assert (tmp_path / "data" / "computed.json").exists()
    for name in ["index", "leaks", "losses", "process", "sessions"]:
        out = tmp_path / "dashboard" / f"{name}.html"
        assert out.exists(), f"missing {name}.html"
        html = out.read_text()
        assert "window.DATA" in html
