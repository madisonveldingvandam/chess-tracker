"""Load the user's strategy plan (openings) from plan.json."""
import json
from pathlib import Path

DEFAULT_PLAN_PATH = Path(__file__).parent / "plan.json"


def load_plan(path: Path | str = DEFAULT_PLAN_PATH) -> dict:
    """Read plan.json. Returns {"openings": []} if missing.

    The plan is in-repo config (chess_tracker/plan.json), not user-runtime
    state — edit it directly when your strategy changes. Missing-file fallback
    keeps compute_all working in test fixtures that don't ship a plan.
    """
    path = Path(path)
    if not path.exists():
        return {"openings": []}
    return json.loads(path.read_text())
