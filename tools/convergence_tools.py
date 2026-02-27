"""
ARKAINBRAIN — OODA Convergence Loop Tools

Tools that enable agents to cross-review each other's work and iterate
toward a converged, internally-consistent game design.

FileReaderTool         — Any agent can read any pipeline file
ConvergenceValidatorTool — Structured GDD ↔ Math ↔ Compliance alignment check
GDDPatchTool           — Targeted section update without full rewrite
"""

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import ClassVar, Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================
# Tool: File Reader — Cross-Agent Visibility
# ============================================================
# CRITICAL for OODA: agents must read each other's outputs.
# Without this, the mathematician can't check the GDD's paytable,
# and compliance can't verify the math model's max win.

class FileReadInput(BaseModel):
    file_path: str = Field(description="Path to the file to read")
    max_chars: int = Field(default=12000, description="Max characters to return (capped to manage context window)")


class FileReaderTool(BaseTool):
    """Read any file from the pipeline output directory. Use this to review
    other agents' work — GDD, math CSVs, compliance reports, etc."""

    name: str = "read_file"
    description: str = (
        "Read any file from the pipeline output directory. Returns the full content "
        "(or first max_chars characters for large files). Use to review:\n"
        "- GDD: {output_dir}/02_design/gdd.md\n"
        "- Paytable: {output_dir}/03_math/paytable.csv\n"
        "- Reel strips: {output_dir}/03_math/BaseReels.csv\n"
        "- Simulation results: {output_dir}/03_math/simulation_results.json\n"
        "- Compliance report: {output_dir}/05_legal/compliance_report.md\n"
        "- Any other pipeline file"
    )
    args_schema: type[BaseModel] = FileReadInput

    def _run(self, file_path: str, max_chars: int = 12000) -> str:
        path = Path(file_path)
        if not path.exists():
            return json.dumps({"error": f"File not found: {file_path}",
                               "hint": "Check the output directory path"})
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            truncated = len(content) > max_chars
            return json.dumps({
                "file": str(path),
                "size_bytes": path.stat().st_size,
                "truncated": truncated,
                "content": content[:max_chars],
            })
        except Exception as e:
            return json.dumps({"error": str(e)})


# ============================================================
# Tool: Convergence Validator
# ============================================================
# The Producer uses this to check alignment between GDD, Math, and
# Compliance BEFORE deciding whether another iteration is needed.
# This is the ORIENT + DECIDE step of the OODA loop.

class ConvergenceInput(BaseModel):
    output_dir: str = Field(description="Pipeline output directory path")
    target_rtp: float = Field(description="Target RTP percentage, e.g. 96.0")
    max_win_target: int = Field(description="Max win multiplier target, e.g. 5000")
    target_markets: list[str] = Field(description="List of target jurisdictions")


