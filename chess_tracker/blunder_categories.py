"""Aggregate Stockfish blunder evidence into a compact dashboard payload."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from chess_tracker.analysis import ANALYSIS_CACHE_VERSION


CATEGORY_LABELS: dict[str, str] = {
    "material_loss": "Material loss",
    "missed_capture_or_recapture": "Missed capture or recapture",
    "mate_threat_or_mate_allowed": "Mate threat or mate allowed",
    "opening_phase_blunder": "Opening phase",
    "early_middlegame_blunder": "Early middlegame",
    "endgame_blunder": "Endgame",
    "time_pressure_blunder": "Time pressure",
    "large_eval_swing": "Large eval swing",
    "conversion_error": "Conversion error",
}

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "material_loss": "Opponent's best reply after your move captures material.",
    "missed_capture_or_recapture": "Stockfish's best move was a capture or recapture and your move was not.",
    "mate_threat_or_mate_allowed": "The position after your move is a forced mate against you.",
    "opening_phase_blunder": "The blunder happened by move 8.",
    "early_middlegame_blunder": "The blunder happened from moves 9-20.",
    "endgame_blunder": "The blunder happened in an endgame position.",
    "time_pressure_blunder": "The clock after your move was at or below 10 seconds.",
    "large_eval_swing": "The centipawn loss was at least 500.",
    "conversion_error": "You were clearly better before the move and the advantage collapsed.",
}

PHASE_LABELS: dict[str, str] = {
    "opening": "Opening (moves 1-8)",
    "early_middlegame": "Early middlegame (moves 9-20)",
    "middlegame": "Middlegame (moves 21+)",
    "endgame": "Endgame",
}


@dataclass
class _Accumulator:
    count: int = 0
    cp_sum: int = 0
    worst_cp_loss: int = 0

    def add(self, cp_loss: int) -> None:
        self.count += 1
        self.cp_sum += cp_loss
        self.worst_cp_loss = max(self.worst_cp_loss, cp_loss)

    def row(self, key: str, label: str, total: int, **extra) -> dict:
        return {
            "key": key,
            "label": label,
            "count": self.count,
            "pct": round(100.0 * self.count / total, 1) if total else 0.0,
            "avg_cp_loss": round(self.cp_sum / self.count) if self.count else None,
            "worst_cp_loss": self.worst_cp_loss if self.count else None,
            **extra,
        }


def _record_meta(record) -> dict:
    return {
        "opening": getattr(record, "opening", None),
        "family": getattr(record, "family", None),
        "side": getattr(record, "side", None),
        "eco": getattr(record, "eco", None),
        "end_time": getattr(record, "end_time", None),
    }


def _summary_blunders(summary: dict, record_by_url: dict[str, object]) -> list[dict]:
    url = summary.get("game_url")
    record = record_by_url.get(url) if url else None
    meta = _record_meta(record) if record else {}
    out = []
    for blunder in summary.get("blunder_evidence", []) or []:
        item = {
            **blunder,
            "game_url": url,
            "opening": meta.get("opening"),
            "family": meta.get("family"),
            "eco": meta.get("eco"),
            "game_side": meta.get("side") or blunder.get("side"),
            "end_time": meta.get("end_time"),
        }
        out.append(item)
    return out


def compute_blunder_analysis(
    summaries: list[dict],
    records: list[object],
    *,
    eligible_games: int,
    max_examples: int = 12,
    max_openings: int = 10,
) -> dict:
    """Return compact category/phase/opening/example tables for blunders.html."""
    analyzed = [s for s in summaries if s and s.get("moves_analyzed")]
    record_by_url = {
        getattr(record, "url", ""): record
        for record in records
        if getattr(record, "url", "")
    }

    blunders: list[dict] = []
    for summary in analyzed:
        blunders.extend(_summary_blunders(summary, record_by_url))

    total_blunders = len(blunders)
    categorized_blunders = sum(1 for b in blunders if b.get("categories"))
    games_with_blunders = {
        b.get("game_url") for b in blunders if b.get("game_url")
    }

    category_acc: dict[str, _Accumulator] = defaultdict(_Accumulator)
    phase_acc: dict[str, _Accumulator] = defaultdict(_Accumulator)
    opening_acc: dict[tuple[str, str], _Accumulator] = defaultdict(_Accumulator)
    opening_games: dict[tuple[str, str], set[str]] = defaultdict(set)

    for blunder in blunders:
        cp_loss = int(blunder.get("cp_loss") or 0)
        phase = blunder.get("phase_bucket") or blunder.get("phase") or "middlegame"
        phase_acc[phase].add(cp_loss)

        for category in blunder.get("categories", []) or []:
            category_acc[category].add(cp_loss)

        family = blunder.get("family") or blunder.get("opening") or "Unknown opening"
        side = blunder.get("game_side") or blunder.get("side") or "unknown"
        key = (family, side)
        opening_acc[key].add(cp_loss)
        if blunder.get("game_url"):
            opening_games[key].add(blunder["game_url"])

    categories = [
        acc.row(
            key,
            CATEGORY_LABELS.get(key, key.replace("_", " ").title()),
            total_blunders,
            description=CATEGORY_DESCRIPTIONS.get(key, ""),
        )
        for key, acc in category_acc.items()
    ]
    categories.sort(key=lambda row: (-row["count"], -row["worst_cp_loss"], row["label"]))

    phase_order = ["opening", "early_middlegame", "middlegame", "endgame"]
    phase_breakdown = [
        phase_acc[key].row(key, PHASE_LABELS.get(key, key), total_blunders)
        for key in phase_order
        if key in phase_acc
    ]

    affected_openings = []
    for (family, side), acc in opening_acc.items():
        affected_openings.append(acc.row(
            f"{family}|{side}",
            family,
            total_blunders,
            side=side,
            affected_games=len(opening_games[(family, side)]),
        ))
    affected_openings.sort(
        key=lambda row: (-row["count"], -row["worst_cp_loss"], row["label"])
    )

    blunders_sorted = sorted(
        blunders,
        key=lambda b: (
            int(b.get("cp_loss") or 0),
            int(b.get("end_time") or 0),
        ),
        reverse=True,
    )
    for idx, blunder in enumerate(blunders_sorted, start=1):
        side = blunder.get("side")
        move_prefix = f"{blunder.get('fullmove') or '?'}."
        if side == "black":
            move_prefix += ".."
        category_keys = blunder.get("categories") or []
        primary = category_keys[0] if category_keys else None
        blunder["id"] = f"blunder-{idx}"
        blunder["move_label"] = (
            f"{move_prefix} "
            f"{blunder.get('played_move_san') or blunder.get('played_move_uci') or 'unknown'}"
        )
        blunder["primary_category"] = primary
        blunder["primary_category_label"] = (
            CATEGORY_LABELS.get(primary, primary.replace("_", " ").title())
            if primary else "Uncategorized"
        )
        blunder["categories_label"] = ", ".join(
            CATEGORY_LABELS.get(category, category.replace("_", " ").title())
            for category in category_keys
        )
        blunder["opening_label"] = (
            blunder.get("opening") or blunder.get("family") or "Unknown opening"
        )
        if blunder.get("fen_before"):
            blunder["position_url"] = (
                "https://lichess.org/analysis/standard/"
                + blunder["fen_before"].replace(" ", "_")
            )

    examples = blunders_sorted[:max_examples]

    return {
        "cache_version": ANALYSIS_CACHE_VERSION,
        "engine_coverage": {
            "analyzed_games": len(analyzed),
            "eligible_games": eligible_games,
            "games_with_blunders": len(games_with_blunders),
            "blunders_analyzed": total_blunders,
            "categorized_blunders": categorized_blunders,
            "uncategorized_blunders": total_blunders - categorized_blunders,
        },
        "category_labels": CATEGORY_LABELS,
        "category_descriptions": CATEGORY_DESCRIPTIONS,
        "categories": categories,
        "phase_breakdown": phase_breakdown,
        "affected_openings": affected_openings[:max_openings],
        "blunders": blunders_sorted,
        "examples": examples,
    }
