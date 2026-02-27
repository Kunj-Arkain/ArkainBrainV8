"""
ARKAINBRAIN — Cost Tracker (Phase A3)

Instruments LLM API calls to track:
- Token usage (input/output)
- Cost per call (from cost_rates table)
- Latency
- Provider and model

Usage:
    from tools.cost_tracker import track_llm_call, track_image_gen, get_cost_summary

    # Wrap any OpenAI/Anthropic call
    result = track_llm_call(
        user_id="u123", job_id="j456",
        provider="openai", model="gpt-4o-mini",
        input_tokens=1500, output_tokens=800,
        latency_ms=1200
    )

    # Track DALL-E image generation
    track_image_gen(user_id="u123", job_id="j456", count=4, model="dall-e-3")
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("arkainbrain.costs")

# ═══════════════════════════════════════════════
# Default Cost Rates (fallback if DB has no rates)
# ═══════════════════════════════════════════════

DEFAULT_RATES = {
    # OpenAI - per 1K tokens
    ("openai", "gpt-4o"):           {"input": 0.0025, "output": 0.010},
    ("openai", "gpt-4o-mini"):      {"input": 0.00015, "output": 0.0006},
    ("openai", "gpt-4.1"):          {"input": 0.002, "output": 0.008},
    ("openai", "gpt-4.1-mini"):     {"input": 0.0004, "output": 0.0016},
    ("openai", "gpt-4.1-nano"):     {"input": 0.0001, "output": 0.0004},
    ("openai", "o3-mini"):          {"input": 0.0011, "output": 0.0044},
    # Anthropic
    ("anthropic", "claude-sonnet-4-5-20250514"): {"input": 0.003, "output": 0.015},
    ("anthropic", "claude-haiku-3-5"):           {"input": 0.0008, "output": 0.004},
    # Images
    ("openai", "dall-e-3"):         {"image": 0.040},
    ("openai", "dall-e-3-hd"):      {"image": 0.080},
    ("openai", "gpt-image-1"):      {"image": 0.040},
    # Compute (per second)
    ("compute", "simulation"):      {"per_second": 0.00005},
    ("compute", "export"):          {"per_second": 0.00002},
}


def _get_rate(provider: str, model: str, db=None) -> dict:
    """Look up cost rate from DB, fallback to defaults."""
    if db:
        try:
            row = db.execute(
                "SELECT * FROM cost_rates WHERE provider=? AND model=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC LIMIT 1",
                (provider, model, datetime.now().isoformat())
            ).fetchone()
            if row:
                return {
                    "input": row["input_cost_per_1k"] or 0,
                    "output": row["output_cost_per_1k"] or 0,
                    "image": row["image_cost"] or 0,
                }
        except Exception:
            pass
    return DEFAULT_RATES.get((provider, model), {"input": 0, "output": 0})


def _calculate_cost(provider: str, model: str, input_tokens: int = 0,
                    output_tokens: int = 0, image_count: int = 0, db=None) -> float:
    """Calculate cost in USD."""
    rate = _get_rate(provider, model, db)
    cost = 0.0
    if input_tokens:
        cost += (input_tokens / 1000) * rate.get("input", 0)
    if output_tokens:
        cost += (output_tokens / 1000) * rate.get("output", 0)
    if image_count:
        cost += image_count * rate.get("image", 0)
    return round(cost, 6)


# ═══════════════════════════════════════════════
# Tracking Functions
# ═══════════════════════════════════════════════

def track_llm_call(user_id: str, job_id: str = None, provider: str = "openai",
                   model: str = "gpt-4o-mini", input_tokens: int = 0,
                   output_tokens: int = 0, latency_ms: int = 0,
                   metadata: dict = None) -> dict:
    """Record an LLM API call with cost."""
    try:
        from config.database import get_db
        db = get_db()
        cost = _calculate_cost(provider, model, input_tokens, output_tokens, db=db)
        event_id = str(uuid.uuid4())[:12]

        db.execute(
            "INSERT INTO cost_events (id, job_id, user_id, event_type, provider, model, "
            "input_tokens, output_tokens, cost_usd, latency_ms, metadata, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, job_id, user_id, "llm_call", provider, model,
             input_tokens, output_tokens, cost,
             latency_ms, json.dumps(metadata) if metadata else None,
             datetime.now().isoformat())
        )
        db.commit()
        return {"id": event_id, "cost_usd": cost, "tokens": input_tokens + output_tokens}
    except Exception as e:
        logger.warning(f"Cost tracking failed: {e}")
        return {"id": None, "cost_usd": 0, "error": str(e)}


def track_image_gen(user_id: str, job_id: str = None, count: int = 1,
                    model: str = "dall-e-3", provider: str = "openai",
                    latency_ms: int = 0, metadata: dict = None) -> dict:
    """Record image generation cost."""
    try:
        from config.database import get_db
        db = get_db()
        cost = _calculate_cost(provider, model, image_count=count, db=db)
        event_id = str(uuid.uuid4())[:12]

        db.execute(
            "INSERT INTO cost_events (id, job_id, user_id, event_type, provider, model, "
            "image_count, cost_usd, latency_ms, metadata, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, job_id, user_id, "image_gen", provider, model,
             count, cost, latency_ms,
             json.dumps(metadata) if metadata else None,
             datetime.now().isoformat())
        )
        db.commit()
        return {"id": event_id, "cost_usd": cost, "images": count}
    except Exception as e:
        logger.warning(f"Image cost tracking failed: {e}")
        return {"id": None, "cost_usd": 0, "error": str(e)}


def track_compute(user_id: str, job_id: str = None, event_type: str = "simulation",
                  duration_seconds: float = 0, metadata: dict = None) -> dict:
    """Record compute cost (simulation, export, etc.)."""
    try:
        from config.database import get_db
        db = get_db()
        rate = _get_rate("compute", event_type, db)
        cost = round(duration_seconds * rate.get("per_second", 0.00005), 6)
        event_id = str(uuid.uuid4())[:12]

        db.execute(
            "INSERT INTO cost_events (id, job_id, user_id, event_type, provider, model, "
            "cost_usd, latency_ms, metadata, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (event_id, job_id, user_id, event_type, "compute", event_type,
             cost, int(duration_seconds * 1000),
             json.dumps(metadata) if metadata else None,
             datetime.now().isoformat())
        )
        db.commit()
        return {"id": event_id, "cost_usd": cost}
    except Exception as e:
        logger.warning(f"Compute cost tracking failed: {e}")
        return {"id": None, "cost_usd": 0, "error": str(e)}


# ═══════════════════════════════════════════════
# Query Functions
# ═══════════════════════════════════════════════

def get_cost_summary(db, user_id: str = None, days: int = 30) -> dict:
    """Get cost summary, optionally filtered by user."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    user_filter = "AND user_id=?" if user_id else ""
    params = [since] + ([user_id] if user_id else [])

    total = db.execute(
        f"SELECT COALESCE(SUM(cost_usd),0) as total FROM cost_events WHERE created_at>=? {user_filter}",
        params
    ).fetchone()["total"]

    by_provider = db.execute(
        f"SELECT provider, SUM(cost_usd) as cost, COUNT(*) as calls FROM cost_events WHERE created_at>=? {user_filter} GROUP BY provider ORDER BY cost DESC",
        params
    ).fetchall()

    by_model = db.execute(
        f"SELECT model, SUM(cost_usd) as cost, SUM(input_tokens) as inp, SUM(output_tokens) as out, COUNT(*) as calls FROM cost_events WHERE created_at>=? {user_filter} GROUP BY model ORDER BY cost DESC",
        params
    ).fetchall()

    by_type = db.execute(
        f"SELECT event_type, SUM(cost_usd) as cost, COUNT(*) as calls FROM cost_events WHERE created_at>=? {user_filter} GROUP BY event_type ORDER BY cost DESC",
        params
    ).fetchall()

    by_day = db.execute(
        f"SELECT DATE(created_at) as day, SUM(cost_usd) as cost FROM cost_events WHERE created_at>=? {user_filter} GROUP BY DATE(created_at) ORDER BY day",
        params
    ).fetchall()

    return {
        "total_usd": round(total, 4),
        "period_days": days,
        "by_provider": [{"provider": r["provider"], "cost": round(r["cost"], 4), "calls": r["calls"]} for r in by_provider],
        "by_model": [{"model": r["model"], "cost": round(r["cost"], 4), "input_tokens": r["inp"] or 0, "output_tokens": r["out"] or 0, "calls": r["calls"]} for r in by_model],
        "by_type": [{"type": r["event_type"], "cost": round(r["cost"], 4), "calls": r["calls"]} for r in by_type],
        "by_day": [{"day": r["day"], "cost": round(r["cost"], 4)} for r in by_day],
    }