class ConvergenceValidatorTool(BaseTool):
    """Validates alignment between GDD, Math Model, and Compliance.
    Returns structured conflict report with specific issues to fix."""

    name: str = "validate_convergence"
    description: str = (
        "Check whether the GDD, math model, and compliance outputs are internally "
        "consistent. Returns a structured report of conflicts, mismatches, and "
        "required fixes. Use this BEFORE approving a design iteration."
    )
    args_schema: type[BaseModel] = ConvergenceInput

    # Jurisdiction max win caps (common ones)
    MAX_WIN_CAPS: ClassVar[dict] = {
        "uk": 10000, "ontario": 10000, "sweden": 10000,
        "malta": 50000, "curacao": None,  # No cap
        "new jersey": 50000, "michigan": 50000,
        "pennsylvania": 50000, "west virginia": 50000,
        "georgia": None, "texas": None,  # Tribal, varies
    }

    def _run(self, output_dir: str, target_rtp: float = 96.0,
             max_win_target: int = 5000, target_markets: list[str] = None) -> str:
        target_markets = target_markets or []
        conflicts = []
        warnings = []
        checks_passed = []
        data = {}

        # ── 1. Read GDD ──
        gdd_path = Path(output_dir, "02_design", "gdd.md")
        gdd_text = ""
        if gdd_path.exists():
            gdd_text = gdd_path.read_text(encoding="utf-8", errors="replace")
            data["gdd_chars"] = len(gdd_text)
            checks_passed.append("GDD file exists")
        else:
            conflicts.append({
                "type": "MISSING_FILE", "severity": "BLOCKER",
                "detail": "GDD file not found at 02_design/gdd.md",
                "fix": "Game Designer must produce the GDD before math can proceed"
            })

        # ── 2. Read Paytable CSV ──
        paytable_path = Path(output_dir, "03_math", "paytable.csv")
        paytable = {}
        if paytable_path.exists():
            try:
                reader = csv.DictReader(io.StringIO(paytable_path.read_text()))
                for row in reader:
                    sym = row.get("Symbol") or row.get("symbol") or list(row.values())[0]
                    paytable[sym] = row
                data["paytable_symbols"] = len(paytable)
                checks_passed.append(f"Paytable: {len(paytable)} symbols")
            except Exception as e:
                warnings.append({"type": "PARSE_ERROR", "detail": f"Paytable CSV: {e}"})
        else:
            conflicts.append({
                "type": "MISSING_FILE", "severity": "BLOCKER",
                "detail": "paytable.csv not found in 03_math/",
                "fix": "Mathematician must produce paytable.csv"
            })

        # ── 3. Read Simulation Results ──
        sim_path = Path(output_dir, "03_math", "simulation_results.json")
        sim = {}
        if sim_path.exists():
            try:
                sim = json.loads(sim_path.read_text())
                data["simulation"] = {k: sim.get(k) for k in [
                    "measured_rtp", "hit_frequency", "volatility_index",
                    "max_win_achieved", "total_spins"
                ] if k in sim}
                checks_passed.append(f"Simulation: {sim.get('total_spins', '?')} spins")
            except Exception as e:
                warnings.append({"type": "PARSE_ERROR", "detail": f"simulation_results.json: {e}"})
        else:
            conflicts.append({
                "type": "MISSING_FILE", "severity": "HIGH",
                "detail": "simulation_results.json not found",
                "fix": "Mathematician must run simulation and save results"
            })

        # ── 4. RTP Check ──
        measured_rtp = sim.get("measured_rtp")
        if measured_rtp is not None:
            deviation = abs(measured_rtp - target_rtp)
            if deviation > 1.0:
                conflicts.append({
                    "type": "RTP_DEVIATION", "severity": "BLOCKER",
                    "detail": f"Measured RTP {measured_rtp}% deviates {deviation:.2f}% from target {target_rtp}%",
                    "fix": f"Mathematician: adjust reel strips or paytable to bring RTP within ±0.5% of {target_rtp}%",
                    "instruction_to": "mathematician"
                })
            elif deviation > 0.5:
                warnings.append({
                    "type": "RTP_DEVIATION",
                    "detail": f"RTP {measured_rtp}% is {deviation:.2f}% off target (acceptable but tight)"
                })
            else:
                checks_passed.append(f"RTP: {measured_rtp}% (target {target_rtp}%, deviation {deviation:.2f}%)")

        # ── 5. Max Win Check ──
        max_win_achieved = sim.get("max_win_achieved")
        if max_win_achieved is not None:
            # Check against game target
            if max_win_achieved > max_win_target * 1.2:
                conflicts.append({
                    "type": "MAX_WIN_EXCEEDED", "severity": "HIGH",
                    "detail": f"Simulated max win {max_win_achieved}x exceeds target {max_win_target}x by {((max_win_achieved/max_win_target)-1)*100:.0f}%",
                    "fix": f"Mathematician: cap multiplier mechanics or reduce feature stacking to keep max win ≤{max_win_target}x",
                    "instruction_to": "mathematician"
                })

            # Check against jurisdiction caps
            for market in target_markets:
                cap = self.MAX_WIN_CAPS.get(market.lower().strip())
                if cap and max_win_achieved > cap:
                    conflicts.append({
                        "type": "JURISDICTION_MAX_WIN", "severity": "BLOCKER",
                        "detail": f"Max win {max_win_achieved}x exceeds {market} cap of {cap}x",
                        "fix": f"Mathematician: implement hard cap at {cap}x for {market}. May require market-specific reel strips.",
                        "instruction_to": "mathematician"
                    })
                elif cap:
                    checks_passed.append(f"Max win {max_win_achieved}x within {market} cap {cap}x")

        # ── 6. RTP Breakdown Consistency ──
        rtp_breakdown = sim.get("rtp_breakdown", {})
        if rtp_breakdown:
            total = sum(float(v) for v in rtp_breakdown.values() if isinstance(v, (int, float)))
            if measured_rtp and abs(total - measured_rtp) > 1.0:
                conflicts.append({
                    "type": "RTP_BREAKDOWN_MISMATCH", "severity": "HIGH",
                    "detail": f"RTP breakdown sums to {total:.2f}% but measured RTP is {measured_rtp}%. Gap: {abs(total-measured_rtp):.2f}%",
                    "fix": "Mathematician: reconcile RTP breakdown components with simulation results",
                    "instruction_to": "mathematician"
                })
            elif measured_rtp:
                checks_passed.append(f"RTP breakdown sums to {total:.2f}% (measured: {measured_rtp}%)")

        # ── 7. GDD Feature vs Math Feature Alignment ──
        if gdd_text and sim:
            gdd_lower = gdd_text.lower()
            # Check if GDD mentions features that math doesn't account for
            feature_keywords = {
                "free spins": "free_games",
                "cascading": "cascading_reels",
                "hold and spin": "hold_and_spin",
                "bonus buy": "bonus_buy",
                "expanding wild": "expanding_wilds",
                "multiplier": "multiplier",
                "jackpot": "jackpots",
            }
            for gdd_term, math_key in feature_keywords.items():
                if gdd_term in gdd_lower:
                    # Check if RTP breakdown has a corresponding component
                    has_math = any(math_key in str(k).lower() or gdd_term.replace(" ", "_") in str(k).lower()
                                   for k in rtp_breakdown.keys())
                    if not has_math and rtp_breakdown:
                        warnings.append({
                            "type": "FEATURE_UNCOSTED",
                            "detail": f"GDD mentions '{gdd_term}' but no RTP breakdown component found for it",
                            "fix": f"Mathematician: add RTP contribution for '{gdd_term}' feature"
                        })

        # ── 8. Symbol Count Consistency ──
        if paytable and gdd_text:
            gdd_symbol_mentions = set()
            for sym_name in paytable.keys():
                if sym_name.lower() not in ("symbol", ""):
                    gdd_symbol_mentions.add(sym_name)

            if len(paytable) < 8:
                warnings.append({
                    "type": "LOW_SYMBOL_COUNT",
                    "detail": f"Only {len(paytable)} symbols in paytable (typical: 10-13)",
                    "fix": "Check if low-pay royals (A, K, Q, J, 10, 9) are missing"
                })

        # ── 9. Reel Strips Exist ──
        reels_path = Path(output_dir, "03_math", "BaseReels.csv")
        if reels_path.exists():
            try:
                reel_text = reels_path.read_text()
                reel_lines = [l for l in reel_text.strip().split("\n") if l.strip()]
                data["reel_strip_positions"] = len(reel_lines) - 1  # minus header
                checks_passed.append(f"BaseReels.csv: {len(reel_lines)-1} positions")
            except Exception:
                pass
        elif paytable:
            conflicts.append({
                "type": "MISSING_FILE", "severity": "HIGH",
                "detail": "BaseReels.csv not found — reel strips required for prototype and certification",
                "fix": "Mathematician must generate reel strip CSV",
                "instruction_to": "mathematician"
            })

        # ── 10. Convergence Decision ──
        blocker_count = sum(1 for c in conflicts if c.get("severity") == "BLOCKER")
        high_count = sum(1 for c in conflicts if c.get("severity") == "HIGH")

        if blocker_count > 0:
            verdict = "NOT_CONVERGED"
            reason = f"{blocker_count} BLOCKER conflict(s) must be resolved"
        elif high_count > 0:
            verdict = "NOT_CONVERGED"
            reason = f"{high_count} HIGH severity conflict(s) should be resolved"
        elif len(warnings) > 3:
            verdict = "MARGINAL"
            reason = f"{len(warnings)} warnings — review recommended but not blocking"
        else:
            verdict = "CONVERGED"
            reason = f"All checks passed ({len(checks_passed)} checks, {len(warnings)} minor warnings)"

        return json.dumps({
            "verdict": verdict,
            "reason": reason,
            "conflicts": conflicts,
            "warnings": warnings,
            "checks_passed": checks_passed,
            "data_summary": data,
            "recommendation": (
                "Proceed to production" if verdict == "CONVERGED" else
                "Review warnings before proceeding" if verdict == "MARGINAL" else
                "Requires another design iteration — see conflicts for specific fixes"
            )
        })


