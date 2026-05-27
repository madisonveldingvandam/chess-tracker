# chess_tracker/render.py
"""Render dashboard HTML by injecting computed JSON into a template."""
import json
from pathlib import Path

INJECT_MARKER = "/* DATA_INJECTION_POINT */"
DEFAULT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


def _safe_json(payload: dict) -> str:
    """Serialize for inline <script> embedding.

    Escapes </script> sequences which would otherwise break out of the tag.
    """
    raw = json.dumps(payload, indent=2)
    return raw.replace("</", "<\\/")


def render_dashboard(template_path: Path, output_path: Path, payload: dict) -> None:
    template_path = Path(template_path)
    output_path = Path(output_path)
    html = template_path.read_text()
    username = payload.get("username", "")
    html = html.replace("{{USERNAME}}", username)
    embed = f"const DATA = {_safe_json(payload)};"
    html = html.replace(INJECT_MARKER, embed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
