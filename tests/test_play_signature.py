from io import StringIO
import chess.pgn

from chess_tracker.play_signature import play_signature


def _parse(pgn: str):
    return chess.pgn.read_game(StringIO(pgn))


def test_play_signature_returns_string_for_long_enough_game():
    pgn = "1. d4 d5 2. Nf3 Nf6 3. c4 e6 4. Nc3 Be7 5. Bg5 O-O *"
    sig = play_signature(_parse(pgn))
    assert isinstance(sig, str)
    assert "/" in sig  # FEN has rank separators


def test_play_signature_returns_none_for_short_game():
    pgn = "1. d4 d5 2. Nf3 *"  # only 4 plies
    assert play_signature(_parse(pgn)) is None


def test_play_signature_collapses_transpositions():
    direct     = "1. d4 Nf6 2. c4 e6 3. Nc3 d5 4. Nf3 Be7 *"
    transposed = "1. d4 d5  2. c4 e6 3. Nc3 Nf6 4. Nf3 Be7 *"
    assert play_signature(_parse(direct)) == play_signature(_parse(transposed))


def test_play_signature_returns_none_for_empty_pgn():
    assert play_signature(_parse("")) is None


def test_play_signature_distinguishes_different_positions():
    queens = "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 *"   # QGD
    kings  = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *"  # Ruy Lopez
    assert play_signature(_parse(queens)) != play_signature(_parse(kings))


# --- first_moves_san --------------------------------------------------------

from chess_tracker.play_signature import first_moves_san


def test_first_moves_san_returns_compact_san_with_move_numbers():
    pgn = "1. d4 d5 2. Nf3 Nf6 3. c4 e6 4. Nc3 Be7 5. Bg5 O-O *"
    assert first_moves_san(_parse(pgn)) == "1.d4 d5 2.Nf3 Nf6 3.c4 e6 4.Nc3 Be7"


def test_first_moves_san_returns_none_for_short_game():
    pgn = "1. d4 d5 2. Nf3 *"  # only 3 plies
    assert first_moves_san(_parse(pgn)) is None


def test_first_moves_san_returns_none_for_empty_pgn():
    assert first_moves_san(_parse("")) is None


def test_first_moves_san_uses_san_notation_consistently():
    # Same position from different move orders should produce different
    # first_moves strings (move order is preserved verbatim — this is the
    # opposite contract from play_signature).
    direct     = "1. d4 Nf6 2. c4 e6 3. Nc3 d5 4. Nf3 Be7 *"
    transposed = "1. d4 d5  2. c4 e6 3. Nc3 Nf6 4. Nf3 Be7 *"
    assert first_moves_san(_parse(direct)) != first_moves_san(_parse(transposed))
