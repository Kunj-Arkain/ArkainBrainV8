"""
ARKAINBRAIN — Prompt Injector (Phase 6)

Formats memory context into structured text that gets injected
into agent system prompts at pipeline start.

This gives agents awareness of past successes, reusable components,
and RTP budget patterns — without increasing hallucination risk.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("arkainbrain.memory")


def build_memory_prompt(memory_context: dict) -> str:
    """Build a structured memory prompt from query results.

    Returns a multi-section prompt string ready for injection into
    agent system prompts or task descriptions.
    """
    sections = []

    # ── Similar Past Runs ──
    similar = memory_context.get("similar_runs", [])
    if similar:
        lines = ["## Reference: Similar Past Runs"]
        for i, run in enumerate(similar[:3], 1):
            rtp_str = f"{run.get('measured_rtp', '?')}%" if run.get('measured_rtp') else "N/A"
            target_str = f"{run.get('target_rtp', '?')}%"
            ooda = run.get("ooda_iterations", 0)
            warnings = _parse_json_field(run.get("final_warnings", "[]"))

            lines.append(
                f"\n### Run {i}: \"{run.get('theme', 'Unknown')}\"\n"
                f"- Volatility: {run.get('volatility', '?')} | Grid: {run.get('grid', '?')} | "
                f"Eval: {run.get('eval_mode', '?')}\n"
                f"- Target RTP: {target_str} → Measured: {rtp_str}\n"
                f"- OODA iterations: {ooda}\n"
                f"- Markets: {_parse_json_field(run.get('jurisdictions', '[]'))}"
            )
            if warnings:
                lines.append(f"- Warnings: {warnings}")

            # Include GDD summary snippet
            gdd = run.get("gdd_summary", "")
            if gdd:
                lines.append(f"- Design notes: {gdd[:300]}...")

        sections.append("\n".join(lines))

    # ── RTP Budget Templates ──
    rtp_budgets = memory_context.get("rtp_budget_templates", [])
    if rtp_budgets:
        lines = ["## Reference: RTP Budget Templates"]
        for i, comp in enumerate(rtp_budgets[:3], 1):
            lines.append(
                f"\n### Template {i}: {comp.get('name', 'Unknown')}\n"
                f"- {comp.get('description', '')}\n"
                f"- Volatility: {comp.get('volatility_contribution', '?')}"
            )
            # Try to extract base/feature split from config
            config = _safe_parse_json(comp.get("config", "{}"))
            if isinstance(config, dict):
                base = config.get("base_game_pct") or config.get("base_rtp")
                feat = config.get("feature_pct") or config.get("bonus_rtp")
                if base and feat:
                    lines.append(f"- Split: {base}% base / {feat}% features")

        sections.append("\n".join(lines))

    # ── Matching Feature Components ──
    components = memory_context.get("matching_components", [])
    if components:
        lines = ["## Reference: Feature Configurations from Past Games"]
        for i, comp in enumerate(components[:3], 1):
            tags = _parse_json_field(comp.get("tags", "[]"))
            lines.append(
                f"\n### Feature Set {i}: {comp.get('name', 'Unknown')}\n"
                f"- {comp.get('description', '')}\n"
                f"- Tags: {tags}\n"
                f"- Reused: {comp.get('times_reused', 0)} times | "
                f"Satisfaction: {comp.get('avg_satisfaction', 0):.1f}/10"
            )

        sections.append("\n".join(lines))

    # ── Paytable References ──
    paytables = memory_context.get("paytable_references", [])
    if paytables:
        lines = ["## Reference: Paytable Structures from Past Games"]
        for i, comp in enumerate(paytables[:2], 1):
            lines.append(
                f"\n### Paytable {i}: {comp.get('name', 'Unknown')}\n"
                f"- {comp.get('description', '')}"
            )
        sections.append("\n".join(lines))

    # ── Stats Summary ──
    stats = memory_context.get("stats", {})
    if stats.get("total_runs", 0) > 0:
        lines = [
            f"\n## Pipeline Memory Stats",
            f"- Total past runs: {stats['total_runs']}",
        ]
        if stats.get("avg_rtp_delta") is not None:
            lines.append(f"- Average RTP accuracy: ±{stats['avg_rtp_delta']}%")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    header = (
        "# 🧠 Pipeline Memory Context\n"
        "The following data comes from past successful pipeline runs. "
        "Use these as reference points — not as templates to copy verbatim. "
        "Adapt insights to the current game's unique requirements.\n"
    )

    return header + "\n\n".join(sections)


def build_math_agent_context(memory_context: dict) -> str:
    """Build specialized memory context for the mathematician agent.

    Focuses on RTP budgets, convergence patterns, and paytable structures.
    """
    sections = []

    # RTP accuracy from past runs
    similar = memory_context.get("similar_runs", [])
    if similar:
        lines = ["## Past RTP Outcomes (similar games)"]
        for run in similar[:3]:
            if run.get("measured_rtp") and run.get("target_rtp"):
                delta = abs(run["measured_rtp"] - run["target_rtp"])
                ooda = run.get("ooda_iterations", 0)
                lines.append(
                    f"- \"{run.get('theme', '?')}\": target {run['target_rtp']}% → "
                    f"measured {run['measured_rtp']}% (Δ={delta:.2f}%, {ooda} OODA loops)"
                )
        sections.append("\n".join(lines))

    # RTP budgets
    rtp_budgets = memory_context.get("rtp_budget_templates", [])
    if rtp_budgets:
        lines = ["## RTP Budget Templates"]
        for comp in rtp_budgets[:3]:
            config = _safe_parse_json(comp.get("config", "{}"))
            if isinstance(config, dict) and config:
                lines.append(f"\n### {comp.get('name', 'Unknown')}")
                for k, v in list(config.items())[:10]:
                    if isinstance(v, (int, float)):
                        lines.append(f"  - {k}: {v}")
        sections.append("\n".join(lines))

    # Convergence patterns
    convergence_notes = []
    for run in similar[:5]:
        flags = _parse_json_field(run.get("convergence_flags", "[]"), as_list=True)
        if flags:
            convergence_notes.append(
                f"- \"{run.get('theme', '?')}\": {'; '.join(flags)}"
            )
    if convergence_notes:
        sections.append(
            "## Convergence Notes from Past Runs\n" + "\n".join(convergence_notes)
        )

    if not sections:
        return ""

    return "# 🔢 Math Agent Memory\n" + "\n\n".join(sections)


def build_designer_context(memory_context: dict) -> str:
    """Build specialized memory context for the game designer agent.

    Focuses on GDD patterns, feature combinations, and design decisions.
    """
    sections = []

    similar = memory_context.get("similar_runs", [])
    if similar:
        lines = ["## Design Patterns from Similar Games"]
        for run in similar[:3]:
            gdd = run.get("gdd_summary", "")
            if gdd:
                lines.append(f"\n### \"{run.get('theme', '?')}\" ({run.get('volatility', '?')} vol)")
                lines.append(f"{gdd[:500]}")
        sections.append("\n".join(lines))

    components = memory_context.get("matching_components", [])
    if components:
        lines = ["## Feature Combinations That Worked"]
        for comp in components[:3]:
            tags = _parse_json_field(comp.get("tags", "[]"))
            lines.append(
                f"- {comp.get('name', '?')}: {tags} "
                f"(reused {comp.get('times_reused', 0)}x, "
                f"satisfaction {comp.get('avg_satisfaction', 0):.1f}/10)"
            )
        sections.append("\n".join(lines))

    if not sections:
        return ""

    return "# 🎮 Designer Memory\n" + "\n\n".join(sections)


# ── Helpers ──

def _parse_json_field(val, as_list=False):
    """Parse a JSON string field, returning a display string or list."""
    if not val:
        return [] if as_list else ""
    try:
        parsed = json.loads(val) if isinstance(val, str) else val
        if as_list:
            return parsed if isinstance(parsed, list) else [str(parsed)]
        if isinstance(parsed, list):
            return ", ".join(str(x) for x in parsed)
        return str(parsed)
    except (json.JSONDecodeError, TypeError):
        return [str(val)] if as_list else str(val)


def _safe_parse_json(val):
    """Safely parse JSON, returning {} on failure."""
    if not val:
        return {}
    try:
        return json.loads(val) if isinstance(val, str) else val
    except (json.JSONDecodeError, TypeError):
        return {}
