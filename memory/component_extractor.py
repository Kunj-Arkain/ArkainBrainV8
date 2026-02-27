"""
ARKAINBRAIN — Component Extractor (Phase 6)

Extracts reusable components from completed pipeline runs:
- Paytable distributions
- Feature trigger curves
- RTP budget breakdowns
- Reel strip configurations

Components are stored in component_library for reuse by future pipelines.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("arkainbrain.memory")


def extract_components(run_id: str, job_id: str, state, output_dir: str) -> int:
    """Extract reusable components from a completed run.

    Returns the number of components extracted.
    """
    from config.database import get_standalone_db
    from memory.embeddings import get_embedding, build_component_text, serialize_embedding

    od = Path(output_dir)
    idea = state.game_idea
    if not idea:
        return 0

    components = []

    # ── 1. Paytable Component ──
    pt_path = od / "03_math" / "paytable.json"
    if pt_path.exists():
        try:
            pt_data = json.loads(pt_path.read_text())
            vol = idea.volatility.value
            features = [f.value for f in idea.requested_features] if idea.requested_features else []

            # Compute basic stats for description
            symbol_count = len(pt_data) if isinstance(pt_data, dict) else 0
            desc = (f"Paytable from {idea.theme}. {symbol_count} symbols. "
                    f"Volatility: {vol}. Grid: {idea.grid_cols}x{idea.grid_rows}. "
                    f"Target RTP: {idea.target_rtp}%.")

            tags = [vol, f"{idea.grid_cols}x{idea.grid_rows}", idea.ways_or_lines]
            tags.extend(features[:5])

            embed_text = build_component_text("paytable", f"Paytable: {idea.theme}", desc, tags)
            embedding = get_embedding(embed_text)

            components.append({
                "component_type": "paytable",
                "name": f"Paytable: {idea.theme}",
                "description": desc,
                "config": pt_path.read_text()[:50000],
                "measured_rtp_contribution": None,  # Full paytable = full RTP
                "volatility_contribution": vol,
                "tags": tags,
                "embedding": embedding,
            })
        except Exception as e:
            logger.debug(f"Paytable extraction: {e}")

    # ── 2. Feature Config Component ──
    fc_path = od / "02_design" / "feature_config.json"
    if not fc_path.exists():
        fc_path = od / "02_design" / "features.json"
    if fc_path.exists():
        try:
            fc_data = json.loads(fc_path.read_text())
            features = [f.value for f in idea.requested_features] if idea.requested_features else []

            desc = (f"Feature configuration from {idea.theme}. "
                    f"Features: {', '.join(features)}. "
                    f"Volatility: {idea.volatility.value}.")

            tags = [idea.volatility.value]
            tags.extend(features[:8])

            embed_text = build_component_text("feature_config", f"Features: {idea.theme}", desc, tags)
            embedding = get_embedding(embed_text)

            components.append({
                "component_type": "feature_config",
                "name": f"Features: {idea.theme}",
                "description": desc,
                "config": fc_path.read_text()[:50000],
                "measured_rtp_contribution": None,
                "volatility_contribution": idea.volatility.value,
                "tags": tags,
                "embedding": embedding,
            })
        except Exception as e:
            logger.debug(f"Feature config extraction: {e}")

    # ── 3. RTP Budget Component ──
    for rtp_name in ["rtp_budget.json", "rtp_breakdown.json"]:
        rtp_path = od / "03_math" / rtp_name
        if rtp_path.exists():
            try:
                rtp_data = json.loads(rtp_path.read_text())
                features = [f.value for f in idea.requested_features] if idea.requested_features else []

                # Try to extract base/feature split
                base_pct = rtp_data.get("base_game_pct") or rtp_data.get("base_rtp")
                feature_pct = rtp_data.get("feature_pct") or rtp_data.get("bonus_rtp")

                desc = (f"RTP budget from {idea.theme}. "
                        f"Target: {idea.target_rtp}%. "
                        f"Volatility: {idea.volatility.value}. "
                        f"Features: {', '.join(features)}.")
                if base_pct and feature_pct:
                    desc += f" Split: {base_pct}% base / {feature_pct}% features."

                tags = [idea.volatility.value, f"rtp_{idea.target_rtp}"]
                tags.extend(features[:5])

                embed_text = build_component_text("rtp_budget", f"RTP Budget: {idea.theme}", desc, tags)
                embedding = get_embedding(embed_text)

                components.append({
                    "component_type": "rtp_budget",
                    "name": f"RTP Budget: {idea.theme}",
                    "description": desc,
                    "config": rtp_path.read_text()[:20000],
                    "measured_rtp_contribution": idea.target_rtp,
                    "volatility_contribution": idea.volatility.value,
                    "tags": tags,
                    "embedding": embedding,
                })
                break  # Only need one RTP budget file
            except Exception as e:
                logger.debug(f"RTP budget extraction: {e}")

    # ── 4. Reel Strip Component ──
    rs_path = od / "03_math" / "reel_strips.json"
    if not rs_path.exists():
        rs_path = od / "03_math" / "reelstrips.json"
    if rs_path.exists():
        try:
            rs_raw = rs_path.read_text()
            if len(rs_raw) < 500000:  # Skip enormous reel strips
                desc = (f"Reel strips from {idea.theme}. "
                        f"Grid: {idea.grid_cols}x{idea.grid_rows}. "
                        f"Eval: {idea.ways_or_lines}.")

                tags = [idea.volatility.value, f"{idea.grid_cols}x{idea.grid_rows}",
                        str(idea.ways_or_lines)]

                embed_text = build_component_text("reel_strip", f"Reels: {idea.theme}", desc, tags)
                embedding = get_embedding(embed_text)

                components.append({
                    "component_type": "reel_strip",
                    "name": f"Reels: {idea.theme}",
                    "description": desc,
                    "config": rs_raw[:100000],
                    "measured_rtp_contribution": None,
                    "volatility_contribution": idea.volatility.value,
                    "tags": tags,
                    "embedding": embedding,
                })
        except Exception as e:
            logger.debug(f"Reel strip extraction: {e}")

    # ── Store all components ──
    if not components:
        return 0

    db = get_standalone_db()
    try:
        for comp in components:
            comp_id = str(uuid.uuid4())[:12]
            db.execute(
                """INSERT INTO component_library (
                    id, source_run_id, component_type, name, description,
                    config, measured_rtp_contribution, volatility_contribution,
                    tags, embedding
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    comp_id, run_id, comp["component_type"],
                    comp["name"], comp["description"],
                    comp["config"], comp["measured_rtp_contribution"],
                    comp["volatility_contribution"],
                    json.dumps(comp["tags"]),
                    serialize_embedding(comp["embedding"]),
                ]
            )
        db.commit()
        logger.info(f"Extracted {len(components)} components from run {run_id}")
    finally:
        db.close()

    return len(components)
