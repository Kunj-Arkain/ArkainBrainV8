"""
ARKAINBRAIN — Tier 1 Intelligence Upgrades

UPGRADE 6:  VisionQATool          — GPT-4o vision analyzes generated images
UPGRADE 7:  PaytableOptimizerTool — Iterative reel strip optimization converging on target RTP
UPGRADE 8:  JurisdictionIntersect — Computes the legal intersection across multiple markets
UPGRADE 9:  PlayerBehaviorModel   — Simulates player session dynamics, churn risk, engagement
UPGRADE 10: AgentDebateTool       — Multi-round negotiation between designer + mathematician
UPGRADE 11: TrendRadarTool        — Scrapes recent releases to identify market trajectory
"""

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================
# UPGRADE 6: Vision QA — GPT-4o Analyzes Generated Images
# ============================================================
# Every DALL-E image currently flows through unchecked.
# This tool encodes the image as base64, sends it to GPT-4o-vision,
# and gets a structured QA report.

class VisionQAInput(BaseModel):
    image_path: str = Field(description="Path to the image file to analyze")
    qa_context: str = Field(
        default="slot_symbol",
        description="QA context: 'slot_symbol', 'background', 'mood_board', 'logo', 'ui_element'"
    )
    theme: str = Field(default="", description="Game theme for context, e.g. 'Ancient Egyptian'")
    requirements: str = Field(default="", description="Specific requirements to check, e.g. 'must not appeal to minors'")


class VisionQATool(BaseTool):
    """
    Analyzes generated images using GPT-4o vision.

    Checks: symbol distinguishability, color palette consistency, mobile readability,
    regulatory compliance (no minor-appeal), theme adherence, art quality.
    Returns a structured QA report with PASS/WARN/FAIL per criterion.
    """

    name: str = "vision_qa"
    description: str = (
        "Analyze a generated image using AI vision. Checks: symbol distinguishability at small sizes, "
        "color palette coherence, mobile readability, regulatory compliance (UK ASA / responsible gaming), "
        "theme adherence, art quality, and cultural sensitivity. Returns structured QA report with "
        "PASS/WARN/FAIL grades. Use after EVERY image generation to catch problems early."
    )
    args_schema: type[BaseModel] = VisionQAInput

    # QA prompts per context
    QA_PROMPTS: ClassVar[dict] = {
        "slot_symbol": (
            "You are a senior QA analyst reviewing a slot game symbol. Evaluate:\n"
            "1. DISTINGUISHABILITY: Would this be clearly recognizable at 64x64px on a mobile screen?\n"
            "2. COLOR: Are colors vivid enough? Good contrast against dark/light backgrounds?\n"
            "3. STYLE CONSISTENCY: Does it look like it belongs in a professional slot game?\n"
            "4. THEME: Does it match the stated theme?\n"
            "5. REGULATORY: Could this be seen as appealing primarily to children? Any offensive content?\n"
            "6. TECHNICAL: Clean edges? Proper alpha transparency potential? No artifacts?\n"
        ),
        "background": (
            "You are a QA analyst reviewing a slot game background. Evaluate:\n"
            "1. READABILITY: Will game UI elements (reels, buttons, HUD) be readable over this?\n"
            "2. VISUAL DEPTH: Does it create atmosphere without being distracting?\n"
            "3. COLOR BALANCE: Does it work with typical slot UI colors (gold, white text)?\n"
            "4. THEME ADHERENCE: Does it match the stated theme?\n"
            "5. MOBILE: Will it look good cropped to portrait orientation?\n"
            "6. REGULATORY: Nothing inappropriate or targeting minors?\n"
        ),
        "mood_board": (
            "You are a creative director reviewing a mood board concept. Evaluate:\n"
            "1. DISTINCTIVENESS: Does this look different from the 1000 other slots in this theme?\n"
            "2. COHERENCE: Is there a clear visual language and color palette?\n"
            "3. MARKET FIT: Does this feel premium/AAA or budget/generic?\n"
            "4. SCALABILITY: Can this style be maintained across 50+ assets?\n"
            "5. EMOTIONAL IMPACT: Does it evoke the right feeling for the theme?\n"
            "6. COMPETITIVE EDGE: Would a player choose this over existing games visually?\n"
        ),
        "logo": (
            "You are reviewing a slot game logo. Evaluate:\n"
            "1. LEGIBILITY: Is the game name clearly readable?\n"
            "2. BRAND IMPACT: Is it memorable and distinctive?\n"
            "3. SCALABILITY: Will it work at both large (splash screen) and small (lobby thumbnail) sizes?\n"
            "4. THEME FIT: Does it match the game's visual identity?\n"
            "5. TECHNICAL: Clean rendering, no artifacts, good contrast?\n"
        ),
        "ui_element": (
            "You are reviewing a slot game UI element. Evaluate:\n"
            "1. TOUCH TARGET SIZE: Large enough for mobile (minimum 44x44px equivalent)?\n"
            "2. VISUAL HIERARCHY: Is purpose immediately clear?\n"
            "3. ACCESSIBILITY: Good contrast ratio for text? Color-blind friendly?\n"
            "4. CONSISTENCY: Matches the game's visual language?\n"
            "5. STATE CLARITY: Can you tell if it's active/inactive/pressed?\n"
        ),
    }

    def _run(self, image_path: str, qa_context: str = "slot_symbol", theme: str = "", requirements: str = "") -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({"error": "OPENAI_API_KEY not set", "status": "skipped"})

        path = Path(image_path)
        if not path.exists():
            return json.dumps({"error": f"Image not found: {image_path}", "status": "skipped"})

        try:
            import base64
            from openai import OpenAI

            client = OpenAI(api_key=api_key)

            # Encode image
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            ext = path.suffix.lower().lstrip(".")
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")

            # Build the QA prompt
            base_prompt = self.QA_PROMPTS.get(qa_context, self.QA_PROMPTS["slot_symbol"])
            full_prompt = (
                f"{base_prompt}\n"
                f"THEME: {theme}\n"
                f"ADDITIONAL REQUIREMENTS: {requirements}\n\n"
                f"For each criterion, respond with:\n"
                f"- Grade: PASS / WARN / FAIL\n"
                f"- Brief explanation (1 sentence)\n"
                f"- Fix suggestion if WARN or FAIL\n\n"
                f"End with an OVERALL VERDICT: PASS / PASS_WITH_WARNINGS / FAIL\n"
                f"And a 1-sentence summary.\n\n"
                f"Respond in JSON format with keys: criteria (list), overall_verdict, summary"
            )

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": full_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
                    ]
                }],
                max_tokens=1500,
                temperature=0.2,
            )

            result_text = response.choices[0].message.content

            # Try to parse as JSON
            try:
                # Strip markdown code fences
                cleaned = re.sub(r"```json\s*|```\s*", "", result_text).strip()
                parsed = json.loads(cleaned)
                parsed["image_path"] = image_path
                parsed["qa_context"] = qa_context
                return json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                return json.dumps({
                    "image_path": image_path,
                    "qa_context": qa_context,
                    "raw_analysis": result_text,
                    "note": "Could not parse as JSON, returning raw analysis",
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e), "image_path": image_path, "status": "error"})


