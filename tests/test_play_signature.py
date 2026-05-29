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


# --- opening_moves_san (best-effort, up to N plies) -------------------------
from chess_tracker.play_signature import opening_moves_san


def test_opening_moves_san_returns_up_to_12_plies():
    pgn = ('[Event "x"]\n\n1. d4 d5 2. Nf3 Nf6 3. e3 e6 4. Bd3 c5 '
           '5. b3 Nc6 6. Bb2 Bd6 7. O-O O-O 1-0')
    assert opening_moves_san(_parse(pgn)) == (
        "1.d4 d5 2.Nf3 Nf6 3.e3 e6 4.Bd3 c5 5.b3 Nc6 6.Bb2 Bd6")


def test_opening_moves_san_best_effort_for_short_game():
    # Only 6 plies — returns what exists rather than None.
    pgn = '[Event "x"]\n\n1. e4 e5 2. Nf3 Nc6 3. Nc3 Nf6 1-0'
    assert opening_moves_san(_parse(pgn)) == "1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6"


def test_opening_moves_san_returns_none_for_empty():
    assert opening_moves_san(None) is None


# --- fens_from_san (tolerant prefix parsing) --------------------------------
from chess_tracker.play_signature import fens_from_san


def test_fens_from_san_parses_clean_line():
    fens, labels = fens_from_san("1.e4 e5 2.Nf3 Nc6")
    assert len(fens) == 5  # start + 4 plies
    assert labels == ["1.e4", "e5", "2.Nf3", "Nc6"]


def test_fens_from_san_stops_at_first_unparseable_token():
    # Annotated multi-branch line (Four Knights): the board renders the
    # parseable prefix through 4.Nxe5 and ignores "(Halloween) / 4.d4 ...".
    fens, labels = fens_from_san(
        "1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Nxe5 (Halloween) / 4.d4 exd4 5.Nd5")
    assert len(fens) == 8        # start + 7 plies (through Nxe5)
    assert labels[-1] == "4.Nxe5"


def test_fens_from_san_empty_for_no_moves():
    assert fens_from_san("") == ([], [])


def test_fens_from_san_no_board_when_first_token_unparseable():
    # Nothing parses -> at most the start fen; caller checks len > 1.
    fens, labels = fens_from_san("(Halloween) / nonsense")
    assert len(fens) <= 1
    assert labels == []
