"""
ARKAINBRAIN — Review API Logic (Phase 8)

Backend functions for the interactive review system.
Called by web_app.py route handlers.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("arkainbrain.review")


# ═══════════════════════════════════════════════
# GDD Section Parsing
# ═══════════════════════════════════════════════

def parse_gdd_sections(job_id: str, output_dir: str) -> list[dict]:
    """Parse GDD markdown into sections for section-level review."""
    gdd_path = _find_gdd(output_dir)
    if not gdd_path:
        return []

    text = gdd_path.read_text(encoding="utf-8")
    sections = []
    current = None

    for line in text.split("\n"):
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = {
                "id": f"gdd-{len(sections)}",
                "title": line.lstrip("#").strip(),
                "content": "",
                "line_start": 0,
            }
        elif current:
            current["content"] += line + "\n"

    if current:
        sections.append(current)

    # Add metadata
    for s in sections:
        s["content"] = s["content"].strip()
        s["word_count"] = len(s["content"].split())

    return sections


def save_gdd_section(output_dir: str, section_id: str, new_content: str) -> bool:
    """Save an edited GDD section back to the file."""
    gdd_path = _find_gdd(output_dir)
    if not gdd_path:
        return False

    sections = parse_gdd_sections("", output_dir)
    idx = next((i for i, s in enumerate(sections) if s["id"] == section_id), None)
    if idx is None:
        return False

    sections[idx]["content"] = new_content

    # Reconstruct full GDD
    lines = []
    for s in sections:
        lines.append(f"## {s['title']}")
        lines.append(s["content"])
        lines.append("")

    gdd_path.write_text("\n".join(lines), encoding="utf-8")

    # Save backup
    backup = gdd_path.parent / f"{gdd_path.stem}_backup_{datetime.now().strftime('%H%M%S')}{gdd_path.suffix}"
    backup.write_text("\n".join(lines), encoding="utf-8")

    return True


def _find_gdd(output_dir: str) -> Optional[Path]:
    """Find the GDD file in the output directory."""
    od = Path(output_dir)
    for name in ["gdd.md", "game_design_document.md", "GDD.md"]:
        p = od / "02_design" / name
        if p.exists():
            return p
    # Fallback: search
    for f in od.rglob("*.md"):
        if "gdd" in f.name.lower() or "game_design" in f.name.lower():
            return f
    return None


# ═══════════════════════════════════════════════
# Paytable Operations
# ═══════════════════════════════════════════════

def load_paytable(output_dir: str) -> Optional[dict]:
    """Load paytable data from the output directory."""
    od = Path(output_dir)
    for name in ["paytable.json", "paytable.csv"]:
        p = od / "03_math" / name
        if p.exists():
            if name.endswith(".json"):
                return json.loads(p.read_text())
            else:
                return _csv_to_paytable(p)
    return None


def save_paytable(output_dir: str, paytable: dict) -> bool:
    """Save edited paytable back to the output directory."""
    od = Path(output_dir)
    pt_path = od / "03_math" / "paytable.json"

    # Backup existing
    if pt_path.exists():
        backup = od / "03_math" / f"paytable_backup_{datetime.now().strftime('%H%M%S')}.json"
        backup.write_text(pt_path.read_text(), encoding="utf-8")

    pt_path.write_text(json.dumps(paytable, indent=2), encoding="utf-8")
    return True


def update_paytable_cell(output_dir: str, symbol: str, count: int, pay: float) -> dict:
    """Update a single paytable cell and return the new value."""
    pt = load_paytable(output_dir)
    if not pt:
        return {"error": "Paytable not found"}

    # Handle various paytable formats
    if isinstance(pt, dict):
        if symbol in pt:
            if isinstance(pt[symbol], dict):
                key = f"{count}oak" if count > 1 else "pay"
                pt[symbol][key] = pay
            elif isinstance(pt[symbol], list) and count <= len(pt[symbol]):
                pt[symbol][count - 1] = pay
    elif isinstance(pt, list):
        for row in pt:
            if row.get("symbol") == symbol or row.get("name") == symbol:
                key = f"{count}_of_a_kind" if count > 1 else f"pay_{count}"
                row[key] = pay
                break

    save_paytable(output_dir, pt)
    return {"success": True, "symbol": symbol, "count": count, "pay": pay}


def quick_rtp_estimate(output_dir: str, target_rtp: float = 96.0) -> dict:
    """Quick RTP estimate based on paytable structure.
    Returns estimated RTP and delta from target."""
    pt = load_paytable(output_dir)
    if not pt:
        return {"error": "No paytable found", "estimated_rtp": None}

    # Try to read simulation results for baseline
    sim_path = Path(output_dir) / "03_math" / "simulation_results.json"
    if sim_path.exists():
        try:
            sim = json.loads(sim_path.read_text())
            r = sim.get("results", sim)
            measured = r.get("measured_rtp") or r.get("rtp")
            if measured:
                delta = measured - target_rtp
                return {
                    "estimated_rtp": round(measured, 3),
                    "target_rtp": target_rtp,
                    "delta": round(delta, 3),
                    "warning": f"{'Exceeds' if delta > 0 else 'Below'} target by {abs(delta):.2f}%" if abs(delta) > 0.3 else None,
                    "source": "simulation",
                }
        except Exception:
            pass

    return {
        "estimated_rtp": None,
        "target_rtp": target_rtp,
        "delta": None,
        "warning": "No simulation data available — run simulation for accurate RTP",
        "source": "none",
    }


def _csv_to_paytable(path: Path) -> dict:
    """Convert CSV paytable to dict format."""
    result = {}
    try:
        lines = path.read_text().strip().split("\n")
        if len(lines) < 2:
            return result
        headers = [h.strip() for h in lines[0].split(",")]
        for line in lines[1:]:
            cols = [c.strip() for c in line.split(",")]
            if len(cols) >= 2:
                symbol = cols[0]
                result[symbol] = {}
                for i, h in enumerate(headers[1:], 1):
                    if i < len(cols):
                        try:
                            result[symbol][h] = float(cols[i])
                        except ValueError:
                            result[symbol][h] = cols[i]
    except Exception as e:
        logger.warning(f"CSV paytable parse: {e}")
    return result


# ═══════════════════════════════════════════════
# Simulation Results
# ═══════════════════════════════════════════════

def load_sim_results(output_dir: str) -> Optional[dict]:
    """Load simulation results for the sim dashboard."""
    od = Path(output_dir)
    sim_path = od / "03_math" / "simulation_results.json"
    if sim_path.exists():
        try:
            data = json.loads(sim_path.read_text())
            return data.get("results", data)
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════
# Comments
# ═══════════════════════════════════════════════

def add_comment(db, job_id: str, section: str, content: str,
                author: str = "", parent_id: str = None) -> dict:
    """Add a threaded comment on a section."""
    comment_id = str(uuid.uuid4())[:10]
    db.execute(
        "INSERT INTO review_comments (id, job_id, section, author, content, parent_id) "
        "VALUES (?,?,?,?,?,?)",
        (comment_id, job_id, section, author, content, parent_id)
    )
    db.commit()
    return {"id": comment_id, "section": section, "content": content,
            "author": author, "parent_id": parent_id}


def get_comments(db, job_id: str, section: str = None) -> list[dict]:
    """Get comments for a job, optionally filtered by section."""
    if section:
        rows = db.execute(
            "SELECT * FROM review_comments WHERE job_id=? AND section=? ORDER BY created_at",
            (job_id, section)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM review_comments WHERE job_id=? ORDER BY section, created_at",
            (job_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_comment(db, comment_id: str) -> bool:
    """Mark a comment as resolved."""
    db.execute(
        "UPDATE review_comments SET resolved=1 WHERE id=?", (comment_id,)
    )
    db.commit()
    return True


# ═══════════════════════════════════════════════
# Section-Level Approvals
# ═══════════════════════════════════════════════

def set_section_approval(db, job_id: str, section: str, status: str,
                         reviewer: str = "", role: str = "", feedback: str = "") -> dict:
    """Set approval status for a specific section."""
    approval_id = str(uuid.uuid4())[:10]
    # Upsert
    try:
        db.execute(
            "INSERT INTO section_approvals (id, job_id, section, status, reviewer, role, feedback, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(job_id, section, reviewer) DO UPDATE SET status=?, feedback=?, updated_at=?",
            (approval_id, job_id, section, status, reviewer, role, feedback,
             datetime.now().isoformat(), status, feedback, datetime.now().isoformat())
        )
    except Exception:
        # Fallback for SQLite without ON CONFLICT
        db.execute(
            "DELETE FROM section_approvals WHERE job_id=? AND section=? AND reviewer=?",
            (job_id, section, reviewer)
        )
        db.execute(
            "INSERT INTO section_approvals (id, job_id, section, status, reviewer, role, feedback) "
            "VALUES (?,?,?,?,?,?,?)",
            (approval_id, job_id, section, status, reviewer, role, feedback)
        )
    db.commit()
    return {"section": section, "status": status, "reviewer": reviewer}


def get_section_approvals(db, job_id: str) -> list[dict]:
    """Get all section approvals for a job."""
    rows = db.execute(
        "SELECT * FROM section_approvals WHERE job_id=? ORDER BY section",
        (job_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════
# Diff Generation
# ═══════════════════════════════════════════════

def get_ooda_diff(output_dir: str) -> list[dict]:
    """Find OODA loop revision diffs in the output directory."""
    od = Path(output_dir)
    diffs = []

    # Look for versioned files
    math_dir = od / "03_math"
    design_dir = od / "02_design"

    for d in [math_dir, design_dir]:
        if not d.exists():
            continue
        files = sorted(d.glob("*_backup_*"))
        for backup in files:
            original_name = backup.name.split("_backup_")[0] + backup.suffix
            original = d / original_name
            if original.exists():
                try:
                    old_text = backup.read_text(encoding="utf-8")[:5000]
                    new_text = original.read_text(encoding="utf-8")[:5000]
                    if old_text != new_text:
                        diffs.append({
                            "file": original_name,
                            "directory": d.name,
                            "old": old_text,
                            "new": new_text,
                            "backup_file": backup.name,
                        })
                except Exception:
                    pass

    # Also check for adversarial review files
    for f in od.glob("adversarial_review_*.md"):
        try:
            diffs.append({
                "file": f.name,
                "directory": "root",
                "old": "",
                "new": f.read_text(encoding="utf-8")[:5000],
                "type": "adversarial_review",
            })
        except Exception:
            pass

    return diffs


# ═══════════════════════════════════════════════
# Review Summary Builder
# ═══════════════════════════════════════════════

def build_review_data(job_id: str, output_dir: str, target_rtp: float = 96.0) -> dict:
    """Build comprehensive review data for the interactive review UI."""
    od = Path(output_dir) if output_dir else Path(".")

    data = {
        "job_id": job_id,
        "output_dir": str(od),
        "gdd_sections": parse_gdd_sections(job_id, str(od)),
        "paytable": load_paytable(str(od)),
        "sim_results": load_sim_results(str(od)),
        "rtp_estimate": quick_rtp_estimate(str(od), target_rtp),
        "diffs": get_ooda_diff(str(od)),
        "files": [],
    }

    # Collect key files
    if od.exists():
        for f in sorted(od.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                data["files"].append({
                    "path": str(f.relative_to(od)),
                    "size": f.stat().st_size,
                    "ext": f.suffix.lower(),
                })

    return data
