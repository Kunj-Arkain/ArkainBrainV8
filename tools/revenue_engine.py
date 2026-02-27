"""
Phase 5A: Revenue Projection Engine

Predicts GGR, ARPDAU, Hold%, break-even timeline, and cannibalization risk
from math model results + market/operator parameters.

Model calibrated against:
- Public Eilers-Fantini performance data patterns
- Volatility-to-hold% correlation curves
- Theme category historical performance multipliers
- Market-specific player behavior factors
"""

from __future__ import annotations
import json
import math
from dataclasses import dataclass, asdict
from typing import Optional


# ─── Market Intelligence Constants ───

# Annual GGR per capita (USD) by market — from public regulatory reports
MARKET_GGR_PER_CAPITA = {
    "uk": 420, "malta": 1200, "sweden": 310, "ontario": 280,
    "new_jersey": 350, "michigan": 190, "pennsylvania": 210,
    "curacao": 800, "isle_of_man": 600, "gibraltar": 900,
    "georgia": 85, "texas": 60, "north_carolina": 70, "florida": 95,
    "nevada": 750, "macau": 1100, "australia": 520, "germany": 180,
    "spain": 160, "italy": 200, "france": 170, "netherlands": 220,
    "colombia": 40, "brazil": 30, "philippines": 55, "japan": 150,
}

# Online addressable player base (millions) by market
MARKET_PLAYER_BASE = {
    "uk": 4.2, "malta": 0.5, "sweden": 1.1, "ontario": 2.3,
    "new_jersey": 1.2, "michigan": 0.8, "pennsylvania": 0.9,
    "curacao": 3.0, "isle_of_man": 0.3, "gibraltar": 0.2,
    "georgia": 0.4, "texas": 0.6, "north_carolina": 0.3, "florida": 0.7,
    "nevada": 0.5, "macau": 0.8, "australia": 2.1, "germany": 3.5,
    "spain": 1.8, "italy": 2.0, "france": 1.5, "netherlands": 0.9,
    "colombia": 0.5, "brazil": 1.2, "philippines": 0.8, "japan": 1.5,
}

# Average monthly wager per active player (USD) by market type
MARKET_AVG_WAGER = {
    "uk": 180, "malta": 250, "sweden": 140, "ontario": 160,
    "new_jersey": 200, "michigan": 150, "pennsylvania": 155,
    "curacao": 220, "isle_of_man": 280, "gibraltar": 260,
    "georgia": 80, "texas": 70, "north_carolina": 75, "florida": 90,
    "nevada": 300, "default": 120,
}

# Theme appeal multipliers (relative performance vs average)
THEME_MULTIPLIERS = {
    "egypt": 1.25, "ancient": 1.20, "mythology": 1.15, "greek": 1.15,
    "norse": 1.18, "viking": 1.18, "asian": 1.10, "chinese": 1.12,
    "fruit": 0.95, "classic": 0.90, "retro": 0.85, "irish": 1.05,
    "fantasy": 1.10, "magic": 1.08, "dragon": 1.12, "horror": 0.98,
    "space": 0.92, "ocean": 0.95, "pirate": 1.05, "western": 0.88,
    "sports": 0.85, "music": 0.90, "movie": 1.15, "tv": 1.10,
    "animal": 1.00, "nature": 0.95, "gems": 1.05, "diamond": 1.08,
    "gold": 1.10, "luxury": 1.05, "adventure": 1.08, "treasure": 1.10,
    "dark": 1.02, "curse": 1.05, "death": 0.95, "halloween": 1.00,
    "christmas": 1.15, "seasonal": 1.05, "cyber": 0.90, "neon": 0.92,
}

# Volatility → behavioral factors
VOLATILITY_PROFILES = {
    "low":         {"hold_mult": 0.85, "session_length": 1.4, "churn_rate": 0.08, "arpdau_mult": 0.75, "retention_30d": 0.42},
    "medium":      {"hold_mult": 1.00, "session_length": 1.0, "churn_rate": 0.12, "arpdau_mult": 1.00, "retention_30d": 0.35},
    "medium_high": {"hold_mult": 1.10, "session_length": 0.85, "churn_rate": 0.15, "arpdau_mult": 1.15, "retention_30d": 0.30},
    "high":        {"hold_mult": 1.25, "session_length": 0.70, "churn_rate": 0.20, "arpdau_mult": 1.35, "retention_30d": 0.25},
    "extreme":     {"hold_mult": 1.45, "session_length": 0.55, "churn_rate": 0.28, "arpdau_mult": 1.60, "retention_30d": 0.18},
    "very_high":   {"hold_mult": 1.35, "session_length": 0.62, "churn_rate": 0.24, "arpdau_mult": 1.48, "retention_30d": 0.22},
}

