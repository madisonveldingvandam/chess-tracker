"""Read/write the user-owned annotations.json sidecar."""
import json
from pathlib import Path


def default_annotations() -> dict:
    return {"openings": {}, "games": {}, "error_log": []}


def load_annotations(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return default_annotations()
    data = json.loads(path.read_text())
    # Backfill missing sections
    for k, v in default_annotations().items():
        data.setdefault(k, v)
    return data


def save_annotations(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