# ============================================================
# UPGRADE 7: Paytable Optimizer — Iterative RTP Convergence
# ============================================================
# Instead of one-shot simulation hoping RTP lands close,
# this runs an optimization loop:
# 1. Start with initial reel weights
# 2. Simulate
# 3. If RTP too high → reduce high-pay symbol frequency
# 4. If RTP too low → increase high-pay symbol frequency
# 5. Repeat until within ±0.1% of target
#
# This is what real math teams do — iterative convergence.

class PaytableOptInput(BaseModel):
    paytable_json: str = Field(description="JSON string of the paytable: {symbol: {count: payout, ...}, ...}")
    reel_strips_json: str = Field(description="JSON string of reel strips: [[sym1, sym2, ...], [sym1, ...], ...]")
    target_rtp: float = Field(description="Target RTP as percentage, e.g. 96.0")
    grid_cols: int = Field(default=5, description="Number of columns/reels")
    grid_rows: int = Field(default=3, description="Number of rows")
    ways: int = Field(default=243, description="Number of ways or paylines")
    tolerance: float = Field(default=0.1, description="Acceptable RTP deviation in %, e.g. 0.1 means ±0.1%")
    max_iterations: int = Field(default=20, description="Maximum optimization iterations")
    spins_per_iteration: int = Field(default=500000, description="Spins per simulation iteration")


class PaytableOptimizerTool(BaseTool):
    """
    Iteratively optimizes reel strips to converge on exact target RTP.

    Takes initial paytable + reel strips, simulates, adjusts symbol
    frequencies based on RTP deviation, and repeats until the RTP
    is within tolerance. Returns the optimized reel strips and final
    simulation results.

    This is what real game math teams do — not one simulation, but
    iterative convergence to the exact target.
    """

    name: str = "optimize_paytable"
    description: str = (
        "Iteratively optimize reel strips to hit an exact RTP target. Provide the paytable "
        "and initial reel strips. The tool runs a simulation loop, adjusting symbol frequencies "
        "each iteration until RTP converges within ±0.1% of target. Returns optimized reel "
        "strips and final simulation results. Use this AFTER the initial math model to fine-tune "
        "the RTP to exact compliance requirements."
    )
    args_schema: type[BaseModel] = PaytableOptInput

    def _run(self, paytable_json: str, reel_strips_json: str, target_rtp: float,
             grid_cols: int = 5, grid_rows: int = 3, ways: int = 243,
             tolerance: float = 0.1, max_iterations: int = 20,
             spins_per_iteration: int = 500000) -> str:

        # Build the optimization script
        script = f"""
import numpy as np
import json
import copy

# --- Configuration ---
TARGET_RTP = {target_rtp}
TOLERANCE = {tolerance}
MAX_ITERS = {max_iterations}
SPINS = {spins_per_iteration}
COLS = {grid_cols}
ROWS = {grid_rows}
WAYS = {ways}

paytable = json.loads('''{paytable_json}''')
reel_strips = json.loads('''{reel_strips_json}''')

def simulate(reels, pt, n_spins):
    \"\"\"Fast vectorized slot simulation.\"\"\"
    total_wagered = n_spins
    total_won = 0.0

    for _ in range(n_spins):
        # Pick random positions on each reel
        window = []
        for r in range(COLS):
            reel = reels[r]
            pos = np.random.randint(0, len(reel))
            col = []
            for row in range(ROWS):
                col.append(reel[(pos + row) % len(reel)])
            window.append(col)

        # Check for wins (simplified: count symbols on each row from left)
        for sym, pays in pt.items():
            for row in range(ROWS):
                count = 0
                for col in range(COLS):
                    if window[col][row] == sym:
                        count += 1
                    else:
                        break
                pay_key = str(count)
                if pay_key in pays and count >= 3:
                    total_won += pays[pay_key]

    return (total_won / total_wagered) * 100 if total_wagered > 0 else 0

def adjust_reels(reels, current_rtp, target, iteration):
    \"\"\"Adjust symbol frequencies to move RTP toward target.\"\"\"
    adjusted = copy.deepcopy(reels)
    deviation = current_rtp - target
    # Determine adjustment strength (decreases over iterations for fine-tuning)
    strength = max(1, int(abs(deviation) * 2 / (1 + iteration * 0.3)))

    high_pay_symbols = list(paytable.keys())[:3]  # Top 3 highest-paying
    low_pay_symbols = list(paytable.keys())[3:] if len(paytable) > 3 else []

    for r in range(min(len(adjusted), COLS)):
        reel = adjusted[r]
        if deviation > 0:  # RTP too high: reduce high-pay, add low-pay
            for _ in range(strength):
                for sym in high_pay_symbols:
                    if sym in reel and reel.count(sym) > 1:
                        reel.remove(sym)
                        if low_pay_symbols:
                            reel.append(np.random.choice(low_pay_symbols))
                        break
        else:  # RTP too low: add high-pay, remove low-pay
            for _ in range(strength):
                if low_pay_symbols:
                    for sym in low_pay_symbols:
                        if sym in reel and reel.count(sym) > 1:
                            reel.remove(sym)
                            reel.append(np.random.choice(high_pay_symbols))
                            break
                else:
                    reel.append(np.random.choice(high_pay_symbols))

    return adjusted

# --- Optimization Loop ---
history = []
best_reels = copy.deepcopy(reel_strips)
best_deviation = 999

for i in range(MAX_ITERS):
    rtp = simulate(reel_strips, paytable, SPINS)
    deviation = abs(rtp - TARGET_RTP)

    history.append({{"iteration": i+1, "rtp": round(rtp, 4), "deviation": round(deviation, 4)}})

    if deviation < best_deviation:
        best_deviation = deviation
        best_reels = copy.deepcopy(reel_strips)

    if deviation <= TOLERANCE:
        break

    reel_strips = adjust_reels(reel_strips, rtp, TARGET_RTP, i)

# Final high-precision simulation on best reels
final_rtp = simulate(best_reels, paytable, SPINS * 2)

result = {{
    "status": "converged" if best_deviation <= TOLERANCE else "best_effort",
    "target_rtp": TARGET_RTP,
    "final_rtp": round(final_rtp, 4),
    "deviation": round(abs(final_rtp - TARGET_RTP), 4),
    "iterations": len(history),
    "history": history,
    "optimized_reel_strips": best_reels,
    "reel_lengths": [len(r) for r in best_reels],
}}

print(json.dumps(result))
"""
        # Execute
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(script)
            script_path = f.name

        try:
            result = subprocess.run(
                ["python3", script_path],
                capture_output=True, text=True,
                timeout=300, cwd="/tmp",
            )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    parsed = json.loads(result.stdout)
                    return json.dumps(parsed, indent=2)
                except json.JSONDecodeError:
                    return json.dumps({"stdout": result.stdout[:5000], "stderr": result.stderr[:2000]})
            else:
                return json.dumps({"error": "Script failed", "stderr": result.stderr[:3000], "stdout": result.stdout[:2000]})
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Optimization timed out (300s)"})
        finally:
            try: os.unlink(script_path)
            except OSError: pass


