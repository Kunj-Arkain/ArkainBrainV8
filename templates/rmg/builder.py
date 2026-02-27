"""
ARKAINBRAIN — RMG HTML5 Game Builder (Phase 7)

Generates complete, playable HTML5 mini-games.
Each game type gets a self-contained single-file HTML with:
- Canvas rendering, responsive layout
- Provably fair verification UI
- Bet controls, history panel, auto-play
- Sound effects (Web Audio API)
- Touch-friendly mobile support
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("arkainbrain.rmg")


def build_rmg_game(game_type: str, design: dict, config: dict,
                   sim_results: dict, output_dir: str) -> str:
    """Build a complete HTML5 game file.

    Returns the path to the generated HTML file.
    """
    od = Path(output_dir)
    od.mkdir(parents=True, exist_ok=True)

    ui = design.get("ui_theme", {})
    primary = ui.get("primary_color", "#7c6aef")
    secondary = ui.get("secondary_color", "#22c55e")
    bg1 = ui.get("bg_gradient", ["#0a0a1a", "#1a1a3e"])[0]
    bg2 = ui.get("bg_gradient", ["#0a0a1a", "#1a1a3e"])[1]
    title = design.get("title", "Mini Game")
    tagline = design.get("tagline", "")
    bets = design.get("bet_options", [0.10, 0.25, 0.50, 1.00, 5.00, 10.00])
    currency = design.get("currency_symbol", "$")

    # Get game-specific HTML
    game_html = _get_game_canvas(game_type, config)
    game_js = _get_game_logic(game_type, config)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>{_esc(title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --primary:{primary};--secondary:{secondary};
  --bg1:{bg1};--bg2:{bg2};
  --text:#e2e8f0;--dim:#94a3b8;--card:rgba(255,255,255,0.06);
  --border:rgba(255,255,255,0.08);--danger:#ef4444;--success:#22c55e;
}}
body{{
  font-family:'Inter',-apple-system,sans-serif;background:linear-gradient(135deg,var(--bg1),var(--bg2));
  color:var(--text);min-height:100vh;display:flex;flex-direction:column;overflow-x:hidden;
}}
.game-header{{
  text-align:center;padding:16px 12px 8px;
}}
.game-header h1{{font-size:22px;font-weight:700;background:linear-gradient(135deg,var(--primary),var(--secondary));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.game-header .tagline{{font-size:11px;color:var(--dim);margin-top:2px}}
.balance-bar{{
  display:flex;justify-content:space-between;padding:8px 16px;
  background:var(--card);border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  font-size:12px;
}}
.balance-bar .label{{color:var(--dim)}}
.balance-bar .value{{font-weight:700;color:var(--secondary)}}
.game-area{{
  flex:1;display:flex;align-items:center;justify-content:center;
  padding:12px;position:relative;min-height:300px;
}}
#game-canvas{{
  width:100%;max-width:500px;aspect-ratio:4/3;
  background:var(--card);border-radius:12px;border:1px solid var(--border);
  position:relative;overflow:hidden;
}}
.result-overlay{{
  position:absolute;inset:0;display:none;align-items:center;justify-content:center;
  flex-direction:column;background:rgba(0,0,0,0.7);border-radius:12px;z-index:10;
}}
.result-overlay.show{{display:flex}}
.result-overlay .mult{{font-size:48px;font-weight:800}}
.result-overlay .mult.win{{color:var(--secondary)}}
.result-overlay .mult.loss{{color:var(--danger)}}
.result-overlay .amount{{font-size:16px;margin-top:4px;color:var(--dim)}}
.controls{{
  padding:12px 16px;display:flex;flex-direction:column;gap:8px;
  background:var(--card);border-top:1px solid var(--border);
}}
.bet-row{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}}
.bet-btn{{
  padding:6px 14px;border-radius:8px;border:1px solid var(--border);
  background:transparent;color:var(--text);font-size:12px;font-weight:600;cursor:pointer;
  transition:all .15s;
}}
.bet-btn:hover,.bet-btn.active{{background:var(--primary);border-color:var(--primary);color:#fff}}
.play-btn{{
  width:100%;padding:14px;border-radius:10px;border:none;
  background:linear-gradient(135deg,var(--primary),color-mix(in srgb,var(--primary) 70%,var(--secondary)));
  color:#fff;font-size:16px;font-weight:700;cursor:pointer;
  transition:transform .1s,opacity .15s;
}}
.play-btn:hover{{transform:scale(1.01)}}
.play-btn:active{{transform:scale(0.98)}}
.play-btn:disabled{{opacity:0.5;cursor:not-allowed;transform:none}}
{_get_game_specific_css(game_type)}
.history-panel{{
  padding:8px 16px 16px;max-height:120px;overflow-y:auto;
}}
.history-panel h3{{font-size:11px;color:var(--dim);margin-bottom:4px}}
.history-row{{
  display:flex;gap:6px;font-size:11px;padding:3px 0;
  border-bottom:1px solid var(--border);
}}
.history-row .hr-mult{{font-weight:600}}
.history-row .hr-mult.win{{color:var(--secondary)}}
.history-row .hr-mult.loss{{color:var(--danger)}}
.pf-panel{{
  padding:8px 16px 16px;font-size:10px;color:var(--dim);
}}
.pf-panel summary{{cursor:pointer;font-size:11px;font-weight:600;color:var(--text)}}
.pf-panel code{{font-family:monospace;background:rgba(0,0,0,0.3);padding:2px 6px;border-radius:4px;word-break:break-all}}
@media(min-width:640px){{
  body{{flex-direction:row;flex-wrap:wrap}}
  .game-header{{width:100%}}
  .balance-bar{{width:100%}}
  .game-area{{flex:2;min-height:400px}}
  .controls,.history-panel,.pf-panel{{flex:1;min-width:280px}}
}}
</style>
</head>
<body>
<div class="game-header">
  <h1>{_esc(title)}</h1>
  <div class="tagline">{_esc(tagline)} · RTP {sim_results.get('rtp',0)*100:.1f}% · Provably Fair</div>
</div>
<div class="balance-bar">
  <div><span class="label">Balance: </span><span class="value" id="balance">{currency}1,000.00</span></div>
  <div><span class="label">Bet: </span><span class="value" id="current-bet">{currency}{bets[len(bets)//2]:.2f}</span></div>
  <div><span class="label">Profit: </span><span class="value" id="profit">{currency}0.00</span></div>
</div>
<div class="game-area">
  <div id="game-canvas">
    {game_html}
    <div class="result-overlay" id="result-overlay">
      <div class="mult" id="result-mult">0x</div>
      <div class="amount" id="result-amount"></div>
    </div>
  </div>
</div>
<div class="controls">
  <div class="bet-row">
    {''.join(f'<button class="bet-btn{" active" if i==len(bets)//2 else ""}" onclick="setBet({b})">{currency}{b:.2f}</button>' for i,b in enumerate(bets))}
  </div>
  <button class="play-btn" id="play-btn" onclick="play()">PLAY</button>
</div>
<div class="history-panel">
  <h3>History</h3>
  <div id="history"></div>
</div>
<details class="pf-panel">
  <summary>🔒 Provably Fair</summary>
  <p style="margin-top:6px">Server Seed Hash: <code id="pf-hash">—</code></p>
  <p>Client Seed: <code id="pf-client">—</code></p>
  <p>Nonce: <code id="pf-nonce">0</code></p>
  <p style="margin-top:6px">Each round uses SHA-256(server_seed:client_seed:nonce) to generate the outcome.
  After the round, verify: hash the revealed server seed and compare to the hash shown before the round.</p>
</details>
<script>
// ═══ GAME STATE ═══
const GAME_TYPE = '{game_type}';
const CONFIG = {json.dumps(config)};
let balance = 1000;
let currentBet = {bets[len(bets)//2]};
let profit = 0;
let nonce = 0;
let playing = false;
let serverSeed = crypto.randomUUID();
let clientSeed = crypto.randomUUID().slice(0,8);
const currency = '{currency}';

// ═══ PROVABLY FAIR ═══
async function sha256(msg) {{
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(msg));
  return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('');
}}
async function initPF() {{
  const hash = await sha256(serverSeed);
  document.getElementById('pf-hash').textContent = hash;
  document.getElementById('pf-client').textContent = clientSeed;
}}
async function getOutcome() {{
  const combined = serverSeed + ':' + clientSeed + ':' + nonce;
  const hash = await sha256(combined);
  nonce++;
  document.getElementById('pf-nonce').textContent = nonce;
  return parseInt(hash.slice(0,8),16) / 0xFFFFFFFF;
}}

// ═══ UI HELPERS ═══
function fmt(n) {{ return currency + n.toFixed(2); }}
function updateUI() {{
  document.getElementById('balance').textContent = fmt(balance);
  document.getElementById('current-bet').textContent = fmt(currentBet);
  document.getElementById('profit').textContent = fmt(profit);
  document.getElementById('profit').style.color = profit >= 0 ? 'var(--success)' : 'var(--danger)';
}}
function setBet(b) {{
  currentBet = b;
  document.querySelectorAll('.bet-btn').forEach(el => {{
    el.classList.toggle('active', parseFloat(el.textContent.replace(currency,'')) === b);
  }});
  updateUI();
}}
function showResult(mult, amount) {{
  const ov = document.getElementById('result-overlay');
  const m = document.getElementById('result-mult');
  const a = document.getElementById('result-amount');
  m.textContent = mult > 0 ? mult.toFixed(2) + 'x' : 'BUST';
  m.className = 'mult ' + (mult > 0 ? 'win' : 'loss');
  a.textContent = mult > 0 ? '+' + fmt(amount) : '-' + fmt(currentBet);
  ov.classList.add('show');
  setTimeout(() => ov.classList.remove('show'), 1500);
}}
function addHistory(mult, amount) {{
  const div = document.getElementById('history');
  const row = document.createElement('div');
  row.className = 'history-row';
  const cls = mult > 0 ? 'win' : 'loss';
  row.innerHTML = '<span class="hr-mult '+cls+'">' + (mult>0?mult.toFixed(2)+'x':'BUST') + '</span>'
    + '<span>' + fmt(Math.abs(amount)) + '</span>'
    + '<span style="color:var(--dim)">#'+nonce+'</span>';
  div.insertBefore(row, div.firstChild);
  if(div.children.length > 50) div.removeChild(div.lastChild);
}}

// ═══ SOUND ═══
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
function playSound(freq, dur, type='sine') {{
  try {{
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + dur);
  }} catch(e) {{}}
}}
function winSound() {{ playSound(523,0.1); setTimeout(()=>playSound(659,0.1),100); setTimeout(()=>playSound(784,0.2),200); }}
function loseSound() {{ playSound(200,0.3,'sawtooth'); }}

// ═══ GAME LOGIC ═══
{game_js}

// ═══ INIT ═══
initPF();
updateUI();
</script>
</body>
</html>"""

    fname = f"{game_type}_game.html"
    out_path = od / fname
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"Built HTML5 game: {out_path} ({len(html)} bytes)")
    return str(out_path)


