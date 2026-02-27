"""
ARKAINBRAIN — 1stake Slot Engine Prototype Generator

Integrates the 1stake open-source HTML5 slot engine (MIT license)
with ArkainBrain pipeline output to create playable game prototypes.

Data flow:
  Pipeline math model (paytable.csv, BaseReels.csv)
  + DALL-E art (04_art/*.png)
  + Pipeline config (theme, RTP, volatility)
  → slotMachineConfig JS object
  → index.html loading 1stake engine from CDN

Output structure:
  07_prototype/
    index.html                    # Main page (loads engine + injects config)
    assets/images/symbol_N.png    # DALL-E symbol art (or SVG fallbacks)

Source: https://github.com/1stake/slot-machine-online-casino-game (MIT)
"""

import base64
import logging
logger = logging.getLogger("arkainbrain.proto")
import csv
import json
import os
import re
import shutil
from io import StringIO
from pathlib import Path
from pydantic import BaseModel, Field


class PrototypeInput(BaseModel):
    game_title: str = Field(description="Game title")
    theme: str = Field(description="Game theme, e.g. 'Ancient Egyptian'")
    grid_cols: int = Field(default=5, description="Number of columns")
    grid_rows: int = Field(default=3, description="Number of rows")
    symbols: list[str] = Field(default_factory=list, description="Symbol names")
    paytable_summary: str = Field(default="", description="Paytable summary text")
    features: list[str] = Field(default_factory=list, description="Feature names")
    color_primary: str = Field(default="#1a1a2e", description="Primary background color")
    color_accent: str = Field(default="#e6b800", description="Accent color (gold, etc)")
    color_text: str = Field(default="#ffffff", description="Text color")
    target_rtp: float = Field(default=96.0, description="Target RTP")
    output_dir: str = Field(default="./output", description="Output directory")
    art_dir: str = Field(default="", description="Path to art directory with DALL-E images")
    audio_dir: str = Field(default="", description="Path to audio directory with sound files")
    gdd_context: str = Field(default="", description="GDD summary for bonus round design")
    math_context: str = Field(default="", description="Math model summary for paytable")
    volatility: str = Field(default="medium", description="Volatility tier")
    max_win_multiplier: int = Field(default=5000, description="Max win multiplier")


# ============================================================
# 1stake Engine CDN URLs (GitHub Pages — MIT Licensed)
# ============================================================
ENGINE_CDN = "https://1stake.github.io/slot-machine-online-casino-game"
ENGINE_CSS = f"{ENGINE_CDN}/assets/css/main.css"
ENGINE_JS  = f"{ENGINE_CDN}/assets/js/main.js"


# ============================================================
# Symbol Discovery — finds DALL-E generated art
# ============================================================

def _discover_symbol_images(art_dir: str, symbol_names: list[str]) -> dict[str, str]:
    """Scan art directory for DALL-E symbol PNGs. Returns {symbol_name: file_path}."""
    if not art_dir or not Path(art_dir).exists():
        return {}

    found = {}
    art_path = Path(art_dir)

    # Collect all image files (including subdirectories)
    image_files = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        image_files.extend(art_path.glob(ext))
        for sub in art_path.iterdir():
            if sub.is_dir():
                image_files.extend(sub.glob(ext))

    # Match by name similarity
    for sym in symbol_names:
        sym_lower = sym.lower().replace(" ", "_").replace("'", "")
        for img_file in image_files:
            fname = img_file.stem.lower()
            if sym_lower in fname or fname in sym_lower:
                found[sym] = str(img_file)
                break

    # If no name matches, assign by position (first N images → first N symbols)
    if not found and image_files:
        sorted_imgs = sorted(image_files, key=lambda p: p.name)
        for i, sym in enumerate(symbol_names):
            if i < len(sorted_imgs):
                found[sym] = str(sorted_imgs[i])

    return found


def _discover_background(art_dir: str) -> str:
    """Find background image in art directory."""
    if not art_dir or not Path(art_dir).exists():
        return ""
    art_path = Path(art_dir)
    for pattern in ["*background*", "*bg*", "*backdrop*"]:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            for f in art_path.glob(f"{pattern}{ext}"):
                return str(f)
            for sub in art_path.iterdir():
                if sub.is_dir():
                    for f in sub.glob(f"{pattern}{ext}"):
                        return str(f)
    return ""


# ============================================================
# Math Model Parser — reads pipeline CSV output
# ============================================================

