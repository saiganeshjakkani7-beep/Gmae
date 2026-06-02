const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");
const scoreValue = document.getElementById("scoreValue");
const targetValue = document.getElementById("targetValue");
const movesValue = document.getElementById("movesValue");
const bestValue = document.getElementById("bestValue");
const progressBar = document.getElementById("progressBar");
const resultPanel = document.getElementById("resultPanel");
const resultLabel = document.getElementById("resultLabel");
const resultTitle = document.getElementById("resultTitle");
const continueButton = document.getElementById("continueButton");
const newGameButton = document.getElementById("newGameButton");
const shuffleButton = document.getElementById("shuffleButton");
const hintButton = document.getElementById("hintButton");
const soundButton = document.getElementById("soundButton");

const size = 6;
const colors = ["#2bb673", "#3478f6", "#f2655b", "#f5b942", "#8e67d2"];
const labels = ["leaf", "wave", "spark", "sun", "moon"];
const storageKey = "chain-bloom-best";

let level = 1;
let board = [];
let path = [];
let dragging = false;
let hinted = [];
let score = 0;
let target = 900;
let moves = 18;
let soundOn = true;
let best = Number(localStorage.getItem(storageKey) || 0);

function randomTile() {
  const type = Math.floor(Math.random() * colors.length);
  return { type };
}

function createBoard() {
  board = Array.from({ length: size }, () => Array.from({ length: size }, randomTile));
}

function startGame(nextLevel = 1) {
  level = nextLevel;
  target = 760 + level * 160;
  moves = Math.max(12, 19 - Math.floor(level / 2));
  score = 0;
  path = [];
  hinted = [];
  dragging = false;
  resultPanel.hidden = true;
  createBoard();
  updateHud();
  draw();
}

function updateHud() {
  scoreValue.textContent = score;
  targetValue.textContent = target;
  movesValue.textContent = moves;
  bestValue.textContent = best;
  progressBar.style.width = `${Math.min(100, (score / target) * 100)}%`;
}

function tileCenter(row, col) {
  const cell = canvas.width / size;
  return {
    x: col * cell + cell / 2,
    y: row * cell + cell / 2,
    r: cell * 0.31,
  };
}

