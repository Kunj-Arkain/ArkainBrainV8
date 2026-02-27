"""
ARKAINBRAIN — Portfolio Intelligence Engine (Phase 11)

Aggregates cross-portfolio analytics:
- Theme/volatility/jurisdiction coverage heatmaps
- Gap analysis with actionable recommendations
- Revenue projection aggregation
- Trend monitoring signals
- Historical generation cadence
"""

import json
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("arkainbrain.portfolio")


# ═══════════════════════════════════════════════
# Theme Taxonomy
# ═══════════════════════════════════════════════

THEME_CATEGORIES = {
    "egyptian": ["egypt", "pharaoh", "cleopatra", "pyramid", "nile", "sphinx", "ra", "anubis", "scarab"],
    "asian": ["dragon", "chinese", "japanese", "samurai", "koi", "panda", "fortune", "jade", "lucky", "lunar"],
    "mythology": ["zeus", "thor", "odin", "greek", "norse", "roman", "athena", "poseidon", "viking"],
    "adventure": ["explorer", "treasure", "jungle", "pirate", "quest", "island", "safari", "expedition"],
    "fantasy": ["wizard", "magic", "unicorn", "fairy", "elf", "goblin", "enchanted", "spell", "crystal"],
    "horror": ["vampire", "zombie", "halloween", "werewolf", "haunted", "dark", "blood", "ghost"],
    "fruits": ["fruit", "cherry", "lemon", "watermelon", "classic", "retro", "7s", "bar"],
    "animals": ["wolf", "lion", "eagle", "bear", "buffalo", "horse", "wild animal"],
    "ocean": ["ocean", "sea", "fish", "mermaid", "underwater", "coral", "shark", "atlantis"],
    "space": ["space", "star", "galaxy", "cosmic", "alien", "planet", "moon", "nebula"],
    "irish": ["irish", "leprechaun", "clover", "shamrock", "pot of gold", "rainbow"],
    "music": ["rock", "band", "music", "concert", "dj", "disco"],
    "sports": ["football", "soccer", "basketball", "racing", "boxing"],
    "food": ["sweet", "candy", "cake", "chocolate", "sugar", "bakery"],
}

MECHANIC_CATEGORIES = {
    "free_spins": ["free_spin", "free spin", "freespin"],
    "cascading": ["cascade", "tumble", "avalanche", "cascading"],
    "megaways": ["megaway", "mega ways"],
    "hold_and_spin": ["hold_and_spin", "hold and spin", "respin", "re-spin"],
    "cluster_pays": ["cluster", "cluster_pay"],
    "bonus_buy": ["bonus_buy", "buy bonus", "feature buy"],
    "multiplier_wilds": ["multiplier_wild", "wild multiplier", "expanding wild"],
    "progressive": ["progressive", "jackpot", "grand jackpot"],
    "pick_bonus": ["pick_bonus", "pick and click", "pick bonus"],
    "gamble": ["gamble", "double up", "risk game"],
    "expanding_reels": ["expanding_reel", "expanding grid"],
    "sticky_wilds": ["sticky_wild", "sticky wild"],
    "split_symbols": ["split_symbol", "split symbol"],
    "random_wilds": ["random_wild", "random wild"],
}

MARKET_DATA = {
    "themes": {
        "egyptian": 12.5, "asian": 14.2, "mythology": 11.8, "adventure": 9.5,
        "fantasy": 8.3, "horror": 4.2, "fruits": 10.1, "animals": 7.6,
        "ocean": 5.4, "space": 3.8, "irish": 6.2, "music": 2.1, "sports": 1.8, "food": 2.5,
    },
    "mechanics": {
        "free_spins": 82, "cascading": 28, "megaways": 18, "hold_and_spin": 22,
        "cluster_pays": 12, "bonus_buy": 35, "multiplier_wilds": 45,
        "progressive": 15, "pick_bonus": 20, "gamble": 30,
    },
    "volatility": {"low": 15, "medium": 35, "medium_high": 25, "high": 20, "extreme": 5},
}