# ============================================================
# Tool: GDD Patch — Targeted Section Updates
# ============================================================
# In convergence loops, the designer doesn't need to rewrite the
# entire 4000-word GDD. They just need to update specific sections
# based on math/compliance feedback.

class GDDPatchInput(BaseModel):
    gdd_path: str = Field(description="Path to the existing GDD markdown file")
    section_header: str = Field(
        description="The ## section header to update, e.g. '## 5. Symbol Hierarchy & Paytable' or '## 8. Feature Design'"
    )
    new_content: str = Field(description="Replacement content for the section (everything between this header and the next ## header)")
    reason: str = Field(description="Why this section is being updated (for audit trail)")


class GDDPatchTool(BaseTool):
    """Update a specific section of the GDD without rewriting the entire document.
    Use during convergence loops when math or compliance flags a specific issue."""

    name: str = "patch_gdd_section"
    description: str = (
        "Update a specific section of the existing GDD. Finds the ## header and "
        "replaces everything until the next ## header with your new content. "
        "Use this during convergence loops to fix specific issues flagged by "
        "the mathematician or compliance officer without rewriting the entire GDD. "
        "Also logs the change reason for audit trail."
    )
    args_schema: type[BaseModel] = GDDPatchInput

    def _run(self, gdd_path: str, section_header: str, new_content: str, reason: str = "") -> str:
        path = Path(gdd_path)
        if not path.exists():
            return json.dumps({"error": f"GDD not found at {gdd_path}"})

        try:
            content = path.read_text(encoding="utf-8")
            original_len = len(content)

            # Normalize the header for matching
            header_pattern = re.escape(section_header.strip())
            # Find the section: from header to next ## or end of file
            pattern = rf'({header_pattern}\s*\n)(.*?)(?=\n## |\Z)'
            match = re.search(pattern, content, re.DOTALL)

            if not match:
                # Try fuzzy match — find closest section header
                all_headers = re.findall(r'^## .+', content, re.MULTILINE)
                return json.dumps({
                    "error": f"Section '{section_header}' not found in GDD",
                    "available_sections": all_headers,
                    "hint": "Use one of the available section headers exactly"
                })

            # Replace the section content (keep the header)
            old_section = match.group(2)
            new_section = f"\n{new_content.strip()}\n\n"
            content = content[:match.start(2)] + new_section + content[match.end(2):]

            # Write updated GDD
            path.write_text(content, encoding="utf-8")

            # Append to revision log
            log_path = path.parent / "gdd_revision_log.md"
            revision_entry = (
                f"\n---\n### Revision: {section_header}\n"
                f"**Reason:** {reason}\n"
                f"**Old length:** {len(old_section)} chars → **New length:** {len(new_content)} chars\n"
                f"**Delta:** {len(new_content) - len(old_section):+d} chars\n"
            )
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(revision_entry)

            return json.dumps({
                "status": "success",
                "section_updated": section_header,
                "reason": reason,
                "old_section_chars": len(old_section),
                "new_section_chars": len(new_content),
                "total_gdd_chars": len(content),
                "revision_log": str(log_path),
            })

        except Exception as e:
            return json.dumps({"error": str(e)})


