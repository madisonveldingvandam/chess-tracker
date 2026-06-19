from chess_tracker.opening_match import match_opening

CZ_RULE = {
    "white_requires_any": [["e3", "b3"], ["e3", "Bb2"]],
    "white_forbids": ["Bf4"],
    "window_plies": 12,
}
VH_RULE = {
    "applicable_if_black_plays": "e5",
    "white_requires": ["Bc4", "Nc3"],
    "white_forbids": ["f4"],
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


def test_vienna_hybrid_is_on_plan():
    m = match_opening("1.e4 e5 2.Bc4 Nf6 3.d3 Nc6 4.Nc3 Bc5", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True
    assert m["flags"] == []


def test_vienna_hybrid_transposition_is_on_plan():
    # Same position via Vienna Game move order: Nc3 before Bc4.
    m = match_opening("1.e4 e5 2.Nc3 Nf6 3.Bc4 Nc6 4.d3", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is True


def test_vienna_gambit_f4_is_deviated():
    # f4 is the Vienna Gambit — forbidden in the Hybrid plan.
    m = match_opening("1.e4 e5 2.Nc3 Nc6 3.f4", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is False


def test_missing_bc4_is_deviated():
    # Nc3 present but no Bc4 -> not the hybrid.
    m = match_opening("1.e4 e5 2.Nc3 Nc6 3.Nf3 Nf6 4.d4", VH_RULE)
    assert m["applicable"] is True
    assert m["on_plan"] is False


def test_e4_vs_non_e5_is_not_applicable():
    # Scandinavian: black does NOT play ...e5 -> Vienna Hybrid impossible.
    m = match_opening("1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5 4.d4 Nf6", VH_RULE)
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
    m2 = match_opening(None, VH_RULE)
    assert m2["applicable"] is False  # can't confirm black ...e5


def test_cz_not_applicable_when_black_plays_e5():
    # Opponent answers 1.d4 with the Englund (1...e5): a Colle setup is
    # impossible, so the game must not count toward CZ adherence.
    rule = {**CZ_RULE, "not_applicable_if_black_plays": "e5"}
    m = match_opening("1.d4 e5 2.dxe5 Nc6 3.Nf3 d5 4.Nc3 Bg4 5.h3 Bxf3", rule)
    assert m["applicable"] is False
    # A normal 1...d5 game still applies and can be on-plan.
    m2 = match_opening(
        "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6", rule)
    assert m2["applicable"] is True
    assert m2["on_plan"] is True


def test_negative_guard_absent_keeps_all_applicable():
    # Without the negative guard, a 1.d4 e5 game stays applicable (prior behavior).
    m = match_opening("1.d4 e5 2.dxe5 Nc6 3.Nf3 d5 4.Nc3 Bg4", CZ_RULE)
    assert m["applicable"] is True
