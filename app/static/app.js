const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const PIECES = {
  K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};
const SAMPLE_PGNS = {
white: `[Event "MoveWise Sample — White wins"]
[Site "Local Demo"]
[Date "2025.04.12"]
[White "Alex Morgan"]
[Black "Jamie Lee"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7
6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 10. d4 Nbd7
11. c4 c6 12. Nc3 Qc7 13. Be3 Bb7 14. Rc1 b4 15. Nd5! cxd5
16. cxd5 Qb8 17. dxe5 dxe5 18. d6 Bxd6 19. Nh4 g6 20. Bh6 Re8
21. Qf3 Bf8 22. Bg5 Bg7 23. Red1 a5 24. Rxd7 Nxd7 25. Qxf7+ Kh8
26. Qxd7 1-0`,
black: `[Event "MoveWise Sample — Black wins"]
[Site "Local Demo"]
[White "Alex Morgan"]
[Black "Jamie Lee"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1`,
draw: `[Event "MoveWise Sample — Draw agreed"]
[Site "Local Demo"]
[White "Alex Morgan"]
[Black "Jamie Lee"]
[Result "1/2-1/2"]
[Termination "Draw agreed"]

1. e4 e5 2. Nf3 Nc6 1/2-1/2`,
};

const boardElement = document.querySelector("#board");
const notice = document.querySelector("#notice");
const moveList = document.querySelector("#moves-list");
let currentGame = null;
let currentPly = 0;

function renderBoard(fen, ply) {
  const ranks = fen.split(" ")[0].split("/");
  boardElement.replaceChildren();
  ranks.forEach((rankText, rankIndex) => {
    const row = [];
    for (const symbol of rankText) {
      if (/\d/.test(symbol)) row.push(...Array(Number(symbol)).fill(null));
      else row.push(symbol);
    }
    row.forEach((piece, fileIndex) => {
      const square = document.createElement("div");
      const isLight = (rankIndex + fileIndex) % 2 === 1;
      square.className = `square ${isLight ? "light" : "dark"}`;
      square.dataset.rank = String(8 - rankIndex);
      square.dataset.file = "abcdefgh"[fileIndex];
      if (piece) {
        square.textContent = PIECES[piece];
        square.classList.add(piece === piece.toUpperCase() ? "white-piece" : "black-piece");
      }
      boardElement.append(square);
    });
  });
  boardElement.setAttribute("aria-label", `Chessboard after ${ply} half-moves`);
}

function resultLabel(result) {
  return ({ "1-0": "White wins", "0-1": "Black wins", "1/2-1/2": "Draw", "*": "In progress" })[result] || result;
}

function evaluationLabel(evaluation) {
  const value = Number(evaluation);
  if (!Number.isFinite(value)) return evaluation;
  if (Math.abs(value) < 0.01) return "Equal";
  return `${value > 0 ? "White" : "Black"} +${Math.abs(value).toFixed(2)}`;
}

function renderMoves() {
  const rows = [];
  for (let index = 0; index < currentGame.moves.length; index += 2) {
    const white = currentGame.moves[index];
    const black = currentGame.moves[index + 1];
    const row = document.createElement("div");
    row.className = "move-row";
    const number = document.createElement("span");
    number.className = "move-no";
    number.textContent = `${white.move_number}.`;
    row.append(number, makeMoveButton(white), black ? makeMoveButton(black) : makeEmptyCell());
    rows.push(row);
  }
  moveList.replaceChildren(...rows);
  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = '<div class="empty-symbol">♘</div><strong>This game has no moves</strong><p>Try another PGN file with a completed game.</p>';
    moveList.replaceChildren(empty);
  }
}

function makeMoveButton(move) {
  const button = document.createElement("button");
  button.type = "button";
  const analysis = currentGame.analysis?.find((item) => item.ply === move.ply);
  button.className = `move-cell${currentPly === move.ply ? " active" : ""}${analysis ? ` grade-${analysis.label}` : ""}`;
  button.textContent = move.san;
  button.title = analysis
    ? `${move.mover}'s move ${move.move_number}: ${move.san} — ${analysis.label}, ${analysis.loss_cp} centipawns lost; engine preferred ${analysis.best_move}`
    : `Jump to ${move.mover}'s move ${move.move_number}: ${move.san}`;
  if (analysis && ["inaccuracy", "mistake", "blunder"].includes(analysis.label)) {
    const badge = document.createElement("span");
    badge.className = "move-grade-badge";
    badge.textContent = ({ inaccuracy: "?!", mistake: "?", blunder: "??" })[analysis.label];
    button.append(badge);
  }
  button.addEventListener("click", () => setPly(move.ply));
  return button;
}