# ═══════════════════════════════════════════════
# Portfolio Aggregation
# ═══════════════════════════════════════════════

def get_portfolio_overview(db: sqlite3.Connection, user_id: str) -> dict:
    """Aggregate portfolio-wide statistics."""
    jobs = db.execute(
        "SELECT * FROM jobs WHERE user_id=? AND status='complete' AND job_type IN ('slot_pipeline','variant','iterate','hybrid')",
        (user_id,)
    ).fetchall()

    if not jobs:
        return {"total_games": 0, "themes": {}, "volatility": {}, "jurisdictions": {},
                "mechanics": {}, "rtp_stats": {}, "timeline": [], "revenue": {}}

    themes = Counter()
    volatilities = Counter()
    jurisdictions = Counter()
    mechanics = Counter()
    rtps = []
    timeline = defaultdict(int)
    revenue_total = 0
    revenue_items = []

    for job in jobs:
        params = json.loads(job["params"]) if job["params"] else {}
        theme = params.get("theme", job["title"] if job["title"] else "")

        # Classify theme
        for cat, keywords in THEME_CATEGORIES.items():
            if any(kw in theme.lower() for kw in keywords):
                themes[cat] += 1
                break
        else:
            themes["other"] += 1

        # Volatility
        vol = params.get("volatility", "medium")
        volatilities[vol] += 1

        # Jurisdictions
        markets = params.get("target_markets", [])
        if isinstance(markets, str):
            markets = [m.strip() for m in markets.split(",")]
        for m in markets:
            jurisdictions[m.strip().lower()] += 1

        # Mechanics
        feats = params.get("requested_features", [])
        if isinstance(feats, str):
            feats = [f.strip() for f in feats.split(",")]
        for feat in feats:
            for mech, keywords in MECHANIC_CATEGORIES.items():
                if any(kw in feat.lower() for kw in keywords):
                    mechanics[mech] += 1
                    break

        # RTP
        rtp = params.get("target_rtp")
        if rtp: rtps.append(float(rtp))

        # Timeline
        created = job["created_at"] if job["created_at"] else ""
        if created:
            month = created[:7]
            timeline[month] += 1

        # Revenue
        if job["output_dir"]:
            rev_path = Path(job["output_dir"]) / "08_revenue" / "revenue_projection.json"
            if rev_path.exists():
                try:
                    rev = json.loads(rev_path.read_text())
                    ggr = rev.get("ggr_365d", 0)
                    if isinstance(ggr, (int, float)):
                        revenue_total += ggr
                        revenue_items.append({
                            "title": job["title"] or "",
                            "ggr_365d": ggr,
                            "arpdau": rev.get("arpdau", 0),
                            "roi_365d": rev.get("roi_365d", 0),
                        })
                except Exception:
                    pass

    rtp_stats = {}
    if rtps:
        rtps.sort()
        rtp_stats = {
            "min": min(rtps), "max": max(rtps),
            "mean": sum(rtps) / len(rtps),
            "median": rtps[len(rtps) // 2],
            "count": len(rtps),
        }

    return {
        "total_games": len(jobs),
        "themes": dict(themes.most_common()),
        "volatility": dict(volatilities.most_common()),
        "jurisdictions": dict(jurisdictions.most_common()),
        "mechanics": dict(mechanics.most_common()),
        "rtp_stats": rtp_stats,
        "timeline": [{"month": k, "count": v} for k, v in sorted(timeline.items())],
        "revenue": {
            "total_projected_ggr": revenue_total,
            "game_count_with_revenue": len(revenue_items),
            "top_games": sorted(revenue_items, key=lambda x: x.get("ggr_365d", 0), reverse=True)[:10],
        },
    }


# ═══════════════════════════════════════════════
# Gap Analysis
# ═══════════════════════════════════════════════

def analyze_gaps(overview: dict) -> list[dict]:
    """Identify portfolio gaps with actionable recommendations."""
    gaps = []
    total = overview.get("total_games", 0)
    if total == 0:
        return [{"type": "info", "severity": "info", "icon": "ℹ️",
                 "title": "Empty Portfolio", "message": "Generate your first game to see portfolio analytics."}]

    themes = overview.get("themes", {})
    vols = overview.get("volatility", {})
    mechs = overview.get("mechanics", {})
    jurisdictions = overview.get("jurisdictions", {})

    # ── Theme gaps ──
    for cat, market_pct in MARKET_DATA["themes"].items():
        count = themes.get(cat, 0)
        portfolio_pct = (count / total * 100) if total > 0 else 0
        if market_pct > 5 and count == 0:
            gaps.append({
                "type": "theme_gap", "severity": "high", "icon": "🎨",
                "title": f"Missing {cat.title()} Theme",
                "message": f"{cat.title()} represents {market_pct}% of market but you have 0 games.",
                "recommendation": f"Generate a {cat} slot to capture this segment.",
                "market_share": market_pct,
            })
        elif market_pct > 8 and portfolio_pct < market_pct * 0.3:
            gaps.append({
                "type": "theme_underweight", "severity": "medium", "icon": "📊",
                "title": f"Underweight {cat.title()}",
                "message": f"{cat.title()} is {market_pct}% of market but only {portfolio_pct:.0f}% of your portfolio ({count}/{total}).",
                "recommendation": f"Consider adding more {cat} variants.",
                "market_share": market_pct,
            })

    # Check for over-concentration
    if themes:
        top_theme, top_count = max(themes.items(), key=lambda x: x[1])
        if top_count / total > 0.4 and total >= 3:
            gaps.append({
                "type": "theme_concentration", "severity": "medium", "icon": "⚠️",
                "title": f"Theme Concentration Risk",
                "message": f"{top_count}/{total} games ({top_count/total*100:.0f}%) are {top_theme}. Diversify to reduce risk.",
                "recommendation": "Explore other popular themes like Asian, Mythology, or Adventure.",
            })

    # ── Volatility gaps ──
    for vol, market_pct in MARKET_DATA["volatility"].items():
        count = vols.get(vol, 0)
        if market_pct > 10 and count == 0 and total >= 3:
            gaps.append({
                "type": "volatility_gap", "severity": "medium", "icon": "📈",
                "title": f"No {vol.replace('_', ' ').title()} Volatility Games",
                "message": f"{vol.replace('_', ' ').title()} volatility is {market_pct}% of market but missing from your portfolio.",
                "recommendation": f"Create a {vol.replace('_', ' ')} volatility game for broader coverage.",
            })

    # ── Mechanic gaps ──
    for mech, adoption_pct in MARKET_DATA["mechanics"].items():
        count = mechs.get(mech, 0)
        if adoption_pct > 20 and count == 0 and total >= 3:
            gaps.append({
                "type": "mechanic_gap", "severity": "low", "icon": "⚡",
                "title": f"Missing {mech.replace('_', ' ').title()} Mechanic",
                "message": f"{mech.replace('_', ' ').title()} is in {adoption_pct}% of new slots but missing from your portfolio.",
                "recommendation": f"Add {mech.replace('_', ' ')} to your next game.",
            })

    # ── Jurisdiction gaps ──
    key_markets = ["uk", "malta", "ontario", "michigan", "new jersey", "sweden"]
    for market in key_markets:
        if market not in [j.lower() for j in jurisdictions]:
            gaps.append({
                "type": "jurisdiction_gap", "severity": "low", "icon": "🌍",
                "title": f"No games targeting {market.title()}",
                "message": f"Consider expanding to the {market.title()} market for additional revenue.",
            })

    # ── RTP distribution ──
    rtp_stats = overview.get("rtp_stats", {})
    if rtp_stats.get("count", 0) >= 3:
        if rtp_stats.get("max", 0) - rtp_stats.get("min", 0) < 1.0:
            gaps.append({
                "type": "rtp_narrow", "severity": "low", "icon": "🎯",
                "title": "Narrow RTP Range",
                "message": f"All games cluster around {rtp_stats['mean']:.1f}%. Consider a wider range for different operator needs.",
                "recommendation": "Create variants at 94% (high vol) and 97% (premium) for flexibility.",
            })

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    gaps.sort(key=lambda g: severity_order.get(g.get("severity", "low"), 3))

    return gaps


# ═══════════════════════════════════════════════
# Coverage Heatmap
# ═══════════════════════════════════════════════

def build_coverage_heatmap(overview: dict) -> dict:
    """Build theme × volatility coverage matrix."""
    themes = list(THEME_CATEGORIES.keys())
    vols = ["low", "medium", "medium_high", "high", "extreme"]

    # We only have aggregate counts, so build from the overview
    heatmap = {t: {v: 0 for v in vols} for t in themes}

    # In a real system, this would query individual games
    # For now, distribute proportionally
    theme_counts = overview.get("themes", {})
    vol_counts = overview.get("volatility", {})
    total = overview.get("total_games", 0)

    if total > 0:
        vol_probs = {v: vol_counts.get(v, 0) / total for v in vols}
        for theme, count in theme_counts.items():
            if theme in heatmap:
                for v in vols:
                    heatmap[theme][v] = round(count * vol_probs.get(v, 0), 1)

    return {"themes": themes, "volatilities": vols, "data": heatmap,
            "market_data": MARKET_DATA["themes"]}


# ═══════════════════════════════════════════════
# Revenue Scenarios
# ═══════════════════════════════════════════════

def project_portfolio_revenue(overview: dict, scenario: str = "base") -> dict:
    """Aggregate and project portfolio revenue."""
    rev = overview.get("revenue", {})
    total_ggr = rev.get("total_projected_ggr", 0)
    game_count = rev.get("game_count_with_revenue", 0)
    top_games = rev.get("top_games", [])

    multipliers = {"conservative": 0.6, "base": 1.0, "optimistic": 1.5, "bull": 2.0}
    mult = multipliers.get(scenario, 1.0)

    quarterly = total_ggr * mult / 4
    monthly = total_ggr * mult / 12

    return {
        "scenario": scenario,
        "annual_ggr": round(total_ggr * mult, 2),
        "quarterly_ggr": round(quarterly, 2),
        "monthly_ggr": round(monthly, 2),
        "games_contributing": game_count,
        "avg_ggr_per_game": round(total_ggr * mult / max(game_count, 1), 2),
        "top_games": [{**g, "adjusted_ggr": round(g.get("ggr_365d", 0) * mult, 2)} for g in top_games[:5]],
    }


# ═══════════════════════════════════════════════
# Trend Signals
# ═══════════════════════════════════════════════

def get_trend_signals() -> list[dict]:
    """Return current market trend signals (static data for now, can be enhanced with scraper)."""
    return [
        {"category": "mechanic", "name": "Bonus Buy", "trend": "rising",
         "signal": "35% of new releases include bonus buy option. Growing 8% YoY.",
         "action": "Consider adding bonus buy to new games."},
        {"category": "mechanic", "name": "Megaways", "trend": "stable",
         "signal": "18% market share, stable for 2 years. Still popular but growth plateauing.",
         "action": "Include in portfolio but don't over-invest."},
        {"category": "mechanic", "name": "Cluster Pays", "trend": "rising",
         "signal": "12% and growing. Popular with modern/casual players.",
         "action": "Good diversification for non-traditional slot fans."},
        {"category": "theme", "name": "Asian/Lunar", "trend": "rising",
         "signal": "14.2% market share, driven by Asian market expansion.",
         "action": "Create Asian-themed games for growing markets."},
        {"category": "regulation", "name": "Ontario iGaming", "trend": "rising",
         "signal": "Ontario opened April 2022. Growing rapidly. Requires AGCO compliance.",
         "action": "Target Ontario jurisdiction in new games."},
        {"category": "regulation", "name": "UK Max Stake", "trend": "warning",
         "signal": "UK considering further stake limits. Currently £5 online.",
         "action": "Ensure all UK-targeted games comply with bet limits."},
        {"category": "technology", "name": "HTML5 Mobile-First", "trend": "stable",
         "signal": "75%+ of slot play is on mobile. Performance critical.",
         "action": "Prioritize mobile optimization and touch interactions."},
        {"category": "mechanic", "name": "Hold and Spin", "trend": "rising",
         "signal": "22% adoption and growing. Popular for jackpot-style features.",
         "action": "Strong feature for high-volatility games."},
    ]


# ═══════════════════════════════════════════════
# Market Alignment Score
# ═══════════════════════════════════════════════

def calculate_alignment_score(overview: dict) -> dict:
    """Calculate how well the portfolio aligns with market demand.

    Returns a 0-100 score plus per-dimension breakdown.
    """
    total = overview.get("total_games", 0)
    if total == 0:
        return {"overall": 0, "dimensions": {}, "grade": "N/A"}

    themes = overview.get("themes", {})
    vols = overview.get("volatility", {})
    mechs = overview.get("mechanics", {})

    def _dimension_score(portfolio_dist: dict, market_dist: dict) -> float:
        """Compare portfolio distribution vs market. Lower divergence = higher score."""
        if not portfolio_dist or not market_dist:
            return 50.0
        p_total = sum(portfolio_dist.values()) or 1
        m_total = sum(market_dist.values()) or 1
        divergence = 0
        all_keys = set(list(portfolio_dist.keys()) + list(market_dist.keys()))
        for k in all_keys:
            p_pct = (portfolio_dist.get(k, 0) / p_total) * 100
            m_pct = (market_dist.get(k, 0) / m_total) * 100
            divergence += abs(p_pct - m_pct)
        # Max possible divergence is ~200 (all in one bucket vs opposite)
        return max(0, 100 - divergence)

    theme_score = _dimension_score(themes, MARKET_DATA["themes"])
    vol_score = _dimension_score(vols, MARKET_DATA["volatility"])
    mech_score = _dimension_score(mechs, MARKET_DATA["mechanics"])

    # Coverage bonus: reward having games in more categories
    coverage = len(themes) / max(len(THEME_CATEGORIES), 1) * 100
    coverage_score = min(100, coverage * 1.5)

    # Weighted overall
    overall = (theme_score * 0.3 + vol_score * 0.25 + mech_score * 0.25 + coverage_score * 0.2)

    grades = [(90, "A+"), (80, "A"), (70, "B+"), (60, "B"), (50, "C+"), (40, "C"), (0, "D")]
    grade = next(g for threshold, g in grades if overall >= threshold)

    return {
        "overall": round(overall, 1),
        "grade": grade,
        "dimensions": {
            "theme_alignment": round(theme_score, 1),
            "volatility_alignment": round(vol_score, 1),
            "mechanic_alignment": round(mech_score, 1),
            "category_coverage": round(coverage_score, 1),
        },
        "interpretation": {
            "theme_alignment": "How well your theme mix matches market demand",
            "volatility_alignment": "How your volatility spread matches player preferences",
            "mechanic_alignment": "Whether you use the mechanics players want",
            "category_coverage": "How many theme categories you cover",
        },
    }


# ═══════════════════════════════════════════════
# Scenario Builder
# ═══════════════════════════════════════════════

def build_launch_scenario(overview: dict, selected_games: list[dict],
                          quarter: str = "Q3") -> dict:
    """Project revenue if selected games are launched in a given quarter.

    Args:
        overview: Current portfolio overview
        selected_games: List of {title, ggr_365d, ...} for games to include
        quarter: Target launch quarter (Q1-Q4)
    """
    quarter_months = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}
    months_remaining = 12 - quarter_months.get(quarter, 6)

    existing_ggr = overview.get("revenue", {}).get("total_projected_ggr", 0)
    new_ggr = sum(g.get("ggr_365d", 0) for g in selected_games)

    # Partial year for new launches
    partial_new = new_ggr * (months_remaining / 12) if months_remaining > 0 else 0

    # Ramp factor (games take 2-3 months to reach full performance)
    ramp_factor = max(0.5, 1.0 - (2 / max(months_remaining, 1)))

    return {
        "quarter": quarter,
        "selected_games": len(selected_games),
        "existing_annual_ggr": round(existing_ggr, 2),
        "new_games_full_year_ggr": round(new_ggr, 2),
        "new_games_partial_ggr": round(partial_new * ramp_factor, 2),
        "combined_ggr": round(existing_ggr + partial_new * ramp_factor, 2),
        "months_remaining": months_remaining,
        "ramp_factor": round(ramp_factor, 2),
        "scenarios": {
            "conservative": round((existing_ggr + partial_new * ramp_factor) * 0.6, 2),
            "base": round(existing_ggr + partial_new * ramp_factor, 2),
            "optimistic": round((existing_ggr + partial_new * ramp_factor) * 1.5, 2),
        },
    }


