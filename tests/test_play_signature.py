from chess_tracker.play_signature import play_signature, PLY_DEPTH


def test_play_signature_returns_string_for_long_enough_game():
    pgn = "1. d4 d5 2. Nf3 Nf6 3. c4 e6 4. Nc3 Be7 5. Bg5 O-O *"
    sig = play_signature(pgn)
    assert isinstance(sig, str)
    assert "/" in sig  # FEN has rank separators


def test_play_signature_returns_none_for_short_game():
    pgn = "1. d4 d5 2. Nf3 *"  # only 4 plies
    assert play_signature(pgn) is None


def test_play_signature_collapses_transpositions():
    direct     = "1. d4 Nf6 2. c4 e6 3. Nc3 d5 4. Nf3 Be7 *"
    transposed = "1. d4 d5  2. c4 e6 3. Nc3 Nf6 4. Nf3 Be7 *"
    assert play_signature(direct) == play_signature(transposed)


def test_play_signature_returns_none_for_empty_pgn():
    assert play_signature("") is None


def test_play_signature_distinguishes_different_positions():
    queens = "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 *"   # QGD
    kings  = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *"  # Ruy Lopez
    assert play_signature(queens) != play_signature(kings)