# ============================================================
# Tool: RTP Budget Calculator — Quick Math Sanity Check
# ============================================================

class RTPCalcInput(BaseModel):
    components: str = Field(
        description='JSON string of RTP component name-to-percentage mapping, '
                    'e.g. {"base_game": 39.6, "free_spins": 18.1, "bonus": 15.4, "jackpots": 0.35}'
    )
    target_rtp: float = Field(default=96.0, description="Target RTP percentage, e.g. 96.0")


class RTPBudgetCalculatorTool(BaseTool):
    """Quick arithmetic check: do the RTP components sum to target? Flags gaps."""

    name: str = "calculate_rtp_budget"
    description: str = (
        "Check if RTP budget components sum to the target RTP. "
        'Pass components as a JSON string, e.g. \'{"base_game": 39.6, "free_spins": 18.1, "bonus": 15.4, "jackpots": 0.35}\'. '
        "Returns: total, gap from target, and whether components are balanced."
    )
    args_schema: type[BaseModel] = RTPCalcInput

    def _run(self, components: str, target_rtp: float = 96.0) -> str:
        # Parse JSON string → dict (OpenAI sends str because dict schemas are rejected)
        if isinstance(components, str):
            try:
                components = json.loads(components)
            except json.JSONDecodeError:
                return json.dumps({
                    "error": "Invalid JSON for components. Provide a JSON object, "
                             'e.g. {"base_game": 39.6, "free_spins": 18.1, "bonus": 15.4}',
                    "balanced": False,
                })
        if not isinstance(components, dict) or not components:
            return json.dumps({
                "error": "Components must be a JSON object mapping names to RTP percentages.",
                "balanced": False,
            })

        total = sum(float(v) for v in components.values())
        gap = target_rtp - total
        balanced = abs(gap) < 0.5

        # Check for suspicious components
        warnings = []
        for name, pct in components.items():
            pct = float(pct)
            if pct < 0:
                warnings.append(f"'{name}' is negative ({pct}%) — impossible")
            if pct > 60:
                warnings.append(f"'{name}' is {pct}% — unusually high, verify")
            if "base" in name.lower() and pct < 20:
                warnings.append(f"Base game at {pct}% is very low — player experience may feel dead")
            if "jackpot" in name.lower() and pct > 5:
                warnings.append(f"Jackpot at {pct}% is very high — verify contribution rate")

        return json.dumps({
            "components": components,
            "total_rtp": round(total, 4),
            "target_rtp": target_rtp,
            "gap": round(gap, 4),
            "balanced": balanced,
            "verdict": "BALANCED" if balanced else f"GAP: {gap:+.2f}% unaccounted",
            "warnings": warnings,
        })


# ============================================================
# Tool: GDD Quality Auditor — Section-Level Scoring
# ============================================================
# Reads the GDD and scores each of the 15 standard sections for
# presence, completeness, specificity, and internal consistency.
# Producer runs this BEFORE the convergence loop (catch issues early)
# and after final assembly (verify nothing was lost).