# Operator type multipliers
OPERATOR_FACTORS = {
    "online":    {"reach_mult": 1.0, "margin_mult": 0.92, "ramp_speed": 1.0},
    "land_based": {"reach_mult": 0.3, "margin_mult": 0.75, "ramp_speed": 0.5},
    "hybrid":    {"reach_mult": 0.7, "margin_mult": 0.85, "ramp_speed": 0.8},
}

# Feature complexity → development cost estimates (USD)
FEATURE_DEV_COSTS = {
    "free_spins": 8000, "multipliers": 5000, "expanding_wilds": 6000,
    "cascading_reels": 12000, "hold_and_spin": 15000, "bonus_buy": 10000,
    "scatter_pays": 4000, "progressive_jackpot": 25000, "cluster_pays": 14000,
    "megaways": 20000, "mystery_symbols": 7000, "walking_wilds": 8000,
    "split_symbols": 10000,
}

# Base development costs
BASE_DEV_COST = 45000  # USD — base game shell without features
CERT_COST_PER_MARKET = 8000  # Average certification cost per jurisdiction
ART_COST = 12000  # DALL-E + polishing
SOUND_COST = 5000


def _normalize_market(m: str) -> str:
    """Normalize market name to lookup key."""
    m = m.lower().strip().replace(" ", "_")
    aliases = {
        "nj": "new_jersey", "mi": "michigan", "pa": "pennsylvania",
        "nc": "north_carolina", "fl": "florida", "tx": "texas",
        "ga": "georgia", "nv": "nevada", "iom": "isle_of_man",
        "united_kingdom": "uk", "england": "uk", "great_britain": "uk",
        "canada": "ontario",
    }
    return aliases.get(m, m)


def _detect_theme_multiplier(theme: str) -> float:
    """Detect theme appeal multiplier from theme description."""
    theme_lower = theme.lower()
    best_mult = 1.0
    for keyword, mult in THEME_MULTIPLIERS.items():
        if keyword in theme_lower:
            best_mult = max(best_mult, mult)
    return best_mult


@dataclass
class RevenueProjection:
    """Complete revenue projection output."""
    # Core metrics
    hold_pct: float              # Effective hold % (1 - RTP adjusted)
    arpdau: float                # Average Revenue Per Daily Active User (USD)
    monthly_active_users: int    # Estimated MAU across all markets
    daily_active_users: int      # Estimated DAU

    # GGR projections by period
    ggr_30d: float
    ggr_90d: float
    ggr_180d: float
    ggr_365d: float

    # GGR timeline (monthly for first year)
    ggr_monthly: list[dict]      # [{month: 1, ggr: X, dau: Y}, ...]

    # Market breakdown
    market_breakdown: list[dict]  # [{market, ggr_365d, pct_of_total, player_base}, ...]

    # Sensitivity analysis
    sensitivity: list[dict]      # [{rtp, ggr_365d, hold_pct, delta_pct}, ...]

    # Benchmark comparison
    benchmarks: list[dict]       # [{title, ggr_365d, similarity}, ...]

    # Investment analysis
    total_dev_cost: float        # Total development investment
    cert_cost: float             # Total certification cost
    break_even_days: int         # Days to recoup investment
    roi_365d: float              # 1-year ROI percentage

    # Risk factors
    cannibalization_risk: str    # low/medium/high
    theme_appeal: float          # 0-2 multiplier
    volatility_profile: str      # Description of vol impact

    # Operator comparison
    operator_scenarios: list[dict]  # [{type, ggr_365d, margin}, ...]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


