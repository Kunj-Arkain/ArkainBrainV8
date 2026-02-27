"""
ARKAINBRAIN — Database Abstraction Layer (Phase 5A)

Dual-mode: SQLite for local dev, PostgreSQL for Railway production.
Auto-detects based on DATABASE_URL environment variable.

Usage:
    from config.database import get_db, init_db, query_db, execute_db

    # In Flask request context — auto-managed lifecycle
    rows = query_db("SELECT * FROM jobs WHERE user_id = %s", [user_id])

    # Outside request context — returns standalone connection, caller closes
    db = get_db()
    ...
    db.close()
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("arkainbrain.db")

# ── Detect database mode ──
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        HAS_PSYCOPG = True
    except ImportError:
        logger.warning("DATABASE_URL is set but psycopg3 not installed — falling back to SQLite")
        HAS_PSYCOPG = False
        USE_POSTGRES = False
else:
    HAS_PSYCOPG = False

# ── SQLite fallback path ──
SQLITE_PATH = os.getenv("DB_PATH", "arkainbrain.db")

# ── Connection pool (PostgreSQL only) ──
_pg_pool = None


def _get_pg_pool():
    """Lazy-init PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is None and USE_POSTGRES and HAS_PSYCOPG:
        conninfo = DATABASE_URL
        # Railway uses postgres:// but psycopg wants postgresql://
        if conninfo.startswith("postgres://"):
            conninfo = conninfo.replace("postgres://", "postgresql://", 1)
        _pg_pool = ConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=20,
            max_idle=300,
            kwargs={"row_factory": dict_row, "autocommit": False},
        )
        logger.info(f"PostgreSQL pool initialized (min=2, max=20)")
    return _pg_pool


# ── SQLite dict-row wrapper ──
class _SqliteDict(dict):
    """Makes sqlite3.Row behave like a dict with .get() support."""
    pass


def _sqlite_dict_factory(cursor, row):
    d = _SqliteDict()
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def _open_sqlite():
    """Open a raw SQLite connection."""
    conn = sqlite3.connect(SQLITE_PATH, timeout=10)
    conn.row_factory = _sqlite_dict_factory
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

class DatabaseConnection:
    """Unified wrapper around SQLite or PostgreSQL connections.

    Normalizes the interface so callers don't care which backend is active.
    - Uses %s placeholders (PostgreSQL style) — auto-converts to ? for SQLite
    - Returns list[dict] from queries
    - Supports .execute(), .fetchone(), .fetchall(), .commit(), .close()
    """

    def __init__(self, conn, is_pg=False):
        self._conn = conn
        self._is_pg = is_pg
        self._cursor = None

    def _adapt_sql(self, sql):
        """Convert between placeholder styles.
        Accepts BOTH ? (SQLite) and %s (PostgreSQL) — converts to active backend.
        Handles datetime('now') vs CURRENT_TIMESTAMP for PG compat."""
        if self._is_pg:
            # Convert ? → %s for PostgreSQL
            sql = sql.replace("?", "%s")
            # SQLite datetime functions → PG equivalents
            sql = sql.replace("datetime('now')", "CURRENT_TIMESTAMP")
            sql = sql.replace("datetime('now', '-100 minutes')",
                              "(CURRENT_TIMESTAMP - INTERVAL '100 minutes')")
        else:
            # Convert %s → ? for SQLite
            sql = sql.replace("%s", "?")
        return sql

    def execute(self, sql, params=None):
        """Execute a query. Returns self for chaining."""
        sql = self._adapt_sql(sql)
        if self._is_pg:
            self._cursor = self._conn.execute(sql, params or [])
        else:
            self._cursor = self._conn.execute(sql, params or [])
        return self

    def executescript(self, sql):
        """Execute multiple statements (SQLite-style). For PG, splits on semicolons."""
        if self._is_pg:
            # PostgreSQL: execute each statement
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    self._conn.execute(stmt)
        else:
            self._conn.executescript(sql)
        return self

    def fetchone(self):
        """Fetch one row as dict, or None."""
        if self._cursor is None:
            return None
        row = self._cursor.fetchone()
        return dict(row) if row and not isinstance(row, dict) else row

    def fetchall(self):
        """Fetch all rows as list[dict]."""
        if self._cursor is None:
            return []
        rows = self._cursor.fetchall()
        return [dict(r) if not isinstance(r, dict) else r for r in rows]

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._is_pg:
            # Return connection to pool
            self._conn.close()
        else:
            self._conn.close()

    # Context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

    # Make it work with sqlite3.Row-style access: row["col"]
    def __getitem__(self, key):
        if self._cursor:
            return self._cursor.__getitem__(key)
        raise KeyError(key)


