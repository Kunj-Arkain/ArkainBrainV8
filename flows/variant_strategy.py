"""
ARKAINBRAIN — Variant Strategy Engine (Phase 9)

Generates deliberately divergent variant briefs from a single user concept.
Each variant explores a different design space: volatility, features, RTP budget,
max win, and mechanic combinations. Uses LLM for creative divergence with
deterministic fallback.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger("arkainbrain.variants")

# ═══════════════════════════════════════════════
# Predefined Strategy Templates
# ═══════════════════════════════════════════════

STRATEGY_TEMPLATES = [
    {
        "label": "High Vol + Hold-and-Spin",
        "icon": "🔥",
        "strategy": "Maximum drama: high volatility with hold-and-spin bonus. Long dry spells punctuated by massive wins. Target thrill-seekers.",
        "volatility": "high",
        "rtp_budget": {"base_game": 55, "free_spins": 15, "hold_and_spin": 30},
        "max_win_multiplier": 10000,
        "features": ["hold_and_spin", "free_spins", "expanding_wilds"],
        "target_audience": "High-roller thrill seekers",
    },
    {
        "label": "Medium Vol + Cascading",
        "icon": "🌊",
        "strategy": "Balanced excitement with cascading reels and multiplier wilds. Sweet spot between session length and win potential.",
        "volatility": "medium_high",
        "rtp_budget": {"base_game": 65, "cascade_multipliers": 25, "free_spins": 10},
        "max_win_multiplier": 5000,
        "features": ["cascading_reels", "multiplier_wilds", "free_spins"],
        "target_audience": "Regular players seeking engagement",
    },
    {
        "label": "Low Vol + Frequent Features",
        "icon": "🎯",
        "strategy": "Frequent small wins and constant feature triggers. Short session, high entertainment value. Mobile-first design.",
        "volatility": "low",
        "rtp_budget": {"base_game": 72, "free_spins": 18, "multipliers": 10},
        "max_win_multiplier": 2000,
        "features": ["free_spins", "stacked_wilds", "random_wilds", "respin"],
        "target_audience": "Casual and mobile players",
    },
    {
        "label": "Megaways + Progressive",
        "icon": "💎",
        "strategy": "Megaways mechanic with progressive jackpot contribution. Dream-big psychology with life-changing win potential.",
        "volatility": "extreme",
        "rtp_budget": {"base_game": 58, "free_spins": 22, "progressive": 20},
        "max_win_multiplier": 25000,
        "features": ["megaways", "free_spins", "progressive_jackpot", "multiplier_trail"],
        "target_audience": "Jackpot chasers and dreamers",
    },
    {
        "label": "Premium High RTP",
        "icon": "👑",
        "strategy": "Highest RTP tier targeting fairness-conscious players. Clean math, transparent mechanics, premium feel.",
        "volatility": "medium",
        "rtp_budget": {"base_game": 70, "free_spins": 20, "bonus_buy": 10},
        "max_win_multiplier": 5000,
        "features": ["free_spins", "bonus_buy", "expanding_wilds", "scatter_pays"],
        "target_audience": "Value-conscious experienced players",
    },
    {
        "label": "Cluster Pays + Multipliers",
        "icon": "⚡",
        "strategy": "No paylines — cluster pays with cascading multipliers. Modern mechanic that builds excitement through chain reactions.",
        "volatility": "medium_high",
        "rtp_budget": {"base_game": 62, "cluster_cascades": 28, "free_spins": 10},
        "max_win_multiplier": 8000,
        "features": ["cluster_pays", "cascading_reels", "multiplier_wilds", "free_spins"],
        "target_audience": "Modern slot enthusiasts",
    },
    {
        "label": "Pick-and-Click Bonus",
        "icon": "🎁",
        "strategy": "Interactive pick-and-click bonus rounds with player agency. Multiple bonus types for variety and replay value.",
        "volatility": "medium",
        "rtp_budget": {"base_game": 60, "pick_bonus": 25, "free_spins": 15},
        "max_win_multiplier": 3000,
        "features": ["pick_bonus", "free_spins", "multiplier_wilds", "gamble_feature"],
        "target_audience": "Players seeking interactive experiences",
    },
]

# ═══════════════════════════════════════════════
# LLM-Powered Strategy Generation
# ═══════════════════════════════════════════════

def generate_variant_strategies(theme: str, base_params: dict,
                                 count: int = 3, use_llm: bool = True) -> list[dict]:
    """Generate divergent variant strategies for a theme.

    Args:
        theme: User's game theme/concept
        base_params: Base pipeline parameters
        count: Number of variants (2-5)
        use_llm: Whether to use LLM for creative strategies

    Returns:
        List of variant strategy dicts with modified params
    """
    count = max(2, min(5, count))

    if use_llm:
        try:
            strategies = _llm_generate_strategies(theme, base_params, count)
            if strategies and len(strategies) == count:
                return strategies
        except Exception as e:
            logger.warning(f"LLM strategy generation failed, using templates: {e}")

    return _template_generate_strategies(theme, base_params, count)


def _llm_generate_strategies(theme: str, base_params: dict, count: int) -> Optional[list[dict]]:
    """Use LLM to generate creative divergent strategies."""
    import openai
    client = openai.OpenAI()

    features_list = ", ".join(base_params.get("requested_features", []))
    vol = base_params.get("volatility", "medium")
    rtp = base_params.get("target_rtp", 96)
    grid = f"{base_params.get('grid_cols',5)}x{base_params.get('grid_rows',3)}"

    prompt = f"""You are a slot game strategist. Given the theme "{theme}" with base config:
- Volatility: {vol}, RTP: {rtp}%, Grid: {grid}
- Features: {features_list or 'none specified'}

Generate exactly {count} DIVERGENT variant strategies. Each must explore a DELIBERATELY DIFFERENT design space.
Rules:
- Each variant should have a unique volatility level
- Feature sets must differ meaningfully (not just reordering)
- RTP budgets must be different allocations
- Max win multipliers should vary by at least 2x between variants
- Each targets a different player segment

Return a JSON array of {count} objects, each with:
- "label": 2-4 word strategy name
- "icon": one emoji
- "strategy": 1-2 sentence description
- "volatility": one of [low, medium, medium_high, high, extreme]
- "rtp_budget": object with category: percentage (must sum to ~100)
- "max_win_multiplier": integer
- "features": array of feature strings
- "target_audience": who this variant targets
- "rtp_adj": RTP adjustment from base (-2 to +2)
- "special_requirements": extra instructions for the pipeline agent

Return ONLY valid JSON array, no markdown."""

    resp = client.chat.completions.create(
        model=os.getenv("LLM_LIGHT", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.9,
    )

    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    strategies = json.loads(text)

    if not isinstance(strategies, list) or len(strategies) != count:
        return None

    # Validate and normalize
    for s in strategies:
        s.setdefault("label", "Variant")
        s.setdefault("icon", "🎰")
        s.setdefault("strategy", "")
        s.setdefault("volatility", "medium")
        s.setdefault("rtp_budget", {"base_game": 65, "features": 35})
        s.setdefault("max_win_multiplier", 5000)
        s.setdefault("features", ["free_spins"])
        s.setdefault("target_audience", "General")
        s.setdefault("rtp_adj", 0)
        s.setdefault("special_requirements", "")

    return strategies


def _template_generate_strategies(theme: str, base_params: dict, count: int) -> list[dict]:
    """Deterministic fallback using predefined templates."""
    templates = STRATEGY_TEMPLATES[:count]
    strategies = []
    for i, t in enumerate(templates):
        s = dict(t)
        s["rtp_adj"] = [-0.5, 0, 0.5, -1.0, 1.0][i % 5]
        s["special_requirements"] = f"VARIANT STRATEGY: {t['strategy']}"
        strategies.append(s)
    return strategies


# ═══════════════════════════════════════════════
# Build Variant Parameters
# ═══════════════════════════════════════════════

VOL_LEVELS = ["low", "medium", "medium_high", "high", "extreme"]


def build_variant_params(base_params: dict, strategy: dict, index: int) -> dict:
    """Build complete pipeline parameters for a variant.

    Merges base params with strategy modifications.
    """
    vp = {**base_params}

    # Apply volatility
    if strategy.get("volatility"):
        vp["volatility"] = strategy["volatility"]

    # Apply RTP adjustment
    rtp_adj = strategy.get("rtp_adj", 0)
    vp["target_rtp"] = round(max(85, min(99, vp.get("target_rtp", 96) + rtp_adj)), 1)

    # Apply max win
    if strategy.get("max_win_multiplier"):
        vp["max_win_multiplier"] = strategy["max_win_multiplier"]

    # Apply features
    if strategy.get("features"):
        vp["requested_features"] = strategy["features"]

    # Add strategy context for the pipeline agents
    strategy_text = strategy.get("strategy", "")
    audience = strategy.get("target_audience", "")
    rtp_budget = json.dumps(strategy.get("rtp_budget", {}))
    special = strategy.get("special_requirements", "")

    variant_context = (
        f"VARIANT STRATEGY: {strategy.get('label', 'Variant')}\n"
        f"Design Philosophy: {strategy_text}\n"
        f"Target Audience: {audience}\n"
        f"RTP Budget Allocation: {rtp_budget}\n"
        f"{special}"
    )
    vp["special_requirements"] = variant_context + "\n" + vp.get("special_requirements", "")

    # Store variant metadata
    vp["_variant"] = {
        "label": strategy.get("label", f"Variant {index+1}"),
        "icon": strategy.get("icon", "🎰"),
        "strategy": strategy_text,
        "target_audience": audience,
        "rtp_budget": strategy.get("rtp_budget", {}),
        "variant_index": index + 1,
    }

    return vp
