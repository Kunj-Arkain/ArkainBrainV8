"""
ARKAINBRAIN — Web-Based Human-in-the-Loop System

When a pipeline hits a checkpoint, it:
1. Creates a review record in the database
2. Polls the DB waiting for the user to approve/reject
3. The web UI shows the review page with content + approve/reject/feedback
4. When the user responds, the DB is updated and the pipeline resumes

Phase 5A: Uses config.database for PostgreSQL/SQLite dual-mode.

Usage (in pipeline code):
    from tools.web_hitl import web_hitl_checkpoint
    approved, feedback = web_hitl_checkpoint(
        job_id="abc123",
        stage="post_research",
        title="Market Research Complete",
        summary="Research found 15 competitors...",
        files=["01_research/market_sweep.json"],
        auto=False,
    )
"""

import logging
import time
import os

logger = logging.getLogger("arkainbrain.hitl")


def _get_db():
    """Get a standalone database connection (works outside Flask context)."""
    try:
        from config.database import get_standalone_db
        return get_standalone_db()
    except ImportError:
        # Fallback: direct SQLite
        import sqlite3
        DB_PATH = os.getenv("DB_PATH", "arkainbrain.db")
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        # Wrap in a compat shim
        return conn


def init_reviews_table():
    """Create the reviews table if it doesn't exist.
    Now handled by config.database.init_db() — this is a no-op safety check."""
    try:
        from config.database import init_db
        # Schema already includes reviews table
        pass
    except ImportError:
        import sqlite3
        DB_PATH = os.getenv("DB_PATH", "arkainbrain.db")
        db = sqlite3.connect(DB_PATH, timeout=10)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                files TEXT,
                status TEXT DEFAULT 'pending',
                approved INTEGER,
                feedback TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );
            CREATE INDEX IF NOT EXISTS idx_reviews_job ON reviews(job_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
        """)
        db.close()


# Initialize on import
init_reviews_table()


def web_hitl_checkpoint(
    job_id: str,
    stage: str,
    title: str,
    summary: str,
    files: list[str] = None,
    auto: bool = False,
    timeout: int = 3600,  # 1 hour max wait
) -> tuple[bool, str]:
    """
    Block the pipeline and wait for user review via the web UI.

    Uses DB-polling so it works across processes (subprocess workers).

    Args:
        job_id: The pipeline job ID
        stage: Checkpoint name
        title: Human-readable title shown in the review UI
        summary: Description of what to review
        files: List of relative file paths the user should look at
        auto: If True, auto-approve without blocking
        timeout: Max seconds to wait for review (default 1 hour)

    Returns:
        (approved: bool, feedback: str)
    """
    if auto:
        return True, ""

    import uuid
    import json

    review_id = f"rev_{uuid.uuid4().hex[:8]}"

    # Create the review record
    db = _get_db()
    db.execute(
        "INSERT INTO reviews (id, job_id, stage, title, summary, files, status) "
        "VALUES (?,?,?,?,?,?,?)",
        (review_id, job_id, stage, title, summary, json.dumps(files or []), "pending")
    )
    db.commit()
    db.close()

    # Update the job's current_stage to indicate it's waiting for review
    db = _get_db()
    db.execute(
        "UPDATE jobs SET current_stage=? WHERE id=?",
        (f"\u23f8 Waiting for review: {title}", job_id)
    )
    db.commit()
    db.close()

    logger.info(f"Pipeline paused at '{stage}' -- waiting for review: {review_id}")

    # Poll the DB until the review is resolved or timeout
    poll_interval = 3  # seconds
    elapsed = 0
    while elapsed < timeout:
        time.sleep(poll_interval)
        elapsed += poll_interval

        db = _get_db()
        row = db.execute(
            "SELECT status, approved, feedback FROM reviews WHERE id=?",
            (review_id,)
        ).fetchone()
        db.close()

        if row and row["status"] != "pending":
            approved = bool(row["approved"])
            feedback = row["feedback"] or ""
            logger.info(f"Review {review_id}: {'APPROVED' if approved else 'REJECTED'} -- {feedback}")
            return approved, feedback

    # Timeout -- auto-approve
    logger.warning(f"Review {review_id}: TIMEOUT after {timeout}s -- auto-approving")
    db = _get_db()
    db.execute(
        "UPDATE reviews SET status='approved', approved=1, "
        "feedback='Auto-approved (timeout)', resolved_at=datetime('now') WHERE id=?",
        (review_id,)
    )
    db.commit()
    db.close()
    return True, "Auto-approved (timeout)"


def submit_review(review_id: str, approved: bool, feedback: str = ""):
    """Called by the web UI when the user submits a review."""
    db = _get_db()
    db.execute(
        "UPDATE reviews SET status=?, approved=?, feedback=?, resolved_at=datetime('now') "
        "WHERE id=?",
        ("approved" if approved else "rejected", 1 if approved else 0, feedback, review_id)
    )
    db.commit()
    db.close()


def get_pending_reviews(job_id: str = None) -> list[dict]:
    """Get all pending reviews, optionally filtered by job_id."""
    db = _get_db()
    if job_id:
        rows = db.execute(
            "SELECT r.*, j.title as job_title, j.output_dir FROM reviews r "
            "JOIN jobs j ON r.job_id = j.id WHERE r.status='pending' AND r.job_id=? "
            "ORDER BY r.created_at DESC", (job_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT r.*, j.title as job_title, j.output_dir FROM reviews r "
            "JOIN jobs j ON r.job_id = j.id WHERE r.status='pending' "
            "ORDER BY r.created_at DESC"
        ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_review(review_id: str) -> dict:
    """Get a single review by ID."""
    db = _get_db()
    row = db.execute(
        "SELECT r.*, j.title as job_title, j.output_dir FROM reviews r "
        "JOIN jobs j ON r.job_id = j.id WHERE r.id=?", (review_id,)
    ).fetchone()
    db.close()
    return dict(row) if row else None
