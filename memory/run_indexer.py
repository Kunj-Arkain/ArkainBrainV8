"""
ARKAINBRAIN — Run Indexer (Phase 6)

Indexes completed pipeline runs into the run_records table.
Extracts key metrics, generates embeddings, and triggers component extraction.

Called at pipeline completion (assemble_package) and iteration completion.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("arkainbrain.memory")


def index_completed_run(job_id: str, state, output_dir: str, user_id: str = "") -> Optional[str]:
    """Index a completed pipeline run into run_records.

    Args:
        job_id: The job ID
        state: PipelineState object from the flow
        output_dir: Path to the output directory
        user_id: Owner's user ID

    Returns:
        run_record ID if successful, None otherwise
    """
    try:
        from config.database import get_standalone_db
        from memory.embeddings import (
            get_embedding, build_run_text, serialize_embedding
        )
        from memory.component_extractor import extract_components

        idea = state.game_idea
        if not idea:
            logger.warning(f"No game_idea in state for job {job_id} — skipping index")
            return None

        od = Path(output_dir)
        run_id = str(uuid.uuid4())[:12]

        # ── Extract metrics from output files ──
        measured_rtp = None
        hit_frequency = None
        max_win_achieved = None
        paytable_data = None
        feature_config_data = None
        rtp_budget_data = None
        sim_config_data = None
        reel_strips_data = None
        convergence_flags = []
        final_warnings = []

        # Simulation results
        sim_path = od / "03_math" / "simulation_results.json"
        if sim_path.exists():
            try:
                sim = json.loads(sim_path.read_text())
                r = sim.get("results", sim)
                measured_rtp = r.get("measured_rtp") or r.get("rtp")
                hit_frequency = r.get("hit_frequency") or r.get("hit_rate")
                max_win_achieved = r.get("max_win") or r.get("max_win_achieved")
                if r.get("convergence_warning"):
                    convergence_flags.append(r["convergence_warning"])
                if r.get("warnings"):
                    final_warnings.extend(r["warnings"] if isinstance(r["warnings"], list) else [r["warnings"]])
                sim_config_data = json.dumps({
                    k: r.get(k) for k in ["spins", "batches", "confidence_interval", "seed"]
                    if r.get(k) is not None
                })
            except Exception as e:
                logger.debug(f"Sim results parse: {e}")

        # Paytable
        pt_path = od / "03_math" / "paytable.json"
        if pt_path.exists():
            try:
                paytable_data = pt_path.read_text()[:50000]
            except Exception:
                pass

        # Feature config
        fc_path = od / "02_design" / "feature_config.json"
        if not fc_path.exists():
            fc_path = od / "02_design" / "features.json"
        if fc_path.exists():
            try:
                feature_config_data = fc_path.read_text()[:50000]
            except Exception:
                pass

        # RTP budget
        for rtp_name in ["rtp_budget.json", "rtp_breakdown.json"]:
            rtp_path = od / "03_math" / rtp_name
            if rtp_path.exists():
                try:
                    rtp_budget_data = rtp_path.read_text()[:20000]
                    break
                except Exception:
                    pass

        # Reel strips
        rs_path = od / "03_math" / "reel_strips.json"
        if not rs_path.exists():
            rs_path = od / "03_math" / "reelstrips.json"
        if rs_path.exists():
            try:
                reel_strips_data = rs_path.read_text()[:100000]
            except Exception:
                pass

        # GDD summary
        gdd_summary = ""
        gdd_path = od / "02_design" / "gdd.md"
        if not gdd_path.exists():
            gdd_path = od / "02_design" / "game_design_document.md"
        if gdd_path.exists():
            try:
                gdd_summary = gdd_path.read_text()[:3000]
            except Exception:
                pass

        # Math summary
        math_summary = ""
        if state.math_model and isinstance(state.math_model, dict):
            math_summary = str(state.math_model.get("output", ""))[:2000]

        # ── Build embedding ──
        features_list = [f.value for f in idea.requested_features] if idea.requested_features else []
        embed_text = build_run_text(
            theme=idea.theme,
            volatility=idea.volatility.value,
            features=features_list,
            jurisdictions=idea.target_markets,
            grid=f"{idea.grid_cols}x{idea.grid_rows}",
            gdd_summary=gdd_summary[:500],
            math_summary=math_summary[:300],
        )
        embedding = get_embedding(embed_text)

        # ── Insert run record ──
        db = get_standalone_db()
        try:
            db.execute(
                """INSERT INTO run_records (
                    id, job_id, user_id, theme, theme_tags, grid, eval_mode,
                    volatility, measured_rtp, target_rtp, hit_frequency,
                    max_win_achieved, jurisdictions, features, reel_strips,
                    paytable, feature_config, rtp_budget_breakdown, sim_config,
                    ooda_iterations, convergence_flags, final_warnings,
                    gdd_summary, math_summary, cost_usd, embedding
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )""",
                [
                    run_id, job_id, user_id,
                    idea.theme,
                    json.dumps(_extract_theme_tags(idea.theme)),
                    f"{idea.grid_cols}x{idea.grid_rows}",
                    str(idea.ways_or_lines),
                    idea.volatility.value,
                    measured_rtp,
                    idea.target_rtp,
                    hit_frequency,
                    max_win_achieved,
                    json.dumps(idea.target_markets),
                    json.dumps(features_list),
                    reel_strips_data,
                    paytable_data,
                    feature_config_data,
                    rtp_budget_data,
                    sim_config_data,
                    getattr(state, "convergence_loops_run", 0),
                    json.dumps(convergence_flags),
                    json.dumps(final_warnings),
                    gdd_summary[:5000],
                    math_summary[:3000],
                    getattr(state, "estimated_cost_usd", 0.0),
                    serialize_embedding(embedding),
                ]
            )
            db.commit()
            logger.info(f"Indexed run {run_id} for job {job_id} (RTP={measured_rtp}, theme={idea.theme})")
        finally:
            db.close()

        # ── Extract reusable components ──
        try:
            extract_components(run_id, job_id, state, output_dir)
        except Exception as e:
            logger.warning(f"Component extraction failed (non-fatal): {e}")

        return run_id

    except Exception as e:
        logger.warning(f"Run indexing failed (non-fatal): {e}")
        return None


def _extract_theme_tags(theme: str) -> list[str]:
    """Extract theme tags from the game theme string.
    E.g., 'Ancient Egyptian Adventure' → ['ancient', 'egyptian', 'egypt', 'adventure']
    """
    THEME_CATEGORIES = {
        "egypt": ["egyptian", "pharaoh", "pyramid", "cleopatra", "anubis", "sphinx", "nile"],
        "asian": ["chinese", "dragon", "fortune", "jade", "bamboo", "panda", "koi", "samurai", "ninja", "geisha"],
        "mythology": ["greek", "norse", "zeus", "odin", "thor", "atlas", "medusa", "mythology", "mythic"],
        "fantasy": ["magic", "wizard", "dragon", "elf", "fairy", "enchanted", "mystical", "spell"],
        "adventure": ["adventure", "explorer", "treasure", "quest", "pirate", "jungle", "safari"],
        "fruit": ["fruit", "cherry", "lemon", "orange", "watermelon", "classic"],
        "horror": ["vampire", "zombie", "werewolf", "halloween", "dark", "haunted", "witch"],
        "aquatic": ["ocean", "sea", "fish", "underwater", "mermaid", "pearl", "coral"],
        "space": ["space", "galaxy", "star", "cosmic", "alien", "planet", "nebula"],
        "irish": ["irish", "leprechaun", "clover", "shamrock", "rainbow", "pot of gold"],
        "western": ["western", "cowboy", "gold", "mine", "frontier", "wild west"],
        "luxury": ["diamond", "gold", "jewel", "gem", "luxury", "royal", "crown", "palace"],
    }
    words = theme.lower().split()
    tags = list(set(words))
    for category, keywords in THEME_CATEGORIES.items():
        for word in words:
            if word in keywords:
                if category not in tags:
                    tags.append(category)
                break
    return tags[:15]  # Cap at 15 tags
