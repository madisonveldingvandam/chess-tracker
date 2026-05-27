"""CLI: pull Chess.com archives → compute metrics → render dashboard."""
import argparse
import json
import sys
from pathlib import Path

from chess_tracker.api import fetch_archives_index, fetch_archive
from chess_tracker.pgn import parse_game
from chess_tracker.metrics import compute_all
from chess_tracker.annotations import load_annotations
from chess_tracker.render import render_all_pages, DEFAULT_TEMPLATE_DIR


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh chess tracker dashboard.")
    ap.add_argument("--username", default="M_V-V")
    ap.add_argument("--format", default="bullet", choices=["bullet"])
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch all archives, not just current month.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--dashboard-dir", default="dashboard")
    ap.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR))
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw"
    dashboard_dir = Path(args.dashboard_dir)
    template_dir = Path(args.template_dir)
    annotations_path = data_dir / "annotations.json"

    print(f"[1/5] Loading archives index for {args.username}...")
    archives = fetch_archives_index(args.username)
    print(f"      {len(archives)} archive(s)")

    print(f"[2/5] Fetching archives (force={args.force})...")
    all_games = []
    # Assumes /archives returns months chronologically, oldest first (Chess.com behaviour).
    current_month_url = archives[-1] if archives else None
    for url in archives:
        force_this = args.force or (url == current_month_url)
        data = fetch_archive(url, cache_dir=raw_dir, force=force_this)
        all_games.extend(data.get("games", []))
    print(f"      {len(all_games)} games total")

    print(f"[3/5] Filtering to {args.format} and parsing PGNs...")
    in_format = [g for g in all_games if g.get("time_class") == args.format]
    records = [parse_game(g, username=args.username) for g in in_format]
    print(f"      {len(records)} {args.format} games parsed")

    print("[4/5] Computing metrics + merging annotations...")
    annotations = load_annotations(annotations_path)
    payload = compute_all(records, annotations,
                          username=args.username, format=args.format)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "computed.json").write_text(json.dumps(payload, indent=2))

    print("[5/5] Rendering dashboard...")
    render_all_pages(template_dir=template_dir, output_dir=dashboard_dir, payload=payload)

    print(f"\nDone. Rendered to: {(dashboard_dir / 'index.html').resolve()}")
    print(f"  Browsers block file:// subresources; serve over HTTP instead:")
    print(f"    python3 -m http.server 8000")
    print(f"  Then open: http://localhost:8000/dashboard/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
