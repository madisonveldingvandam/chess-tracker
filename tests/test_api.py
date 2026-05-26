from unittest.mock import patch, MagicMock
import json
from chess_tracker.api import fetch_archives_index


def test_fetch_archives_index_returns_list_of_urls():
    fake_response = json.dumps({
        "archives": [
            "https://api.chess.com/pub/player/m_v-v/games/2026/04",
            "https://api.chess.com/pub/player/m_v-v/games/2026/05",
        ]
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response
    mock_resp.__enter__.return_value = mock_resp

    with patch("chess_tracker.api.urlopen", return_value=mock_resp):
        urls = fetch_archives_index("m_v-v")

    assert len(urls) == 2
    assert urls[0].endswith("/2026/04")
    assert urls[1].endswith("/2026/05")
