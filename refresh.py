"""CLI: pull Chess.com archives → compute metrics → render dashboard."""
import argparse
import json
import sys
from pathlib import Path

from chess_tracker.api import fetch_archives_index, fetch_archive
from chess_tracker.pgn import parse_game
from chess_tracker.metrics import compute_all
from chess_tracker.annotations import load_annotations
from chess_tracker.plan import load_plan
from chess_tracker.puzzles import attach_puzzles, find_engine_path
from chess_tracker.analysis import (
    run_move_quality_pass, aggregate_move_quality,
    load_quality_cache, save_quality_cache,
)
from chess_tracker.render import render_all_pages, DEFAULT_TEMPLATE_DIR


def accept_game(game: dict, time_class: str, time_control: str | None = None) -> bool:
    """True if a Chess.com game dict is a rated standard-chess game in the
    requested time class.

    time_control=None accepts every control within the class; pass an exact
    Chess.com TimeControl string (e.g. "60", "60+1", "1/86400") to narrow.
    """
    if game.get("time_class") != time_class:
        return False
    if time_control is not None and str(game.get("time_control")) != str(time_control):
        return False
    return game.get("rated") is True and game.get("rules") == "chess"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh chess tracker dashboard.")
    ap.add_argument("--username", default="M_V-V")
    ap.add_argument("--format", default="bullet",
                    choices=["bullet", "blitz", "rapid", "daily"])
    ap.add_argument("--time-control", default=None,
                    help="Optional exact Chess.com time_control filter "
                         "(e.g. 60, 60+1, 1/86400). Default: all controls in the class.")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch all archives, not just current month.")
    ap.add_argument("--no-puzzles", action="store_true",
                    help="Skip the Stockfish pass that attaches a puzzle to each recent loss.")
    ap.add_argument("--no-analysis", action="store_true",
                    help="Skip the Stockfish move-quality pass (accuracy%, blunders, cp-loss).")
    ap.add_argument("--analysis-depth", type=int, default=12,
                    help="Search depth for the move-quality pass (default 12).")
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

    tc_label = args.time_control or "all controls"
    print(f"[3/5] Filtering to rated standard {args.format} games ({tc_label})...")
    in_format = [g for g in all_games
                 if accept_game(g, args.format, args.time_control)]
    records = [parse_game(g, username=args.username) for g in in_format]
    print(f"      {len(records)} rated {args.format} games parsed")

    print("[4/5] Computing metrics + merging annotations + plan...")
    annotations = load_annotations(annotations_path)
    plan = load_plan()
    payload = compute_all(records, annotations,
                          username=args.username, format=args.format,
                          plan=plan)

    if args.no_puzzles:
        for loss in payload.get("recent_losses", []):
            loss["puzzle"] = None
        print("[4.5/5] Puzzle pass skipped (--no-puzzles).")
    elif find_engine_path() is None:
        for loss in payload.get("recent_losses", []):
            loss["puzzle"] = None
        print("[4.5/5] No Stockfish found; losses carry no puzzles "
              "(set $STOCKFISH_PATH or install stockfish).")
    else:
        # Loss dicts only keep the opening's first plies; the full PGN lives in
        # the raw game dicts. Key both by URL so attach_puzzles can find them.
        pgn_by_url = {g["url"]: g["pgn"] for g in in_format if g.get("url") and g.get("pgn")}
        side_by_url = {r.url: r.side for r in records if r.url}
        n = attach_puzzles(payload.get("recent_losses", []), pgn_by_url, side_by_url)
        print(f"[4.5/5] Stockfish puzzle pass: {n} of "
              f"{len(payload.get('recent_losses', []))} recent losses got a puzzle.")

    analysis_cache_path = data_dir / "analysis_cache.json"
    if args.no_analysis:
        payload["move_quality"] = None
        print("[4.6/5] Move-quality analysis skipped (--no-analysis).")
    elif find_engine_path() is None:
        payload["move_quality"] = None
        print("[4.6/5] No Stockfish found; move-quality analysis skipped.")
    else:
        side_by_url = {r.url: r.side for r in records if r.url}
        cache = load_quality_cache(analysis_cache_path)
        summaries = run_move_quality_pass(in_format, side_by_url, cache,
                                          depth=args.analysis_depth)
        save_quality_cache(analysis_cache_path, cache)
        payload["move_quality"] = aggregate_move_quality(summaries)
        print(f"[4.6/5] Move-quality pass: {len(summaries)} games analyzed/cached "
              f"(depth {args.analysis_depth}).")

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