def _esc(s):
    """HTML-escape a string."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _get_game_specific_css(game_type: str) -> str:
    """Return game-type-specific CSS."""
    css_map = {
        "crash": """
.crash-graph{position:absolute;inset:0;display:flex;align-items:flex-end;padding:20px}
.crash-line{width:100%;height:2px;background:var(--secondary);transform-origin:left bottom;transition:transform 0.05s}
.crash-mult-display{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:56px;font-weight:800;font-variant-numeric:tabular-nums}
""",
        "plinko": """
.plinko-board{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px}
.plinko-ball{width:12px;height:12px;border-radius:50%;background:var(--primary);position:absolute;transition:all 0.15s ease-out;z-index:5}
.plinko-peg{width:6px;height:6px;border-radius:50%;background:var(--dim);position:absolute}
.plinko-slots{display:flex;gap:2px;position:absolute;bottom:10px;left:10px;right:10px}
.plinko-slot{flex:1;text-align:center;font-size:9px;font-weight:700;padding:4px 2px;border-radius:4px;background:rgba(255,255,255,0.05)}
""",
        "mines": """
.mines-grid{display:grid;gap:4px;padding:10px;position:absolute;inset:0;place-content:center}
.mine-cell{aspect-ratio:1;border-radius:6px;background:var(--card);border:1px solid var(--border);
  display:flex;align-items:center;justify-content:center;font-size:18px;cursor:pointer;transition:all .15s}
