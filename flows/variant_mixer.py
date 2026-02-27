"""
ARKAINBRAIN — Variant Mixer (Phase 9)

Mix-and-match components from different completed variants to create hybrid games.
User selects: "Variant A's math + Variant B's design + Variant C's features"
→ Creates a new hybrid pipeline job with merged components.
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("arkainbrain.variants")


# ═══════════════════════════════════════════════
# Component Types for Mixing
# ═══════════════════════════════════════════════

MIXABLE_COMPONENTS = {
    "math": {
        "label": "Math Model",
        "icon": "🔢",
        "description": "Paytable, RTP budget, simulation config, reel strips",
        "source_dirs": ["03_math"],
        "source_files": ["paytable.json", "paytable.csv", "rtp_budget.json",
                         "reel_strips.json", "simulation_results.json",
                         "feature_config.json", "math_model.json"],
    },
    "design": {
        "label": "Game Design",
        "icon": "🎨",
        "description": "GDD document, theme, art direction, symbol design",
        "source_dirs": ["02_design"],
        "source_files": ["gdd.md", "game_design_document.md", "theme.json"],
    },
    "features": {
        "label": "Feature Set",
        "icon": "⚡",
        "description": "Bonus features, free spins config, special mechanics",
        "source_dirs": ["03_math"],
        "source_files": ["feature_config.json", "bonus_config.json"],
    },
    "compliance": {
        "label": "Compliance",
        "icon": "⚖️",
        "description": "Jurisdiction approvals, legal analysis, certifications",
        "source_dirs": ["05_legal"],
        "source_files": [],  # Copy entire directory
    },
    "revenue": {
        "label": "Revenue Model",
        "icon": "💰",
        "description": "Revenue projections, market analysis, monetization strategy",
        "source_dirs": ["08_revenue"],
        "source_files": [],
    },
    "prototype": {
        "label": "Prototype",
        "icon": "🎮",
        "description": "HTML5 playable prototype",
        "source_dirs": ["06_prototype"],
        "source_files": [],
    },
}


def get_variant_components(output_dir: str) -> dict:
    """Analyze what components are available in a variant's output.

    Returns dict of component_type → {available: bool, files: list, summary: str}
    """
    od = Path(output_dir) if output_dir else None
    if not od or not od.exists():
        return {k: {"available": False, "files": [], "summary": "No output"} for k in MIXABLE_COMPONENTS}

    result = {}
    for comp_type, comp_info in MIXABLE_COMPONENTS.items():
        files_found = []
        for src_dir in comp_info["source_dirs"]:
            dp = od / src_dir
            if dp.exists():
                for f in dp.rglob("*"):
                    if f.is_file():
                        files_found.append(str(f.relative_to(od)))

        # Specific file check
        for sf in comp_info["source_files"]:
            for src_dir in comp_info["source_dirs"]:
                fp = od / src_dir / sf
                if fp.exists() and str(fp.relative_to(od)) not in files_found:
                    files_found.append(str(fp.relative_to(od)))

        summary = ""
        if comp_type == "math":
            sim_path = od / "03_math" / "simulation_results.json"
            if sim_path.exists():
                try:
                    sim = json.loads(sim_path.read_text())
                    rtp = sim.get("measured_rtp", sim.get("rtp", "?"))
                    summary = f"RTP: {rtp}%"
                except Exception:
                    pass
        elif comp_type == "design":
            gdd = od / "02_design" / "gdd.md"
            if gdd.exists():
                words = len(gdd.read_text(errors="replace").split())
                summary = f"{words} words"

        result[comp_type] = {
            "available": len(files_found) > 0,
            "files": files_found,
            "file_count": len(files_found),
            "summary": summary,
        }

    return result


def create_hybrid(selections: dict, variants: dict, base_params: dict,
                  output_dir: str) -> dict:
    """Create a hybrid game by mixing components from different variants.

    Args:
        selections: {component_type: variant_id} mapping
        variants: {variant_id: {"output_dir": str, "params": dict, ...}}
        base_params: Original base parameters
        output_dir: Where to write the hybrid output

    Returns:
        Dict with hybrid metadata and any warnings
    """
    od = Path(output_dir)
    od.mkdir(parents=True, exist_ok=True)

    warnings = []
    copied_from = {}
    total_files = 0

    for comp_type, variant_id in selections.items():
        if variant_id not in variants:
            warnings.append(f"Variant {variant_id} not found for {comp_type}")
            continue

        src_dir = Path(variants[variant_id].get("output_dir", ""))
        if not src_dir.exists():
            warnings.append(f"Output not found for variant {variant_id}")
            continue

        comp_info = MIXABLE_COMPONENTS.get(comp_type)
        if not comp_info:
            continue

        # Copy component directories
        for dir_name in comp_info["source_dirs"]:
            src = src_dir / dir_name
            dst = od / dir_name
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                file_count = sum(1 for f in dst.rglob("*") if f.is_file())
                total_files += file_count
                copied_from[comp_type] = {
                    "variant_id": variant_id,
                    "variant_label": variants[variant_id].get("label", variant_id),
                    "files_copied": file_count,
                    "directory": dir_name,
                }

    # Generate hybrid manifest
    manifest = {
        "type": "hybrid",
        "created_at": datetime.now().isoformat(),
        "selections": selections,
        "copied_from": copied_from,
        "total_files": total_files,
        "warnings": warnings,
        "base_theme": base_params.get("theme", "Unknown"),
    }
    (od / "HYBRID_MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    # Generate hybrid GDD header
    _generate_hybrid_gdd_header(od, manifest, variants, selections)

    return manifest


def _generate_hybrid_gdd_header(od: Path, manifest: dict, variants: dict, selections: dict):
    """Add a hybrid provenance section to the GDD."""
    gdd_path = od / "02_design" / "gdd.md"
    if not gdd_path.exists():
        return

    header = "\n\n## Hybrid Provenance\n\n"
    header += "This game was created by mixing components from multiple variants:\n\n"
    for comp_type, variant_id in selections.items():
        info = MIXABLE_COMPONENTS.get(comp_type, {})
        label = variants.get(variant_id, {}).get("label", variant_id)
        header += f"- **{info.get('label', comp_type)}**: from {label}\n"
    header += "\n---\n"

    try:
        existing = gdd_path.read_text(encoding="utf-8")
        gdd_path.write_text(existing + header, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to update hybrid GDD: {e}")


def build_hybrid_params(base_params: dict, selections: dict, variants: dict) -> dict:
    """Build pipeline parameters for a hybrid re-run.

    Takes the math from one variant, design from another, etc.
    """
    hp = {**base_params}

    # If math is from a specific variant, use its RTP/volatility
    math_vid = selections.get("math")
    if math_vid and math_vid in variants:
        math_params = variants[math_vid].get("params", {})
        if isinstance(math_params, str):
            math_params = json.loads(math_params)
        hp["target_rtp"] = math_params.get("target_rtp", hp.get("target_rtp", 96))
        hp["volatility"] = math_params.get("volatility", hp.get("volatility", "medium"))
        hp["max_win_multiplier"] = math_params.get("max_win_multiplier", hp.get("max_win_multiplier", 5000))

    # If features from a specific variant, use its feature set
    feat_vid = selections.get("features")
    if feat_vid and feat_vid in variants:
        feat_params = variants[feat_vid].get("params", {})
        if isinstance(feat_params, str):
            feat_params = json.loads(feat_params)
        hp["requested_features"] = feat_params.get("requested_features", hp.get("requested_features", []))

    # Add hybrid context
    sources = []
    for comp, vid in selections.items():
        label = variants.get(vid, {}).get("label", vid)
        sources.append(f"{MIXABLE_COMPONENTS.get(comp, {}).get('label', comp)} from {label}")

    hp["special_requirements"] = (
        f"HYBRID BUILD: This is a mix-and-match hybrid combining:\n"
        f"{chr(10).join('  - ' + s for s in sources)}\n\n"
        + hp.get("special_requirements", "")
    )

    hp["_hybrid"] = {
        "selections": selections,
        "source_variants": {vid: variants[vid].get("label", vid) for vid in set(selections.values())},
    }

    return hp