def get_top_spenders(db, days: int = 30, limit: int = 20) -> list:
    """Get users sorted by total cost."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT c.user_id, u.email, u.name, u.plan, SUM(c.cost_usd) as total_cost, COUNT(*) as total_calls, "
        "SUM(c.input_tokens) as total_input, SUM(c.output_tokens) as total_output "
        "FROM cost_events c LEFT JOIN users u ON c.user_id=u.id "
        "WHERE c.created_at>=? GROUP BY c.user_id ORDER BY total_cost DESC LIMIT ?",
        (since, limit)
    ).fetchall()
    return [{"user_id": r["user_id"], "email": r["email"], "name": r["name"] or "",
             "plan": r["plan"] or "free", "cost": round(r["total_cost"], 4),
             "calls": r["total_calls"],
             "tokens": (r["total_input"] or 0) + (r["total_output"] or 0)} for r in rows]


def get_cost_per_job(db, days: int = 30, limit: int = 20) -> list:
    """Get per-job cost breakdown."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT c.job_id, j.title, j.job_type, j.user_id, u.email, "
        "SUM(c.cost_usd) as total_cost, COUNT(*) as calls, "
        "SUM(c.input_tokens) as inp, SUM(c.output_tokens) as out "
        "FROM cost_events c "
        "LEFT JOIN jobs j ON c.job_id=j.id "
        "LEFT JOIN users u ON c.user_id=u.id "
        "WHERE c.created_at>=? AND c.job_id IS NOT NULL "
        "GROUP BY c.job_id ORDER BY total_cost DESC LIMIT ?",
        (since, limit)
    ).fetchall()
    return [{"job_id": r["job_id"], "title": r["title"], "type": r["job_type"] or "",
             "email": r["email"] or "", "cost": round(r["total_cost"], 4),
             "calls": r["calls"], "tokens": (r["inp"] or 0) + (r["out"] or 0)} for r in rows]


def seed_cost_rates(db):
    """Seed the cost_rates table with current pricing if empty."""
    count = db.execute("SELECT COUNT(*) as c FROM cost_rates").fetchone()["c"]
    if count > 0:
        return

    now = datetime.now().isoformat()
    for (provider, model), rates in DEFAULT_RATES.items():
        db.execute(
            "INSERT OR IGNORE INTO cost_rates (id, provider, model, input_cost_per_1k, output_cost_per_1k, image_cost, effective_from) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4())[:8], provider, model,
             rates.get("input", 0), rates.get("output", 0), rates.get("image", rates.get("per_second", 0)),
             now)
        )
    db.commit()
    logger.info(f"Seeded {len(DEFAULT_RATES)} cost rates")