# ═══════════════════════════════════════════════
# Portfolio Snapshots
# ═══════════════════════════════════════════════

def capture_snapshot(db: sqlite3.Connection, user_id: str, overview: dict = None) -> str:
    """Capture current portfolio state as a snapshot for historical tracking."""
    import uuid as _uuid

    if overview is None:
        overview = get_portfolio_overview(db, user_id)

    gaps = analyze_gaps(overview)
    snap_id = str(_uuid.uuid4())[:8]
    today = datetime.now().strftime("%Y-%m-%d")

    db.execute(
        """INSERT INTO portfolio_snapshots
           (id, user_id, snapshot_date, total_games, total_revenue_projected,
            theme_distribution, volatility_distribution, jurisdiction_coverage,
            mechanic_coverage, rtp_stats, gap_analysis, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (snap_id, user_id, today, overview.get("total_games", 0),
         overview.get("revenue", {}).get("total_projected_ggr", 0),
         json.dumps(overview.get("themes", {})),
         json.dumps(overview.get("volatility", {})),
         json.dumps(overview.get("jurisdictions", {})),
         json.dumps(overview.get("mechanics", {})),
         json.dumps(overview.get("rtp_stats", {})),
         json.dumps([{"severity": g.get("severity"), "title": g.get("title")} for g in gaps]),
         datetime.now().isoformat())
    )
    db.commit()
    return snap_id


def get_snapshots(db: sqlite3.Connection, user_id: str, limit: int = 30) -> list[dict]:
    """Get historical portfolio snapshots for trend comparison."""
    rows = db.execute(
        "SELECT * FROM portfolio_snapshots WHERE user_id=? ORDER BY snapshot_date DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()

    snapshots = []
    for r in rows:
        snapshots.append({
            "id": r["id"],
            "date": r["snapshot_date"],
            "total_games": r["total_games"],
            "revenue": r["total_revenue_projected"],
            "themes": json.loads(r["theme_distribution"]) if r["theme_distribution"] else {},
            "volatility": json.loads(r["volatility_distribution"]) if r["volatility_distribution"] else {},
            "jurisdictions": json.loads(r["jurisdiction_coverage"]) if r["jurisdiction_coverage"] else {},
            "mechanics": json.loads(r["mechanic_coverage"]) if r["mechanic_coverage"] else {},
            "rtp_stats": json.loads(r["rtp_stats"]) if r["rtp_stats"] else {},
            "gaps": json.loads(r["gap_analysis"]) if r["gap_analysis"] else [],
        })
    return snapshots
