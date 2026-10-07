# MoveWise

MoveWise is a local chess game review app. Load a PGN to replay a game, inspect Stockfish's recommended moves, review move quality, and get a move explanation from a local language model grounded in engine analysis.

MoveWise runs on your computer; it does not currently have a hosted demo. Stockfish provides the chess evaluations. Ollama is used only to phrase the optional coaching explanation.

## Features

- Upload and replay a PGN with an interactive board and clickable move list.
- Analyze a position with Stockfish and see its evaluation, best move, and principal variation.
- Review the game for inaccuracies, mistakes, and blunders using centipawn loss.
- Ask a local Ollama model to explain a move using the engine findings. Move details are checked, and confusing model wording is hidden.
- Load built-in examples for White wins, Black wins, and draws.
- Run locally without a paid API key.

## Screenshots

### Game overview

<img width="856" alt="MoveWise game board, move list, and position analysis" src="https://github.com/user-attachments/assets/55aeb338-83a2-4110-95eb-23311b9f30be" />

### Move review and explanation

<img width="293" alt="Stockfish move review and local coaching explanation" src="https://github.com/user-attachments/assets/874887f1-6d2c-437b-929e-e4e1ff7fd1b2" />

## Requirements

- Windows 10 or newer
- Python 3.11 or newer
- A Stockfish executable (required for engine analysis)
- Ollama and the `gemma3:1b` model (required for move explanations)
- Git, to clone the repository

## Run locally on Windows

Open Command Prompt and clone the repository:

```bat
git clone https://github.com/aamnasingh/movewise-chess-analyzer.git
cd movewise-chess-analyzer
```

Create a virtual environment and install the Python dependencies:

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Download Stockfish for Windows. Copy the example settings file and edit it:

```bat
copy .env.example .env
notepad .env
```

In `.env`, set `STOCKFISH_PATH` to the full path of your Stockfish executable. Use forward slashes in the path, for example:

```text
STOCKFISH_PATH=C:/Tools/Stockfish/stockfish.exe
```

Install [Ollama for Windows](https://ollama.com/download/windows). In a Command Prompt, download the model by running:

```bat
ollama run gemma3:1b
```

When the model prompt appears, type `/bye`. Ollama's local service should stay available in the background.

Start MoveWise from the repository folder:

```bat
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> in your browser. Load a built-in sample or upload a `.pgn` file, select a move, then choose **Explain this move**. Keep the Command Prompt window running while using the app; press **Ctrl+C** there to stop it.

## How it works

1. FastAPI accepts a PGN, and `python-chess` parses the game and prepares its board positions.
2. Stockfish analyzes positions through its UCI interface and supplies the evaluation, best move, and principal variation.
3. For move explanations, the app sends engine findings to Ollama at `http://127.0.0.1:11434`. Ollama phrases the explanation; Stockfish remains the source of the move evaluations.

## Current limitations

- Games and analysis are held in memory and are cleared when the server restarts.
- The app reads the first game in a PGN. PGN uploads are limited to 1 MB and 300 half-moves; full-game analysis is limited to 120 half-moves.
- Engine scores are estimates at a configured search depth. Higher depth takes longer.
- Small local language models can produce inaccurate chess commentary. MoveWise keeps engine findings visible and hides commentary when it detects a move mix-up. Treat generated wording as an explanation, not as engine analysis.

## Configuration

`.env.example` lists the supported environment variables. `STOCKFISH_PATH` is required for engine analysis. Ollama defaults to `gemma3:1b` at its local API address; set `OLLAMA_MODEL` or `OLLAMA_URL` in your local `.env` to change those defaults. The `.env` file is ignored by Git and should stay on your computer.