function draw() {
  const cell = canvas.width / size;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let row = 0; row < size; row += 1) {
    for (let col = 0; col < size; col += 1) {
      const tile = board[row][col];
      const { x, y, r } = tileCenter(row, col);
      const selected = path.some((point) => point.row === row && point.col === col);
      const isHinted = hinted.some((point) => point.row === row && point.col === col);
      const radius = selected ? r * 1.12 : r;

      ctx.beginPath();
      ctx.fillStyle = "rgba(24, 32, 47, 0.08)";
      ctx.arc(x, y + 7, radius, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.fillStyle = colors[tile.type];
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();

      if (isHinted) {
        ctx.lineWidth = 8;
        ctx.strokeStyle = "rgba(24, 32, 47, 0.24)";
        ctx.stroke();
      }

      ctx.fillStyle = "rgba(255, 255, 255, 0.82)";
      ctx.font = `${cell * 0.25}px system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(labels[tile.type][0].toUpperCase(), x, y + 1);
    }
  }

  if (path.length > 1) {
    ctx.lineWidth = cell * 0.12;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "rgba(24, 32, 47, 0.7)";
    ctx.beginPath();
    path.forEach((point, index) => {
      const { x, y } = tileCenter(point.row, point.col);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  const clientX = event.touches ? event.touches[0].clientX : event.clientX;
  const clientY = event.touches ? event.touches[0].clientY : event.clientY;
  return {
    x: ((clientX - rect.left) / rect.width) * canvas.width,
    y: ((clientY - rect.top) / rect.height) * canvas.height,
  };
}

function pointToCell(point) {
  const cell = canvas.width / size;
  const col = Math.floor(point.x / cell);
  const row = Math.floor(point.y / cell);
  if (row < 0 || col < 0 || row >= size || col >= size) return null;
  return { row, col };
}

function sameCell(a, b) {
  return a && b && a.row === b.row && a.col === b.col;
}

function adjacent(a, b) {
  return Math.abs(a.row - b.row) <= 1 && Math.abs(a.col - b.col) <= 1;
}

function canAdd(cell) {
  if (!cell) return false;
  if (path.some((point) => sameCell(point, cell))) return false;
  if (!path.length) return true;
  const first = path[0];
  const last = path[path.length - 1];
  return adjacent(last, cell) && board[cell.row][cell.col].type === board[first.row][first.col].type;
}

function addCell(cell) {
  if (canAdd(cell)) {
    path.push(cell);
    hinted = [];
    draw();
  }
}

function pointerStart(event) {
  event.preventDefault();
  if (!resultPanel.hidden || moves <= 0) return;
  dragging = true;
  path = [];
  addCell(pointToCell(canvasPoint(event)));
}

function pointerMove(event) {
  if (!dragging) return;
  event.preventDefault();
  addCell(pointToCell(canvasPoint(event)));
}

function pointerEnd() {
  if (!dragging) return;
  dragging = false;
  if (path.length >= 2) commitPath();
  path = [];
  draw();
}

function commitPath() {
  const gained = path.length * path.length * 18 + (path.length >= 5 ? 120 : 0);
  score += gained;
  moves -= 1;
  best = Math.max(best, score);
  localStorage.setItem(storageKey, String(best));

  for (const point of path) {
    board[point.row][point.col] = randomTile();
  }

  pulse(gained);
  updateHud();

  if (score >= target) {
    showResult("Level clear", `Level ${level} bloomed.`);
  } else if (moves <= 0) {
    showResult("Run over", "Try a tighter chain.");
  }
}

function showResult(label, title) {
  resultLabel.textContent = label;
  resultTitle.textContent = title;
  continueButton.textContent = score >= target ? "Next Level" : "Retry";
  resultPanel.hidden = false;
}

function pulse(gained) {
  if (!soundOn) return;
  const AudioEngine = window.AudioContext || window.webkitAudioContext;
  if (!AudioEngine) return;
  const audio = new AudioEngine();
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.connect(gain);
  gain.connect(audio.destination);
  oscillator.frequency.value = Math.min(760, 240 + gained);
  gain.gain.setValueAtTime(0.045, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.12);
  oscillator.start();
  oscillator.stop(audio.currentTime + 0.13);
}

function shuffle() {
  if (!resultPanel.hidden || moves <= 0) return;
  moves = Math.max(0, moves - 1);
  createBoard();
  hinted = [];
  updateHud();
  draw();
  if (moves <= 0 && score < target) showResult("Run over", "Try a tighter chain.");
}

function findHint() {
  let bestChain = [];
  for (let row = 0; row < size; row += 1) {
    for (let col = 0; col < size; col += 1) {
      const type = board[row][col].type;
      const chain = [{ row, col }];
      for (let r = 0; r < size; r += 1) {
        for (let c = 0; c < size; c += 1) {
          const next = { row: r, col: c };
          const last = chain[chain.length - 1];
          const alreadyUsed = chain.some((point) => sameCell(point, next));
          if (!alreadyUsed && board[r][c].type === type && adjacent(last, next)) {
            chain.push(next);
          }
        }
      }
      if (chain.length > bestChain.length) bestChain = chain;
    }
  }
  hinted = bestChain.slice(0, Math.min(5, bestChain.length));
  draw();
}

canvas.addEventListener("mousedown", pointerStart);
canvas.addEventListener("mousemove", pointerMove);
window.addEventListener("mouseup", pointerEnd);
canvas.addEventListener("touchstart", pointerStart, { passive: false });
canvas.addEventListener("touchmove", pointerMove, { passive: false });
window.addEventListener("touchend", pointerEnd);

newGameButton.addEventListener("click", () => startGame(1));
continueButton.addEventListener("click", () => startGame(score >= target ? level + 1 : level));
shuffleButton.addEventListener("click", shuffle);
hintButton.addEventListener("click", findHint);
soundButton.addEventListener("click", () => {
  soundOn = !soundOn;
  soundButton.textContent = soundOn ? "Sound On" : "Sound Off";
  soundButton.setAttribute("aria-pressed", String(soundOn));
});

startGame();