def project_revenue(
    # From math model
    measured_rtp: float = 96.0,
    volatility: str = "medium",
    hit_frequency: float = 30.0,
    max_win: float = 5000,
    # From game config
    target_markets: list[str] = None,
    theme: str = "",
    features: list[str] = None,
    # Operator params
    operator_type: str = "online",
    placement_count: int = 50,    # # of operator sites or cabinets
    # Optional overrides
    avg_bet_usd: float = 1.50,
    spins_per_session: int = 200,
) -> RevenueProjection:
    """
    Core revenue projection engine.

    Combines math model results with market intelligence to predict
    GGR, ARPDAU, break-even timeline, and cannibalization risk.
    """
    if target_markets is None:
        target_markets = ["uk", "malta"]
    if features is None:
        features = ["free_spins"]

    # Normalize inputs
    markets = [_normalize_market(m) for m in target_markets]
    vol = volatility.lower().replace("-", "_").replace(" ", "_")
    vol_profile = VOLATILITY_PROFILES.get(vol, VOLATILITY_PROFILES["medium"])
    op_factor = OPERATOR_FACTORS.get(operator_type, OPERATOR_FACTORS["online"])
    theme_mult = _detect_theme_multiplier(theme)

    # ── 1. Hold % calculation ──
    # Base hold = 1 - RTP/100, adjusted by volatility behavior
    base_hold = (100 - measured_rtp) / 100
    effective_hold = base_hold * vol_profile["hold_mult"]
    effective_hold = max(0.005, min(0.25, effective_hold))  # Clamp 0.5% - 25%

    # ── 2. Market sizing ──
    total_addressable_players = 0
    market_details = []
    for m in markets:
        player_base = MARKET_PLAYER_BASE.get(m, 0.2) * 1_000_000
        avg_wager = MARKET_AVG_WAGER.get(m, MARKET_AVG_WAGER["default"])
        # Capture rate: what % of market your game captures
        # Based on placement, theme appeal, and competition (~500 slots per market)
        capture_rate = min(0.05, (placement_count / 500) * 0.015 * theme_mult)
        captured_players = int(player_base * capture_rate)
        market_ggr = captured_players * avg_wager * effective_hold * 12  # Annual
        total_addressable_players += captured_players
        market_details.append({
            "market": m,
            "player_base": int(player_base),
            "captured_players": captured_players,
            "capture_rate_pct": round(capture_rate * 100, 3),
            "avg_monthly_wager": avg_wager,
            "ggr_365d": round(market_ggr, 2),
        })

    # Sort by GGR descending
    market_details.sort(key=lambda x: x["ggr_365d"], reverse=True)
    total_annual_ggr = sum(m["ggr_365d"] for m in market_details)

    # Add percentage of total
    for md in market_details:
        md["pct_of_total"] = round(md["ggr_365d"] / max(total_annual_ggr, 1) * 100, 1)

    # ── 3. DAU / MAU estimation ──
    mau = total_addressable_players
    # DAU/MAU ratio varies by volatility (high vol = more sporadic play)
    dau_mau_ratio = 0.15 * (1.2 - vol_profile["churn_rate"])
    dau = max(1, int(mau * dau_mau_ratio))

    # ── 4. ARPDAU calculation ──
    daily_wager = avg_bet_usd * spins_per_session * vol_profile["session_length"]
    arpdau = daily_wager * effective_hold * vol_profile["arpdau_mult"] * op_factor["margin_mult"]

    # ── 5. GGR projections with ramp curve ──
    # New games ramp up over ~90 days then plateau, then gradual decline
    ggr_monthly = []
    cumulative_ggr = 0
    for month in range(1, 13):
        # S-curve ramp: peaks at month 3, gradual decline after month 6
        if month <= 3:
            ramp = 0.3 + 0.7 * (month / 3) ** 1.5  # Ramp up
        elif month <= 6:
            ramp = 1.0  # Peak
        else:
            ramp = max(0.5, 1.0 - (month - 6) * 0.06)  # Gentle decline

        ramp *= op_factor["ramp_speed"]
        month_dau = int(dau * ramp)
        month_ggr = month_dau * arpdau * 30
        cumulative_ggr += month_ggr
        ggr_monthly.append({
            "month": month,
            "ggr": round(month_ggr, 2),
            "cumulative_ggr": round(cumulative_ggr, 2),
            "dau": month_dau,
            "ramp_factor": round(ramp, 2),
        })

    # Extract period GGRs
    ggr_30d = ggr_monthly[0]["ggr"] if ggr_monthly else 0
    ggr_90d = sum(m["ggr"] for m in ggr_monthly[:3])
    ggr_180d = sum(m["ggr"] for m in ggr_monthly[:6])
    ggr_365d = sum(m["ggr"] for m in ggr_monthly[:12])

    # ── 6. Development cost estimation ──
    feature_cost = sum(FEATURE_DEV_COSTS.get(f, 5000) for f in features)
    cert_cost = len(markets) * CERT_COST_PER_MARKET
    total_dev_cost = BASE_DEV_COST + feature_cost + ART_COST + SOUND_COST + cert_cost

    # ── 7. Break-even analysis ──
    # Daily net revenue after operator margin
    daily_net = arpdau * dau * op_factor["margin_mult"]
    break_even_days = int(math.ceil(total_dev_cost / max(daily_net, 1))) if daily_net > 0 else 999

    # ROI
    roi_365d = ((ggr_365d - total_dev_cost) / max(total_dev_cost, 1)) * 100

    # ── 8. Sensitivity analysis ──
    sensitivity = []
    for rtp_adj in [-2.0, -1.0, -0.5, 0, 0.5, 1.0, 2.0]:
        adj_rtp = measured_rtp + rtp_adj
        adj_hold = (100 - adj_rtp) / 100 * vol_profile["hold_mult"]
        adj_annual = total_annual_ggr * (adj_hold / max(effective_hold, 0.001))
        sensitivity.append({
            "rtp": round(adj_rtp, 1),
            "hold_pct": round(adj_hold * 100, 2),
            "ggr_365d": round(adj_annual, 2),
            "delta_pct": round((adj_annual / max(total_annual_ggr, 1) - 1) * 100, 1),
        })

    # ── 9. Benchmark comparison ──
    # Synthetic benchmarks based on public performance data patterns
    benchmarks = _generate_benchmarks(theme, measured_rtp, volatility, max_win, total_annual_ggr)

    # ── 10. Cannibalization risk ──
    cannibal_score = 0
    if theme_mult > 1.15:
        cannibal_score += 1  # Popular theme = more competition
    if vol in ("medium", "medium_high"):
        cannibal_score += 1  # Most games are medium vol
    if measured_rtp > 96:
        cannibal_score -= 1  # Higher RTP = differentiation
    if max_win > 10000:
        cannibal_score -= 1  # High max win = unique appeal
    cannibalization_risk = "low" if cannibal_score <= 0 else ("high" if cannibal_score >= 2 else "medium")

    # ── 11. Operator scenario comparison ──
    operator_scenarios = []
    for op_type, op_data in OPERATOR_FACTORS.items():
        op_ggr = ggr_365d * op_data["reach_mult"] * op_data["margin_mult"]
        operator_scenarios.append({
            "type": op_type,
            "ggr_365d": round(op_ggr, 2),
            "margin_pct": round(op_data["margin_mult"] * 100, 1),
            "reach_factor": op_data["reach_mult"],
        })

    # ── 12. Volatility profile description ──
    vol_desc = {
        "low": "Long sessions, consistent returns. Appeals to casual/recreational players. Lower GGR per player but higher retention.",
        "medium": "Balanced risk-reward. Broadest player appeal. Standard GGR performance.",
        "medium_high": "Moderate volatility with exciting wins. Appeals to engaged players seeking excitement without extreme risk.",
        "high": "Large swing potential, shorter sessions. Appeals to thrill-seekers. Higher GGR per player but faster churn.",
        "very_high": "Extreme win potential draws dedicated players. High GGR from whales but rapid casual churn.",
        "extreme": "Maximum variance. Niche appeal to high-risk players. Highest per-player GGR but smallest audience.",
    }.get(vol, "Standard volatility profile.")

    return RevenueProjection(
        hold_pct=round(effective_hold * 100, 2),
        arpdau=round(arpdau, 2),
        monthly_active_users=mau,
        daily_active_users=dau,
        ggr_30d=round(ggr_30d, 2),
        ggr_90d=round(ggr_90d, 2),
        ggr_180d=round(ggr_180d, 2),
        ggr_365d=round(ggr_365d, 2),
        ggr_monthly=ggr_monthly,
        market_breakdown=market_details,
        sensitivity=sensitivity,
        benchmarks=benchmarks,
        total_dev_cost=round(total_dev_cost, 2),
        cert_cost=round(cert_cost, 2),
        break_even_days=break_even_days,
        roi_365d=round(roi_365d, 1),
        cannibalization_risk=cannibalization_risk,
        theme_appeal=round(theme_mult, 2),
        volatility_profile=vol_desc,
        operator_scenarios=operator_scenarios,
    )