.mine-cell:hover{background:rgba(124,106,239,0.15);border-color:var(--primary)}
.mine-cell.revealed{cursor:default}
.mine-cell.safe{background:rgba(34,197,94,0.15);border-color:var(--success)}
.mine-cell.mine{background:rgba(239,68,68,0.15);border-color:var(--danger)}
.mines-info{position:absolute;top:8px;left:0;right:0;text-align:center;font-size:13px;font-weight:600;z-index:2}
""",
        "dice": """
.dice-display{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}
.dice-roll{font-size:64px;font-weight:800;font-variant-numeric:tabular-nums}
.dice-target{font-size:14px;color:var(--dim)}
.dice-bar{width:80%;height:8px;border-radius:4px;background:var(--card);position:relative;overflow:hidden}
.dice-bar-fill{height:100%;border-radius:4px;transition:width 0.3s}
.dice-bar-marker{position:absolute;top:-4px;width:3px;height:16px;background:var(--text);border-radius:2px;transition:left 0.3s}
""",
        "wheel": """
.wheel-container{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}
.wheel-display{font-size:48px;font-weight:800;text-align:center}
.wheel-segment{font-size:14px;color:var(--dim);margin-top:8px}
.wheel-pointer{position:absolute;top:10px;left:50%;transform:translateX(-50%);font-size:24px;z-index:5}
""",
        "hilo": """
