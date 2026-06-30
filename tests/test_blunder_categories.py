from chess_tracker.blunder_categories import compute_blunder_analysis
from chess_tracker.pgn import GameRecord


def _record(url="g1", opening="Italian Game", family="Italian Game", side="white"):
    return GameRecord(
        url=url,
        end_time=1_700_000_000,
        time_class="bullet",
        side=side,
        my_rating=500,
        opp_rating=500,
        result="resigned",
        opp_result="win",
        plies=20,
        fullmoves=10,
        opening=opening,
        family=family,
        variation="",
        eco="C50",
    )


def _summary(url="g1"):
    return {
        "game_url": url,
        "moves_analyzed": 12,
        "blunder_evidence": [
            {
                "fullmove": 6,
                "side": "white",
                "phase": "opening",
                "phase_bucket": "opening",
                "cp_loss": 620,
                "played_move_san": "Qxe5",
                "best_move_san": "Nf3",
                "fen_before": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
                "categories": [
                    "material_loss",
                    "opening_phase_blunder",
                    "large_eval_swing",
                ],
            },
            {
                "fullmove": 14,
                "side": "white",
                "phase": "middlegame",
                "phase_bucket": "early_middlegame",
                "cp_loss": 310,
                "played_move_san": "h3",
                "best_move_san": "Bxf7+",
                "fen_before": "8/8/8/8/8/8/8/8 w - - 0 1",
                "categories": ["missed_capture_or_recapture", "early_middlegame_blunder"],
            },
        ],
    }


def test_compute_blunder_analysis_aggregates_categories_phases_and_openings():
    result = compute_blunder_analysis([_summary()], [_record()], eligible_games=5)

    cov = result["engine_coverage"]
    assert cov["analyzed_games"] == 1
    assert cov["eligible_games"] == 5
    assert cov["blunders_analyzed"] == 2
    assert cov["categorized_blunders"] == 2

    cats = {row["key"]: row for row in result["categories"]}
    assert cats["material_loss"]["count"] == 1
    assert cats["large_eval_swing"]["avg_cp_loss"] == 620
    assert cats["opening_phase_blunder"]["pct"] == 50.0

    phases = {row["key"]: row for row in result["phase_breakdown"]}
    assert phases["opening"]["count"] == 1
    assert phases["early_middlegame"]["count"] == 1

    openings = result["affected_openings"]
    assert openings[0]["label"] == "Italian Game"
    assert openings[0]["side"] == "white"
    assert openings[0]["count"] == 2
    assert openings[0]["affected_games"] == 1

    blunders = result["blunders"]
    assert len(blunders) == 2
    assert blunders[0]["id"] == "blunder-1"
    assert blunders[0]["move_label"] == "6. Qxe5"
    assert blunders[0]["opening_label"] == "Italian Game"
    assert blunders[0]["primary_category_label"] == "Material loss"
    assert blunders[0]["position_url"].startswith("https://lichess.org/analysis/standard/")

    impact = {row["key"]: row for row in result["impact_rows"]}
    material = impact["material_loss"]
    assert material["row_type"] == "category"
    assert material["focus_area"] == "Tactical/material"
    assert material["count"] == 1
    assert material["total_cp_loss"] == 620
    assert material["top_phase_label"] == "Opening (moves 1-8)"
    assert material["top_opening_label"] == "Italian Game"
    assert material["representative_blunder_id"] == "blunder-1"
    assert material["pattern_count"] == 1
    pattern = material["_children"][0]
    assert pattern["row_type"] == "pattern"
    assert pattern["label"] == "Material loss · Opening (moves 1-8)"
    assert pattern["count"] == 1
    assert pattern["pct"] == 100.0
    assert pattern["representative_blunder_id"] == "blunder-1"
    assert pattern["_children"][0]["row_type"] == "blunder"
    assert pattern["_children"][0]["blunder_id"] == "blunder-1"
    missed = impact["missed_capture_or_recapture"]["_children"][0]
    assert missed["label"] == "Missed capture · Early middlegame (moves 9-20)"


def test_compute_blunder_analysis_examples_are_worst_first_and_capped():
    summaries = [_summary("g1"), _summary("g2")]
    records = [_record("g1"), _record("g2", opening="Sicilian Defense",
                       family="Sicilian Defense", side="black")]
    result = compute_blunder_analysis(
        summaries,
        records,
        eligible_games=2,
        max_examples=2,
    )

    examples = result["examples"]
    assert len(examples) == 2
    assert [e["cp_loss"] for e in examples] == [620, 620]
    assert {e["opening"] for e in examples} == {"Italian Game", "Sicilian Defense"}
    assert len(result["blunders"]) == 4
    assert result["impact_rows"][0]["total_cp_loss"] >= result["impact_rows"][1]["total_cp_loss"]
