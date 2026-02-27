"""
ARKAINBRAIN — Memory Query Engine (Phase 6)

Semantic search across run_records and component_library.
Uses pgvector for PostgreSQL, in-memory cosine similarity for SQLite.
Falls back to keyword matching when embeddings unavailable.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("arkainbrain.memory")


def search_similar_runs(
    theme: str,
    volatility: str = "",
    features: list[str] = None,
    jurisdictions: list[str] = None,
    grid: str = "",
    limit: int = 5,
    user_id: str = "",
) -> list[dict]:
    """Find similar past pipeline runs via semantic search.

    Returns list of run_record dicts sorted by relevance.
    """
    from config.database import get_standalone_db, USE_POSTGRES
    from memory.embeddings import (
        get_embedding, build_run_text, cosine_similarity,
        deserialize_embedding, keyword_similarity,
    )

    features = features or []
    jurisdictions = jurisdictions or []

    # Build query embedding
    query_text = build_run_text(
        theme=theme, volatility=volatility,
        features=features, jurisdictions=jurisdictions, grid=grid,
    )
    query_embedding = get_embedding(query_text)

    db = get_standalone_db()
    try:
        # Fetch candidates
        if user_id:
            db.execute(
                "SELECT * FROM run_records WHERE user_id = %s ORDER BY created_at DESC LIMIT 100",
                [user_id]
            )
        else:
            db.execute(
                "SELECT * FROM run_records ORDER BY created_at DESC LIMIT 100"
            )
        candidates = db.fetchall()
    finally:
        db.close()

    if not candidates:
        return []

    # Score and rank
    scored = []
    for row in candidates:
        row = dict(row) if not isinstance(row, dict) else row
        score = 0.0

        if query_embedding:
            row_embedding = deserialize_embedding(row.get("embedding"))
            if row_embedding:
                score = cosine_similarity(query_embedding, row_embedding)
            else:
                # Fallback: keyword similarity
                row_text = f"{row.get('theme', '')} {row.get('volatility', '')} {row.get('features', '')}"
                score = keyword_similarity(query_text, row_text)
        else:
            # No embedding available — pure keyword match
            row_text = f"{row.get('theme', '')} {row.get('volatility', '')} {row.get('features', '')}"
            score = keyword_similarity(query_text, row_text)

        # Boost exact volatility match
        if volatility and row.get("volatility") == volatility:
            score += 0.1

        # Boost overlapping features
        try:
            row_feats = json.loads(row.get("features", "[]"))
            overlap = set(features) & set(row_feats)
            score += 0.05 * len(overlap)
        except Exception:
            pass

        # Boost overlapping jurisdictions
        try:
            row_markets = json.loads(row.get("jurisdictions", "[]"))
            market_overlap = set(j.lower() for j in jurisdictions) & set(j.lower() for j in row_markets)
            score += 0.03 * len(market_overlap)
        except Exception:
            pass

        row["_relevance_score"] = round(score, 4)
        scored.append(row)

    scored.sort(key=lambda x: x["_relevance_score"], reverse=True)

    # Clean up large fields before returning
    results = []
    for row in scored[:limit]:
        clean = {k: v for k, v in row.items()
                 if k not in ("embedding", "reel_strips") and v is not None}
        # Truncate large JSON fields
        for field in ("paytable", "feature_config", "rtp_budget_breakdown", "sim_config"):
            if field in clean and isinstance(clean[field], str) and len(clean[field]) > 2000:
                clean[field] = clean[field][:2000] + "..."
        results.append(clean)

    return results


def search_components(
    component_type: str = "",
    features: list[str] = None,
    volatility: str = "",
    query_text: str = "",
    limit: int = 10,
) -> list[dict]:
    """Search the component library for reusable components.

    Args:
        component_type: Filter by type (paytable, feature_config, rtp_budget, reel_strip)
        features: Filter by feature tags
        volatility: Filter by volatility level
        query_text: Free-text semantic search
        limit: Max results to return
    """
    from config.database import get_standalone_db
    from memory.embeddings import (
        get_embedding, cosine_similarity,
        deserialize_embedding, keyword_similarity,
    )

    features = features or []

    db = get_standalone_db()
    try:
        if component_type:
            db.execute(
                "SELECT * FROM component_library WHERE component_type = %s ORDER BY times_reused DESC LIMIT 200",
                [component_type]
            )
        else:
            db.execute(
                "SELECT * FROM component_library ORDER BY times_reused DESC LIMIT 200"
            )
        candidates = db.fetchall()
    finally:
        db.close()

    if not candidates:
        return []

    # Build search text
    search_text = query_text or ""
    if features:
        search_text += " " + " ".join(features)
    if volatility:
        search_text += " " + volatility

    query_embedding = get_embedding(search_text) if search_text.strip() else None

    scored = []
    for row in candidates:
        row = dict(row) if not isinstance(row, dict) else row
        score = 0.0

        if query_embedding:
            row_embedding = deserialize_embedding(row.get("embedding"))
            if row_embedding:
                score = cosine_similarity(query_embedding, row_embedding)
            else:
                row_text = f"{row.get('name', '')} {row.get('description', '')} {row.get('tags', '')}"
                score = keyword_similarity(search_text, row_text)
        elif search_text.strip():
            row_text = f"{row.get('name', '')} {row.get('description', '')} {row.get('tags', '')}"
            score = keyword_similarity(search_text, row_text)
        else:
            score = row.get("times_reused", 0) * 0.01  # Default: sort by reuse count

        # Boost matching volatility
        if volatility and row.get("volatility_contribution") == volatility:
            score += 0.1

        # Boost matching features in tags
        try:
            row_tags = json.loads(row.get("tags", "[]"))
            overlap = set(features) & set(row_tags)
            score += 0.05 * len(overlap)
        except Exception:
            pass

        # Quality boost: higher satisfaction → higher score
        avg_sat = row.get("avg_satisfaction") or 0
        score += avg_sat * 0.02

        row["_relevance_score"] = round(score, 4)
        scored.append(row)

    scored.sort(key=lambda x: x["_relevance_score"], reverse=True)

    # Clean up
    results = []
    for row in scored[:limit]:
        clean = {k: v for k, v in row.items()
                 if k not in ("embedding",) and v is not None}
        if "config" in clean and isinstance(clean["config"], str) and len(clean["config"]) > 3000:
            clean["config"] = clean["config"][:3000] + "..."
        results.append(clean)

    return results


def get_memory_context(game_idea, user_id: str = "", max_runs: int = 3, max_components: int = 5) -> dict:
    """Get full memory context for a new pipeline run.

    Returns a dict with:
        - similar_runs: past runs with similar themes/mechanics
        - matching_components: reusable components that match requested features
        - rtp_budget_templates: RTP budget breakdowns from similar games
        - stats: summary statistics (total runs, avg RTP accuracy, etc.)
    """
    features = [f.value for f in game_idea.requested_features] if game_idea.requested_features else []

    # Search similar runs
    similar = search_similar_runs(
        theme=game_idea.theme,
        volatility=game_idea.volatility.value,
        features=features,
        jurisdictions=game_idea.target_markets,
        grid=f"{game_idea.grid_cols}x{game_idea.grid_rows}",
        limit=max_runs,
        user_id=user_id,
    )

    # Search matching components
    feature_components = search_components(
        component_type="feature_config",
        features=features,
        volatility=game_idea.volatility.value,
        limit=max_components,
    )

    # RTP budget templates
    rtp_budgets = search_components(
        component_type="rtp_budget",
        features=features,
        volatility=game_idea.volatility.value,
        limit=3,
    )

    # Paytable references
    paytables = search_components(
        component_type="paytable",
        volatility=game_idea.volatility.value,
        query_text=game_idea.theme,
        limit=3,
    )

    # Summary stats
    from config.database import get_standalone_db
    stats = {"total_runs": 0, "avg_rtp_delta": None}
    try:
        db = get_standalone_db()
        db.execute("SELECT COUNT(*) as c FROM run_records")
        row = db.fetchone()
        stats["total_runs"] = (row or {}).get("c", 0)

        db.execute(
            "SELECT AVG(ABS(measured_rtp - target_rtp)) as avg_delta "
            "FROM run_records WHERE measured_rtp IS NOT NULL AND target_rtp IS NOT NULL"
        )
        row = db.fetchone()
        if row and row.get("avg_delta") is not None:
            stats["avg_rtp_delta"] = round(row["avg_delta"], 3)
        db.close()
    except Exception:
        pass

    return {
        "similar_runs": similar,
        "matching_components": feature_components,
        "rtp_budget_templates": rtp_budgets,
        "paytable_references": paytables,
        "stats": stats,
    }


def increment_component_reuse(component_id: str):
    """Increment the reuse counter for a component."""
    from config.database import get_standalone_db
    db = get_standalone_db()
    try:
        db.execute(
            "UPDATE component_library SET times_reused = times_reused + 1 WHERE id = %s",
            [component_id]
        )
        db.commit()
    finally:
        db.close()


def record_iteration_feedback(
    run_id: str, parent_run_id: str = "",
    changes_made: str = "", rtp_before: float = None,
    rtp_after: float = None, user_modifications: str = "",
    improvement_score: float = None,
):
    """Record feedback from an iteration for the 'What Worked' loop."""
    import uuid
    from config.database import get_standalone_db

    fb_id = str(uuid.uuid4())[:12]
    db = get_standalone_db()
    try:
        db.execute(
            """INSERT INTO iteration_feedback (
                id, run_id, parent_run_id, changes_made,
                rtp_before, rtp_after, user_modifications, improvement_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [fb_id, run_id, parent_run_id, changes_made,
             rtp_before, rtp_after, user_modifications, improvement_score]
        )
        db.commit()
    finally:
        db.close()

    # Update component quality scores based on iteration feedback
    if improvement_score is not None and improvement_score > 0:
        try:
            _update_component_satisfaction(run_id, improvement_score)
        except Exception as e:
            logger.debug(f"Component satisfaction update: {e}")


def _update_component_satisfaction(run_id: str, improvement_score: float):
    """Update avg_satisfaction for components from this run based on iteration feedback."""
    from config.database import get_standalone_db
    db = get_standalone_db()
    try:
        db.execute(
            "SELECT id, avg_satisfaction, times_reused FROM component_library WHERE source_run_id = %s",
            [run_id]
        )
        components = db.fetchall()
        for comp in components:
            comp = dict(comp) if not isinstance(comp, dict) else comp
            old_avg = comp.get("avg_satisfaction") or 0
            reuse_count = max(comp.get("times_reused", 0), 1)
            # Running average
            new_avg = ((old_avg * (reuse_count - 1)) + improvement_score) / reuse_count
            db.execute(
                "UPDATE component_library SET avg_satisfaction = %s WHERE id = %s",
                [round(new_avg, 3), comp["id"]]
            )
        db.commit()
    finally:
        db.close()
