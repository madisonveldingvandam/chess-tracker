"""Compute the 8-ply canonical FEN signature for a chess game.

Two games that reach the same position after 8 plies (regardless of move
order — i.e., transpositions collapse) produce identical signatures.
"""
from io import StringIO
import chess
import chess.pgn

PLY_DEPTH = 8


def play_signature(pgn_text: str) -> str | None:
    """Return canonical FEN at ply 8, or None if the game has < 8 plies.

    FEN's halfmove and fullmove counters are stripped: the signature is
    placement + side-to-move + castling rights + en-passant target. Two
    transpositions reaching the same position get identical signatures.
    """
    try:
        game = chess.pgn.read_game(StringIO(pgn_text))
    except Exception:
        return None
    if game is None:
        return None
    board = game.board()
    plies = 0
    for move in game.mainline_moves():
        if plies >= PLY_DEPTH:
            break
        board.push(move)
        plies += 1
    if plies < PLY_DEPTH:
        return None
    parts = board.fen().split()
    return " ".join(parts[:4])  # drop halfmove + fullmove counters