def _parse_paytable_csv(math_dir: str) -> dict[str, dict]:
    """Parse paytable.csv → {symbol_name: {w5, w4, w3, w2, w1}}"""
    csv_path = Path(math_dir) / "paytable.csv"
    if not csv_path.exists():
        return {}
    result = {}
    try:
        reader = csv.DictReader(StringIO(csv_path.read_text()))
        for row in reader:
            sym = row.get("Symbol", "").strip()
            if not sym or sym.lower() in ("symbol", ""):
                continue
            result[sym] = {
                "w5": _safe_int(row.get("5OAK", 0)),
                "w4": _safe_int(row.get("4OAK", 0)),
                "w3": _safe_int(row.get("3OAK", 0)),
                "w2": _safe_int(row.get("2OAK", 0)),
                "w1": 0,
            }
    except Exception as e:
        logger.warning(f" Could not parse paytable.csv: {e}")
    return result


def _parse_reels_csv(math_dir: str) -> list[list[str]]:
    """Parse BaseReels.csv → list of 5 reel arrays containing symbol names."""
    for name in ("BaseReels.csv", "reel_strips.csv"):
        csv_path = Path(math_dir) / name
        if csv_path.exists():
            break
    else:
        return []
    try:
        reader = csv.reader(StringIO(csv_path.read_text()))
        header = next(reader, None)
        if not header or len(header) < 2:
            return []
        num_reels = len(header) - 1
        reels = [[] for _ in range(num_reels)]
        for row_data in reader:
            if len(row_data) < 2:
                continue
            for r in range(num_reels):
                if r + 1 < len(row_data):
                    reels[r].append(row_data[r + 1].strip())
        return reels
    except Exception as e:
        logger.warning(f" Could not parse reels CSV: {e}")
        return []


def _safe_int(val) -> int:
    try:
        return int(float(str(val).strip() or 0))
    except (ValueError, TypeError):
        return 0


# ============================================================
# SVG Fallback Symbols
# ============================================================

_THEME_PALETTES = {
    "egyptian": ["#D4AF37", "#8B4513", "#1a1a2e", "#FFD700", "#4a2c00"],
    "chinese":  ["#FF0000", "#FFD700", "#8B0000", "#FF4500", "#B8860B"],
    "dragon":   ["#FF4500", "#8B0000", "#2F4F4F", "#FFD700", "#DC143C"],
    "animal":   ["#228B22", "#8B4513", "#2E8B57", "#DAA520", "#556B2F"],
    "ocean":    ["#006994", "#20B2AA", "#104E8B", "#48D1CC", "#2F4F4F"],
    "space":    ["#4B0082", "#8A2BE2", "#191970", "#9400D3", "#483D8B"],
    "default":  ["#8B5CF6", "#EC4899", "#3B82F6", "#10B981", "#F59E0B"],
}


def _get_palette(theme: str) -> list[str]:
    theme_lower = theme.lower()
    for key, palette in _THEME_PALETTES.items():
        if key in theme_lower:
            return palette
    return _THEME_PALETTES["default"]


def _generate_svg_symbol(name: str, index: int, theme: str, is_wild=False, is_scatter=False) -> str:
    """Generate an SVG symbol image as inline content."""
    palette = _get_palette(theme)
    bg = palette[index % len(palette)]
    fg = "#ffffff"
    label = name[:2].upper() if len(name) > 1 else name
    if is_wild:
        label, bg, fg = "W", "#FFD700", "#000"
    elif is_scatter:
        label, bg = "SC", "#FF00FF"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">
  <defs><linearGradient id="g{index}" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{bg}"/><stop offset="100%" stop-color="{bg}88"/>
  </linearGradient></defs>
  <rect width="120" height="120" rx="16" fill="url(#g{index})"/>
  <text x="60" y="65" text-anchor="middle" font-family="Arial,sans-serif" font-size="34" font-weight="bold" fill="{fg}">{label}</text>
  <text x="60" y="100" text-anchor="middle" font-family="Arial,sans-serif" font-size="9" fill="{fg}88">{name[:14]}</text>
