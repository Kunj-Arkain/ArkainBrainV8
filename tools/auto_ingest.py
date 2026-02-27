"""
Automated Slot Studio — Auto-Ingest for State Recon Results

After the State Recon Flow completes, this module:
1. Converts the recon output into a RAG-compatible markdown document
2. Generates a jurisdiction config entry for us_jurisdictions.py
3. Optionally embeds into Qdrant immediately

Usage:
    from tools.auto_ingest import ingest_recon_result
    ingest_recon_result("output/recon/north_carolina/")
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def load_recon_package(recon_dir: str) -> dict:
    """Load all recon output files from a directory."""
    base = Path(recon_dir)
    package = {}

    for filename in ["recon_package.json", "01_raw_research.json",
                     "02_legal_profile.json", "03_game_architecture.json",
                     "04_defense_brief.json"]:
        filepath = base / filename
        if filepath.exists():
            package[filename.replace(".json", "")] = json.loads(filepath.read_text("utf-8"))

    return package


def generate_rag_document(package: dict, state: str) -> str:
    """Convert recon package into a RAG-optimized markdown document."""

    profile = package.get("02_legal_profile", {})
    arch = package.get("03_game_architecture", {})
    brief = package.get("04_defense_brief", {})
    meta = package.get("recon_package", {})

    risk_tier = profile.get("risk_tier", meta.get("risk_tier", "UNKNOWN"))
    pathway = meta.get("legal_pathway", "unknown")

    slug = state.lower().replace(" ", "_")

    lines = [
        f"JURISDICTION: {state}",
        f"DOCUMENT_TYPE: State Gaming Regulation (Auto-Generated Recon)",
        f"CATEGORY: {'Skill Game' if 'skill' in pathway else 'Gaming Compliance'}",
        f"LAST_UPDATED: {datetime.now().strftime('%Y-%m')}",
        f"RISK_TIER: {risk_tier}",
        "",
        f"# {state} Gaming Regulations — Recon Intelligence Brief",
        "",
        f"**Risk Level:** {risk_tier}",
        f"**Best Legal Pathway:** {pathway}",
        f"**Recon Date:** {meta.get('completed_at', 'unknown')[:10]}",
        "",
    ]

    # Gambling Definition
    gdef = profile.get("gambling_definition", {})
    if gdef:
        lines.extend([
            "## Gambling Definition",
            f"**Citation:** {gdef.get('citation', 'N/A')}",
            f"**Elements:** {', '.join(gdef.get('elements', []))}",
            f"**Chance Test:** {gdef.get('chance_test', 'unknown')}",
            f"**Key Language:** {gdef.get('key_language', 'N/A')}",
            "",
        ])

    # Element Negation
    negation = profile.get("element_negation_map", {})
    if negation:
        lines.append("## Element Negation Strategies")
        for element, data in negation.items():
            if isinstance(data, dict):
                lines.append(f"**{element.title()}:** {'CAN negate' if data.get('can_negate') else 'CANNOT negate'}")
                lines.append(f"  Strategy: {data.get('strategy', 'N/A')}")
                lines.append(f"  Legal Basis: {data.get('legal_basis', 'N/A')}")
        lines.append("")

    # Exemptions
    exemptions = profile.get("exemptions", [])
    if exemptions:
        lines.append("## Exemptions & Carve-Outs")
        for ex in exemptions:
            if isinstance(ex, dict):
                lines.append(f"### {ex.get('name', 'Unknown Exemption')}")
                lines.append(f"- **Statutory Basis:** {ex.get('statutory_basis', 'N/A')}")
                lines.append(f"- **Strength:** {ex.get('strength', 'UNKNOWN')}")
                reqs = ex.get('requirements', [])
                if reqs:
                    lines.append(f"- **Requirements:** {'; '.join(reqs) if isinstance(reqs, list) else reqs}")
                lines.append(f"- **Prize Limits:** {ex.get('prize_limits', 'N/A')}")
                constraints = ex.get('game_design_constraints', [])
                if constraints:
                    lines.append(f"- **Game Design Constraints:** {'; '.join(constraints) if isinstance(constraints, list) else constraints}")
        lines.append("")

    # Game Architecture Summary
    if arch:
        lines.extend([
            "## Recommended Game Architecture",
            f"**Legal Classification:** {arch.get('legal_classification', 'N/A')}",
        ])
        concept = arch.get("game_concept", {})
        if concept:
            lines.append(f"**Game Concept:** {concept.get('description', 'N/A')}")

        mechs = arch.get("core_mechanics", {})
        skills = mechs.get("skill_elements", [])
        if skills:
            lines.append("### Skill Elements")
            for s in skills:
                if isinstance(s, dict):
                    lines.append(f"- **{s.get('mechanic', 'N/A')}:** {s.get('player_action', 'N/A')}")
                    lines.append(f"  Effect: {s.get('outcome_effect', 'N/A')}")
                    lines.append(f"  Legal Justification: {s.get('legal_justification', 'N/A')}")

        prize = arch.get("prize_structure", {})
        if prize:
            lines.extend([
                "### Prize Structure",
                f"- Form: {prize.get('form', 'N/A')}",
                f"- Max Prize: {prize.get('max_single_prize', 'N/A')}",
                f"- Statutory Basis: {prize.get('statutory_basis', 'N/A')}",
            ])

        prohibited = arch.get("prohibited_features", [])
        if prohibited:
            lines.append("### Prohibited Features")
            for p in prohibited:
                if isinstance(p, dict):
                    lines.append(f"- {p.get('feature', 'N/A')}: {p.get('reason', 'N/A')}")
        lines.append("")

    # Risk Assessment from Defense Brief
    if brief:
        risk_matrix = brief.get("risk_matrix", {})
        if risk_matrix:
            lines.extend([
                "## Risk Assessment",
                f"- **Prosecution Probability:** {risk_matrix.get('prosecution_probability', 'N/A')}",
                f"- **Conviction Probability:** {risk_matrix.get('conviction_probability_if_prosecuted', 'N/A')}",
                f"- **Penalty Severity:** {risk_matrix.get('penalty_severity', 'N/A')}",
            ])
        overall = brief.get("overall_assessment", "")
        if overall:
            lines.append(f"\n**Overall Assessment:** {overall}")

        precautions = brief.get("recommended_precautions", [])
        if precautions:
            lines.append("\n## Recommended Precautions")
            for p in precautions:
                lines.append(f"- {p}")

        watchlist = brief.get("legislative_watchlist", [])
        if watchlist:
            lines.append("\n## Legislative Watchlist")
            for w in watchlist:
                lines.append(f"- {w}")

    lines.extend([
        "",
        "---",
        "**DISCLAIMER:** Auto-generated by Arkain State Recon Pipeline. "
        "NOT legal advice. Requires review by licensed attorney in this jurisdiction.",
    ])

    return "\n".join(lines)


def generate_jurisdiction_entry(package: dict, state: str) -> dict:
    """Generate a jurisdiction config entry from recon results."""

    profile = package.get("02_legal_profile", {})
    arch = package.get("03_game_architecture", {})
    brief = package.get("04_defense_brief", {})
    meta = package.get("recon_package", {})

    risk_tier = profile.get("risk_tier", "UNKNOWN")
    pathway = meta.get("legal_pathway", "unknown")

    # Map risk tier to status
    status_map = {
        "DEPLOY_NOW": "LEGAL_REGULATED",
        "STRUCTURED_DEPLOY": "LEGAL_WITH_STRUCTURE",
        "GRAY_AREA": "GRAY_AREA",
        "HIGH_RISK": "HIGH_RISK_GRAY_AREA",
        "DO_NOT_ENTER": "BANNED",
    }

    risk_map = {
        "DEPLOY_NOW": "LOW",
        "STRUCTURED_DEPLOY": "LOW-MEDIUM",
        "GRAY_AREA": "MEDIUM",
        "HIGH_RISK": "HIGH",
        "DO_NOT_ENTER": "HOSTILE",
    }

    gdef = profile.get("gambling_definition", {})
    enforcement = profile.get("enforcement_profile", {})
    exemptions = profile.get("exemptions", [])
    pathways_ranked = profile.get("legal_pathways_ranked", [])

    # Build loophole strategies from architecture
    strategies = []
    if arch:
        skills = arch.get("core_mechanics", {}).get("skill_elements", [])
        if skills:
            strategies.append({
                "strategy": "SKILL-GATE MECHANIC",
                "description": "; ".join([
                    f"{s.get('mechanic', 'N/A')}: {s.get('player_action', 'N/A')}"
                    for s in skills if isinstance(s, dict)
                ]),
                "legal_basis": skills[0].get("legal_justification", "N/A") if skills else "N/A",
                "risk": risk_map.get(risk_tier, "UNKNOWN"),
            })

        prize = arch.get("prize_structure", {})
        if prize:
            strategies.append({
                "strategy": "PRIZE STRUCTURE",
                "description": f"Form: {prize.get('form', 'N/A')}, Max: {prize.get('max_single_prize', 'N/A')}",
                "legal_basis": prize.get("statutory_basis", "N/A"),
                "risk": risk_map.get(risk_tier, "UNKNOWN"),
            })

    entry = {
        "status": status_map.get(risk_tier, "UNKNOWN"),
        "risk_level": risk_map.get(risk_tier, "UNKNOWN"),
        "regulator": enforcement.get("primary_enforcer", "Unknown"),
        "governing_law": gdef.get("citation", "Unknown"),
        "gambling_definition": gdef.get("key_language", "See recon report"),
        "chance_test": gdef.get("chance_test", "unknown"),
        "legal_classification": pathway,
        "exemptions": [
            {
                "name": ex.get("name", "Unknown"),
                "statutory_basis": ex.get("statutory_basis", "N/A"),
                "strength": ex.get("strength", "UNKNOWN"),
            }
            for ex in exemptions if isinstance(ex, dict)
        ],
        "prize_restrictions": arch.get("prize_structure", {}).get("form", "See recon report") if arch else "See recon report",
        "loophole_strategies": strategies,
        "enforcement_posture": enforcement.get("posture", "unknown"),
        "court_rulings": [
            r.get("case", "Unknown") for r in profile.get("court_rulings_analysis", [])
            if isinstance(r, dict)
        ],
        "risk_matrix": brief.get("risk_matrix", {}) if brief else {},
        "recon_date": meta.get("completed_at", "unknown")[:10] if meta.get("completed_at") else "unknown",
        "auto_generated": True,
    }

    return entry


def ingest_recon_result(recon_dir: str, embed: bool = False):
    """
    Ingest a completed recon result:
    1. Generate RAG markdown document
    2. Generate jurisdiction config entry
    3. Optionally embed into Qdrant

    Args:
        recon_dir: Path to the recon output directory
        embed: If True, immediately embed into Qdrant (requires API keys)
    """
    package = load_recon_package(recon_dir)
    meta = package.get("recon_package", {})
    state = meta.get("state", Path(recon_dir).name.replace("_", " ").title())

    slug = state.lower().replace(" ", "_")

    # 1. Generate RAG document
    rag_doc = generate_rag_document(package, state)
    rag_dir = Path("data/regulations/us_states")
    rag_dir.mkdir(parents=True, exist_ok=True)
    rag_path = rag_dir / f"{slug}_recon.md"
    rag_path.write_text(rag_doc, encoding="utf-8")
    print(f"✓ RAG document saved: {rag_path}")

    # 2. Generate jurisdiction entry
    entry = generate_jurisdiction_entry(package, state)
    entry_path = Path(recon_dir) / "jurisdiction_entry.json"
    entry_path.write_text(json.dumps({state: entry}, indent=2), encoding="utf-8")
    print(f"✓ Jurisdiction entry saved: {entry_path}")
    print(f"  To add to config: US_STATE_JURISDICTIONS['{state}'] = <entry>")

    # 3. Optionally embed
    if embed:
        try:
            from tools.ingest_regulations import chunk_text, embed_texts
            from qdrant_client import QdrantClient
            from qdrant_client.models import PointStruct
            import hashlib

            url = os.getenv("QDRANT_URL", "")
            key = os.getenv("QDRANT_API_KEY", "")
            if not url or not os.getenv("OPENAI_API_KEY"):
                print("⚠ Cannot embed: QDRANT_URL or OPENAI_API_KEY not set")
                return

            chunks = chunk_text(rag_doc)
            embeddings = embed_texts([c for c in chunks])

            client = QdrantClient(url=url, api_key=key) if key else QdrantClient(url=url)
            collection = os.getenv("QDRANT_COLLECTION", "slot_regulations")

            points = []
            for chunk, emb in zip(chunks, embeddings):
                pid = int(hashlib.md5(chunk.encode()).hexdigest()[:12], 16)
                points.append(PointStruct(id=pid, vector=emb, payload={
                    "text": chunk,
                    "source": f"data/regulations/us_states/{slug}_recon.md",
                    "jurisdiction": state,
                    "category": "Auto-Generated Recon",
                    "filename": f"{slug}_recon.md",
                    "chunk_index": 0,
                }))

            client.upsert(collection_name=collection, points=points)
            print(f"✓ Embedded {len(points)} chunks into Qdrant collection '{collection}'")

        except Exception as e:
            print(f"⚠ Embedding failed: {e}")

    return {"rag_path": str(rag_path), "entry": entry, "state": state}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("recon_dir", help="Path to recon output directory")
    parser.add_argument("--embed", action="store_true", help="Embed into Qdrant immediately")
    args = parser.parse_args()
    ingest_recon_result(args.recon_dir, embed=args.embed)