def get_db():
    """Get a database connection.

    In Flask request context: caches on g, auto-closed on teardown.
    Outside request context: returns standalone connection — caller must close.
    """
    from flask import g, has_app_context

    try:
        if has_app_context():
            if "_database" not in g:
                g._database = _make_connection()
            return g._database
    except RuntimeError:
        pass

    return _make_connection()


def get_standalone_db():
    """Always returns a new standalone connection (for workers, background tasks).
    Caller MUST close this connection."""
    return _make_connection()


def _make_connection():
    """Create a new DatabaseConnection."""
    if USE_POSTGRES and HAS_PSYCOPG:
        pool = _get_pg_pool()
        conn = pool.getconn()
        return DatabaseConnection(conn, is_pg=True)
    else:
        conn = _open_sqlite()
        return DatabaseConnection(conn, is_pg=False)


def close_db_on_teardown(exc):
    """Flask teardown handler — auto-close the per-request connection."""
    from flask import g
    db = g.pop("_database", None)
    if db is not None:
        db.close()


def query_db(sql, params=None, one=False):
    """Convenience: execute + fetch in one call.
    Uses the request-scoped connection in Flask context."""
    db = get_db()
    db.execute(sql, params)
    return db.fetchone() if one else db.fetchall()


def execute_db(sql, params=None):
    """Convenience: execute + commit in one call."""
    db = get_db()
    db.execute(sql, params)
    db.commit()


# ═══════════════════════════════════════════════════════════════
# Schema Initialization & Migration
# ═══════════════════════════════════════════════════════════════

# SQL that works for BOTH SQLite and PostgreSQL
# We use TEXT for timestamps (SQLite compat) — PG auto-casts fine
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    picture TEXT,
    email_notify INTEGER DEFAULT 1,
    role TEXT DEFAULT 'user',
    plan TEXT DEFAULT 'free',
    plan_started_at TEXT,
    plan_expires_at TEXT,
    monthly_job_limit INTEGER DEFAULT 10,
    monthly_jobs_used INTEGER DEFAULT 0,
    is_suspended INTEGER DEFAULT 0,
    suspension_reason TEXT,
    last_active_at TEXT,
    metadata TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_type TEXT NOT NULL DEFAULT 'slot_pipeline',
    title TEXT NOT NULL,
    params TEXT,
    status TEXT DEFAULT 'queued',
    current_stage TEXT DEFAULT 'Initializing',
    output_dir TEXT,
    error TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    completed_at TEXT,
    parent_job_id TEXT,
    version INTEGER DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

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
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    resolved_at TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_job ON reviews(job_id);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);

CREATE TABLE IF NOT EXISTS file_tags (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_file_tags_job ON file_tags(job_id);
CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag);

