# Chess Tracker

Local Chess.com bullet behavior recorder + feedback loop. Pulls your
games via the public API, computes per-session and per-opening
metrics, surfaces leaks, and proposes a next-session rule.

## Setup

    uv sync --group dev

## Refresh

    uv run refresh.py                       # default: bullet, user M_V-V
    uv run refresh.py --force               # re-fetch all months

Then open `dashboard/index.html` in your browser.

## What you'll see

1. **KPI strip** — current rating, total games, recent form
2. **Leak summary** — what's bleeding rating right now
3. **Next session rule** — game cap, move-10 target, stop signal
4. **Recent losses → error log** — click "Copy starter entries" to populate annotations
5. **Process metrics** — clock and session behavior
6. **Play signatures** — sortable; low-confidence rows (N<15) are dimmed; grouped by 8-ply FEN, not ECO label
7. **Sessions** — chronological list with tilt flags

## Annotations

Edit `data/annotations.json` directly. Schema:

```json
{
  "openings": {
    "<opening name>": {"tag": "in_repertoire|experimenting|drop", "note": "..."}
  },
  "games":    { "<game_url>": {"tags": ["..."], "note": "..."} },
  "error_log": [{"id": "...", "title": "...", "pattern": "...", "game_refs": []}]
}
```

The dashboard generates starter entries for you (Recent Losses panel) — paste them in.

Re-running `refresh.py` picks up changes immediately.

## Testing

    uv run pytest

## Layout

- `refresh.py` — CLI entrypoint
- `chess_tracker/` — pipeline modules (api, pgn, metrics, annotations, render, play_signature)
- `dashboard/` — HTML/JS/CSS frontend; `vendor/` has Tabulator (offline-safe)
- `data/` — generated (cached archives, computed.json, annotations.json)
- `docs/superpowers/` — spec + plan

## Design

See `docs/superpowers/specs/2026-05-26-bullet-chess-tracker-design.md`.
