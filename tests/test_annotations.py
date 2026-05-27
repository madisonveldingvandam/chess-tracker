import json
from chess_tracker.annotations import load_annotations, save_annotations, default_annotations


def test_default_annotations_has_three_sections():
    d = default_annotations()
    assert set(d.keys()) == {"openings", "games", "error_log"}
    assert d["openings"] == {}
    assert d["games"] == {}
    assert d["error_log"] == []


def test_load_creates_default_when_missing(tmp_path):
    path = tmp_path / "annotations.json"
    data = load_annotations(path)
    assert data == default_annotations()


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "annotations.json"
    payload = {
        "openings": {"Petrovs Defense": {"tag": "in_repertoire", "note": "main"}},
        "games": {},
        "error_log": [{"id": "err-001", "title": "queen blunders"}],
    }
    save_annotations(path, payload)
    assert load_annotations(path) == payload


def test_load_validates_structure(tmp_path):
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps({"openings": {}}))  # missing keys
    data = load_annotations(path)
    # Missing sections must be backfilled with defaults
    assert "games" in data
    assert "error_log" in data
    assert data["error_log"] == []
