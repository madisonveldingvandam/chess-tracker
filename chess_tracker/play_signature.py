"""Compute the 8-ply canonical FEN signature for a chess game.

Two games that reach the same position after 8 plies (regardless of move
order — i.e., transpositions collapse) produce identical signatures.
"""
import chess
import chess.pgn

PLY_DEPTH = 8


def play_signature(game: chess.pgn.Game | None) -> str | None:
    """Return canonical FEN at ply 8, or None if the game has < 8 plies.

    FEN's halfmove and fullmove counters are stripped: the signature is
    placement + side-to-move + castling rights + en-passant target. Two
    transpositions reaching the same position get identical signatures.
    """
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


def first_moves_san(game: chess.pgn.Game | None, count: int = PLY_DEPTH) -> str | None:
    """Return the first `count` plies as a compact SAN string with move
    numbers, e.g. "1.d4 d5 2.Nf3 Nc6 3.c4 e6 4.Nc3 Nf6".

    Returns None for a missing game or fewer than `count` plies.
    """
    if game is None:
        return None
    board = game.board()
    tokens: list[str] = []
    plies = 0
    for move in game.mainline_moves():
        if plies >= count:
            break
        san = board.san(move)
        if plies % 2 == 0:
            tokens.append(f"{plies // 2 + 1}.{san}")
        else:
            tokens.append(san)
        board.push(move)
        plies += 1
    if plies < count:
        return None
    return " ".join(tokens)