# ============================================================
# UPGRADE 8: Multi-Jurisdiction Intersection Engine
# ============================================================
# When targeting UK + Malta + Ontario, this computes the legal
# intersection: tightest RTP range, feature bans across ANY
# market, universal compliance requirements.

class JurisdictionIntersectInput(BaseModel):
    markets: list[str] = Field(description="List of target markets, e.g. ['UK', 'Malta', 'Ontario']")
    proposed_rtp: float = Field(default=96.0, description="Proposed RTP to check")
    proposed_features: list[str] = Field(default_factory=list, description="Proposed features, e.g. ['free_spins', 'bonus_buy', 'multipliers']")
    proposed_max_win: int = Field(default=5000, description="Proposed max win multiplier")


class JurisdictionIntersectionTool(BaseTool):
    """
    Computes the regulatory intersection across multiple target markets.

    Given a list of markets and proposed game parameters, returns:
    - Tightest RTP range that satisfies ALL markets
    - Features banned in ANY market (e.g., bonus buy banned in UK)
    - Universal compliance requirements
    - Per-market breakdown
    - Go/No-Go recommendation

    Use this BEFORE design to set constraints, and AFTER design to validate.
    """

    name: str = "jurisdiction_intersection"
    description: str = (
        "Compute the legal intersection across multiple target markets. Returns: tightest RTP range, "
        "features banned in ANY market, universal compliance requirements, and Go/No-Go per market. "
        "ALWAYS run this before designing a multi-market game to set hard constraints."
    )
    args_schema: type[BaseModel] = JurisdictionIntersectInput

    # Regulatory database (expanded from settings.py)
    REGULATIONS: ClassVar[dict] = {
        "UK": {
            "min_rtp": 70.0, "max_rtp": 99.9,
            "max_win_cap": None,
            "banned_features": ["bonus_buy"],  # Banned Oct 2021
            "required_features": ["reality_check_60min", "session_limits", "loss_limits", "rg_messaging", "self_exclusion"],
            "content_rules": ["no_minor_appeal", "no_gambling_glorification", "no_crypto_only"],
            "certifiers": ["GLI", "BMM", "eCOGRA", "NMi"],
            "data_privacy": "GDPR",
            "notes": "Bonus buy banned since Oct 2021. Strictest content rules in the industry.",
        },
        "Malta": {
            "min_rtp": 85.0, "max_rtp": 99.9,
            "max_win_cap": None,
            "banned_features": [],
            "required_features": ["rng_certification", "rg_messaging"],
            "content_rules": ["no_offensive_content"],
            "certifiers": ["GLI", "BMM", "iTech Labs"],
            "data_privacy": "GDPR",
            "notes": "Relatively permissive. Bonus buy allowed.",
        },
        "Ontario": {
            "min_rtp": 85.0, "max_rtp": 99.9,
            "max_win_cap": None,
            "banned_features": [],
            "required_features": ["rg_tools", "self_exclusion_integration", "play_break_reminders"],
            "content_rules": ["no_inducements_to_problem_gambling"],
            "certifiers": ["GLI", "BMM", "iTech Labs", "Gaming Associates"],
            "data_privacy": "PIPEDA",
            "notes": "Strong responsible gambling focus. Bonus buy allowed but scrutinized.",
        },
        "New Jersey": {
            "min_rtp": 83.0, "max_rtp": 99.9,
            "max_win_cap": None,
            "banned_features": [],
            "required_features": ["geolocation", "age_verification", "rg_features"],
            "content_rules": ["standard_gaming_content"],
            "certifiers": ["GLI", "BMM"],
            "data_privacy": "NJ_privacy_laws",
            "notes": "Geolocation mandatory. Established market.",
        },
        "Curacao": {
            "min_rtp": 75.0, "max_rtp": 99.9,
            "max_win_cap": None,
            "banned_features": [],
            "required_features": ["basic_rg"],
            "content_rules": ["basic_standards"],
            "certifiers": ["GLI", "iTech Labs"],
            "data_privacy": "minimal",
            "notes": "Most permissive jurisdiction. New regulations tightening in 2025+.",
        },
        "Sweden": {
            "min_rtp": 80.0, "max_rtp": 99.9,
            "max_win_cap": None,
            "banned_features": ["bonus_buy", "autoplay"],
            "required_features": ["deposit_limits", "session_limits", "rg_messaging", "panic_button"],
            "content_rules": ["no_minor_appeal", "no_gambling_glorification"],
            "certifiers": ["GLI", "BMM"],
            "data_privacy": "GDPR",
            "notes": "Very strict. Bonus buy AND autoplay banned. Temporary loss limits possible.",
        },
        "Spain": {
            "min_rtp": 85.0, "max_rtp": 99.9,
            "max_win_cap": None,
            "banned_features": ["bonus_buy"],
            "required_features": ["session_limits", "deposit_limits", "rg_messaging"],
            "content_rules": ["no_minor_appeal", "no_celebrity_endorsement"],
            "certifiers": ["GLI", "BMM"],
            "data_privacy": "GDPR",
            "notes": "Advertising restrictions very tight. No celebrity/influencer promotion.",
        },
    }

    def _run(self, markets: list[str], proposed_rtp: float = 96.0,
             proposed_features: list[str] = None, proposed_max_win: int = 5000) -> str:

        proposed_features = proposed_features or []
        results = {"markets": markets, "proposed": {"rtp": proposed_rtp, "features": proposed_features, "max_win": proposed_max_win}}

        # Collect per-market analysis
        market_details = {}
        known_markets = []
        unknown_markets = []

        for m in markets:
            reg = self.REGULATIONS.get(m)
            if reg:
                known_markets.append(m)
                market_details[m] = {
                    "rtp_range": f"{reg['min_rtp']}% - {reg['max_rtp']}%",
                    "rtp_compliant": reg["min_rtp"] <= proposed_rtp <= reg["max_rtp"],
                    "banned_features_hit": [f for f in proposed_features if f in reg["banned_features"]],
                    "required_features": reg["required_features"],
                    "content_rules": reg["content_rules"],
                    "certifiers": reg["certifiers"],
                    "data_privacy": reg["data_privacy"],
                    "notes": reg["notes"],
                }
            else:
                unknown_markets.append(m)
                # Try Qdrant for US states
                try:
                    from tools.qdrant_store import JurisdictionStore
                    store = JurisdictionStore()
                    qdrant_results = store.search(f"{m} gambling law RTP requirements", jurisdiction=m, limit=3)
                    if qdrant_results and "error" not in qdrant_results[0]:
                        market_details[m] = {
                            "source": "qdrant_rag",
                            "data": [r["text"][:500] for r in qdrant_results],
                            "note": "US state data from Qdrant. Manual review of constraints required.",
                        }
                    else:
                        market_details[m] = {"error": f"No data for {m}. Run State Recon first."}
                except Exception:
                    market_details[m] = {"error": f"No data for {m}. Run State Recon first."}

        # Compute intersection
        intersection = {}

        # Tightest RTP range
        min_rtps = [self.REGULATIONS[m]["min_rtp"] for m in known_markets if m in self.REGULATIONS]
        if min_rtps:
            tightest_min = max(min_rtps)  # Highest minimum = tightest constraint
            intersection["rtp_floor"] = tightest_min
            intersection["rtp_compliant"] = proposed_rtp >= tightest_min
            intersection["rtp_headroom"] = round(proposed_rtp - tightest_min, 2)
            intersection["binding_market"] = known_markets[min_rtps.index(max(min_rtps))]

        # Features banned in ANY market
        all_banned = set()
        ban_sources = {}
        for m in known_markets:
            reg = self.REGULATIONS.get(m, {})
            for b in reg.get("banned_features", []):
                all_banned.add(b)
                ban_sources.setdefault(b, []).append(m)

        banned_hits = {f: ban_sources[f] for f in proposed_features if f in all_banned}
        intersection["banned_features"] = dict(ban_sources)
        intersection["proposed_feature_conflicts"] = banned_hits

        # Universal required features (union across all markets)
        all_required = set()
        for m in known_markets:
            all_required.update(self.REGULATIONS.get(m, {}).get("required_features", []))
        intersection["required_features_union"] = sorted(all_required)

        # Common certifiers
        certifier_sets = [set(self.REGULATIONS.get(m, {}).get("certifiers", [])) for m in known_markets]
        if certifier_sets:
            intersection["common_certifiers"] = sorted(set.intersection(*certifier_sets)) if certifier_sets else []

        # Data privacy requirements
        privacy = {m: self.REGULATIONS.get(m, {}).get("data_privacy", "unknown") for m in known_markets}
        intersection["data_privacy"] = privacy
        intersection["strictest_privacy"] = "GDPR" if "GDPR" in privacy.values() else max(privacy.values(), key=len) if privacy else "unknown"

        # Go/No-Go
        blockers = []
        if not intersection.get("rtp_compliant", True):
            blockers.append(f"RTP {proposed_rtp}% below floor of {intersection['rtp_floor']}%")
        for feature, markets_banned in banned_hits.items():
            blockers.append(f"Feature '{feature}' banned in: {', '.join(markets_banned)}")

        intersection["blockers"] = blockers
        intersection["verdict"] = "GO" if not blockers else "NO-GO (fix blockers first)"

        results["per_market"] = market_details
        results["intersection"] = intersection
        results["unknown_markets"] = unknown_markets

        return json.dumps(results, indent=2)