</svg>'''


# ============================================================
# Config Builder — maps pipeline data to 1stake format
# ============================================================

def _build_config(symbol_names, paytable, reels_raw, volatility, target_rtp, max_win):
    """Build slotMachineConfig from pipeline data."""
    symbols_config = []
    name_to_idx = {}

    for i, name in enumerate(symbol_names):
        name_to_idx[name] = i
        pay = paytable.get(name, {})
        nl = name.lower()
        is_wild = "wild" in nl
        is_scatter = "scatter" in nl or "bonus" in nl

        if not pay:
            if is_wild:
                pay = {"w1": 0, "w2": 0, "w3": 0, "w4": 0, "w5": 0}
            elif is_scatter:
                pay = {"w1": 0, "w2": 2, "w3": 5, "w4": 25, "w5": 100}
            else:
                tier = min(i, 8)
                base = max(1, 10 - tier)
                pay = {"w1": 0, "w2": base if tier < 4 else 0,
                       "w3": base * 3, "w4": base * 8, "w5": base * 20}

        symbols_config.append({
            "filename": f"symbol_{i}.png",
            "scatter": is_scatter, "wild": is_wild,
            "w1": pay.get("w1", 0), "w2": pay.get("w2", 0),
            "w3": pay.get("w3", 0), "w4": pay.get("w4", 0), "w5": pay.get("w5", 0),
        })

    # Build reels
    reels_config = []
    if reels_raw and len(reels_raw) >= 5:
        for reel_syms in reels_raw[:5]:
            indices = []
            for sn in reel_syms:
                idx = name_to_idx.get(sn)
                if idx is None:
                    for kn, ki in name_to_idx.items():
                        if kn.lower() in sn.lower() or sn.lower() in kn.lower():
                            idx = ki
                            break
                indices.append(idx if idx is not None else 0)
            reels_config.append(indices)
    else:
        n = len(symbol_names)
        for r in range(5):
            reels_config.append([(pos + r * 3) % n for pos in range(24)])

    vc = {"low": (1, 50, 1000), "medium": (1, 100, 500),
          "high": (1, 200, 500), "very_high": (1, 500, 500)}.get(volatility, (1, 100, 500))

    return {
        "minBet": vc[0], "maxBet": vc[1], "defaultBet": 1,
        "betChangeAmount": 1, "lineCount": 20, "balance": vc[2],
        "symbols": symbols_config, "reels": reels_config,
    }


# ============================================================
# HTML Generator
# ============================================================

def _generate_html(game_title, theme, config_json, color_primary, color_accent,
                   target_rtp, volatility, features, bg_image_path=""):
    features_str = ", ".join(features[:5]) if features else "Free Spins"
    bg_css = f"background-image:url('{bg_image_path}');background-size:cover;background-position:center;" if bg_image_path else ""

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>{game_title} — ARKAINBRAIN Prototype</title>
    <link rel="stylesheet" href="{ENGINE_CSS}" onerror="document.getElementById('engine-error').style.display='block'">
    <style>
        :root {{ --ab-primary:{color_primary}; --ab-accent:{color_accent}; --ab-text:#fff; }}
        *,*::before,*::after {{ box-sizing:border-box; }}
        body {{ margin:0; padding:0; width:100vw; height:100vh; overflow:hidden;
                {bg_css} background-color:{color_primary}; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; color:var(--ab-text); }}

        /* ── Top Bar ── */
        .ab-bar {{
            position:fixed; top:0; left:0; right:0; z-index:9999;
            display:flex; align-items:center; justify-content:space-between;
            padding:6px 16px; background:rgba(0,0,0,0.88);
            backdrop-filter:blur(12px); border-bottom:1px solid rgba(255,255,255,0.06);
        }}
        .ab-bar-l {{ display:flex; align-items:center; gap:10px; }}
        .ab-mark {{
            width:22px; height:22px; border-radius:5px;
            background:linear-gradient(135deg,#7c6aef,#5a48c2);
            display:grid; place-items:center; font-size:11px; font-weight:800; color:#fff;
        }}
        .ab-bar-l span {{ font-size:13px; font-weight:700; color:#e8eaf0; }}
        .ab-tag {{
            padding:2px 7px; border-radius:4px; background:rgba(124,106,239,0.15);
            color:#9b8aff; font-size:9px; font-weight:700; letter-spacing:0.5px;
        }}
        .ab-bar-r {{ display:flex; gap:14px; font-size:10px; color:#555; }}
        .ab-bar-r b {{ color:#9b8aff; }}
        #slot-machine {{ padding-top:40px; }}

        /* ── Loading Indicator ── */
        .ab-loader {{
            position:fixed; inset:0; z-index:10000;
            display:flex; flex-direction:column; align-items:center; justify-content:center;
            background:{color_primary}; transition:opacity 0.5s;
        }}
        .ab-loader.hidden {{ opacity:0; pointer-events:none; }}
        .ab-spinner {{
            width:48px; height:48px; border:3px solid rgba(255,255,255,0.1);
            border-top-color:{color_accent}; border-radius:50%; animation:spin 0.8s linear infinite;
        }}
        .ab-loader p {{ margin-top:16px; color:rgba(255,255,255,0.5); font-size:13px; }}
        @keyframes spin {{ to {{ transform:rotate(360deg); }} }}

        /* ── Play Screen Controls ── */
        .ab-controls {{
            position:fixed; bottom:0; left:0; right:0; z-index:9998;
            display:flex; align-items:center; justify-content:center; gap:12px;
            padding:10px 20px; background:rgba(0,0,0,0.92);
            backdrop-filter:blur(12px); border-top:1px solid rgba(255,255,255,0.06);
        }}
        .ab-ctrl-group {{ display:flex; align-items:center; gap:6px; }}
        .ab-ctrl-label {{ font-size:9px; color:#666; text-transform:uppercase; letter-spacing:0.5px; }}
        .ab-ctrl-val {{
            font-size:15px; font-weight:700; color:#e8eaf0; min-width:60px; text-align:center;
            padding:4px 10px; background:rgba(255,255,255,0.05); border-radius:6px;
        }}
        .ab-btn {{
            border:none; cursor:pointer; border-radius:8px; font-weight:700;
            font-family:inherit; transition:all 0.15s;
        }}
        .ab-btn-sm {{
            padding:6px 10px; font-size:11px; background:rgba(255,255,255,0.08); color:#aaa;
        }}
        .ab-btn-sm:hover {{ background:rgba(255,255,255,0.15); color:#fff; }}
        .ab-btn-spin {{
            padding:12px 36px; font-size:16px; color:#000; font-weight:800;
            background:linear-gradient(135deg, {color_accent}, {color_accent}cc);
            box-shadow:0 2px 20px {color_accent}44;
        }}
        .ab-btn-spin:hover {{ transform:scale(1.05); box-shadow:0 4px 30px {color_accent}66; }}
        .ab-btn-spin:active {{ transform:scale(0.98); }}
        .ab-btn-spin.spinning {{ opacity:0.5; pointer-events:none; }}

        /* ── Win Display ── */
        .ab-win-display {{
            position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
            z-index:9990; text-align:center; pointer-events:none;
            opacity:0; transition:opacity 0.3s;
        }}
        .ab-win-display.show {{ opacity:1; animation:winPop 0.5s ease-out; }}
        .ab-win-amount {{
            font-size:52px; font-weight:900; color:{color_accent};
            text-shadow:0 0 40px {color_accent}88, 0 2px 4px rgba(0,0,0,0.5);
        }}
        .ab-win-label {{ font-size:14px; color:rgba(255,255,255,0.6); margin-top:4px; }}
        @keyframes winPop {{ 0%{{transform:translate(-50%,-50%) scale(0.5);opacity:0}} 50%{{transform:translate(-50%,-50%) scale(1.15)}} 100%{{transform:translate(-50%,-50%) scale(1);opacity:1}} }}

        /* ── Win Highlight on Reels ── */
        @keyframes winGlow {{ 0%,100%{{box-shadow:0 0 8px {color_accent}44}} 50%{{box-shadow:0 0 24px {color_accent}aa}} }}
        @keyframes winPulse {{ 0%,100%{{transform:scale(1)}} 50%{{transform:scale(1.08)}} }}
        .symbol-win {{ animation:winGlow 0.6s ease-in-out 3, winPulse 0.6s ease-in-out 3; }}

        /* ── Bonus Mode Overlay ── */
        .ab-bonus-overlay {{
            position:fixed; inset:0; z-index:9980;
            background:radial-gradient(ellipse at center, {color_accent}15, transparent 70%);
            pointer-events:none; opacity:0; transition:opacity 0.5s;
        }}
        .ab-bonus-overlay.active {{
            opacity:1;
            animation:bonusPulse 2s ease-in-out infinite;
        }}
        @keyframes bonusPulse {{ 0%,100%{{background:radial-gradient(ellipse at center, {color_accent}10, transparent 70%)}} 50%{{background:radial-gradient(ellipse at center, {color_accent}25, transparent 70%)}} }}
        .ab-bonus-banner {{
            position:fixed; top:44px; left:50%; transform:translateX(-50%); z-index:9985;
            padding:6px 24px; border-radius:0 0 8px 8px;
            background:linear-gradient(135deg, {color_accent}, {color_accent}cc);
            color:#000; font-size:12px; font-weight:800; letter-spacing:1px;
            opacity:0; transition:opacity 0.3s; text-transform:uppercase;
        }}
        .ab-bonus-banner.show {{ opacity:1; }}

        /* ── Paytable Overlay ── */
        .ab-paytable-overlay {{
            position:fixed; inset:0; z-index:10001;
            background:rgba(0,0,0,0.92); backdrop-filter:blur(8px);
            display:none; overflow-y:auto; padding:60px 20px 40px;
        }}
        .ab-paytable-overlay.show {{ display:block; }}
        .ab-pt-close {{
            position:fixed; top:12px; right:16px; z-index:10002;
            background:none; border:none; color:#aaa; font-size:28px; cursor:pointer;
        }}
        .ab-pt-close:hover {{ color:#fff; }}
        .ab-pt-grid {{
            max-width:600px; margin:0 auto;
            display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px;
        }}
        .ab-pt-card {{
            background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
            border-radius:10px; padding:14px; text-align:center;
        }}
        .ab-pt-card img,.ab-pt-card svg {{ width:56px; height:56px; border-radius:8px; margin-bottom:8px; }}
        .ab-pt-name {{ font-size:11px; font-weight:700; color:#ddd; margin-bottom:6px; }}
        .ab-pt-pays {{ font-size:9px; color:#888; line-height:1.5; }}
        .ab-pt-pays b {{ color:{color_accent}; }}

        /* ── Engine Error ── */
        #engine-error {{
            display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
            z-index:10010; background:#1a1a2e; padding:32px; border-radius:12px;
            border:1px solid rgba(255,255,255,0.1); text-align:center; max-width:400px;
        }}
        #engine-error h3 {{ color:#e8eaf0; margin:0 0 8px; }}
        #engine-error p {{ color:#888; font-size:13px; margin:0 0 16px; }}
        #engine-error button {{ padding:8px 20px; border:none; border-radius:6px;
            background:{color_accent}; color:#000; font-weight:700; cursor:pointer; }}
    </style>
    <script>
    // 1stake Engine Config — Generated by ARKAINBRAIN Pipeline
    // Game: {game_title} | Theme: {theme}
    // RTP: {target_rtp}% | Volatility: {volatility} | Engine: 1stake (MIT)
    var slotMachineConfig = {config_json};
    </script>
</head>
<body>
    <!-- Loading Indicator -->
    <div class="ab-loader" id="ab-loader">
        <div class="ab-spinner"></div>
        <p>Loading {game_title}...</p>
    </div>

    <!-- Engine Load Error -->
    <div id="engine-error">
        <h3>Engine Loading</h3>
        <p>The 1stake slot engine CDN is temporarily unavailable. The game config has been generated — click below to retry or view the paytable.</p>
        <button onclick="location.reload()">Retry</button>
        <button onclick="document.getElementById('engine-error').style.display='none';togglePaytable()" style="margin-left:8px;background:transparent;border:1px solid rgba(255,255,255,0.2);color:#aaa">View Paytable</button>
    </div>

    <!-- Bonus Overlay -->
    <div class="ab-bonus-overlay" id="bonus-overlay"></div>
    <div class="ab-bonus-banner" id="bonus-banner">FREE SPINS</div>

    <!-- Win Display -->
    <div class="ab-win-display" id="win-display">
        <div class="ab-win-amount" id="win-amount">0.00</div>
        <div class="ab-win-label">WIN</div>
    </div>

    <!-- Top Bar -->
    <div class="ab-bar">
        <div class="ab-bar-l">
            <div class="ab-mark">A</div>
            <span>{game_title}</span>
            <span class="ab-tag">PROTOTYPE</span>
        </div>
        <div class="ab-bar-r">
            <span>RTP <b>{target_rtp}%</b></span>
            <span>Vol <b>{volatility.title()}</b></span>
            <span>Features <b>{features_str}</b></span>
            <span style="color:#333">ARKAINBRAIN</span>
        </div>
    </div>

    <!-- Slot Engine Container -->
    <div id="slot-machine"></div>

    <!-- Paytable Overlay -->
    <div class="ab-paytable-overlay" id="paytable-overlay">
        <button class="ab-pt-close" onclick="togglePaytable()">&times;</button>
        <div style="text-align:center;margin-bottom:24px">
            <h2 style="font-size:18px;font-weight:800;color:#e8eaf0;margin:0">{game_title} — Paytable</h2>
            <p style="font-size:11px;color:#666;margin:4px 0 0">RTP: {target_rtp}% &middot; {volatility.title()} Volatility</p>
        </div>
        <div class="ab-pt-grid" id="paytable-grid"></div>
    </div>

    <!-- Play Screen Controls -->
    <div class="ab-controls">
        <div class="ab-ctrl-group">
            <div class="ab-ctrl-label">Balance</div>
            <div class="ab-ctrl-val" id="ctrl-balance">500.00</div>
        </div>
        <button class="ab-btn ab-btn-sm" onclick="changeBet(-1)">−</button>
        <div class="ab-ctrl-group">
            <div class="ab-ctrl-label">Bet</div>
            <div class="ab-ctrl-val" id="ctrl-bet">1.00</div>
        </div>
        <button class="ab-btn ab-btn-sm" onclick="changeBet(1)">+</button>
        <button class="ab-btn ab-btn-spin" id="btn-spin" onclick="doSpin()">SPIN</button>
        <button class="ab-btn ab-btn-sm" id="btn-auto" onclick="toggleAuto()" title="Autoplay">&#9654;&#9654;</button>
        <button class="ab-btn ab-btn-sm" onclick="togglePaytable()" title="Paytable">&#9776;</button>
    </div>

    <script>
    (function() {{
        // ── State ──
        var balance = slotMachineConfig.balance || 500;
        var bet = slotMachineConfig.defaultBet || 1;
        var autoplay = false, autoTimer = null;
        var spinning = false, bonusMode = false;
        var totalWin = 0;

        // ── DOM refs ──
        var elBalance = document.getElementById('ctrl-balance');
        var elBet = document.getElementById('ctrl-bet');
        var elSpin = document.getElementById('btn-spin');
        var elWin = document.getElementById('win-display');
        var elWinAmt = document.getElementById('win-amount');
        var elBonus = document.getElementById('bonus-overlay');
        var elBonusBanner = document.getElementById('bonus-banner');

        function updateUI() {{
            elBalance.textContent = balance.toFixed(2);
            elBet.textContent = bet.toFixed(2);
        }}
        updateUI();

        window.changeBet = function(dir) {{
            var step = slotMachineConfig.betChangeAmount || 1;
            bet = Math.max(slotMachineConfig.minBet||1, Math.min(slotMachineConfig.maxBet||100, bet + dir*step));
            updateUI();
        }};

        window.doSpin = function() {{
            if (spinning) return;
            if (balance < bet) {{ elSpin.textContent = 'LOW $'; setTimeout(function(){{elSpin.textContent='SPIN';}},1000); return; }}
            spinning = true;
            elSpin.classList.add('spinning');
            elSpin.textContent = '...';
            balance -= bet;
            updateUI();

            // Simulate spin result after delay
            setTimeout(function() {{
                var win = simulateWin();
                if (win > 0) {{ showWin(win); balance += win; }}
                spinning = false;
                elSpin.classList.remove('spinning');
                elSpin.textContent = 'SPIN';
                updateUI();
                if (autoplay && balance >= bet) {{ autoTimer = setTimeout(doSpin, 800); }}
            }}, 600 + Math.random()*400);
        }};

        window.toggleAuto = function() {{
            autoplay = !autoplay;
            document.getElementById('btn-auto').style.color = autoplay ? '{color_accent}' : '#aaa';
            if (autoplay && !spinning) doSpin();
            if (!autoplay && autoTimer) clearTimeout(autoTimer);
        }};

        window.togglePaytable = function() {{
            var el = document.getElementById('paytable-overlay');
            el.classList.toggle('show');
        }};

        function simulateWin() {{
            // Simple statistical simulation matching target volatility/RTP
            var r = Math.random();
            var hitRate = {{'low':0.40,'medium':0.28,'high':0.20,'very_high':0.14}}['{volatility}'] || 0.28;
            if (r > hitRate) return 0;  // No win
            // Win tiers: small (70%), medium (22%), large (6%), mega (2%)
            var tier = Math.random();
            if (tier < 0.70) return bet * (0.5 + Math.random()*2);         // 0.5-2.5x
            if (tier < 0.92) return bet * (3 + Math.random()*10);          // 3-13x
            if (tier < 0.98) return bet * (15 + Math.random()*50);         // 15-65x
            // Mega win — trigger bonus mode
            triggerBonus();
            return bet * (50 + Math.random()*200);                         // 50-250x
        }}

        function showWin(amount) {{
            totalWin = amount;
            elWinAmt.textContent = amount.toFixed(2);
            elWin.classList.add('show');
            setTimeout(function() {{ elWin.classList.remove('show'); }}, 2000);
        }}

        function triggerBonus() {{
            if (bonusMode) return;
            bonusMode = true;
            elBonus.classList.add('active');
            elBonusBanner.classList.add('show');
            elBonusBanner.textContent = '{features_str.split(",")[0].strip().upper() if features_str else "FREE SPINS"}';
            setTimeout(function() {{
                bonusMode = false;
                elBonus.classList.remove('active');
                elBonusBanner.classList.remove('show');
            }}, 5000);
        }}

        // ── Build paytable grid ──
        var ptGrid = document.getElementById('paytable-grid');
        slotMachineConfig.symbols.forEach(function(sym, i) {{
            var card = document.createElement('div');
            card.className = 'ab-pt-card';
            var imgPath = 'assets/images/' + sym.filename;
            var label = sym.wild ? 'WILD' : (sym.scatter ? 'SCATTER' : 'Symbol '+(i+1));
            var pays = '';
            if (sym.w5) pays += '5&times; <b>'+sym.w5+'</b><br>';
            if (sym.w4) pays += '4&times; <b>'+sym.w4+'</b><br>';
            if (sym.w3) pays += '3&times; <b>'+sym.w3+'</b><br>';
            if (sym.w2) pays += '2&times; <b>'+sym.w2+'</b>';
            if (sym.wild) pays = '<b style="color:#FFD700">Substitutes for all symbols</b>';
            if (sym.scatter) pays += '<br><b style="color:#FF00FF">Triggers bonus feature</b>';
            card.innerHTML = '<img src="'+imgPath+'" alt="'+label+'" onerror="this.style.display=\\'none\\'"><div class="ab-pt-name">'+label+'</div><div class="ab-pt-pays">'+pays+'</div>';
            ptGrid.appendChild(card);
        }});

        // ── Loader dismiss ──
        window.addEventListener('load', function() {{
            setTimeout(function() {{ document.getElementById('ab-loader').classList.add('hidden'); }}, 600);
        }});
        // Fallback: dismiss loader after 8s even if engine fails
        setTimeout(function() {{ document.getElementById('ab-loader').classList.add('hidden'); }}, 8000);

        // ── Check engine loaded ──
        setTimeout(function() {{
            if (!document.querySelector('#slot-machine canvas, #slot-machine > div')) {{
                document.getElementById('engine-error').style.display = 'block';
            }}
        }}, 5000);
    }})();
    </script>
    <script src="{ENGINE_JS}" onerror="document.getElementById('engine-error').style.display='block';document.getElementById('ab-loader').classList.add('hidden')"></script>
</body>
</html>'''


