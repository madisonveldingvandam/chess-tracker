from chess_tracker.opening_match import match_opening

CZ_RULE = {
    "white_requires_any": [["e3", "b3"], ["e3", "Bb2"]],
    "white_forbids": ["Bf4"],
    "window_plies": 12,
}
FK_RULE = {
    "applicable_if_black_plays": "e5",
    "white_requires": ["Nf3", "Nc3"],
    "gambit_flags": {"Halloween": ["Nxe5"], "Belgrade": ["Nd5"]},
    # 12, not 8: the Belgrade's defining Nd5 is White's 5th move (ply 9).
    "window_plies": 12,
}


def test_colle_zukertort_is_on_plan():
    m = match_opening(
        "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6", CZ_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True


def test_london_via_bf4_is_deviated():
    # Bf4 played early -> forbidden -> NOT the Colle, even though e3 appears.
    m = match_opening(
        "1.d4 d5 2.Nf3 Nf6 3.Bf4 e6 4.e3 Bd6 5.Bd3 O-O 6.O-O c5", CZ_RULE)
    assert m["applicable"] is True   # all d4 games are applicable to CZ
    assert m["on_plan"] is False


def test_four_knights_is_on_plan_no_flags():
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Bb5 Bb4", FK_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True
    assert m["flags"] == []


def test_halloween_gambit_flagged():
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Nxe5 Nxe5", FK_RULE)
    assert m["on_plan"] is True
    assert m["flags"] == ["Halloween"]


def test_belgrade_gambit_flagged():
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.d4 exd4 5.Nd5 Nxd5", FK_RULE)
    assert m["on_plan"] is True
    assert m["flags"] == ["Belgrade"]


def test_scotch_is_deviated():
    # 1.e4 e5 with d4 push but NO Nc3 -> fails white_requires.
    m = match_opening("1.e4 e5 2.Nf3 Nc6 3.d4 exd4 4.Nxd4 Nf6", FK_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is False


def test_e4_vs_non_e5_is_not_applicable():
    # Scandinavian: black does NOT play ...e5 -> Four Knights impossible.
    m = match_opening("1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5 4.d4 Nf6", FK_RULE)
    assert m["applicable"] is False


def test_token_normalization_capture_and_check():
    # Bxb2 satisfies a "Bb2" requirement; Nd5+ satisfies "Nd5".
    rule = {"white_requires": ["Bb2", "Nd5"], "window_plies": 12}
    m = match_opening("1.d4 Nf6 2.Bb2 e6 3.Nd5+ Be7 4.Bxb2 d5", rule)
    # (contrived line — just exercising normalization on white moves)
    assert m["on_plan"] is True


def test_empty_moves_not_on_plan():
    m = match_opening(None, CZ_RULE)
    assert m["on_plan"] is False
    m2 = match_opening(None, FK_RULE)
    assert m2["applicable"] is False  # can't confirm black ...e5