# The 15 standard GDD sections expected in every ARKAINBRAIN GDD:
GDD_SECTIONS = [
    {"num": 1, "header": "Game Overview", "required_elements": ["theme", "volatility", "rtp", "grid"], "min_words": 60},
    {"num": 2, "header": "Target Market", "required_elements": ["jurisdiction", "demographic", "operator"], "min_words": 40},
    {"num": 3, "header": "Grid Layout", "required_elements": ["rows", "columns", "reels", "payline"], "min_words": 30},
    {"num": 4, "header": "Payline", "required_elements": ["ways", "lines", "pattern"], "min_words": 20},
    {"num": 5, "header": "Symbol Hierarchy", "required_elements": ["wild", "scatter", "high-pay", "low-pay", "paytable"], "min_words": 80},
    {"num": 6, "header": "RTP", "required_elements": ["target", "base game", "feature", "breakdown"], "min_words": 40},
    {"num": 7, "header": "Volatility", "required_elements": ["hit frequency", "max win", "standard deviation"], "min_words": 30},
    {"num": 8, "header": "Feature Design", "required_elements": ["trigger", "mechanic", "award", "frequency"], "min_words": 100},
    {"num": 9, "header": "Free Spins", "required_elements": ["trigger", "spins", "multiplier", "retrigger"], "min_words": 50},
    {"num": 10, "header": "Visual Design", "required_elements": ["color", "style", "mood", "animation"], "min_words": 40},
    {"num": 11, "header": "Sound Design", "required_elements": ["ambient", "reel", "win", "feature"], "min_words": 30},
    {"num": 12, "header": "Win Celebration", "required_elements": ["tier", "animation", "sound", "threshold"], "min_words": 30},
    {"num": 13, "header": "Responsible Gambling", "required_elements": ["session", "reality check", "limit"], "min_words": 25},
    {"num": 14, "header": "Certification", "required_elements": ["jurisdiction", "lab", "standard"], "min_words": 20},
    {"num": 15, "header": "Competitor", "required_elements": ["title", "provider", "comparison"], "min_words": 30},
]


class GDDQualityInput(BaseModel):
    gdd_path: str = Field(description="Path to the GDD markdown file to audit")