CREATE TABLE IF NOT EXISTS run_records (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    user_id TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    theme TEXT,
    theme_tags TEXT,
    grid TEXT,
    eval_mode TEXT,
    volatility TEXT,
    measured_rtp REAL,
    target_rtp REAL,
    hit_frequency REAL,
    max_win_achieved REAL,
    jurisdictions TEXT,
    features TEXT,
    reel_strips TEXT,
    paytable TEXT,
    feature_config TEXT,
    rtp_budget_breakdown TEXT,
    sim_config TEXT,
    ooda_iterations INTEGER DEFAULT 0,
    convergence_flags TEXT,
    final_warnings TEXT,
    gdd_summary TEXT,
    math_summary TEXT,
    cost_usd REAL,
    embedding TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_run_records_job ON run_records(job_id);
CREATE INDEX IF NOT EXISTS idx_run_records_theme ON run_records(theme);
CREATE INDEX IF NOT EXISTS idx_run_records_volatility ON run_records(volatility);

CREATE TABLE IF NOT EXISTS component_library (
    id TEXT PRIMARY KEY,
    source_run_id TEXT,
    component_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    config TEXT,
    measured_rtp_contribution REAL,
    volatility_contribution TEXT,
    tags TEXT,
    times_reused INTEGER DEFAULT 0,
    avg_satisfaction REAL DEFAULT 0.0,
    embedding TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY (source_run_id) REFERENCES run_records(id)
);

CREATE INDEX IF NOT EXISTS idx_components_type ON component_library(component_type);
CREATE INDEX IF NOT EXISTS idx_components_source ON component_library(source_run_id);

CREATE TABLE IF NOT EXISTS iteration_feedback (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    parent_run_id TEXT,
    changes_made TEXT,
    rtp_before REAL,
    rtp_after REAL,
    user_modifications TEXT,
    improvement_score REAL,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY (run_id) REFERENCES run_records(id)
);

CREATE INDEX IF NOT EXISTS idx_iteration_feedback_run ON iteration_feedback(run_id);

CREATE TABLE IF NOT EXISTS review_comments (
    id TEXT PRIMARY KEY,
    review_id TEXT,
    job_id TEXT NOT NULL,
    section TEXT NOT NULL,
    author TEXT,
    content TEXT NOT NULL,
    parent_id TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_review_comments_job ON review_comments(job_id);
CREATE INDEX IF NOT EXISTS idx_review_comments_section ON review_comments(section);

CREATE TABLE IF NOT EXISTS section_approvals (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    section TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    reviewer TEXT,
    role TEXT,
    feedback TEXT,
    updated_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    UNIQUE(job_id, section, reviewer)
);

CREATE INDEX IF NOT EXISTS idx_section_approvals_job ON section_approvals(job_id);

CREATE TABLE IF NOT EXISTS market_trends (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL,
    market_share REAL,
    source TEXT,
    period TEXT,
    metadata TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE IF NOT EXISTS export_history (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    format TEXT NOT NULL,
    file_path TEXT,
    file_size INTEGER DEFAULT 0,
    file_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'complete',
    metadata TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_export_history_job ON export_history(job_id);
CREATE INDEX IF NOT EXISTS idx_export_history_user ON export_history(user_id);

CREATE INDEX IF NOT EXISTS idx_market_trends_category ON market_trends(category);
CREATE INDEX IF NOT EXISTS idx_market_trends_period ON market_trends(period);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    total_games INTEGER DEFAULT 0,
    total_revenue_projected REAL DEFAULT 0,
    theme_distribution TEXT,
    volatility_distribution TEXT,
    jurisdiction_coverage TEXT,
    mechanic_coverage TEXT,
    rtp_stats TEXT,
    gap_analysis TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user ON portfolio_snapshots(user_id);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id TEXT PRIMARY KEY,
    admin_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_admin ON admin_audit_log(admin_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON admin_audit_log(target_type, target_id);

CREATE TABLE IF NOT EXISTS cost_events (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    image_count INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    metadata TEXT,
    created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX IF NOT EXISTS idx_cost_events_user ON cost_events(user_id);
CREATE INDEX IF NOT EXISTS idx_cost_events_job ON cost_events(job_id);
CREATE INDEX IF NOT EXISTS idx_cost_events_date ON cost_events(created_at);

CREATE TABLE IF NOT EXISTS cost_rates (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_cost_per_1k REAL DEFAULT 0,
    output_cost_per_1k REAL DEFAULT 0,
    image_cost REAL DEFAULT 0,
    effective_from TEXT,
    effective_to TEXT,
    UNIQUE(provider, model, effective_from)
);
"""


def init_db():
    """Initialize the database schema."""
    db = _make_connection()
    try:
        db.executescript(SCHEMA_SQL)
        db.commit()
        mode = "PostgreSQL" if (USE_POSTGRES and HAS_PSYCOPG) else "SQLite"
        logger.info(f"Database initialized ({mode})")
    finally:
        db.close()


def migrate_db():
    """Run migrations — add columns that may be missing from older schemas."""
    db = _make_connection()
    try:
        if USE_POSTGRES and HAS_PSYCOPG:
            # PostgreSQL: use information_schema to check columns
            _pg_migrate(db)
        else:
            _sqlite_migrate(db)
        db.commit()
    except Exception as e:
        logger.warning(f"DB migration check: {e}")
    finally:
        db.close()


def _sqlite_migrate(db):
    """SQLite-specific migration using PRAGMA table_info."""
    # Jobs table
    db.execute("PRAGMA table_info(jobs)")
    cols = [r["name"] for r in db.fetchall()]
    if "parent_job_id" not in cols:
        db.execute("ALTER TABLE jobs ADD COLUMN parent_job_id TEXT")
    if "version" not in cols:
        db.execute("ALTER TABLE jobs ADD COLUMN version INTEGER DEFAULT 1")

    # Users table — admin columns (Phase A1)
    db.execute("PRAGMA table_info(users)")
    user_cols = [r["name"] for r in db.fetchall()]
    for col, default in [
        ("email_notify", "INTEGER DEFAULT 1"),
        ("role", "TEXT DEFAULT 'user'"),
        ("plan", "TEXT DEFAULT 'free'"),
        ("plan_started_at", "TEXT"),
        ("plan_expires_at", "TEXT"),
        ("monthly_job_limit", "INTEGER DEFAULT 10"),
        ("monthly_jobs_used", "INTEGER DEFAULT 0"),
        ("is_suspended", "INTEGER DEFAULT 0"),
        ("suspension_reason", "TEXT"),
        ("last_active_at", "TEXT"),
        ("metadata", "TEXT"),
    ]:
        if col not in user_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {default}")


def _pg_migrate(db):
    """PostgreSQL-specific migration using information_schema."""
    def _col_exists(table, column):
        db.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
            [table, column]
        )
        return db.fetchone() is not None

    if not _col_exists("jobs", "parent_job_id"):
        db.execute("ALTER TABLE jobs ADD COLUMN parent_job_id TEXT")
    if not _col_exists("jobs", "version"):
        db.execute("ALTER TABLE jobs ADD COLUMN version INTEGER DEFAULT 1")

    # Users table — admin columns (Phase A1)
    for col, default in [
        ("email_notify", "INTEGER DEFAULT 1"),
        ("role", "TEXT DEFAULT 'user'"),
        ("plan", "TEXT DEFAULT 'free'"),
        ("plan_started_at", "TEXT"),
        ("plan_expires_at", "TEXT"),
        ("monthly_job_limit", "INTEGER DEFAULT 10"),
        ("monthly_jobs_used", "INTEGER DEFAULT 0"),
        ("is_suspended", "INTEGER DEFAULT 0"),
        ("suspension_reason", "TEXT"),
        ("last_active_at", "TEXT"),
        ("metadata", "TEXT"),
    ]:
        if not _col_exists("users", col):
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {default}")


def recover_stale_jobs():
    """On startup, mark jobs stuck in running/queued from a crashed process."""
    db = _make_connection()
    try:
        if USE_POSTGRES and HAS_PSYCOPG:
            db.execute(
                "UPDATE jobs SET status='failed', error='Timed out — exceeded maximum pipeline duration' "
                "WHERE status IN ('running','queued') "
                "AND created_at < (CURRENT_TIMESTAMP - INTERVAL '100 minutes')"
            )
        else:
            db.execute(
                "UPDATE jobs SET status='failed', error='Timed out — exceeded maximum pipeline duration' "
                "WHERE status IN ('running','queued') "
                "AND created_at < datetime('now', '-100 minutes')"
            )
        db.commit()
    except Exception as e:
        logger.warning(f"Stale job recovery: {e}")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# Worker-specific helpers (used by worker.py outside Flask)
# ═══════════════════════════════════════════════════════════════

_ALLOWED_JOB_COLUMNS = frozenset({
    "status", "current_stage", "output_dir", "error", "completed_at",
    "params", "parent_job_id", "version",
})


def worker_update_job(job_id: str, **kw):
    """Update a job from the worker process (outside Flask context).
    Uses a standalone connection that's immediately closed."""
    bad = set(kw.keys()) - _ALLOWED_JOB_COLUMNS
    if bad:
        raise ValueError(f"Disallowed column(s): {bad}")

    db = _make_connection()
    try:
        sets = ", ".join(f"{k} = %s" for k in kw)
        db.execute(f"UPDATE jobs SET {sets} WHERE id = %s", list(kw.values()) + [job_id])
        db.commit()
    finally:
        db.close()


def worker_query(sql, params=None, one=False):
    """Execute a query from the worker process (outside Flask context)."""
    db = _make_connection()
    try:
        db.execute(sql, params)
        return db.fetchone() if one else db.fetchall()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# Queue System — Redis (production) or subprocess (fallback)
# ═══════════════════════════════════════════════════════════════

REDIS_URL = os.getenv("REDIS_URL", "")
USE_REDIS = bool(REDIS_URL)

_redis_conn = None
_rq_queue = None


def get_redis():
    """Get or create Redis connection."""
    global _redis_conn
    if _redis_conn is None and USE_REDIS:
        try:
            import redis
            _redis_conn = redis.from_url(REDIS_URL, decode_responses=True)
            _redis_conn.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e} — falling back to subprocess")
            _redis_conn = None
    return _redis_conn


def get_job_queue():
    """Get or create the RQ job queue."""
    global _rq_queue
    if _rq_queue is None and USE_REDIS:
        try:
            import redis as _redis_mod
            from rq import Queue
            r = _redis_mod.from_url(REDIS_URL)
            _rq_queue = Queue("arkainbrain", connection=r, default_timeout=5400)
            logger.info("RQ job queue initialized")
        except Exception as e:
            logger.warning(f"RQ unavailable: {e} — falling back to subprocess")
            _rq_queue = None
    return _rq_queue


def enqueue_job(job_type: str, job_id: str, *args):
    """Enqueue a job — uses Redis/RQ if available, subprocess fallback otherwise.

    Returns True if enqueued via Redis, False if spawned as subprocess.
    """
    queue = get_job_queue()
    if queue is not None:
        try:
            if job_type == "pipeline":
                queue.enqueue("worker.run_pipeline", job_id, *args, job_timeout=5400)
            elif job_type == "recon":
                queue.enqueue("worker.run_recon_job", job_id, *args, job_timeout=3600)
            elif job_type == "iterate":
                queue.enqueue("worker.run_iterate", job_id, *args, job_timeout=5400)
            else:
                logger.error(f"Unknown job type: {job_type}")
                return False
            logger.info(f"Job {job_id} enqueued via Redis ({job_type})")
            return True
        except Exception as e:
            logger.warning(f"Redis enqueue failed: {e} — falling back to subprocess")

    # Subprocess fallback
    _spawn_subprocess(job_type, job_id, *args)
    return False


def _spawn_subprocess(job_type: str, job_id: str, *args):
    """Spawn a worker subprocess (fallback when Redis is unavailable)."""
    import subprocess
    worker_path = Path(__file__).parent.parent / "worker.py"
    cmd = ["python3", "-u", str(worker_path), job_type, job_id] + [str(a) for a in args]
    env = {
        **os.environ,
        "DB_PATH": SQLITE_PATH,
        "LOG_DIR": str(Path(os.getenv("LOG_DIR", "./logs"))),
        "CREWAI_TELEMETRY_OPT_OUT": "true",
        "OTEL_SDK_DISABLED": "true",
        "CREWAI_TRACING_ENABLED": "false",
        "DO_NOT_TRACK": "1",
        "OPENAI_MAX_RETRIES": "5",
        "OPENAI_TIMEOUT": "120",
    }
    if DATABASE_URL:
        env["DATABASE_URL"] = DATABASE_URL
    if REDIS_URL:
        env["REDIS_URL"] = REDIS_URL

    proc = subprocess.Popen(
        cmd, env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(worker_path.parent),
        start_new_session=True,
    )
    logger.info(f"Job {job_id} spawned as subprocess PID {proc.pid} ({job_type})")
    return proc