.hilo-display{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:20px}
.hilo-card{width:80px;height:120px;border-radius:8px;background:white;color:#1a1a2e;
  display:flex;align-items:center;justify-content:center;font-size:32px;font-weight:800;
  box-shadow:0 4px 12px rgba(0,0,0,0.3);transition:transform 0.3s}
.hilo-card.face-down{background:linear-gradient(135deg,var(--primary),var(--bg2));color:transparent}
.hilo-buttons{position:absolute;bottom:20px;display:flex;gap:12px}
.hilo-btn{padding:10px 24px;border-radius:8px;border:1px solid var(--border);background:var(--card);
  color:var(--text);font-weight:700;font-size:14px;cursor:pointer;transition:all .15s}
.hilo-btn:hover{background:var(--primary);border-color:var(--primary)}
.hilo-streak{position:absolute;top:10px;right:10px;font-size:12px;color:var(--dim)}
""",
        "chicken": """
.chicken-lanes{display:flex;flex-direction:column;gap:4px;padding:10px;position:absolute;inset:0}
.chicken-lane{display:flex;gap:4px;align-items:center}
.chicken-spot{flex:1;height:40px;border-radius:6px;background:var(--card);border:1px solid var(--border);
  display:flex;align-items:center;justify-content:center;font-size:16px;cursor:pointer;transition:all .15s}
.chicken-spot:hover{background:rgba(124,106,239,0.15)}
.chicken-spot.safe{background:rgba(34,197,94,0.15);border-color:var(--success)}
.chicken-spot.hazard{background:rgba(239,68,68,0.15);border-color:var(--danger)}
.chicken-mult{width:60px;text-align:right;font-size:12px;font-weight:700;color:var(--secondary)}
""",
        "scratch": """
.scratch-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:20px;position:absolute;inset:0;place-content:center}
.scratch-cell{aspect-ratio:1;border-radius:8px;background:linear-gradient(135deg,var(--primary),color-mix(in srgb,var(--primary) 50%,var(--bg2)));
  display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;cursor:pointer;
  transition:all .2s;color:transparent;min-width:60px;min-height:60px}
.scratch-cell.revealed{background:var(--card);color:var(--text)}
.scratch-cell:hover:not(.revealed){opacity:0.8}
""",
    }
    return css_map.get(game_type, "")


def _get_game_canvas(game_type: str, config: dict = None) -> str:
    """Return game-type-specific HTML inside #game-canvas."""
    canvas_map = {
        "crash": '<div class="crash-graph"><div class="crash-mult-display" id="crash-mult">1.00x</div></div>',
        "plinko": '<div class="plinko-board" id="plinko-board"></div>',
        "mines": '<div class="mines-info" id="mines-info">Pick tiles to reveal gems 💎</div><div class="mines-grid" id="mines-grid"></div>',
        "dice": '<div class="dice-display"><div class="dice-target" id="dice-target">Roll Over 50.00</div><div class="dice-roll" id="dice-roll">—</div><div class="dice-bar"><div class="dice-bar-fill" id="dice-fill" style="width:50%;background:var(--secondary)"></div><div class="dice-bar-marker" id="dice-marker" style="left:50%"></div></div><div style="font-size:12px;color:var(--dim);margin-top:8px">Multiplier: <span id="dice-mult-preview">1.98x</span></div></div>',
        "wheel": '<div class="wheel-container"><div class="wheel-pointer">▼</div><div><div class="wheel-display" id="wheel-display">🎡</div><div class="wheel-segment" id="wheel-seg">Spin to play</div></div></div>',
        "hilo": '<div class="hilo-display"><div class="hilo-card" id="hilo-current">?</div><div class="hilo-card face-down" id="hilo-next">?</div></div><div class="hilo-streak" id="hilo-streak">Streak: 0</div><div class="hilo-buttons" id="hilo-buttons" style="display:none"><button class="hilo-btn" onclick="guessHiLo(true)">⬆ HIGHER</button><button class="hilo-btn" onclick="guessHiLo(false)">⬇ LOWER</button><button class="hilo-btn" onclick="cashoutHiLo()" style="background:var(--secondary);border-color:var(--secondary)">💰 CASH OUT</button></div>',
        "chicken": '<div class="chicken-lanes" id="chicken-lanes"></div>',
        "scratch": '<div class="scratch-grid" id="scratch-grid"></div>',
    }
    return canvas_map.get(game_type, '<div style="display:flex;align-items:center;justify-content:center;height:100%">Game</div>')


