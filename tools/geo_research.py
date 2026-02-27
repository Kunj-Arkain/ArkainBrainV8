"""
ARKAINBRAIN — Geographic Market Research Tool

Researches optimal geographic regions within a US state for game placement
based on demographics, socioeconomics, casino density, and gaming revenue.

Uses publicly available data patterns from:
  - US Census Bureau (population, income, demographics)
  - State gaming commission data (GGR, venues, revenue trends)
  - AGA (American Gaming Association) industry reports
  - Tourism and hospitality statistics

Data flow:
  Pipeline params → state + game type
  → Research existing casino density + demographics
  → Score regions by composite index
  → Output ranked regions with placement rationale

Output structure:
  00_preflight/geo_research.json    # Full research output
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    # Pydantic not available — use plain classes for standalone mode
    class BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
    def Field(**kw):
        return kw.get("default", None)

logger = logging.getLogger("arkainbrain.geo")


# ============================================================
# US State Gaming Profiles — Baseline data
# ============================================================

# Pre-compiled from AGA / NCLGS / state commission public reports.
# Updated annually — these represent structural patterns, not live data.
_STATE_GAMING_PROFILES = {
    "nevada": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 200,
        "annual_ggr_billions": 15.2,
        "top_regions": [
            {"region": "Las Vegas Strip", "county": "Clark", "pop": 2_300_000, "median_income": 58_000,
             "casino_density": "very_high", "tourism_annual_m": 42.0, "ggr_share_pct": 65},
            {"region": "Reno / Sparks", "county": "Washoe", "pop": 490_000, "median_income": 62_000,
             "casino_density": "high", "tourism_annual_m": 8.5, "ggr_share_pct": 12},
            {"region": "Laughlin / Henderson", "county": "Clark", "pop": 320_000, "median_income": 55_000,
             "casino_density": "medium", "tourism_annual_m": 3.0, "ggr_share_pct": 5},
        ],
    },
    "new jersey": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 9,
        "annual_ggr_billions": 5.2,
        "top_regions": [
            {"region": "Atlantic City", "county": "Atlantic", "pop": 275_000, "median_income": 52_000,
             "casino_density": "very_high", "tourism_annual_m": 26.0, "ggr_share_pct": 85},
            {"region": "Newark Metro (iGaming)", "county": "Essex", "pop": 860_000, "median_income": 55_000,
             "casino_density": "online_only", "tourism_annual_m": 5.0, "ggr_share_pct": 12},
        ],
    },
    "pennsylvania": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 17,
        "annual_ggr_billions": 5.4,
        "top_regions": [
            {"region": "Philadelphia Metro", "county": "Philadelphia", "pop": 1_600_000, "median_income": 49_000,
             "casino_density": "high", "tourism_annual_m": 46.0, "ggr_share_pct": 30},
            {"region": "Pittsburgh Metro", "county": "Allegheny", "pop": 1_250_000, "median_income": 60_000,
             "casino_density": "medium", "tourism_annual_m": 15.0, "ggr_share_pct": 20},
            {"region": "Poconos / Lehigh Valley", "county": "Monroe/Northampton", "pop": 650_000, "median_income": 57_000,
             "casino_density": "medium", "tourism_annual_m": 8.0, "ggr_share_pct": 15},
        ],
    },
    "michigan": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 26,
        "annual_ggr_billions": 3.8,
        "top_regions": [
            {"region": "Detroit Metro", "county": "Wayne", "pop": 1_800_000, "median_income": 48_000,
             "casino_density": "high", "tourism_annual_m": 20.0, "ggr_share_pct": 55},
            {"region": "Grand Rapids", "county": "Kent", "pop": 660_000, "median_income": 58_000,
             "casino_density": "low", "tourism_annual_m": 3.0, "ggr_share_pct": 8},
            {"region": "Traverse City / Northern MI", "county": "Grand Traverse", "pop": 95_000, "median_income": 52_000,
             "casino_density": "medium", "tourism_annual_m": 5.0, "ggr_share_pct": 10},
        ],
    },
    "georgia": {
        "legal_status": "limited",
        "casino_count_approx": 0,
        "annual_ggr_billions": 0.0,
        "top_regions": [
            {"region": "Atlanta Metro", "county": "Fulton/DeKalb", "pop": 6_100_000, "median_income": 65_000,
             "casino_density": "none", "tourism_annual_m": 57.0, "ggr_share_pct": 0},
            {"region": "Savannah", "county": "Chatham", "pop": 400_000, "median_income": 50_000,
             "casino_density": "none", "tourism_annual_m": 15.0, "ggr_share_pct": 0},
            {"region": "Augusta", "county": "Richmond", "pop": 205_000, "median_income": 42_000,
             "casino_density": "none", "tourism_annual_m": 3.0, "ggr_share_pct": 0},
        ],
    },
    "texas": {
        "legal_status": "limited",
        "casino_count_approx": 3,
        "annual_ggr_billions": 0.3,
        "top_regions": [
            {"region": "Dallas–Fort Worth", "county": "Dallas/Tarrant", "pop": 7_600_000, "median_income": 63_000,
             "casino_density": "very_low", "tourism_annual_m": 38.0, "ggr_share_pct": 0},
            {"region": "Houston Metro", "county": "Harris", "pop": 7_100_000, "median_income": 58_000,
             "casino_density": "very_low", "tourism_annual_m": 22.0, "ggr_share_pct": 0},
            {"region": "San Antonio", "county": "Bexar", "pop": 2_100_000, "median_income": 52_000,
             "casino_density": "none", "tourism_annual_m": 37.0, "ggr_share_pct": 0},
            {"region": "Eagle Pass / Kickapoo", "county": "Maverick", "pop": 58_000, "median_income": 32_000,
             "casino_density": "low", "tourism_annual_m": 0.5, "ggr_share_pct": 90},
        ],
    },
    "connecticut": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 2,
        "annual_ggr_billions": 2.1,
        "top_regions": [
            {"region": "Mashantucket (Foxwoods)", "county": "New London", "pop": 275_000, "median_income": 62_000,
             "casino_density": "high", "tourism_annual_m": 8.0, "ggr_share_pct": 45},
            {"region": "Uncasville (Mohegan Sun)", "county": "New London", "pop": 275_000, "median_income": 62_000,
             "casino_density": "high", "tourism_annual_m": 9.0, "ggr_share_pct": 50},
            {"region": "Hartford Metro (iGaming)", "county": "Hartford", "pop": 900_000, "median_income": 65_000,
             "casino_density": "online_only", "tourism_annual_m": 5.0, "ggr_share_pct": 5},
        ],
    },
    "west virginia": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 5,
        "annual_ggr_billions": 0.9,
        "top_regions": [
            {"region": "Charles Town (Hollywood)", "county": "Jefferson", "pop": 58_000, "median_income": 55_000,
             "casino_density": "medium", "tourism_annual_m": 2.5, "ggr_share_pct": 35},
            {"region": "Wheeling Island", "county": "Ohio", "pop": 43_000, "median_income": 38_000,
             "casino_density": "medium", "tourism_annual_m": 1.5, "ggr_share_pct": 20},
            {"region": "Charleston Metro", "county": "Kanawha", "pop": 180_000, "median_income": 43_000,
             "casino_density": "low", "tourism_annual_m": 2.0, "ggr_share_pct": 15},
        ],
    },
    "indiana": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 14,
        "annual_ggr_billions": 2.5,
        "top_regions": [
            {"region": "Indianapolis Metro", "county": "Marion", "pop": 2_100_000, "median_income": 56_000,
             "casino_density": "medium", "tourism_annual_m": 28.0, "ggr_share_pct": 25},
            {"region": "Gary / NW Indiana", "county": "Lake", "pop": 490_000, "median_income": 48_000,
             "casino_density": "high", "tourism_annual_m": 3.0, "ggr_share_pct": 30},
            {"region": "French Lick / S Indiana", "county": "Orange/Harrison", "pop": 75_000, "median_income": 42_000,
             "casino_density": "low", "tourism_annual_m": 2.0, "ggr_share_pct": 10},
        ],
    },
    "mississippi": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 28,
        "annual_ggr_billions": 2.2,
        "top_regions": [
            {"region": "Tunica County", "county": "Tunica", "pop": 10_000, "median_income": 28_000,
             "casino_density": "very_high", "tourism_annual_m": 6.0, "ggr_share_pct": 25},
            {"region": "Gulf Coast (Biloxi/Gulfport)", "county": "Harrison", "pop": 210_000, "median_income": 45_000,
             "casino_density": "high", "tourism_annual_m": 8.5, "ggr_share_pct": 50},
            {"region": "Vicksburg", "county": "Warren", "pop": 46_000, "median_income": 38_000,
             "casino_density": "medium", "tourism_annual_m": 1.5, "ggr_share_pct": 8},
        ],
    },
    "colorado": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 33,
        "annual_ggr_billions": 1.0,
        "top_regions": [
            {"region": "Black Hawk / Central City", "county": "Gilpin", "pop": 6_000, "median_income": 55_000,
             "casino_density": "very_high", "tourism_annual_m": 5.0, "ggr_share_pct": 75},
            {"region": "Cripple Creek", "county": "Teller", "pop": 25_000, "median_income": 48_000,
             "casino_density": "high", "tourism_annual_m": 2.0, "ggr_share_pct": 15},
            {"region": "Denver Metro (sports)", "county": "Denver", "pop": 2_900_000, "median_income": 72_000,
             "casino_density": "online_only", "tourism_annual_m": 35.0, "ggr_share_pct": 10},
        ],
    },
    "illinois": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 15,
        "annual_ggr_billions": 2.0,
        "top_regions": [
            {"region": "Chicago Metro", "county": "Cook", "pop": 5_200_000, "median_income": 62_000,
             "casino_density": "medium", "tourism_annual_m": 58.0, "ggr_share_pct": 40},
            {"region": "Joliet / Will County", "county": "Will", "pop": 700_000, "median_income": 72_000,
             "casino_density": "medium", "tourism_annual_m": 2.0, "ggr_share_pct": 20},
            {"region": "East St. Louis Metro", "county": "St. Clair", "pop": 260_000, "median_income": 42_000,
             "casino_density": "medium", "tourism_annual_m": 1.5, "ggr_share_pct": 12},
        ],
    },
    "ohio": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 11,
        "annual_ggr_billions": 2.3,
        "top_regions": [
            {"region": "Columbus Metro", "county": "Franklin", "pop": 2_100_000, "median_income": 58_000,
             "casino_density": "medium", "tourism_annual_m": 20.0, "ggr_share_pct": 25},
            {"region": "Cleveland Metro", "county": "Cuyahoga", "pop": 1_300_000, "median_income": 50_000,
             "casino_density": "medium", "tourism_annual_m": 18.0, "ggr_share_pct": 25},
            {"region": "Cincinnati Metro", "county": "Hamilton", "pop": 2_200_000, "median_income": 55_000,
             "casino_density": "medium", "tourism_annual_m": 12.0, "ggr_share_pct": 20},
        ],
    },
    "florida": {
        "legal_status": "limited",
        "casino_count_approx": 8,
        "annual_ggr_billions": 3.0,
        "top_regions": [
            {"region": "Miami / Ft. Lauderdale", "county": "Miami-Dade/Broward", "pop": 6_200_000, "median_income": 55_000,
             "casino_density": "medium", "tourism_annual_m": 26.0, "ggr_share_pct": 50},
            {"region": "Tampa Bay", "county": "Hillsborough", "pop": 3_200_000, "median_income": 55_000,
             "casino_density": "low", "tourism_annual_m": 15.0, "ggr_share_pct": 25},
            {"region": "Orlando Metro", "county": "Orange", "pop": 2_700_000, "median_income": 52_000,
             "casino_density": "very_low", "tourism_annual_m": 75.0, "ggr_share_pct": 5},
        ],
    },
    "california": {
        "legal_status": "tribal_only",
        "casino_count_approx": 70,
        "annual_ggr_billions": 10.5,
        "top_regions": [
            {"region": "San Diego County", "county": "San Diego", "pop": 3_300_000, "median_income": 72_000,
             "casino_density": "high", "tourism_annual_m": 35.0, "ggr_share_pct": 20},
            {"region": "Riverside / Palm Springs", "county": "Riverside", "pop": 2_500_000, "median_income": 58_000,
             "casino_density": "high", "tourism_annual_m": 12.0, "ggr_share_pct": 30},
            {"region": "LA Metro (fringe)", "county": "Los Angeles", "pop": 10_000_000, "median_income": 65_000,
             "casino_density": "low", "tourism_annual_m": 50.0, "ggr_share_pct": 15},
            {"region": "Sacramento / Central Valley", "county": "Sacramento", "pop": 1_600_000, "median_income": 62_000,
             "casino_density": "medium", "tourism_annual_m": 15.0, "ggr_share_pct": 10},
        ],
    },
    "new york": {
        "legal_status": "fully_regulated",
        "casino_count_approx": 12,
        "annual_ggr_billions": 4.5,
        "top_regions": [
            {"region": "NYC Metro (iGaming pending)", "county": "New York", "pop": 8_300_000, "median_income": 67_000,
             "casino_density": "low", "tourism_annual_m": 66.0, "ggr_share_pct": 15},
            {"region": "Yonkers (Empire City)", "county": "Westchester", "pop": 980_000, "median_income": 90_000,
             "casino_density": "medium", "tourism_annual_m": 5.0, "ggr_share_pct": 20},
            {"region": "Finger Lakes / Catskills", "county": "Sullivan/Ontario", "pop": 200_000, "median_income": 52_000,
             "casino_density": "medium", "tourism_annual_m": 8.0, "ggr_share_pct": 25},
        ],
    },
}

# Default profile for states not in the curated list
_DEFAULT_PROFILE = {
    "legal_status": "varies",
    "casino_count_approx": 0,
    "annual_ggr_billions": 0.0,
    "top_regions": [],
}


# ============================================================
# Region Scoring Engine
# ============================================================

def _score_region(region: dict, game_volatility: str = "medium") -> float:
    """Score a region 0-100 based on composite gaming potential index.

    Factors (weighted):
      - Population (30%): larger metro = more players
      - Tourism (25%): visitor traffic multiplier
      - Income (15%): disposable income for gaming
      - Casino density (20%): saturation vs. underserved
      - GGR share (10%): proven gaming revenue
    """
    pop = region.get("pop", 0)
    tourism = region.get("tourism_annual_m", 0)
    income = region.get("median_income", 50_000)
    density = region.get("casino_density", "none")
    ggr = region.get("ggr_share_pct", 0)

    # Population score (log scale, 0-100)
    import math
    pop_score = min(100, max(0, math.log10(max(pop, 1)) / math.log10(10_000_000) * 100))

    # Tourism score (0-100)
    tourism_score = min(100, tourism / 50 * 100)

    # Income score (centered at $55k national median)
    income_score = min(100, max(0, (income / 55_000) * 60))

    # Casino density — for NEW game placement, underserved markets score higher
    density_map = {"none": 90, "very_low": 80, "low": 65, "medium": 45,
                   "high": 30, "very_high": 15, "online_only": 50}
    density_score = density_map.get(density, 50)

    # GGR (proven revenue = good for established; zero = greenfield opportunity)
    ggr_score = min(100, ggr * 2) if ggr > 0 else 40  # Greenfield gets moderate score

    # Volatility adjustment — high-vol games do better in tourist-heavy, high-density markets
    if game_volatility in ("high", "very_high", "extreme"):
        tourism_score *= 1.2
        density_score = 100 - density_score  # Flip: prefer established venues for high-vol
        density_score = max(10, density_score)

    composite = (
        pop_score * 0.30 +
        tourism_score * 0.25 +
        income_score * 0.15 +
        density_score * 0.20 +
        ggr_score * 0.10
    )
    return round(min(100, max(0, composite)), 1)


def _generate_placement_rationale(region: dict, score: float, game_volatility: str) -> str:
    """Generate human-readable placement rationale for a region."""
    pop = region.get("pop", 0)
    density = region.get("casino_density", "none")
    tourism = region.get("tourism_annual_m", 0)
    name = region.get("region", "Unknown")

    parts = []
    if pop > 1_000_000:
        parts.append(f"Large metro population ({pop:,})")
    elif pop > 200_000:
        parts.append(f"Mid-size market ({pop:,})")

    if tourism > 10:
        parts.append(f"strong tourism ({tourism:.0f}M visitors/yr)")
    elif tourism > 3:
        parts.append(f"moderate tourism flow")

    if density in ("none", "very_low"):
        parts.append("underserved gaming market — greenfield opportunity")
    elif density == "low":
        parts.append("limited competition — room for new entrants")
    elif density in ("high", "very_high"):
        parts.append("established gaming corridor with proven demand")

    if game_volatility in ("high", "very_high") and tourism > 10:
        parts.append("tourist demographics favor high-volatility play")

    return ". ".join(parts) + "." if parts else f"Standard market profile for {name}."


# ============================================================
# Main Research Function
# ============================================================

def run_geo_research(
    state: str,
    game_volatility: str = "medium",
    target_rtp: float = 96.0,
    game_theme: str = "",
    output_dir: Optional[str] = None,
) -> dict:
    """Run geographic market research for a US state.

    Returns a structured report with ranked regions, scores, and placement rationale.
    """
    state_lower = state.strip().lower()
    logger.info(f"Geo research: {state} (volatility={game_volatility})")

    # Lookup state profile
    profile = _STATE_GAMING_PROFILES.get(state_lower, _DEFAULT_PROFILE)
    regions = profile.get("top_regions", [])

    # Score each region
    scored_regions = []
    for r in regions:
        score = _score_region(r, game_volatility)
        rationale = _generate_placement_rationale(r, score, game_volatility)
        scored_regions.append({
            **r,
            "composite_score": score,
            "placement_rationale": rationale,
        })

    # Sort by score descending
    scored_regions.sort(key=lambda x: x["composite_score"], reverse=True)

    # Assign rank
    for i, r in enumerate(scored_regions):
        r["rank"] = i + 1

    # Build report
    report = {
        "state": state,
        "generated_at": datetime.now().isoformat(),
        "game_context": {
            "volatility": game_volatility,
            "target_rtp": target_rtp,
            "theme": game_theme,
        },
        "state_profile": {
            "legal_status": profile.get("legal_status", "unknown"),
            "casino_count_approx": profile.get("casino_count_approx", 0),
            "annual_ggr_billions": profile.get("annual_ggr_billions", 0),
        },
        "ranked_regions": scored_regions,
        "top_recommendation": scored_regions[0] if scored_regions else None,
        "summary": _build_summary(state, scored_regions, profile),
    }

    # Save to file
    if output_dir:
        od = Path(output_dir)
        od.mkdir(parents=True, exist_ok=True)
        out_path = od / "geo_research.json"
        out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info(f"Geo research saved: {out_path}")

    return report


def _build_summary(state: str, regions: list, profile: dict) -> str:
    """Build a text summary paragraph."""
    legal = profile.get("legal_status", "unknown")
    ggr = profile.get("annual_ggr_billions", 0)
    n_casinos = profile.get("casino_count_approx", 0)

    if not regions:
        return (f"{state} does not have curated regional data in our database. "
                f"Legal status: {legal}. Consider running a manual State Recon for detailed analysis.")

    top = regions[0]
    summary = f"{state} ({legal} gaming, ~{n_casinos} venues, ${ggr:.1f}B annual GGR). "
    summary += f"Top recommended region: {top['region']} (score: {top['composite_score']}/100). "
    summary += top.get("placement_rationale", "")

    if len(regions) > 1:
        runner_up = regions[1]
        summary += f" Runner-up: {runner_up['region']} (score: {runner_up['composite_score']}/100)."

    return summary


# ============================================================
# CrewAI Tool Wrapper (optional pipeline integration)
# ============================================================

try:
    from crewai.tools import BaseTool

    class GeoResearchInput(BaseModel):
        state: str = Field(description="US state name, e.g. 'Georgia'")
        volatility: str = Field(default="medium", description="Game volatility: low, medium, high, very_high")
        target_rtp: float = Field(default=96.0, description="Target RTP percentage")
        theme: str = Field(default="", description="Game theme for context")
        output_dir: str = Field(default="", description="Output directory for JSON report")

    class GeoResearchTool(BaseTool):
        """Research optimal geographic regions for game placement within a US state."""

        name: str = "geographic_market_research"
        description: str = (
            "Research optimal regions within a US state for game placement. "
            "Analyzes demographics, casino density, tourism, and income to rank regions. "
            "Input: state name. Returns ranked regions with placement rationale."
        )
        args_schema: type[BaseModel] = GeoResearchInput

        def _run(self, state: str, volatility: str = "medium",
                 target_rtp: float = 96.0, theme: str = "", output_dir: str = "") -> str:
            result = run_geo_research(
                state=state,
                game_volatility=volatility,
                target_rtp=target_rtp,
                game_theme=theme,
                output_dir=output_dir or None,
            )
            return json.dumps(result, indent=2, default=str)

except ImportError:
    pass  # CrewAI not installed — standalone mode only
