from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from uuid import uuid4

import chess
import chess.engine
import chess.pgn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
ENV_FILE = ROOT.parent / ".env"
load_dotenv(ENV_FILE, override=True)
MAX_PGN_BYTES = 1_000_000
MAX_PLIES = 300
MAX_ANALYSIS_PLIES = 120
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b")

app = FastAPI(title="MoveWise", description="A chess game review and coaching app")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Local MVP storage. This is intentionally in memory; a database can come later.
games: dict[str, dict] = {}
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "").strip().strip('"')


def describe_move(board: chess.Board, move: chess.Move) -> str:
    """Return literal piece, square, and capture facts for a move."""
    piece = board.piece_at(move.from_square)
    if piece is None:
        return board.san(move)
    color_name = "White" if piece.color == chess.WHITE else "Black"
    piece_name = chess.piece_name(piece.piece_type)
    origin = chess.square_name(move.from_square)
    destination = chess.square_name(move.to_square)
    detail = f"{color_name}'s {piece_name} moves from {origin} to {destination}"
    capture_square = move.to_square
    if board.is_en_passant(move):
        capture_square += -8 if piece.color == chess.WHITE else 8
    captured_piece = board.piece_at(capture_square)
    if captured_piece is not None:
        captured_color = "White" if captured_piece.color == chess.WHITE else "Black"
        detail += (
            f" and captures {captured_color}'s "
            f"{chess.piece_name(captured_piece.piece_type)} on {chess.square_name(capture_square)}"
        )
    if move.promotion:
        detail += f", promoting to a {chess.piece_name(move.promotion)}"
    return f"{detail} (SAN: {board.san(move)})."


def commentary_matches_engine(text: str, played_san: str, best_san: str, quality: str) -> bool:
    """Reject local-model text that omits or misidentifies the two key moves."""
    normalized = text.casefold()

    def has_move(san: str) -> bool:
        return re.search(rf"(?<![a-z0-9]){re.escape(san.casefold())}(?![a-z0-9])", normalized) is not None

    if not has_move(played_san) or not has_move(best_san):
        return False
    if played_san != best_san:
        best_called_played = re.search(
            rf"\b(?:played|chose|selected|made|moved)\s+(?:(?:a|the)\s+)?(?:move\s+)?(?:of\s+)?(?<![a-z0-9]){re.escape(best_san.casefold())}(?![a-z0-9])",
            normalized,
        )
        if best_called_played:
            return False
    if quality in {"inaccuracy", "mistake", "blunder"} and re.search(
        r"\b(?:good|great|solid|excellent|brilliant|strong)\b", normalized
    ):
        return False
    return True


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "config_file_found": str(ENV_FILE.is_file()).lower(),
        "stockfish_configured": str(bool(STOCKFISH_PATH)).lower(),
        "stockfish_executable_found": str(bool(STOCKFISH_PATH and Path(STOCKFISH_PATH).is_file())).lower(),
    }


@app.post("/api/games")
async def upload_game(file: UploadFile = File(...)) -> dict:
    if file.filename and not file.filename.lower().endswith((".pgn", ".txt")):
        raise HTTPException(status_code=400, detail="Please upload a .pgn file.")

    raw = await file.read(MAX_PGN_BYTES + 1)
    if len(raw) > MAX_PGN_BYTES:
        raise HTTPException(status_code=413, detail="PGN files must be smaller than 1 MB.")

    try:
        pgn_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="The PGN file must use UTF-8 text encoding.") from exc

    try:
        game = chess.pgn.read_game(StringIO(pgn_text))
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail="Could not read this PGN file.") from exc

    if game is None:
        raise HTTPException(status_code=400, detail="No chess game was found in this PGN.")
    if game.errors:
        raise HTTPException(status_code=400, detail="This PGN contains invalid moves. Please check the file and try again.")

    board = game.board()
    positions = [board.fen()]
    moves = []
    for move in game.mainline_moves():
        if len(moves) >= MAX_PLIES:
            raise HTTPException(status_code=400, detail=f"This demo supports games up to {MAX_PLIES} plies.")
        san = board.san(move)
        mover = "White" if board.turn == chess.WHITE else "Black"
        move_number = board.fullmove_number
        uci = move.uci()
        board.push(move)
        moves.append({
            "ply": len(moves) + 1,
            "move_number": move_number,
            "mover": mover,
            "san": san,
            "uci": uci,
        })
        positions.append(board.fen())

    headers = game.headers
    game_id = str(uuid4())
    payload = {
        "id": game_id,
        "headers": {
            "white": headers.get("White", "White"),
            "black": headers.get("Black", "Black"),
            "event": headers.get("Event", "Casual Game"),
            "site": headers.get("Site", ""),
            "date": headers.get("Date", ""),
            "result": headers.get("Result", "*"),
        },
        "initial_fen": positions[0],
        "positions": positions,
        "moves": moves,
        "ply_count": len(moves),
        "result": headers.get("Result", "*"),
    }
    games[game_id] = {"pgn": pgn_text, **payload}
    return payload