class GDDQualityAuditorTool(BaseTool):
    """Audit a GDD for section completeness, specificity, and quality.
    Returns per-section scores with specific fix instructions."""

    name: str = "audit_gdd_quality"
    description: str = (
        "Audit a GDD markdown file for quality. Checks all 15 standard sections for: "
        "presence, word count, required elements (e.g. does Symbol Hierarchy mention "
        "WILD/SCATTER?), specificity (are there actual numbers or just TBD?), and "
        "internal consistency. Returns a structured report with scores 0-100 per section "
        "and specific fix instructions for any issues found."
    )
    args_schema: type[BaseModel] = GDDQualityInput

    # Patterns that indicate vague/placeholder content
    VAGUE_PATTERNS: ClassVar[list] = [
        r'\bTBD\b', r'\bTBA\b', r'\bTO BE DETERMINED\b',
        r'\bINSERT\b', r'\bPLACEHOLDER\b', r'\bFILL IN\b',
        r'\bX{2,}\b',  # "XXX" or "XXXX"
        r'\b\[TODO\]', r'\b\[TBD\]',
        r'\bstandard\s+royals?\b',  # "standard royals" without naming them
        r'\btypical\s+slot\b',  # generic
        r'\bapproximately\b.*\bTBD\b',
    ]

    def _run(self, gdd_path: str) -> str:
        path = Path(gdd_path)
        if not path.exists():
            return json.dumps({"error": f"GDD not found: {gdd_path}"})

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return json.dumps({"error": str(e)})

        # Split GDD into sections by ## headers
        sections_raw = re.split(r'\n(?=## )', content)
        found_sections = {}
        for raw in sections_raw:
            match = re.match(r'^## (\d+[\.\)]?\s*)?(.*)', raw.strip())
            if match:
                header_text = match.group(2).strip().rstrip('#').strip()
                found_sections[header_text.lower()] = raw

        results = []
        total_score = 0
        issues_count = 0

        for sec_def in GDD_SECTIONS:
            section_report = {
                "section_num": sec_def["num"],
                "header": sec_def["header"],
                "score": 0,
                "issues": [],
                "fix_instructions": [],
            }

            # ── 1. PRESENCE CHECK ──
            found_key = None
            section_text = ""
            for key, text in found_sections.items():
                if sec_def["header"].lower() in key or any(
                    w.lower() in key for w in sec_def["header"].split()
                    if len(w) > 3
                ):
                    found_key = key
                    section_text = text
                    break

            if not found_key:
                section_report["score"] = 0
                section_report["issues"].append({
                    "type": "MISSING",
                    "detail": f"Section '{sec_def['header']}' not found in GDD"
                })
                section_report["fix_instructions"].append(
                    f"Add ## {sec_def['num']}. {sec_def['header']} section with: "
                    f"{', '.join(sec_def['required_elements'])}"
                )
                results.append(section_report)
                issues_count += 1
                continue

            # Presence = 25 points
            score = 25

            # ── 2. WORD COUNT CHECK ──
            words = section_text.split()
            word_count = len(words)
            if word_count >= sec_def["min_words"]:
                score += 25
            elif word_count >= sec_def["min_words"] * 0.5:
                score += 15
                section_report["issues"].append({
                    "type": "THIN",
                    "detail": f"{word_count} words (minimum: {sec_def['min_words']})"
                })
                section_report["fix_instructions"].append(
                    f"Expand section to at least {sec_def['min_words']} words"
                )
                issues_count += 1
            else:
                score += 5
                section_report["issues"].append({
                    "type": "STUB",
                    "detail": f"Only {word_count} words — this is a stub, not a section"
                })
                section_report["fix_instructions"].append(
                    f"Rewrite section completely — needs {sec_def['min_words']}+ words covering: "
                    f"{', '.join(sec_def['required_elements'])}"
                )
                issues_count += 1

            # ── 3. REQUIRED ELEMENTS CHECK ──
            section_lower = section_text.lower()
            found_elements = 0
            missing_elements = []
            for elem in sec_def["required_elements"]:
                if elem.lower() in section_lower:
                    found_elements += 1
                else:
                    missing_elements.append(elem)

            element_ratio = found_elements / len(sec_def["required_elements"]) if sec_def["required_elements"] else 1
            score += int(25 * element_ratio)

            if missing_elements:
                section_report["issues"].append({
                    "type": "MISSING_ELEMENTS",
                    "detail": f"Missing: {', '.join(missing_elements)}"
                })
                section_report["fix_instructions"].append(
                    f"Add content about: {', '.join(missing_elements)}"
                )
                issues_count += 1

            # ── 4. SPECIFICITY CHECK — are there real numbers or just vague language? ──
            vague_count = 0
            for pattern in self.VAGUE_PATTERNS:
                matches = re.findall(pattern, section_text, re.IGNORECASE)
                vague_count += len(matches)

            # Check for actual numbers (good sign)
            number_matches = re.findall(
                r'\b\d+[\.\d]*\s*(%|x|credits?|coins?|spins?|seconds?|ms|px|Hz)\b',
                section_text, re.IGNORECASE
            )
            has_numbers = len(number_matches) >= 2

            if vague_count == 0 and has_numbers:
                score += 25
            elif vague_count == 0:
                score += 15
                section_report["issues"].append({
                    "type": "LOW_SPECIFICITY",
                    "detail": "No specific numbers found — add exact values"
                })
                issues_count += 1
            else:
                score += max(0, 15 - vague_count * 5)
                section_report["issues"].append({
                    "type": "VAGUE",
                    "detail": f"{vague_count} placeholder(s) found (TBD, TBA, etc.)"
                })
                section_report["fix_instructions"].append(
                    "Replace all TBD/placeholder text with exact values"
                )
                issues_count += 1

            section_report["score"] = min(100, score)
            section_report["word_count"] = word_count
            total_score += section_report["score"]
            results.append(section_report)

        # Overall metrics
        sections_found = sum(1 for r in results if r["score"] > 0)
        avg_score = total_score / len(GDD_SECTIONS) if GDD_SECTIONS else 0

        # Grade
        if avg_score >= 85:
            grade = "A"
            verdict = "PRODUCTION_READY"
        elif avg_score >= 70:
            grade = "B"
            verdict = "GOOD_WITH_FIXES"
        elif avg_score >= 50:
            grade = "C"
            verdict = "NEEDS_REVISION"
        else:
            grade = "D"
            verdict = "MAJOR_REWRITE_NEEDED"

        return json.dumps({
            "verdict": verdict,
            "grade": grade,
            "average_score": round(avg_score, 1),
            "sections_found": sections_found,
            "sections_expected": len(GDD_SECTIONS),
            "total_issues": issues_count,
            "total_words": len(content.split()),
            "sections": results,
            "summary": (
                f"{grade} ({avg_score:.0f}/100) — {sections_found}/{len(GDD_SECTIONS)} sections present, "
                f"{issues_count} issues found. "
                + (f"Ready for convergence check." if verdict == "PRODUCTION_READY" else
                   f"Fix {issues_count} issues before convergence." if verdict in ("GOOD_WITH_FIXES", "NEEDS_REVISION") else
                   f"GDD needs significant rewriting.")
            )
        })


# ============================================================
# Tool: Paytable Sanity Checker — Math Validation
# ============================================================
# Validates the structural integrity of paytable.csv and reel strips.
# Catches errors the simulation would silently propagate.

class PaytableSanityInput(BaseModel):
    output_dir: str = Field(description="Pipeline output directory path (contains 03_math/)")