function makeEmptyCell() {
  const span = document.createElement("span");
  span.className = "move-cell empty";
  return span;
}

function setPly(ply) {
  if (!currentGame) return;
  currentPly = Math.max(0, Math.min(ply, currentGame.moves.length));
  document.querySelector("#engine-result").textContent = "Position changed. Click Analyze this position to refresh Stockfish's evaluation.";
  document.querySelector("#coach-result").textContent = currentPly === 0
    ? "Select a move, then ask the local coach to explain it."
    : "Move changed. Generate a fresh explanation for this move.";
  document.querySelector("#coach-move").disabled = currentPly === 0;
  renderBoard(currentGame.positions[currentPly], currentPly);
  const selected = currentPly === 0 ? null : currentGame.moves[currentPly - 1];
  document.querySelector("#move-counter").textContent = selected
    ? `${selected.move_number}${selected.mover === "White" ? "." : "..."} ${selected.san}`
    : "Starting position";
  document.querySelector("#first-move").disabled = currentPly === 0;
  document.querySelector("#prev-move").disabled = currentPly === 0;
  document.querySelector("#next-move").disabled = currentPly === currentGame.moves.length;
  document.querySelector("#last-move").disabled = currentPly === currentGame.moves.length;
  renderMoves();
  const active = moveList.querySelector(".move-cell.active");
  if (active) active.scrollIntoView({ block: "nearest" });
}

function showGame(game) {
  currentGame = game;
  currentPly = 0;
  document.querySelector("#game-title").textContent = game.headers.event || "Chess game";
  document.querySelector("#white-name").textContent = game.headers.white || "White";
  document.querySelector("#black-name").textContent = game.headers.black || "Black";
  document.querySelector("#white-result").textContent = game.result === "1-0" ? "1" : game.result === "1/2-1/2" ? "½" : "";
  document.querySelector("#black-result").textContent = game.result === "0-1" ? "1" : game.result === "1/2-1/2" ? "½" : "";
  document.querySelector("#game-result").textContent = resultLabel(game.result);
  document.querySelector("#game-event").textContent = game.headers.event || "Casual Game";
  document.querySelector("#game-date").textContent = game.headers.date && game.headers.date !== "????.??.??" ? game.headers.date : "Not provided";
  document.querySelector("#move-count-pill").textContent = `${game.ply_count} PLY`;
  notice.textContent = "";
  setPly(0);
}