@app.post("/api/games/{game_id}/analysis")
def analyze_position(
    game_id: str,
    ply: int = Query(0, ge=0),
    depth: int = Query(10, ge=1, le=18),
) -> dict:
    game = games.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found. Upload the PGN again and retry.")
    if ply >= len(game["positions"]):
        raise HTTPException(status_code=400, detail="That position is outside the game.")
    if not STOCKFISH_PATH:
        raise HTTPException(
            status_code=503,
            detail="Stockfish is not configured. Set the STOCKFISH_PATH environment variable and restart the app.",
        )
    engine_file = Path(STOCKFISH_PATH)
    if not engine_file.is_file():
        raise HTTPException(status_code=503, detail=f"Stockfish executable was not found at: {engine_file}")

    board = chess.Board(game["positions"][ply])
    try:
        with chess.engine.SimpleEngine.popen_uci(str(engine_file)) as engine:
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
    except (chess.engine.EngineError, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"Could not start Stockfish: {exc}") from exc

    best_move = info.get("pv", [None])[0]
    if best_move is None:
        raise HTTPException(status_code=500, detail="Stockfish did not return a best move for this position.")

    white_score = info["score"].white()
    mate_in = white_score.mate()
    centipawns = white_score.score()
    if mate_in is not None:
        evaluation = "Mate in 0" if mate_in == 0 else f"Mate in {abs(mate_in)} for {'White' if mate_in > 0 else 'Black'}"
    else:
        evaluation = f"{(centipawns or 0) / 100:+.2f}"

    line_board = board.copy()
    principal_variation = []
    for move in info.get("pv", [])[:6]:
        principal_variation.append(line_board.san(move))
        line_board.push(move)

    return {
        "ply": ply,
        "depth": info.get("depth", depth),
        "side_to_move": "White" if board.turn == chess.WHITE else "Black",
        "best_move": board.san(best_move),
        "best_move_uci": best_move.uci(),
        "evaluation": evaluation,
        "score_cp_white": centipawns,
        "mate_white": mate_in,
        "principal_variation": principal_variation,
    }


@app.post("/api/games/{game_id}/analyze-game")
def analyze_game(
    game_id: str,
    depth: int = Query(8, ge=1, le=14),
) -> dict:
    game = games.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found. Upload the PGN again and retry.")
    if not STOCKFISH_PATH:
        raise HTTPException(status_code=503, detail="Stockfish is not configured. Check the project's .env file and restart the app.")
    engine_file = Path(STOCKFISH_PATH)
    if not engine_file.is_file():
        raise HTTPException(status_code=503, detail=f"Stockfish executable was not found at: {engine_file}")
    if len(game["moves"]) > MAX_ANALYSIS_PLIES:
        raise HTTPException(status_code=400, detail=f"For this demo, full-game analysis is limited to {MAX_ANALYSIS_PLIES} half-moves.")

    results = []
    try:
        with chess.engine.SimpleEngine.popen_uci(str(engine_file)) as engine:
            board = chess.Board(game["initial_fen"])
            for move_data in game["moves"]:
                mover = board.turn
                played_move = chess.Move.from_uci(move_data["uci"])
                before = engine.analyse(board, chess.engine.Limit(depth=depth))
                best_move = before.get("pv", [None])[0]
                if best_move is None:
                    continue
                best_score = before["score"].pov(mover).score(mate_score=10000) or 0
                best_san = board.san(best_move)
                board.push(played_move)

                outcome = board.outcome(claim_draw=True)
                if outcome is not None:
                    played_score = 10000 if outcome.winner == mover else -10000 if outcome.winner is not None else 0
                else:
                    after = engine.analyse(board, chess.engine.Limit(depth=depth))
                    played_score = after["score"].pov(mover).score(mate_score=10000) or 0

                # The move was the engine's top choice; do not report search jitter as a loss.
                loss_cp = 0 if played_move == best_move else max(0, best_score - played_score)
                if played_move == best_move:
                    label = "best"
                elif loss_cp < 25:
                    label = "great"
                elif loss_cp < 75:
                    label = "good"
                elif loss_cp < 150:
                    label = "inaccuracy"
                elif loss_cp < 300:
                    label = "mistake"
                else:
                    label = "blunder"

                results.append({
                    "ply": move_data["ply"],
                    "move_number": move_data["move_number"],
                    "mover": move_data["mover"],
                    "played_move": move_data["san"],
                    "best_move": best_san,
                    "loss_cp": loss_cp,
                    "label": label,
                })
    except (chess.engine.EngineError, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"Could not complete Stockfish analysis: {exc}") from exc

    summary = {
        label: sum(1 for move in results if move["label"] == label)
        for label in ("best", "great", "good", "inaccuracy", "mistake", "blunder")
    }