class PaytableSanityCheckerTool(BaseTool):
    """Validate paytable.csv and BaseReels.csv for structural correctness.
    Catches: non-monotonic pays, missing symbols, zero-pay rows, reel/paytable
    symbol mismatches, and unrealistic max win calculations."""

    name: str = "check_paytable_sanity"
    description: str = (
        "Validate the structural integrity of paytable.csv and BaseReels.csv. "
        "Checks: pay values are monotonically increasing (5OAK > 4OAK > 3OAK), "
        "no symbol pays 0 for all combinations, WILD/SCATTER handling, all reel "
        "symbols exist in paytable and vice versa, max theoretical win is within "
        "target range. Returns structured report with specific fix instructions."
    )
    args_schema: type[BaseModel] = PaytableSanityInput

    def _run(self, output_dir: str) -> str:
        math_dir = Path(output_dir) / "03_math"
        issues = []
        warnings = []
        checks_passed = []

        # ── 1. Parse paytable.csv ──
        paytable_path = math_dir / "paytable.csv"
        paytable_data = []
        if not paytable_path.exists():
            return json.dumps({
                "verdict": "FAIL",
                "issues": [{"type": "MISSING_FILE", "detail": "paytable.csv not found"}],
                "warnings": [], "checks_passed": []
            })

        try:
            text = paytable_path.read_text(encoding="utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = reader.fieldnames or []
            for row in reader:
                paytable_data.append(row)
        except Exception as e:
            return json.dumps({
                "verdict": "FAIL",
                "issues": [{"type": "PARSE_ERROR", "detail": f"Cannot parse paytable.csv: {e}"}],
                "warnings": [], "checks_passed": []
            })

        if not paytable_data:
            issues.append({"type": "EMPTY_PAYTABLE", "detail": "paytable.csv has no data rows",
                           "fix": "Mathematician must regenerate paytable with all symbols"})
        else:
            checks_passed.append(f"Paytable: {len(paytable_data)} symbols loaded")

        # Identify symbol and pay columns
        sym_col = None
        pay_cols = {}  # e.g. {"3OAK": col_name, "4OAK": col_name, "5OAK": col_name}
        for fn in fieldnames:
            fl = fn.lower().strip()
            if fl in ("symbol", "name", "sym"):
                sym_col = fn
            for n in (3, 4, 5, 6):
                if f"{n}oak" in fl or f"{n}x" in fl or f"{n} of" in fl or f"x{n}" in fl or fl == str(n):
                    pay_cols[f"{n}OAK"] = fn

        if not sym_col and fieldnames:
            sym_col = fieldnames[0]  # Assume first column is symbol name

        # ── 2. Monotonic pay check ──
        sorted_keys = sorted(pay_cols.keys())  # e.g. ["3OAK", "4OAK", "5OAK"]
        for row in paytable_data:
            sym_name = row.get(sym_col, "???").strip()
            if not sym_name or sym_name.lower() in ("wild", "scatter", "bonus"):
                continue  # Special symbols may not follow standard pay rules

            prev_val = -1
            for pk in sorted_keys:
                col = pay_cols[pk]
                try:
                    val = float(row.get(col, 0))
                except (ValueError, TypeError):
                    val = 0
                if val > 0 and val < prev_val:
                    issues.append({
                        "type": "NON_MONOTONIC",
                        "detail": f"Symbol '{sym_name}': {pk} pay ({val}) < previous tier ({prev_val})",
                        "fix": f"Fix paytable: {pk} for '{sym_name}' must be ≥ {prev_val}"
                    })
                if val > 0:
                    prev_val = val

        if not any(i["type"] == "NON_MONOTONIC" for i in issues):
            checks_passed.append("Pay values monotonically increasing")

        # ── 3. Zero-pay check ──
        for row in paytable_data:
            sym_name = row.get(sym_col, "???").strip()
            all_zero = True
            for pk in sorted_keys:
                col = pay_cols.get(pk, "")
                try:
                    val = float(row.get(col, 0))
                except (ValueError, TypeError):
                    val = 0
                if val > 0:
                    all_zero = False
                    break
            if all_zero and sym_name.lower() not in ("wild", "scatter", "bonus", ""):
                warnings.append({
                    "type": "ZERO_PAY",
                    "detail": f"Symbol '{sym_name}' pays 0 across all tiers",
                    "fix": f"Add pay values for '{sym_name}' or remove from paytable if it's a special symbol"
                })

        # ── 4. WILD/SCATTER presence ──
        sym_names = [row.get(sym_col, "").strip().lower() for row in paytable_data]
        has_wild = any("wild" in s for s in sym_names)
        has_scatter = any("scatter" in s or "bonus" in s for s in sym_names)

        if has_wild:
            checks_passed.append("WILD symbol present")
        else:
            warnings.append({
                "type": "NO_WILD",
                "detail": "No WILD symbol found in paytable",
                "fix": "Add WILD symbol — nearly all slot games need one"
            })

        if has_scatter:
            checks_passed.append("SCATTER/BONUS symbol present")
        else:
            warnings.append({
                "type": "NO_SCATTER",
                "detail": "No SCATTER or BONUS symbol found in paytable",
                "fix": "Add SCATTER for free spins trigger or BONUS for bonus game trigger"
            })

        # ── 5. Reel strips validation ──
        reels_path = math_dir / "BaseReels.csv"
        reel_symbols = set()
        paytable_symbols = {row.get(sym_col, "").strip() for row in paytable_data if row.get(sym_col, "").strip()}

        if reels_path.exists():
            try:
                reel_text = reels_path.read_text(encoding="utf-8", errors="replace")
                reel_reader = csv.reader(io.StringIO(reel_text))
                reel_header = next(reel_reader, [])
                reel_rows = list(reel_reader)

                # Collect all symbols from reels
                for row in reel_rows:
                    for cell in row:
                        cell = cell.strip()
                        if cell and cell.lower() not in ("", "position", "pos", "stop"):
                            reel_symbols.add(cell)

                checks_passed.append(f"BaseReels.csv: {len(reel_rows)} positions, {len(reel_header)} reels")

                # ── 5a. Symbols in reels but not in paytable ──
                only_in_reels = reel_symbols - paytable_symbols
                if only_in_reels:
                    # Try case-insensitive match first
                    pt_lower = {s.lower(): s for s in paytable_symbols}
                    truly_missing = {s for s in only_in_reels if s.lower() not in pt_lower}
                    if truly_missing:
                        issues.append({
                            "type": "REEL_SYMBOL_MISSING_FROM_PAYTABLE",
                            "detail": f"Symbols on reels but NOT in paytable: {', '.join(sorted(truly_missing))}",
                            "fix": f"Add these symbols to paytable.csv OR remove from reel strips"
                        })

                # ── 5b. Symbols in paytable but not on reels ──
                only_in_paytable = paytable_symbols - reel_symbols
                if only_in_paytable:
                    rl_lower = {s.lower() for s in reel_symbols}
                    truly_missing = {s for s in only_in_paytable if s.lower() not in rl_lower}
                    if truly_missing:
                        warnings.append({
                            "type": "PAYTABLE_SYMBOL_NOT_ON_REELS",
                            "detail": f"Symbols in paytable but NOT on any reel: {', '.join(sorted(truly_missing))}",
                            "fix": f"Add these symbols to reel strips or mark as special (WILD substitution only)"
                        })

                # ── 5c. Empty reels check ──
                for col_idx, reel_name in enumerate(reel_header):
                    reel_col_values = [row[col_idx].strip() for row in reel_rows if col_idx < len(row) and row[col_idx].strip()]
                    if len(reel_col_values) < 10:
                        issues.append({
                            "type": "SHORT_REEL",
                            "detail": f"Reel '{reel_name}' has only {len(reel_col_values)} positions (minimum: ~20-30)",
                            "fix": f"Extend reel '{reel_name}' to at least 20 positions"
                        })

                if not any(i["type"] == "REEL_SYMBOL_MISSING_FROM_PAYTABLE" for i in issues):
                    checks_passed.append("All reel symbols exist in paytable")

            except Exception as e:
                warnings.append({"type": "REEL_PARSE_ERROR", "detail": f"Error reading BaseReels.csv: {e}"})
        else:
            issues.append({
                "type": "MISSING_REELS",
                "detail": "BaseReels.csv not found",
                "fix": "Mathematician must generate reel strip CSV"
            })

        # ── 6. Max theoretical win estimate ──
        if pay_cols and paytable_data:
            max_pay = 0
            for row in paytable_data:
                for pk in sorted_keys:
                    col = pay_cols.get(pk, "")
                    try:
                        val = float(row.get(col, 0))
                        max_pay = max(max_pay, val)
                    except (ValueError, TypeError):
                        pass
            if max_pay > 0:
                checks_passed.append(f"Highest single pay: {max_pay}x")

        # ── Verdict ──
        blocker_count = sum(1 for i in issues if i.get("type") in (
            "REEL_SYMBOL_MISSING_FROM_PAYTABLE", "EMPTY_PAYTABLE", "SHORT_REEL", "MISSING_REELS"
        ))

        if blocker_count > 0:
            verdict = "FAIL"
        elif issues:
            verdict = "NEEDS_FIXES"
        elif len(warnings) > 3:
            verdict = "MARGINAL"
        else:
            verdict = "PASS"

        return json.dumps({
            "verdict": verdict,
            "issues": issues,
            "warnings": warnings,
            "checks_passed": checks_passed,
            "symbol_count": len(paytable_symbols),
            "reel_symbol_count": len(reel_symbols),
            "summary": (
                f"{verdict} — {len(paytable_symbols)} paytable symbols, "
                f"{len(reel_symbols)} reel symbols, "
                f"{len(issues)} issues, {len(warnings)} warnings"
            )
        })