async function uploadPgn(file) {
  notice.textContent = "";
  const formData = new FormData();
  formData.append("file", file);
  document.querySelector("#upload-trigger").disabled = true;
  document.querySelector("#upload-trigger").classList.add("is-loading");
  try {
    const response = await fetch("/api/games", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not load this game.");
    showGame(result);
  } catch (error) {
    notice.textContent = error.message || "Could not connect to the game server.";
  } finally {
    document.querySelector("#upload-trigger").disabled = false;
    document.querySelector("#upload-trigger").classList.remove("is-loading");
  }
}

document.querySelector("#upload-trigger").addEventListener("click", () => document.querySelector("#pgn-file").click());
document.querySelector("#pgn-file").addEventListener("change", (event) => {
  const [file] = event.target.files;
  if (file) uploadPgn(file);
  event.target.value = "";
});
document.querySelector("#load-demo").addEventListener("click", () => {
  const choice = document.querySelector("#sample-choice").value;
  const file = new File([SAMPLE_PGNS[choice]], `movewise-${choice}-sample.pgn`, { type: "text/plain" });
  uploadPgn(file);
});
document.querySelector("#first-move").addEventListener("click", () => setPly(0));
document.querySelector("#prev-move").addEventListener("click", () => setPly(currentPly - 1));
document.querySelector("#next-move").addEventListener("click", () => setPly(currentPly + 1));
document.querySelector("#last-move").addEventListener("click", () => setPly(currentGame?.moves.length || 0));
document.querySelector("#analyze-position").addEventListener("click", async () => {
  if (!currentGame) {
    notice.textContent = "Load a PGN before analyzing a position.";
    return;
  }
  const button = document.querySelector("#analyze-position");
  const resultElement = document.querySelector("#engine-result");
  button.disabled = true;
  button.innerHTML = "Stockfish is thinking <span>…</span>";
  resultElement.textContent = "Searching this position…";
  try {
    const response = await fetch(`/api/games/${currentGame.id}/analysis?ply=${currentPly}&depth=10`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Analysis failed.");
    const line = result.principal_variation.join(" ");
    resultElement.replaceChildren();
    const summary = document.createElement("strong");
    summary.textContent = `${result.side_to_move} to move · ${evaluationLabel(result.evaluation)}`;
    const best = document.createElement("span");
    best.textContent = `Best move: ${result.best_move}`;
    const variation = document.createElement("small");
    variation.textContent = `Line: ${line || result.best_move}`;
    resultElement.append(summary, best, variation);
  } catch (error) {
    resultElement.textContent = error.message || "Could not connect to Stockfish.";
  } finally {
    button.disabled = false;
    button.innerHTML = 'Analyze this position <span>→</span>';
  }
});
document.querySelector("#analyze-game").addEventListener("click", async () => {
  if (!currentGame) {
    notice.textContent = "Load a PGN before analyzing the game.";
    return;
  }
  const button = document.querySelector("#analyze-game");
  const resultElement = document.querySelector("#game-analysis-results");
  button.disabled = true;
  button.innerHTML = "Reviewing every move <span>…</span>";
  resultElement.textContent = "Stockfish is evaluating each position. Longer games can take a little while.";
  try {
    const response = await fetch(`/api/games/${currentGame.id}/analyze-game?depth=8`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Full-game analysis failed.");
    currentGame.analysis = result.moves;
    renderMoves();
    resultElement.replaceChildren();
    const summary = document.createElement("strong");
    const counts = result.summary;
    summary.textContent = `${counts.blunder} blunders · ${counts.mistake} mistakes · ${counts.inaccuracy} inaccuracies`;
    resultElement.append(summary);
    const critical = result.moves.filter((move) => ["inaccuracy", "mistake", "blunder"].includes(move.label));
    if (critical.length === 0) {
      const calm = document.createElement("span");
      calm.textContent = `No major drops found at depth ${result.depth}.`;
      resultElement.append(calm);
    } else {
      critical.sort((a, b) => b.loss_cp - a.loss_cp);
      critical.slice(0, 5).forEach((move) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = `critical-move grade-${move.label}`;
        item.textContent = `${move.move_number}${move.mover === "White" ? "." : "..."} ${move.played_move} · ${move.label} (${move.loss_cp} cp) · best: ${move.best_move}`;
        item.addEventListener("click", () => setPly(move.ply));
        resultElement.append(item);
      });
    }
  } catch (error) {
    resultElement.textContent = error.message || "Could not connect to Stockfish.";
  } finally {
    button.disabled = false;
    button.innerHTML = 'Review every move <span>↗</span>';
  }
});
document.querySelector("#coach-move").addEventListener("click", async () => {
  if (!currentGame || currentPly === 0) return;
  const button = document.querySelector("#coach-move");
  const resultElement = document.querySelector("#coach-result");
  const selectedPly = currentPly;
  button.disabled = true;
  button.innerHTML = "Coach is thinking <span>…</span>";
  resultElement.textContent = "Stockfish is checking the move, then the local model will explain the result.";
  try {
    const response = await fetch(`/api/games/${currentGame.id}/coach?ply=${selectedPly}&depth=10`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not generate a move explanation.");
    if (currentPly !== selectedPly) return;
    resultElement.replaceChildren();
    const summary = document.createElement("strong");
    summary.textContent = `${result.mover}'s ${result.move}: ${result.quality} · best move ${result.best_move}`;
    const engineFacts = document.createElement("span");
    engineFacts.className = "engine-facts";
    engineFacts.textContent = result.engine_facts;
    const coachLabel = document.createElement("small");
    coachLabel.className = "coach-label";
    coachLabel.textContent = result.commentary_valid
      ? "Local AI wording (may be inaccurate):"
      : "Local AI comment skipped because it confused the moves.";
    const explanation = document.createElement("span");
    explanation.textContent = result.explanation;
    resultElement.append(summary, engineFacts, coachLabel);
    if (result.commentary_valid) resultElement.append(explanation);
  } catch (error) {
    resultElement.textContent = error.message || "Could not connect to the local coach.";
  } finally {
    button.disabled = currentPly === 0;
    button.innerHTML = 'Explain this move <span>✦</span>';
  }
});
document.addEventListener("keydown", (event) => {
  if (event.target instanceof HTMLInputElement) return;
  if (event.key === "ArrowLeft") setPly(currentPly - 1);
  if (event.key === "ArrowRight") setPly(currentPly + 1);
});
renderBoard(START_FEN, 0);