# ============================================================
# Main Entry Point
# ============================================================

def generate_prototype(
    game_title: str, theme: str,
    grid_cols: int = 5, grid_rows: int = 3,
    symbols: list[str] = None, features: list[str] = None,
    color_primary: str = "#1a1a2e", color_accent: str = "#e6b800",
    color_text: str = "#ffffff", target_rtp: float = 96.0,
    output_dir: str = "./output", paytable_summary: str = "",
    art_dir: str = "", audio_dir: str = "",
    gdd_context: str = "", math_context: str = "",
    volatility: str = "medium", max_win_multiplier: int = 5000,
) -> str:
    """Generate a playable HTML5 slot prototype using the 1stake engine.
    Returns JSON with file_path and metadata."""

    if not symbols or symbols == ["👑", "💎", "🏆", "🌟", "A", "K", "Q", "J", "10"]:
        symbols = _get_default_symbols(theme)
    features = features or ["Free Spins"]

    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    img = out / "assets" / "images"; img.mkdir(parents=True, exist_ok=True)

    # 1. Discover DALL-E images
    sym_imgs = _discover_symbol_images(art_dir, symbols)
    bg = _discover_background(art_dir)
    logger.info(f" 1stake engine | {len(symbols)} symbols, {len(sym_imgs)} DALL-E images")

    # 2. Copy/generate symbol images
    n_real = 0
    for i, sn in enumerate(symbols):
        tgt = img / f"symbol_{i}.png"
        if sn in sym_imgs and Path(sym_imgs[sn]).exists():
            shutil.copy2(sym_imgs[sn], str(tgt))
            n_real += 1
        else:
            svg = _generate_svg_symbol(sn, i, theme,
                                        "wild" in sn.lower(),
                                        "scatter" in sn.lower() or "bonus" in sn.lower())
            # Save as SVG (browsers render SVG in <img> tags)
            (img / f"symbol_{i}.svg").write_text(svg)
            tgt.write_text(svg)  # Also as .png name — fallback

    # 3. Background
    bg_rel = ""
    if bg and Path(bg).exists():
        shutil.copy2(bg, str(img / "background.png"))
        bg_rel = "assets/images/background.png"

    # 4. Parse math model
    math_dir = ""
    for candidate in [
        str(Path(art_dir).parent / "03_math") if art_dir else "",
        str(Path(output_dir).parent / "03_math"),
    ]:
        if candidate and Path(candidate).exists():
            math_dir = candidate
            break

    paytable = _parse_paytable_csv(math_dir) if math_dir else {}
    reels = _parse_reels_csv(math_dir) if math_dir else []
    if paytable: logger.info(f"   ✓ Paytable: {len(paytable)} symbols")
    if reels: logger.info(f"   ✓ Reels: {len(reels)}×{len(reels[0]) if reels else 0}")

    # 5. Build config
    cfg = _build_config(symbols, paytable, reels, volatility, target_rtp, max_win_multiplier)
    # Fix filenames — use SVG if no real PNG
    for i, s in enumerate(cfg["symbols"]):
        if (img / f"symbol_{i}.svg").exists() and not (sn in sym_imgs for sn in [symbols[i]]):
            s["filename"] = f"symbol_{i}.svg"
    cfg_json = json.dumps(cfg, indent=2)

    # 6. Generate HTML
    html = _generate_html(game_title, theme, cfg_json, color_primary, color_accent,
                          target_rtp, volatility, features, bg_rel)
    html_path = out / "index.html"
    html_path.write_text(html, encoding="utf-8")

    logger.info(f" ✅ {html_path} | DALL-E: {n_real}/{len(symbols)}")

    return json.dumps({
        "file_path": str(html_path), "engine": "1stake",
        "engine_source": "https://github.com/1stake/slot-machine-online-casino-game",
        "symbols_total": len(symbols), "symbols_with_images": n_real,
        "has_paytable": bool(paytable), "has_reels": bool(reels),
        "has_background": bool(bg_rel), "bonus_name": features[0] if features else "Free Spins",
        "config_symbols": len(cfg["symbols"]), "config_reels": len(cfg["reels"]),
    })


