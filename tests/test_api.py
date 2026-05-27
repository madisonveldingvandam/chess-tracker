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


def test_fetch_archive_caches_to_disk(tmp_path):
    url = "https://api.chess.com/pub/player/m_v-v/games/2025/01"
    payload = {"games": [{"uuid": "abc", "time_class": "bullet"}]}

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__.return_value = mock_resp

    from chess_tracker.api import fetch_archive

    with patch("chess_tracker.api.urlopen", return_value=mock_resp) as m:
        result1 = fetch_archive(url, cache_dir=tmp_path)
        result2 = fetch_archive(url, cache_dir=tmp_path)  # second call: cached

    assert result1 == payload
    assert result2 == payload
    assert m.call_count == 1  # only fetched once

    cache_file = tmp_path / "2025-01.json"
    assert cache_file.exists()


def test_fetch_archive_force_bypasses_cache(tmp_path):
    url = "https://api.chess.com/pub/player/m_v-v/games/2025/01"
    payload = {"games": []}

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__.return_value = mock_resp

    from chess_tracker.api import fetch_archive

    with patch("chess_tracker.api.urlopen", return_value=mock_resp) as m:
        fetch_archive(url, cache_dir=tmp_path)
        fetch_archive(url, cache_dir=tmp_path, force=True)

    assert m.call_count == 2