# ============================================================
# UPGRADE 9: Player Behavior Modeler
# ============================================================
# RTP and volatility are math. But how the game FEELS to play
# is behavioral science. This simulates player sessions.

class PlayerBehaviorInput(BaseModel):
    rtp: float = Field(description="Game RTP as percentage, e.g. 96.0")
    volatility: str = Field(description="'low', 'medium', 'high', 'very_high'")
    hit_frequency: float = Field(default=0.25, description="Base game hit frequency (fraction, e.g. 0.25 = 1 in 4)")
    bonus_trigger_rate: float = Field(default=0.005, description="Bonus trigger probability per spin, e.g. 0.005 = 1 in 200")
    bonus_avg_multiplier: float = Field(default=50.0, description="Average bonus win as multiplier of bet")
    max_win: int = Field(default=5000, description="Maximum win multiplier")
    session_budget: float = Field(default=100.0, description="Simulated player's session budget (in bets)")
    bet_size: float = Field(default=1.0, description="Bet per spin")
    num_sessions: int = Field(default=5000, description="Number of player sessions to simulate")


class PlayerBehaviorModelTool(BaseTool):
    """
    Simulates realistic player sessions to model the actual EXPERIENCE
    of playing the game — not just the math.

    Outputs: median session length, bust rate, bonus trigger distribution,
    near-miss frequency, longest dry streak, engagement score, churn risk.

    Use this to catch "mathematically sound but boring" games.
    """

    name: str = "model_player_behavior"
    description: str = (
        "Simulate realistic player sessions. Models: session length, bust rate, bonus trigger "
        "distribution, dry streaks, near-miss psychology, and engagement score. Catches games that "
        "are mathematically valid but would bore or frustrate players. Use AFTER the math model "
        "is complete to validate the player experience."
    )
    args_schema: type[BaseModel] = PlayerBehaviorInput

    def _run(self, rtp: float, volatility: str, hit_frequency: float = 0.25,
             bonus_trigger_rate: float = 0.005, bonus_avg_multiplier: float = 50.0,
             max_win: int = 5000, session_budget: float = 100.0, bet_size: float = 1.0,
             num_sessions: int = 5000) -> str:

        vol_params = {
            "low":       {"base_mean": 1.5,  "base_std": 0.8,  "big_win_chance": 0.001},
            "medium":    {"base_mean": 2.5,  "base_std": 2.0,  "big_win_chance": 0.003},
            "high":      {"base_mean": 4.0,  "base_std": 5.0,  "big_win_chance": 0.008},
            "very_high": {"base_mean": 8.0,  "base_std": 15.0, "big_win_chance": 0.015},
        }

        vp = json.dumps(vol_params.get(volatility, vol_params["medium"]))

        script = f"""
import numpy as np
import json

RTP = {rtp} / 100.0
HIT_FREQ = {hit_frequency}
BONUS_RATE = {bonus_trigger_rate}
BONUS_AVG = {bonus_avg_multiplier}
MAX_WIN = {max_win}
BUDGET = {session_budget}
BET = {bet_size}
N_SESSIONS = {num_sessions}
VOL_PARAMS = json.loads('''{vp}''')

np.random.seed(42)

sessions = []
for _ in range(N_SESSIONS):
    balance = BUDGET
    spins = 0
    wins = 0
    bonuses_triggered = 0
    max_dry_streak = 0
    current_dry = 0
    biggest_win = 0
    near_misses = 0  # Wins just below 2x bet

    while balance >= BET:
        balance -= BET
        spins += 1

        # Base game spin
        if np.random.random() < HIT_FREQ:
            # Win
            if np.random.random() < BONUS_RATE / HIT_FREQ:
                # Bonus trigger
                bonus_win = BET * max(1, min(MAX_WIN, np.random.lognormal(np.log(BONUS_AVG), 1.0)))
                balance += bonus_win
                bonuses_triggered += 1
                biggest_win = max(biggest_win, bonus_win / BET)
            else:
                # Base win
                win = BET * max(0.1, np.random.lognormal(
                    np.log(VOL_PARAMS["base_mean"]), VOL_PARAMS["base_std"] * 0.3
                ))
                win = min(win, BET * MAX_WIN)
                balance += win
                biggest_win = max(biggest_win, win / BET)
                if 0.5 <= win / BET < 2.0:
                    near_misses += 1

            wins += 1
            if current_dry > max_dry_streak:
                max_dry_streak = current_dry
            current_dry = 0
        else:
            current_dry += 1
            # Near-miss: almost had 3 matching but didn't
            if np.random.random() < 0.15:
                near_misses += 1

        # Quit conditions (player behavior)
        if balance >= BUDGET * 3:  # Big win → some players quit
            if np.random.random() < 0.1:
                break
        if spins >= 500:  # Session fatigue
            if np.random.random() < 0.05:
                break

    sessions.append({{
        "spins": spins,
        "final_balance": round(balance, 2),
        "wins": wins,
        "bonuses": bonuses_triggered,
        "max_dry_streak": max_dry_streak,
        "biggest_win_x": round(biggest_win, 1),
        "near_misses": near_misses,
        "busted": balance < BET,
    }})

# Analyze
spin_counts = [s["spins"] for s in sessions]
balances = [s["final_balance"] for s in sessions]
dry_streaks = [s["max_dry_streak"] for s in sessions]
bonus_counts = [s["bonuses"] for s in sessions]
biggest_wins = [s["biggest_win_x"] for s in sessions]
bust_count = sum(1 for s in sessions if s["busted"])

# Engagement scoring (0-100)
# Good: long sessions, bonus triggers, big wins
# Bad: fast busts, long dry streaks, no bonuses
median_spins = np.median(spin_counts)
avg_dry = np.mean(dry_streaks)
bonus_rate_actual = np.mean(bonus_counts) / np.mean(spin_counts) if np.mean(spin_counts) > 0 else 0

engagement = min(100, max(0, int(
    (min(median_spins / 200, 1.0) * 30) +
    (min(np.mean(bonus_counts), 3) / 3 * 25) +
    (max(0, 1 - avg_dry / 80) * 25) +
    (min(np.max(biggest_wins) / MAX_WIN, 1.0) * 20)
)))

# Churn risk
churn_risk = "LOW"
if median_spins < 50:
    churn_risk = "CRITICAL"
elif median_spins < 100:
    churn_risk = "HIGH"
elif median_spins < 150:
    churn_risk = "MEDIUM"

result = {{
    "sessions_simulated": N_SESSIONS,
    "session_metrics": {{
        "median_spins": int(median_spins),
        "mean_spins": round(np.mean(spin_counts), 1),
        "p10_spins": int(np.percentile(spin_counts, 10)),
        "p90_spins": int(np.percentile(spin_counts, 90)),
    }},
    "financial_metrics": {{
        "bust_rate": round(bust_count / N_SESSIONS * 100, 1),
        "avg_final_balance": round(np.mean(balances), 2),
        "median_final_balance": round(np.median(balances), 2),
        "pct_sessions_profitable": round(sum(1 for b in balances if b > BUDGET) / N_SESSIONS * 100, 1),
    }},
    "bonus_metrics": {{
        "avg_bonuses_per_session": round(np.mean(bonus_counts), 2),
        "pct_sessions_with_bonus": round(sum(1 for b in bonus_counts if b > 0) / N_SESSIONS * 100, 1),
        "pct_sessions_zero_bonus": round(sum(1 for b in bonus_counts if b == 0) / N_SESSIONS * 100, 1),
    }},
    "experience_metrics": {{
        "median_dry_streak": int(np.median(dry_streaks)),
        "p90_dry_streak": int(np.percentile(dry_streaks, 90)),
        "max_dry_streak_observed": int(np.max(dry_streaks)),
        "avg_near_misses_per_session": round(np.mean([s["near_misses"] for s in sessions]), 1),
    }},
    "big_win_metrics": {{
        "pct_sessions_with_100x_plus": round(sum(1 for b in biggest_wins if b >= 100) / N_SESSIONS * 100, 2),
        "pct_sessions_with_1000x_plus": round(sum(1 for b in biggest_wins if b >= 1000) / N_SESSIONS * 100, 3),
        "biggest_win_observed": round(max(biggest_wins), 1),
    }},
    "scores": {{
        "engagement_score": engagement,
        "churn_risk": churn_risk,
    }},
    "recommendations": [],
}}

# Generate recommendations
recs = result["recommendations"]
if churn_risk in ("CRITICAL", "HIGH"):
    recs.append(f"CRITICAL: Median session only {{int(median_spins)}} spins. Players will churn fast. Increase hit frequency or reduce volatility.")
if result["bonus_metrics"]["pct_sessions_zero_bonus"] > 60:
    recs.append(f"WARNING: {{result['bonus_metrics']['pct_sessions_zero_bonus']}}% of sessions never trigger bonus. Consider increasing trigger rate.")
if result["experience_metrics"]["p90_dry_streak"] > 50:
    recs.append(f"WARNING: 10% of sessions have dry streaks of {{result['experience_metrics']['p90_dry_streak']}}+ spins. Add guaranteed mini-wins or near-miss animations.")
if result["financial_metrics"]["bust_rate"] > 80:
    recs.append(f"WARNING: {{result['financial_metrics']['bust_rate']}}% bust rate. Game may feel punishing. Consider dead-spin prevention.")
if engagement < 40:
    recs.append("CRITICAL: Engagement score below 40. This game will not retain players.")
elif engagement >= 70:
    recs.append("GOOD: Engagement score above 70. Player experience should be solid.")

print(json.dumps(result))
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(script)
            sp = f.name

        try:
            result = subprocess.run(["python3", sp], capture_output=True, text=True, timeout=120, cwd="/tmp")
            if result.returncode == 0:
                try:
                    return json.dumps(json.loads(result.stdout), indent=2)
                except json.JSONDecodeError:
                    return json.dumps({"stdout": result.stdout[:5000]})
            return json.dumps({"error": "Script failed", "stderr": result.stderr[:3000]})
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Simulation timed out"})
        finally:
            try: os.unlink(sp)
            except OSError: pass


# ============================================================
# UPGRADE 10: Agent Debate Protocol
# ============================================================
# Instead of sequential handoffs, enables multi-round negotiation.
# Designer proposes → Mathematician pushes back → Designer revises → repeat.

class DebateInput(BaseModel):
    topic: str = Field(description="Debate topic, e.g. 'Should we add a 4th free spin retrigger?'")
    designer_position: str = Field(description="Game Designer's proposal with rationale")
    math_constraints: str = Field(description="Mathematical constraints and concerns")
    max_rounds: int = Field(default=3, description="Maximum debate rounds")
    context: str = Field(default="", description="Additional context: GDD summary, RTP budget, etc.")


class AgentDebateTool(BaseTool):
    """
    Facilitates structured multi-round debate between the Game Designer
    and Mathematician perspectives.

    Round structure:
    1. Designer proposes a feature/change with rationale
    2. Mathematician evaluates mathematical feasibility and concerns
    3. Designer modifies proposal to address concerns
    4. Repeat until consensus or max rounds

    Returns the final agreed proposal with mathematical constraints satisfied.
    Use this for ANY contentious design decision.
    """

    name: str = "agent_debate"
    description: str = (
        "Run a structured debate between Game Designer and Mathematician perspectives. "
        "Provide a design proposal and math constraints. The tool simulates a multi-round "
        "negotiation where each side refines the proposal until it's both creatively compelling "
        "AND mathematically feasible. Returns the final consensus proposal."
    )
    args_schema: type[BaseModel] = DebateInput

    def _run(self, topic: str, designer_position: str, math_constraints: str,
             max_rounds: int = 3, context: str = "") -> str:

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({"error": "OPENAI_API_KEY not set"})

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            rounds = []
            current_proposal = designer_position

            for round_num in range(1, max_rounds + 1):
                # Math critique
                math_response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": (
                            "You are a slot game mathematician. You think in RTP budgets, hit frequencies, "
                            "and variance. You respect creative vision but will NOT approve anything that "
                            "breaks the math. Be specific about numbers. If something works, say so."
                        )},
                        {"role": "user", "content": (
                            f"DEBATE ROUND {round_num}/{max_rounds}\n\n"
                            f"TOPIC: {topic}\n"
                            f"CONTEXT: {context}\n"
                            f"MATH CONSTRAINTS: {math_constraints}\n\n"
                            f"DESIGNER'S PROPOSAL:\n{current_proposal}\n\n"
                            f"Evaluate this proposal mathematically. Be specific:\n"
                            f"- What works?\n- What breaks the math?\n- What modifications would make it feasible?\n"
                            f"- Provide specific numbers (RTP impact, trigger rates, etc.)"
                        )},
                    ],
                    max_tokens=1000,
                    temperature=0.3,
                )
                math_critique = math_response.choices[0].message.content

                # Designer revision
                designer_response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": (
                            "You are a senior slot game designer. You care about player experience "
                            "and creative vision, but you respect mathematical reality. When the "
                            "mathematician raises a valid concern, you adapt. Find creative solutions "
                            "that satisfy both fun AND math."
                        )},
                        {"role": "user", "content": (
                            f"DEBATE ROUND {round_num}/{max_rounds}\n\n"
                            f"TOPIC: {topic}\n"
                            f"CONTEXT: {context}\n\n"
                            f"YOUR PREVIOUS PROPOSAL:\n{current_proposal}\n\n"
                            f"MATHEMATICIAN'S CRITIQUE:\n{math_critique}\n\n"
                            f"Revise your proposal to address the math concerns while preserving "
                            f"the core creative intent. If the math is correct and the feature must "
                            f"change, acknowledge it. Output the REVISED PROPOSAL."
                        )},
                    ],
                    max_tokens=1000,
                    temperature=0.5,
                )
                revised_proposal = designer_response.choices[0].message.content

                rounds.append({
                    "round": round_num,
                    "proposal": current_proposal[:500],
                    "math_critique": math_critique[:500],
                    "revised_proposal": revised_proposal[:500],
                })

                current_proposal = revised_proposal

                # Check for convergence (math explicitly approves)
                if any(phrase in math_critique.lower() for phrase in ["this works", "approved", "feasible as proposed", "no concerns"]):
                    break

            return json.dumps({
                "topic": topic,
                "rounds_completed": len(rounds),
                "rounds": rounds,
                "final_proposal": current_proposal,
                "status": "consensus_reached" if len(rounds) < max_rounds else "max_rounds_reached",
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)})


# ============================================================
# UPGRADE 11: Live Trend Radar
# ============================================================
# Scrapes recent game releases to identify what's trending
# UP vs DOWN in themes, mechanics, providers.

class TrendRadarInput(BaseModel):
    focus: str = Field(
        default="all",
        description="Focus area: 'all', 'themes', 'mechanics', 'providers', 'volatility_trends'"
    )
    timeframe: str = Field(default="6months", description="'3months', '6months', '12months'")
    theme_filter: str = Field(default="", description="Optional theme to track, e.g. 'Egyptian'")


class TrendRadarTool(BaseTool):
    """
    Scrapes recent slot game releases and market data to identify trends.

    Returns: trending themes (up/down), hot mechanics, provider momentum,
    volatility shift direction, and emerging niches. Use at the START of
    every pipeline to ensure the game concept is aligned with market direction.
    """

    name: str = "trend_radar"
    description: str = (
        "Scan the live slot market for trends. Returns: trending themes (rising/falling), "
        "hot mechanics, provider momentum, volatility preferences, and emerging niches. "
        "Use this at the START of every pipeline to validate the game concept against "
        "current market direction. Helps avoid building a game into a saturated declining theme."
    )
    args_schema: type[BaseModel] = TrendRadarInput

    def _run(self, focus: str = "all", timeframe: str = "6months", theme_filter: str = "") -> str:
        serper_key = os.getenv("SERPER_API_KEY")
        if not serper_key:
            return json.dumps({"error": "SERPER_API_KEY not set"})

        import httpx

        # Build targeted search queries
        year = datetime.now().year
        queries = [
            f"new slot game releases {year} top trending themes",
            f"slot game market trends {year} mechanics features",
            f"most popular slot games {year} player favorites",
            f"slot industry trends {year} providers studios",
            f"new slot releases this month site:bigwinboard.com",
            f"slot game trends analysis {year} site:slotcatalog.com",
        ]
        if theme_filter:
            queries.append(f"{theme_filter} themed slot games {year} new releases trend")
            queries.append(f"{theme_filter} slot market saturation {year}")

        # Fetch search results
        all_snippets = []
        all_urls = {}
        for q in queries[:8]:
            try:
                resp = httpx.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                    json={"q": q, "num": 6},
                    timeout=15.0,
                )
                for item in resp.json().get("organic", [])[:5]:
                    all_snippets.append(item.get("snippet", ""))
                    url = item.get("link", "")
                    if url and url not in all_urls:
                        all_urls[url] = item.get("title", "")
            except Exception:
                continue

        # Fetch top 4 sources for deeper analysis
        from tools.advanced_research import WebFetchTool
        fetcher = WebFetchTool()
        articles = []

        priority = ["bigwinboard.com", "slotcatalog.com", "casino.guru", "igamingbusiness.com"]
        ranked_urls = sorted(all_urls.items(), key=lambda x: sum(5 for p in priority if p in x[0].lower()), reverse=True)

        for url, title in ranked_urls[:4]:
            try:
                result = json.loads(fetcher._run(url=url, max_chars=4000))
                if result.get("status") == "success":
                    articles.append({"url": url, "title": title, "content": result["content"][:4000]})
            except Exception:
                continue

        # Analyze content for patterns
        all_text = " ".join(all_snippets + [a["content"] for a in articles]).lower()

        # Theme frequency analysis
        theme_keywords = {
            "Egyptian": ["egypt", "pharaoh", "pyramid", "cleopatra", "book of"],
            "Asian/Oriental": ["dragon", "fortune", "asian", "oriental", "lucky"],
            "Norse/Viking": ["norse", "viking", "thor", "odin", "valhalla"],
            "Irish/Celtic": ["irish", "celtic", "leprechaun", "shamrock"],
            "Fruit/Classic": ["fruit", "classic", "retro", "7s", "bar"],
            "Space/Sci-Fi": ["space", "cosmic", "alien", "sci-fi", "galaxy"],
            "Aztec/Mayan": ["aztec", "mayan", "temple", "gold"],
            "Underwater/Ocean": ["underwater", "ocean", "fish", "deep sea", "atlantis"],
            "Horror/Dark": ["horror", "vampire", "zombie", "dark", "halloween"],
            "Candy/Sweet": ["candy", "sweet", "sugar", "cake"],
            "Cyberpunk/Neon": ["cyberpunk", "neon", "cyber", "synth"],
            "Animal/Wildlife": ["animal", "wildlife", "safari", "jungle"],
            "Music/Rock": ["music", "rock", "band", "dj"],
            "Sports": ["football", "boxing", "racing", "sport"],
        }

        theme_scores = {}
        for theme, keywords in theme_keywords.items():
            count = sum(all_text.count(kw) for kw in keywords)
            theme_scores[theme] = count

        # Mechanic frequency
        mechanic_keywords = {
            "Megaways": ["megaways"],
            "Cluster Pays": ["cluster pays", "cluster"],
            "Cascading/Tumble": ["cascading", "tumble", "avalanche"],
            "Hold & Spin": ["hold and spin", "hold & spin", "respin"],
            "Bonus Buy": ["bonus buy", "feature buy", "ante bet"],
            "Multipliers": ["multiplier"],
            "Progressive Jackpot": ["progressive", "jackpot"],
            "Free Spins": ["free spins", "free spin"],
            "Expanding Wilds": ["expanding wild"],
            "Sticky Wilds": ["sticky wild"],
            "Split Symbols": ["split symbol"],
            "Mystery Symbols": ["mystery symbol", "mystery"],
            "Walking Wilds": ["walking wild"],
            "Infinity Reels": ["infinity reel"],
        }

        mechanic_scores = {}
        for mech, keywords in mechanic_keywords.items():
            count = sum(all_text.count(kw) for kw in keywords)
            mechanic_scores[mech] = count

        # Sort and rank
        trending_themes = sorted(theme_scores.items(), key=lambda x: x[1], reverse=True)
        trending_mechanics = sorted(mechanic_scores.items(), key=lambda x: x[1], reverse=True)

        radar = {
            "scan_date": datetime.now().isoformat(),
            "sources_analyzed": len(articles) + len(all_snippets),
            "trending_themes": [{"theme": t, "mentions": c, "signal": "HOT" if c > 10 else "WARM" if c > 5 else "COOL"} for t, c in trending_themes[:10]],
            "trending_mechanics": [{"mechanic": m, "mentions": c, "signal": "HOT" if c > 8 else "WARM" if c > 3 else "COOL"} for m, c in trending_mechanics[:10]],
            "market_insights": [],
            "articles_read": [{"url": a["url"], "title": a["title"]} for a in articles],
        }

        # Theme-specific analysis
        if theme_filter:
            filter_lower = theme_filter.lower()
            mentions = sum(1 for s in all_snippets if filter_lower in s.lower())
            radar["theme_analysis"] = {
                "theme": theme_filter,
                "mentions_in_recent_results": mentions,
                "saturation_signal": "HIGH" if mentions > 15 else "MEDIUM" if mentions > 5 else "LOW",
                "recommendation": (
                    f"'{theme_filter}' appears heavily saturated. Strong differentiation required."
                    if mentions > 15
                    else f"'{theme_filter}' has moderate presence. Room for a standout entry."
                    if mentions > 5
                    else f"'{theme_filter}' is underrepresented. Potential blue ocean opportunity."
                ),
            }

        # High-level insights
        top_theme = trending_themes[0][0] if trending_themes else "Unknown"
        top_mech = trending_mechanics[0][0] if trending_mechanics else "Unknown"
        radar["market_insights"] = [
            f"Most mentioned theme: {top_theme}",
            f"Most mentioned mechanic: {top_mech}",
            f"Total sources analyzed: {len(articles)} full articles + {len(all_snippets)} snippets",
        ]

        return json.dumps(radar, indent=2)