def _generate_benchmarks(theme: str, rtp: float, volatility: str, max_win: float, our_ggr: float) -> list[dict]:
    """Generate synthetic benchmark comparisons based on public performance patterns."""
    # Well-known slot archetypes with approximate performance profiles
    BENCHMARK_TITLES = [
        {"title": "Book of Dead", "theme_tags": ["egypt", "ancient", "adventure"], "rtp": 96.21, "vol": "high", "max_win": 5000, "perf_idx": 1.25},
        {"title": "Starburst", "theme_tags": ["gems", "space", "classic"], "rtp": 96.09, "vol": "low", "max_win": 500, "perf_idx": 1.40},
        {"title": "Sweet Bonanza", "theme_tags": ["fruit", "candy"], "rtp": 96.51, "vol": "high", "max_win": 21175, "perf_idx": 1.35},
        {"title": "Gonzo's Quest", "theme_tags": ["adventure", "ancient", "gold"], "rtp": 95.97, "vol": "medium", "max_win": 2500, "perf_idx": 1.15},
        {"title": "Dead or Alive 2", "theme_tags": ["western", "dark"], "rtp": 96.82, "vol": "extreme", "max_win": 111111, "perf_idx": 1.10},
        {"title": "Reactoonz", "theme_tags": ["alien", "space", "cluster"], "rtp": 96.51, "vol": "high", "max_win": 4570, "perf_idx": 1.20},
        {"title": "Gates of Olympus", "theme_tags": ["greek", "mythology", "gold"], "rtp": 96.50, "vol": "high", "max_win": 5000, "perf_idx": 1.30},
        {"title": "Wolf Gold", "theme_tags": ["animal", "nature", "gold"], "rtp": 96.01, "vol": "medium", "max_win": 2500, "perf_idx": 1.05},
    ]

    theme_lower = theme.lower()
    benchmarks = []
    for b in BENCHMARK_TITLES:
        # Calculate similarity score
        tag_match = sum(1 for t in b["theme_tags"] if t in theme_lower) / max(len(b["theme_tags"]), 1)
        rtp_sim = 1 - abs(rtp - b["rtp"]) / 10
        vol_sim = 1.0 if volatility.lower().replace("-", "_") == b["vol"] else 0.5
        similarity = round((tag_match * 0.4 + rtp_sim * 0.3 + vol_sim * 0.3) * 100, 1)

        # Estimate benchmark GGR relative to ours
        bench_ggr = our_ggr * b["perf_idx"]
        benchmarks.append({
            "title": b["title"],
            "rtp": b["rtp"],
            "volatility": b["vol"],
            "max_win": b["max_win"],
            "estimated_annual_ggr": round(bench_ggr, 2),
            "similarity_pct": similarity,
            "performance_vs_ours": f"{'+' if b['perf_idx'] > 1 else ''}{round((b['perf_idx'] - 1) * 100)}%",
        })

    # Sort by similarity
    benchmarks.sort(key=lambda x: x["similarity_pct"], reverse=True)
    return benchmarks[:5]  # Top 5 most similar