@app.post("/api/games/{game_id}/coach")
def coach_move(
    game_id: str,
    ply: int = Query(..., ge=1),
    depth: int = Query(10, ge=1, le=18),
) -> dict:
    """Explain one played move using local Ollama, grounded in Stockfish output."""
    game = games.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found. Upload the PGN again and retry.")
    if ply > len(game["moves"]):
        raise HTTPException(status_code=400, detail="That move is outside the game.")
    if not STOCKFISH_PATH or not Path(STOCKFISH_PATH).is_file():
        raise HTTPException(status_code=503, detail="Stockfish is not ready. Check the project's .env file and restart MoveWise.")

    move_data = game["moves"][ply - 1]
    before_board = chess.Board(game["positions"][ply - 1])
    played_move = chess.Move.from_uci(move_data["uci"])
    mover = before_board.turn
    after_board = before_board.copy()
    after_board.push(played_move)

    try:
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            before = engine.analyse(before_board, chess.engine.Limit(depth=depth))
            best_move = before.get("pv", [None])[0]
            if best_move is None:
                raise HTTPException(status_code=503, detail="Stockfish did not return a line for this move.")
            best_score = before["score"].pov(mover).score(mate_score=10000) or 0
            outcome = after_board.outcome(claim_draw=True)
            if outcome is not None:
                actual_score = 10000 if outcome.winner == mover else -10000 if outcome.winner is not None else 0
            else:
                after = engine.analyse(after_board, chess.engine.Limit(depth=depth))
                actual_score = after["score"].pov(mover).score(mate_score=10000) or 0
    except (chess.engine.EngineError, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"Could not analyze this move with Stockfish: {exc}") from exc

    # Separate searches can differ by a few centipawns even when the played move
    # is exactly the engine's top choice, so suppress that search noise.
    loss_cp = 0 if played_move == best_move else max(0, best_score - actual_score)
    if played_move == best_move:
        quality = "best"
    elif loss_cp < 25:
        quality = "great"
    elif loss_cp < 75:
        quality = "good"
    elif loss_cp < 150:
        quality = "inaccuracy"
    elif loss_cp < 300:
        quality = "mistake"
    else:
        quality = "blunder"

    best_san = before_board.san(best_move)
    pv_board = before_board.copy()
    variation = []
    for move in before.get("pv", [])[:5]:
        variation.append(pv_board.san(move))
        pv_board.push(move)

    played_description = describe_move(before_board, played_move)
    best_description = describe_move(before_board, best_move)
    engine_facts = (
        f"Stockfish preferred {best_san}: {best_description} "
        f"The played move {move_data['san']} is rated {quality}; it worsened the engine evaluation "
        f"by about {loss_cp / 100:.2f} pawns at depth {depth} (evaluation change, not material lost)."
    )
    prompt = (
        "Rewrite the supplied Stockfish finding as one friendly sentence for a beginner. "
        "Paraphrase only; add no chess reason, threat, plan, center-control claim, king-safety claim, "
        "or pawn-structure claim that is not explicitly stated in the finding. Preserve its move names and grade exactly.\n\n"
        f"Stockfish finding: {engine_facts}\n"
        f"Played move detail: {played_description}\n"
        f"Player: {'White' if mover == chess.WHITE else 'Black'}\n"
        f"Best line for context only: {' '.join(variation)}"
    )
    request_body = json.dumps({
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": "Paraphrase the supplied Stockfish finding only. Do not add chess claims or alter move notation, piece identity, or quality grade."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.3},
    }).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Local coach unavailable. Install and start Ollama, then download {OLLAMA_MODEL}.",
        ) from exc
    except (TimeoutError, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="The local coach did not return a usable explanation. Try again.") from exc

    explanation = answer.get("message", {}).get("content", "").strip()
    if not explanation:
        raise HTTPException(status_code=503, detail=f"Ollama could not find model {OLLAMA_MODEL}. Download it, then retry.")
    commentary_valid = commentary_matches_engine(explanation, move_data["san"], best_san, quality)
    if not commentary_valid:
        explanation = "The local model mixed up the played move and the engine recommendation, so its wording was hidden. Use the Stockfish finding above."
    return {
        "ply": ply,
        "move": move_data["san"],
        "mover": move_data["mover"],
        "best_move": best_san,
        "engine_facts": engine_facts,
        "commentary_valid": commentary_valid,
        "loss_cp": loss_cp,
        "quality": quality,
        "depth": depth,
        "explanation": explanation,
    }
    return {"depth": depth, "analyzed_plies": len(results), "summary": summary, "moves": results}
