# MoveWise

MoveWise is a local chess-game review app. Upload a PGN to replay the game, inspect Stockfish's recommended moves, review move-quality changes, and get a concise explanation grounded in engine analysis.

## Features

- Upload and replay the first game in a PGN file with an interactive board and clickable move list.
- Analyze a position with Stockfish and view its evaluation, best move, and principal variation.
- Review a full game and flag inaccuracies, mistakes, and blunders using centipawn loss.
- Ask a local Ollama model to paraphrase the engine finding. Move details are checked, and confusing AI wording is hidden while the Stockfish facts remain visible.
- Load built-in White-win, Black-win, and draw examples.
- Run the app and model locally; no paid API key is needed.

## Screenshots 

<img width="856" height="434" alt="movewise-overview" src="https://github.com/user-attachments/assets/55aeb338-83a2-4110-95eb-23311b9f30be" />

<img width="293" height="358" alt="move-analysis" src="https://github.com/user-attachments/assets/874887f1-6d2c-437b-929e-e4e1ff7fd1b2" />

## Requirements

- Windows 10 or newer
- Python 3.11 or newer
- Stockfish executable
- Ollama and the `gemma3:1b` model for local AI wording

## Setup on Windows Command Prompt

Open Command Prompt in the project folder and create the Python environment:

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Download and install Stockfish, then copy `.env.example` to `.env` and set `STOCKFISH_PATH` to the full path of your Stockfish executable. Keep `.env` on your computer; it is ignored by Git.

Install Ollama from [ollama.com/download/windows](https://ollama.com/download/windows). In a new Command Prompt, download and start the local model once:

```bat
ollama run gemma3:1b
```

Wait for the model prompt, then type `/bye`. Ollama's local service should remain available in the background.

Start MoveWise from the project folder:

```bat
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>, load a built-in sample or upload a `.pgn` file, select a move, and choose **Explain this move**. Keep the server window open while using the app.

## How it works

1. FastAPI accepts a PGN and `python-chess` parses the game and creates the board positions.
2. Stockfish analyzes positions through its UCI interface and supplies the evaluation, best move, and principal variation.
3. The coaching endpoint sends those facts to Ollama at `http://127.0.0.1:11434`. The LLM is used to phrase the evidence; Stockfish remains the source of move evaluations.

## Current limitations

- Games and analysis are held in memory and disappear when the server restarts.
- The app currently reads the first game from a PGN, up to 1 MB and 300 half-moves; full-game analysis is limited to 120 half-moves.
- Engine scores are estimates at a configured search depth. Higher depth takes longer.
- Small local language models can produce inaccurate chess commentary. MoveWise keeps the engine-grounded comparison visible and suppresses commentary when it detects a move mix-up; do not treat generated prose as engine analysis.

## Configuration

`.env.example` shows the supported environment variables. `STOCKFISH_PATH` is required for engine analysis. Ollama defaults to `gemma3:1b` at its local API address; override `OLLAMA_MODEL` or `OLLAMA_URL` in your ignored `.env` if needed.