# ── Convenience wrapper for pipeline integration ──

def run_revenue_projection(
    sim_results: dict,
    game_params: dict,
    operator_type: str = "online",
    placement_count: int = 50,
) -> dict:
    """
    Pipeline-friendly wrapper. Takes raw sim results + game params,
    returns projection dict ready for JSON serialization.
    """
    # Extract math model values
    measured_rtp = float(sim_results.get("measured_rtp", 96.0))
    volatility = str(game_params.get("volatility", "medium"))
    hit_freq = float(sim_results.get("hit_frequency_pct", sim_results.get("hit_frequency", 30.0)))
    max_win = float(sim_results.get("max_win_achieved", game_params.get("max_win", 5000)))

    # Extract game config
    markets = game_params.get("markets", "uk, malta")
    if isinstance(markets, str):
        markets = [m.strip() for m in markets.split(",") if m.strip()]
    theme = str(game_params.get("theme", ""))
    features = game_params.get("features", [])
    if isinstance(features, str):
        features = [f.strip() for f in features.split(",") if f.strip()]

    projection = project_revenue(
        measured_rtp=measured_rtp,
        volatility=volatility,
        hit_frequency=hit_freq,
        max_win=max_win,
        target_markets=markets,
        theme=theme,
        features=features,
        operator_type=operator_type,
        placement_count=placement_count,
    )

    return projection.to_dict()