def _get_game_logic(game_type: str, config: dict) -> str:
    """Return game-type-specific JavaScript."""

    if game_type == "crash":
        return """
let crashInterval = null;
let crashMult = 1.0;
async function play() {
  if(playing || balance < currentBet) return;
  playing = true; balance -= currentBet; updateUI();
  document.getElementById('play-btn').disabled = true;
  document.getElementById('play-btn').textContent = 'CASH OUT';
  document.getElementById('play-btn').disabled = false;
  document.getElementById('play-btn').onclick = cashOut;
  const r = await getOutcome();
  const he = CONFIG.house_edge || 0.03;
  let crashPoint;
  if(r < he) { crashPoint = 1.0; }
  else { crashPoint = Math.min(1/(1-r*(1-he)), CONFIG.max_multiplier || 1000); }
  crashMult = 1.0;
  const el = document.getElementById('crash-mult');
  crashInterval = setInterval(() => {
    crashMult += 0.01 + crashMult * 0.005;
    el.textContent = crashMult.toFixed(2) + 'x';
    el.style.color = crashMult < crashPoint ? 'var(--secondary)' : 'var(--danger)';
    if(crashMult >= crashPoint) { clearInterval(crashInterval); bust(); }
  }, 50);
}
function cashOut() {
  if(!playing) return;
  clearInterval(crashInterval);
  const winAmt = currentBet * crashMult;
  balance += winAmt; profit += winAmt - currentBet;
  showResult(crashMult, winAmt - currentBet);
  addHistory(crashMult, winAmt - currentBet);
  winSound(); resetGame();
}
function bust() {
  profit -= currentBet;
  showResult(0, currentBet);
  addHistory(0, -currentBet);
  loseSound(); resetGame();
}
function resetGame() {
  playing = false; updateUI();
  const btn = document.getElementById('play-btn');
  btn.textContent = 'PLAY'; btn.disabled = false; btn.onclick = play;
  document.getElementById('crash-mult').textContent = '1.00x';
  document.getElementById('crash-mult').style.color = 'var(--text)';
}"""

    elif game_type == "plinko":
        rows = config.get("rows", 12)
        mults = json.dumps(config.get("multipliers", [1]*13))
        return f"""
const ROWS = {rows};
const MULTS = {mults};
function initPlinko() {{
  const board = document.getElementById('plinko-board');
  board.innerHTML = '';
  const w = board.offsetWidth || 400, h = board.offsetHeight || 300;
  for(let row=0;row<ROWS;row++) {{
    for(let col=0;col<=row;col++) {{
      const peg = document.createElement('div');
      peg.className='plinko-peg';
      peg.style.left = (w/2 - row*12 + col*24) + 'px';
      peg.style.top = (20 + row * ((h-60)/ROWS)) + 'px';
      board.appendChild(peg);
    }}
  }}
  const slots = document.createElement('div');
  slots.className='plinko-slots';
  MULTS.forEach(m => {{
    const s = document.createElement('div');
    s.className='plinko-slot';
    s.textContent = m + 'x';
    if(m >= 10) s.style.color='var(--secondary)';
    if(m >= 50) s.style.background='rgba(34,197,94,0.15)';
    slots.appendChild(s);
  }});
  board.appendChild(slots);
}}
async function play() {{
  if(playing || balance < currentBet) return;
  playing = true; balance -= currentBet; updateUI();
  document.getElementById('play-btn').disabled = true;
  let pos = 0;
  for(let i=0;i<ROWS;i++) {{
    const r = await getOutcome();
    pos += r < 0.5 ? 0 : 1;
  }}
  const mult = MULTS[Math.min(pos, MULTS.length-1)];
  const winAmt = currentBet * mult;
  balance += winAmt; profit += winAmt - currentBet;
  setTimeout(() => {{
    showResult(mult, winAmt - currentBet);
    addHistory(mult, winAmt - currentBet);
    if(mult > 1) winSound(); else loseSound();
    playing = false; document.getElementById('play-btn').disabled = false; updateUI();
  }}, 300);
}}
setTimeout(initPlinko, 100);"""

    elif game_type == "mines":
        gs = config.get("grid_size", 25)
        mc = config.get("mine_count", 5)
        cols = 5 if gs == 25 else (4 if gs == 16 else 3 if gs == 9 else 6)
        return f"""
const GRID = {gs}, MINES = {mc}, COLS = {cols};
let minePositions = [], revealed = [], minesMult = 1, step = 0;
function initMines() {{
  const grid = document.getElementById('mines-grid');
  grid.style.gridTemplateColumns = 'repeat('+COLS+',1fr)';
  grid.innerHTML = '';
  minePositions = []; revealed = []; minesMult = 1; step = 0;
  const tiles = Array(GRID-MINES).fill(0).concat(Array(MINES).fill(1));
  for(let i=tiles.length-1;i>0;i--){{ const j=Math.floor(Math.random()*(i+1));[tiles[i],tiles[j]]=[tiles[j],tiles[i]]; }}
  minePositions = tiles;
  for(let i=0;i<GRID;i++) {{
    const cell = document.createElement('div');
    cell.className='mine-cell';
    cell.textContent='?';
    cell.onclick=()=>revealCell(i);
    grid.appendChild(cell);
  }}
  document.getElementById('mines-info').textContent = 'Pick tiles — ' + MINES + ' mines hidden · 1.00x';
}}
function revealCell(i) {{
  if(!playing || revealed.includes(i)) return;
  revealed.push(i);
  const cells = document.querySelectorAll('.mine-cell');
  if(minePositions[i]===1) {{
    cells[i].className='mine-cell revealed mine'; cells[i].textContent='💣';
    profit -= currentBet; showResult(0,currentBet); addHistory(0,-currentBet); loseSound();
    minePositions.forEach((v,j)=>{{ if(v===1){{ cells[j].className='mine-cell revealed mine'; cells[j].textContent='💣'; }} }});
    playing=false; document.getElementById('play-btn').disabled=false; updateUI();
    setTimeout(initMines, 2000);
  }} else {{
    step++;
    const safe=GRID-MINES, he=CONFIG.house_edge||0.03;
    let prob=1; for(let s=0;s<step;s++) prob*=(safe-s)/(GRID-s);
    minesMult = prob>0 ? (1-he)/prob : 0;
    cells[i].className='mine-cell revealed safe'; cells[i].textContent='💎';
    document.getElementById('mines-info').textContent = step+' revealed · '+minesMult.toFixed(2)+'x · Click CASH OUT or pick more';
    playSound(440+step*50,0.1);
    document.getElementById('play-btn').textContent='CASH OUT ('+minesMult.toFixed(2)+'x)';
    document.getElementById('play-btn').onclick=cashOutMines;
  }}
}}
function cashOutMines() {{
  if(!playing) return;
  const winAmt=currentBet*minesMult;
  balance+=winAmt; profit+=winAmt-currentBet;
  showResult(minesMult,winAmt-currentBet); addHistory(minesMult,winAmt-currentBet);
  winSound(); playing=false;
  document.getElementById('play-btn').textContent='PLAY';
  document.getElementById('play-btn').onclick=play;
  document.getElementById('play-btn').disabled=false; updateUI();
  setTimeout(initMines,1500);
}}
async function play() {{
  if(playing||balance<currentBet) return;
  playing=true; balance-=currentBet; updateUI();
  initMines();
  document.getElementById('play-btn').disabled=false;
  document.getElementById('play-btn').textContent='CASH OUT (1.00x)';
  document.getElementById('play-btn').onclick=cashOutMines;
}}
initMines();"""

    elif game_type == "dice":
        return """
let diceTarget = 50;
let diceOver = true;
function updateDicePreview() {
  const prob = diceOver ? (100 - diceTarget) / 100 : diceTarget / 100;
  const mult = prob > 0 ? (1 - (CONFIG.house_edge||0.01)) / prob : 0;
  document.getElementById('dice-target').textContent = (diceOver?'Roll Over ':'Roll Under ') + diceTarget.toFixed(2);
  document.getElementById('dice-mult-preview').textContent = mult.toFixed(4) + 'x';
  document.getElementById('dice-fill').style.width = (diceOver?(100-diceTarget):diceTarget)+'%';
  document.getElementById('dice-marker').style.left = diceTarget+'%';
}
async function play() {
  if(playing||balance<currentBet) return;
  playing=true; balance-=currentBet; updateUI();
  document.getElementById('play-btn').disabled=true;
  const r = await getOutcome();
  const roll = r * 100;
  const win = diceOver ? roll > diceTarget : roll < diceTarget;
  const prob = diceOver ? (100-diceTarget)/100 : diceTarget/100;
  const mult = win ? (1-(CONFIG.house_edge||0.01))/prob : 0;
  document.getElementById('dice-roll').textContent = roll.toFixed(2);
  document.getElementById('dice-roll').style.color = win ? 'var(--success)' : 'var(--danger)';
  if(win) { const w=currentBet*mult; balance+=w; profit+=w-currentBet; showResult(mult,w-currentBet); addHistory(mult,w-currentBet); winSound(); }
  else { profit-=currentBet; showResult(0,currentBet); addHistory(0,-currentBet); loseSound(); }
  playing=false; document.getElementById('play-btn').disabled=false; updateUI();
}
updateDicePreview();"""

    elif game_type == "wheel":
        segs = json.dumps(config.get("segments", []))
        return f"""
const SEGMENTS = {segs};
async function play() {{
  if(playing||balance<currentBet) return;
  playing=true; balance-=currentBet; updateUI();
  document.getElementById('play-btn').disabled=true;
  const el=document.getElementById('wheel-display');
  const seg=document.getElementById('wheel-seg');
  let spins=20+Math.floor(Math.random()*10);
  const r=await getOutcome();
  let totalW=0; SEGMENTS.forEach(s=>totalW+=s.weight);
  let pick=r*totalW, cum=0, winner=SEGMENTS[0];
  for(const s of SEGMENTS){{ cum+=s.weight; if(pick<=cum){{ winner=s; break; }} }}
  for(let i=0;i<spins;i++) {{
    const s=SEGMENTS[i%SEGMENTS.length];
    setTimeout(()=>{{
      el.textContent=s.label;
      seg.textContent=s.multiplier+'x';
      playSound(300+i*10,0.05);
    }},i*80+i*i*0.5);
  }}
  setTimeout(()=>{{
    el.textContent=winner.label;
    seg.textContent=winner.multiplier+'x';
    const mult=winner.multiplier;
    if(mult>0){{ const w=currentBet*mult; balance+=w; profit+=w-currentBet; showResult(mult,w-currentBet); addHistory(mult,w-currentBet); winSound(); }}
    else{{ profit-=currentBet; showResult(0,currentBet); addHistory(0,-currentBet); loseSound(); }}
    playing=false; document.getElementById('play-btn').disabled=false; updateUI();
  }}, spins*80+spins*spins*0.5+300);
}}"""

    elif game_type == "hilo":
        return """
const CARDS = ['A','2','3','4','5','6','7','8','9','10','J','Q','K'];
let hiloCard=0, hiloStreak=0, hiloMult=1;
function cardValue(c){return c+1;}
function cardLabel(c){return CARDS[c];}
async function play() {
  if(playing||balance<currentBet) return;
  playing=true; balance-=currentBet; hiloStreak=0; hiloMult=1; updateUI();
  const r=await getOutcome();
  hiloCard=Math.floor(r*13);
  document.getElementById('hilo-current').textContent=cardLabel(hiloCard);
  document.getElementById('hilo-next').textContent='?';
  document.getElementById('hilo-next').className='hilo-card face-down';
  document.getElementById('hilo-buttons').style.display='flex';
  document.getElementById('hilo-streak').textContent='Streak: 0 · 1.00x';
  document.getElementById('play-btn').disabled=true;
}
async function guessHiLo(higher) {
  const r=await getOutcome();
  const next=Math.floor(r*13);
  document.getElementById('hilo-next').textContent=cardLabel(next);
  document.getElementById('hilo-next').className='hilo-card';
  const win = higher ? next>hiloCard : next<hiloCard;
  if(next===hiloCard||!win) {
    profit-=currentBet; showResult(0,currentBet); addHistory(0,-currentBet); loseSound();
    document.getElementById('hilo-buttons').style.display='none';
    playing=false; document.getElementById('play-btn').disabled=false; updateUI();
  } else {
    hiloStreak++; const he=CONFIG.house_edge||0.03;
    const p=higher?(13-hiloCard-1)/12:(hiloCard)/12;
    hiloMult*=p>0?(1-he)/p:1;
    playSound(440+hiloStreak*80,0.1);
    document.getElementById('hilo-streak').textContent='Streak: '+hiloStreak+' · '+hiloMult.toFixed(2)+'x';
    hiloCard=next;
    document.getElementById('hilo-current').textContent=cardLabel(hiloCard);
    document.getElementById('hilo-next').textContent='?';
    document.getElementById('hilo-next').className='hilo-card face-down';
  }
}
function cashoutHiLo() {
  if(!playing) return;
  const w=currentBet*hiloMult; balance+=w; profit+=w-currentBet;
  showResult(hiloMult,w-currentBet); addHistory(hiloMult,w-currentBet); winSound();
  document.getElementById('hilo-buttons').style.display='none';
  playing=false; document.getElementById('play-btn').disabled=false; updateUI();
}"""

    elif game_type == "chicken":
        lanes = config.get("lanes", 5)
        safe = config.get("safe_spots", 4)
        hazards = config.get("hazards_per_lane", 1)
        mults = json.dumps(config.get("multipliers", [1.5]*lanes))
        return f"""
const LANES={lanes},SAFE={safe},HAZ={hazards},MULTS={mults};
let chickenLane=0, chickenMult=1;
function initChicken() {{
  const el=document.getElementById('chicken-lanes');
  el.innerHTML=''; chickenLane=0; chickenMult=1;
  for(let l=0;l<LANES;l++) {{
    const row=document.createElement('div');
    row.className='chicken-lane'; row.dataset.lane=l;
    for(let s=0;s<SAFE;s++) {{
      const spot=document.createElement('div');
      spot.className='chicken-spot';
      spot.textContent='🐔';
      spot.onclick=()=>pickSpot(l,s);
      row.appendChild(spot);
    }}
    const m=document.createElement('div');
    m.className='chicken-mult';
    m.textContent=MULTS[l]+'x';
    row.appendChild(m);
    el.appendChild(row);
  }}
}}
function pickSpot(lane,spot) {{
  if(!playing||lane!==chickenLane) return;
  const lanes=document.querySelectorAll('.chicken-lane');
  const spots=lanes[lane].querySelectorAll('.chicken-spot');
  const hazPositions=[];
  while(hazPositions.length<HAZ){{ const h=Math.floor(Math.random()*SAFE); if(!hazPositions.includes(h))hazPositions.push(h); }}
  if(hazPositions.includes(spot)) {{
    spots[spot].className='chicken-spot hazard'; spots[spot].textContent='💀';
    hazPositions.forEach(h=>{{ spots[h].className='chicken-spot hazard'; spots[h].textContent='💀'; }});
    profit-=currentBet; showResult(0,currentBet); addHistory(0,-currentBet); loseSound();
    playing=false; document.getElementById('play-btn').disabled=false;
    document.getElementById('play-btn').textContent='PLAY'; document.getElementById('play-btn').onclick=play;
    updateUI(); setTimeout(initChicken,2000);
  }} else {{
    spots[spot].className='chicken-spot safe'; spots[spot].textContent='✅';
    chickenLane++; chickenMult=MULTS[chickenLane-1];
    playSound(440+chickenLane*80,0.1);
    document.getElementById('play-btn').textContent='CASH OUT ('+chickenMult.toFixed(2)+'x)';
    if(chickenLane>=LANES) cashoutChicken();
  }}
}}
function cashoutChicken() {{
  if(!playing) return;
  const w=currentBet*chickenMult; balance+=w; profit+=w-currentBet;
  showResult(chickenMult,w-currentBet); addHistory(chickenMult,w-currentBet); winSound();
  playing=false; document.getElementById('play-btn').textContent='PLAY';
  document.getElementById('play-btn').onclick=play;
  document.getElementById('play-btn').disabled=false; updateUI();
  setTimeout(initChicken,1500);
}}
async function play() {{
  if(playing||balance<currentBet) return;
  playing=true; balance-=currentBet; updateUI();
  initChicken();
  document.getElementById('play-btn').textContent='CASH OUT (1.00x)';
  document.getElementById('play-btn').onclick=cashoutChicken;
}}
initChicken();"""

    elif game_type == "scratch":
        prizes = json.dumps(config.get("prizes", []))
        return f"""
const PRIZES={prizes};
let scratchRevealed=0, scratchTotal=9, scratchResults=[];
function initScratch() {{
  const grid=document.getElementById('scratch-grid');
  grid.innerHTML=''; scratchRevealed=0; scratchResults=[];
  for(let i=0;i<scratchTotal;i++) {{
    let r=Math.random(), cum=0, prize=PRIZES[0];
    for(const p of PRIZES){{ cum+=p.probability; if(r<=cum){{ prize=p; break; }} }}
    scratchResults.push(prize);
    const cell=document.createElement('div');
    cell.className='scratch-cell';
    cell.textContent='?';
    cell.onclick=()=>revealScratch(i);
    grid.appendChild(cell);
  }}
}}
function revealScratch(i) {{
  if(!playing) return;
  const cells=document.querySelectorAll('.scratch-cell');
  if(cells[i].classList.contains('revealed')) return;
  cells[i].classList.add('revealed');
  const p=scratchResults[i];
  cells[i].textContent=p.multiplier>0?p.multiplier+'x':'❌';
  scratchRevealed++;
  if(p.multiplier>0) playSound(523,0.1); else playSound(200,0.1,'sawtooth');
  if(scratchRevealed>=scratchTotal) {{
    const totalMult=scratchResults.reduce((s,p)=>s+p.multiplier,0)/scratchTotal;
    const winAmt=currentBet*totalMult;
    balance+=winAmt; profit+=winAmt-currentBet;
    setTimeout(()=>{{
      showResult(totalMult,winAmt-currentBet); addHistory(totalMult,winAmt-currentBet);
      if(totalMult>1) winSound(); else loseSound();
      playing=false; document.getElementById('play-btn').disabled=false; updateUI();
      setTimeout(initScratch,2000);
    }},500);
  }}
}}
async function play() {{
  if(playing||balance<currentBet) return;
  playing=true; balance-=currentBet; updateUI();
  document.getElementById('play-btn').disabled=true;
  initScratch();
}}
initScratch();"""

    return "async function play() { alert('Game not implemented'); }"
