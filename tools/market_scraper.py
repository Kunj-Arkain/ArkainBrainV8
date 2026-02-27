"""
ARKAINBRAIN — Market Trend Data Manager (Phase 11)

Manages market trend data stored in the market_trends table.
In production, this would periodically scrape public game databases
(AskGamblers, SlotCatalog) and regulatory feeds. Currently uses
curated seed data + manual refresh support.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger("arkainbrain.market")


# ═══════════════════════════════════════════════
# Seed Market Data (Curated)
# ═══════════════════════════════════════════════

SEED_THEME_TRENDS = [
    {"category": "theme", "name": "Egyptian", "value": 12.5, "market_share": 12.5, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Asian", "value": 14.2, "market_share": 14.2, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Mythology", "value": 11.8, "market_share": 11.8, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Adventure", "value": 9.5, "market_share": 9.5, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Fantasy", "value": 8.3, "market_share": 8.3, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Horror", "value": 4.2, "market_share": 4.2, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Fruits/Classic", "value": 10.1, "market_share": 10.1, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Animals", "value": 7.6, "market_share": 7.6, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Ocean", "value": 5.4, "market_share": 5.4, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Space/Sci-Fi", "value": 3.8, "market_share": 3.8, "source": "SlotCatalog 2024", "period": "2024-Q4"},
    {"category": "theme", "name": "Irish/Celtic", "value": 6.2, "market_share": 6.2, "source": "SlotCatalog 2024", "period": "2024-Q4"},
]

SEED_MECHANIC_TRENDS = [
    {"category": "mechanic", "name": "Free Spins", "value": 82, "market_share": 82, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Multiplier Wilds", "value": 45, "market_share": 45, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Bonus Buy", "value": 35, "market_share": 35, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Gamble Feature", "value": 30, "market_share": 30, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Cascading Reels", "value": 28, "market_share": 28, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Hold and Spin", "value": 22, "market_share": 22, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Pick Bonus", "value": 20, "market_share": 20, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Megaways", "value": 18, "market_share": 18, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Progressive Jackpot", "value": 15, "market_share": 15, "source": "Industry Report 2024", "period": "2024-Q4"},
    {"category": "mechanic", "name": "Cluster Pays", "value": 12, "market_share": 12, "source": "Industry Report 2024", "period": "2024-Q4"},
]

SEED_VOLATILITY_TRENDS = [
    {"category": "volatility", "name": "Low", "value": 15, "market_share": 15, "source": "Market Analysis 2024", "period": "2024-Q4"},
    {"category": "volatility", "name": "Medium", "value": 35, "market_share": 35, "source": "Market Analysis 2024", "period": "2024-Q4"},
    {"category": "volatility", "name": "Medium-High", "value": 25, "market_share": 25, "source": "Market Analysis 2024", "period": "2024-Q4"},
    {"category": "volatility", "name": "High", "value": 20, "market_share": 20, "source": "Market Analysis 2024", "period": "2024-Q4"},
    {"category": "volatility", "name": "Extreme", "value": 5, "market_share": 5, "source": "Market Analysis 2024", "period": "2024-Q4"},
]

SEED_REGULATION_TRENDS = [
    {"category": "regulation", "name": "Ontario iGaming", "value": 1, "market_share": 0, "source": "AGCO", "period": "2024-Q4",
     "metadata": json.dumps({"status": "active", "opened": "2022-04", "regulator": "AGCO", "growth": "rapid"})},
    {"category": "regulation", "name": "UK Gambling Act Reform", "value": 1, "market_share": 0, "source": "UKGC", "period": "2024-Q4",
     "metadata": json.dumps({"status": "pending", "impact": "high", "max_stake_online": "£5"})},
    {"category": "regulation", "name": "Brazil Legalization", "value": 1, "market_share": 0, "source": "SIGAP", "period": "2024-Q4",
     "metadata": json.dumps({"status": "active", "opened": "2024-01", "regulator": "SIGAP", "growth": "explosive"})},
    {"category": "regulation", "name": "US State Expansion", "value": 1, "market_share": 0, "source": "AGA", "period": "2024-Q4",
     "metadata": json.dumps({"active_states": ["NJ", "MI", "PA", "WV", "CT", "DE"], "pending": ["NY", "IL", "MA"]})},
]


def seed_market_data(db: sqlite3.Connection):
    """Seed the market_trends table with curated data if empty."""
    count = db.execute("SELECT COUNT(*) as c FROM market_trends").fetchone()["c"]
    if count > 0:
        return count

    all_seeds = SEED_THEME_TRENDS + SEED_MECHANIC_TRENDS + SEED_VOLATILITY_TRENDS + SEED_REGULATION_TRENDS
    for s in all_seeds:
        db.execute(
            "INSERT INTO market_trends (id, category, name, value, market_share, source, period, metadata) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4())[:8], s["category"], s["name"], s.get("value", 0),
             s.get("market_share", 0), s.get("source", ""), s.get("period", ""),
             s.get("metadata", ""))
        )
    db.commit()
    logger.info(f"Seeded {len(all_seeds)} market trend records")
    return len(all_seeds)


def get_market_trends(db: sqlite3.Connection, category: Optional[str] = None) -> list[dict]:
    """Get market trends, optionally filtered by category."""
    if category:
        rows = db.execute(
            "SELECT * FROM market_trends WHERE category=? ORDER BY market_share DESC", (category,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM market_trends ORDER BY category, market_share DESC").fetchall()

    return [dict(r) for r in rows]


def get_trend_summary(db: sqlite3.Connection) -> dict:
    """Get aggregated trend summary for dashboard."""
    seed_market_data(db)

    themes = get_market_trends(db, "theme")
    mechanics = get_market_trends(db, "mechanic")
    volatility = get_market_trends(db, "volatility")
    regulations = get_market_trends(db, "regulation")

    return {
        "themes": [{"name": t["name"], "market_share": t["market_share"]} for t in themes],
        "mechanics": [{"name": m["name"], "adoption_pct": m["market_share"]} for m in mechanics],
        "volatility": [{"name": v["name"], "market_share": v["market_share"]} for v in volatility],
        "regulations": [{
            "name": r["name"],
            "metadata": json.loads(r["metadata"]) if r.get("metadata") else {},
            "source": r.get("source", ""),
        } for r in regulations],
        "last_updated": datetime.now().isoformat(),
        "total_records": len(themes) + len(mechanics) + len(volatility) + len(regulations),
    }


def update_trend(db: sqlite3.Connection, category: str, name: str,
                 value: float, market_share: float, source: str = "", period: str = ""):
    """Add or update a market trend record."""
    existing = db.execute(
        "SELECT id FROM market_trends WHERE category=? AND name=?", (category, name)
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE market_trends SET value=?, market_share=?, source=?, period=?, metadata='' WHERE id=?",
            (value, market_share, source, period, existing["id"])
        )
    else:
        db.execute(
            "INSERT INTO market_trends (id, category, name, value, market_share, source, period) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4())[:8], category, name, value, market_share, source, period)
        )
    db.commit()