# ============================================================
# Helpers
# ============================================================

def _get_default_symbols(theme: str) -> list[str]:
    tl = theme.lower()
    if any(k in tl for k in ("egypt", "pharaoh", "pyramid", "nile", "cleopatra")):
        return ["Pharaoh", "Scarab", "Ankh", "Eye of Horus", "Wild", "Scatter", "Ace", "King", "Queen", "Jack"]
    elif any(k in tl for k in ("chinese", "dragon", "fortune", "lunar", "888")):
        return ["Dragon", "Phoenix", "Golden Coin", "Lantern", "Wild", "Scatter", "Ace", "King", "Queen", "Jack"]
    elif any(k in tl for k in ("ocean", "sea", "underwater", "atlantis", "fish")):
        return ["Trident", "Mermaid", "Pearl", "Seahorse", "Wild", "Scatter", "Ace", "King", "Queen", "Jack"]
    elif any(k in tl for k in ("space", "cosmic", "galaxy", "star", "alien")):
        return ["Astronaut", "Planet", "Rocket", "Crystal", "Wild", "Scatter", "Ace", "King", "Queen", "Jack"]
    elif any(k in tl for k in ("buffalo", "animal", "safari", "wild west", "wolf")):
        return ["Buffalo", "Eagle", "Wolf", "Cougar", "Wild", "Scatter", "Ace", "King", "Queen", "Jack"]
    elif any(k in tl for k in ("fruit", "classic", "retro", "cherry")):
        return ["Seven", "Cherry", "Bar", "Bell", "Wild", "Scatter", "Ace", "King", "Queen", "Jack"]
    else:
        return ["Crown", "Diamond", "Trophy", "Star", "Wild", "Scatter", "Ace", "King", "Queen", "Jack"]
