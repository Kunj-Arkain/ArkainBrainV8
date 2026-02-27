"""
ARKAINBRAIN — AI-Powered Gaming Intelligence Platform
by ArkainGames.com
"""
import html, json, logging, os, secrets, sqlite3, subprocess, time, uuid, zipfile, io
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

# ── Structured logging (replaces print statements) ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("arkainbrain")

os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_TRACING_ENABLED"] = "false"  # Disable tracing prompt
os.environ["DO_NOT_TRACK"] = "1"
os.environ["CREWAI_STORAGE_DIR"] = "/tmp/crewai_storage"

# ── Pre-create CrewAI config to prevent interactive tracing prompt ──
for _d in [Path.home() / ".crewai", Path("/tmp/crewai_storage")]:
    _d.mkdir(parents=True, exist_ok=True)
    _cfg = _d / "config.json"
    if not _cfg.exists():
        _cfg.write_text(json.dumps({"tracing_enabled": False, "tracing_disabled": True}))

from flask import Flask, redirect, url_for, session, request, jsonify, send_from_directory, Response, g, has_app_context
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Trust Railway's reverse proxy

# XSS protection — escape user-supplied content before rendering in HTML
_esc = html.escape

# sqlite3.Row does not support .get() — use this helper everywhere
def _rget(row, key, default=None):
    """Safe .get() for sqlite3.Row objects."""
    try:
        val = row[key]
        return val if val is not None else default
    except (IndexError, KeyError):
        return default

# ── Stable SECRET_KEY — survives process restarts, gunicorn recycling, deploys ──
# Priority: env var → persisted file → generate-and-save
# Without this, every gunicorn --max-requests restart invalidates ALL sessions.
def _get_or_create_secret_key():
    # 1. Explicit env var — always wins
    env_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
    if env_key:
        return env_key
    # 2. Persisted to file — survives process restarts within same container
    key_file = Path(os.getenv("DB_PATH", "arkainbrain.db")).parent / ".flask_secret_key"
    try:
        if key_file.exists():
            stored = key_file.read_text().strip()
            if len(stored) >= 32:
                return stored
    except Exception:
        pass
    # 3. Generate once and save
    new_key = secrets.token_hex(32)
    try:
        key_file.write_text(new_key)
    except Exception:
        pass  # In-memory only if filesystem is truly read-only
    return new_key

app.secret_key = _get_or_create_secret_key()
if not (os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")):
    logger.warning("FLASK_SECRET_KEY not set — sessions may not survive Railway redeploys. "
                    "Set it in Railway env vars for permanent session persistence.")

# ── Session configuration — persist across browser restarts + devices ──
app.config["PREFERRED_URL_SCHEME"] = "https"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB — reject oversized uploads/posts
# Only set Secure=True in production (HTTPS)
if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER") or os.getenv("FLY_APP_NAME"):
    app.config["SESSION_COOKIE_SECURE"] = True

LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", "arkainbrain.db")

# ── Database layer (Phase 5A: PostgreSQL + SQLite dual-mode) ──
from config.database import (
    get_db, init_db, migrate_db, recover_stale_jobs, close_db_on_teardown,
    query_db, execute_db, enqueue_job, USE_POSTGRES, USE_REDIS,
)

def _open_db():
    """Legacy compat — returns a DatabaseConnection from the new layer."""
    from config.database import get_standalone_db
    return get_standalone_db()

@app.teardown_appcontext
def _close_db(exc):
    """Auto-close the per-request DB connection."""
    close_db_on_teardown(exc)

init_db()
migrate_db()
recover_stale_jobs()

# ── Admin Blueprint (Phase A1/A2/A3) ──
from admin import admin_bp
app.register_blueprint(admin_bp)
logger.info("Admin blueprint registered at /admin")

# ── Concurrent job limit — Tier 3 GPT access allows higher parallelism ──
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "6"))

def _check_job_limit(user_id):
    """Return error response if user has too many running jobs, else None."""
    db = get_db()
    db.execute(
        "SELECT COUNT(*) as c FROM jobs WHERE user_id=%s AND status IN ('queued','running')",
        [user_id],
    )
    row = db.fetchone()
    running = row["c"] if row else 0
    if running >= MAX_CONCURRENT_JOBS:
        return f"You have {running} jobs in progress (max {MAX_CONCURRENT_JOBS}). Please wait for one to finish.", 429
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session: return redirect(url_for("login_page"))
        # Check suspension
        try:
            db = get_db()
            u = db.execute("SELECT is_suspended, suspension_reason FROM users WHERE id=?", (session["user"].get("id",""),)).fetchone()
            if u and u.get("is_suspended"):
                reason = u.get("suspension_reason", "Contact support for details.")
                return f"<div style='max-width:500px;margin:100px auto;padding:40px;background:#1a1b25;border:1px solid #ef4444;border-radius:12px;text-align:center;font-family:Inter,sans-serif;color:#e2e8f0'><h2 style='color:#ef4444'>Account Suspended</h2><p style='color:#94a3b8;margin-top:8px'>{_esc(reason)}</p><a href='/logout' style='display:inline-block;margin-top:16px;padding:8px 20px;background:#7c6aef;color:#fff;border-radius:6px;text-decoration:none'>Sign Out</a></div>", 403
            # Update last_active
            db.execute("UPDATE users SET last_active_at=? WHERE id=?", (datetime.now().isoformat(), session["user"].get("id","")))
            db.commit()
        except Exception:
            pass
        return f(*args, **kwargs)
    return decorated

@app.before_request
def _refresh_session():
    """Keep sessions alive for 30 days from last activity.
    This runs on every request and resets the 30-day expiry timer."""
    session.permanent = True

@app.before_request
def _csrf_origin_check():
    """Reject cross-origin POST/PUT/DELETE requests (poor-man's CSRF protection).
    Combined with SameSite=Lax cookies, this blocks most CSRF vectors."""
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("Origin") or request.headers.get("Referer", "")
        if origin:
            from urllib.parse import urlparse
            allowed = request.host_url.rstrip("/")
            incoming = f"{urlparse(origin).scheme}://{urlparse(origin).netloc}"
            if incoming and incoming != allowed:
                return "Cross-origin request blocked", 403

def current_user(): return session.get("user", {})

BRAND_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Geist+Mono:wght@400;500&display=swap');
:root{
  --bg-void:#000000;--bg-surface:#0a0a0a;--bg-card:#111111;--bg-card-hover:#1a1a1a;--bg-input:#0a0a0a;
  --border:rgba(255,255,255,0.06);--border-hover:rgba(255,255,255,0.12);--border-focus:rgba(255,255,255,0.20);
  --text:#d4d4d4;--text-bright:#ffffff;--text-muted:#888888;--text-dim:#555555;
  --accent:#ffffff;--accent-soft:rgba(255,255,255,0.06);--accent-mid:rgba(255,255,255,0.10);--accent-bright:#ffffff;
  --success:#22c55e;--success-soft:rgba(34,197,94,0.08);--warning:#eab308;--warning-soft:rgba(234,179,8,0.08);--danger:#ef4444;--danger-soft:rgba(239,68,68,0.08);
  --radius:10px;--radius-lg:14px;--radius-xl:20px;
  --transition:all 0.15s ease;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg-void);color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased;font-size:14px;line-height:1.6}
::selection{background:rgba(255,255,255,0.15);color:#fff}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:10px}::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.14)}
a{color:var(--text-bright);text-decoration:none;transition:var(--transition)}a:hover{color:var(--text-muted)}

/* ── Layout Shell ── */
.topbar{position:sticky;top:0;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 24px;height:52px;background:rgba(0,0,0,0.9);border-bottom:1px solid var(--border);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
.logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:14px;letter-spacing:-0.03em;color:var(--text-bright);text-decoration:none}
.logo-mark{width:28px;height:28px;border-radius:8px;background:#fff;display:grid;place-items:center;font-size:13px;font-weight:800;color:#000}
.version-tag{font-size:10px;font-weight:500;color:var(--text-dim);font-family:'Geist Mono',monospace}
.user-pill{display:flex;align-items:center;gap:8px;padding:5px 14px 5px 5px;border-radius:24px;border:1px solid var(--border);font-size:12px;color:var(--text-muted);text-decoration:none;transition:var(--transition)}
.user-pill img{width:24px;height:24px;border-radius:50%}
.user-pill:hover{border-color:var(--border-hover);color:var(--text-bright)}

.shell{display:grid;grid-template-columns:220px 1fr;min-height:calc(100vh - 52px)}
.sidebar{padding:12px 0;border-right:1px solid var(--border);background:var(--bg-void);display:flex;flex-direction:column;gap:1px}
.sidebar a{display:flex;align-items:center;gap:10px;padding:9px 20px;font-size:13px;font-weight:400;color:var(--text-muted);text-decoration:none;transition:var(--transition);margin:0 8px;border-radius:8px}
.sidebar a:hover{color:var(--text-bright);background:var(--accent-soft)}
.sidebar a.active{color:var(--text-bright);background:var(--accent-soft);font-weight:500}
.sidebar a svg{width:16px;height:16px;opacity:0.4;flex-shrink:0}
.sidebar a:hover svg{opacity:0.65}.sidebar a.active svg{opacity:0.8}
.sidebar .section-label{font-size:10px;font-weight:500;letter-spacing:1.2px;color:var(--text-dim);padding:20px 20px 8px;text-transform:uppercase}

.main{padding:32px 48px;max-width:780px;width:100%;animation:fadeIn 0.15s ease}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.page-title{font-size:22px;font-weight:700;color:var(--text-bright);margin-bottom:4px;letter-spacing:-0.03em}
.page-subtitle{color:var(--text-muted);font-size:13px;margin-bottom:28px;font-weight:400}

/* ── Cards — nearly invisible borders, float on black ── */
.card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:24px;margin-bottom:14px;transition:var(--transition)}
.card:hover{border-color:var(--border-hover)}
.card h2{font-size:11px;font-weight:500;color:var(--text-muted);margin-bottom:16px;display:flex;align-items:center;gap:8px;letter-spacing:0.6px;text-transform:uppercase}

/* ── Forms ── */
label{display:block;font-size:12px;font-weight:500;color:var(--text-muted);margin-bottom:6px;letter-spacing:0.2px}
input,select,textarea{width:100%;padding:10px 14px;border-radius:var(--radius);border:1px solid var(--border);background:var(--bg-input);color:var(--text-bright);font-family:'Inter',sans-serif;font-size:13px;margin-bottom:16px;outline:none;transition:var(--transition)}
input:focus,select:focus,textarea:focus{border-color:var(--border-focus)}
input::placeholder,textarea::placeholder{color:var(--text-dim)}
textarea{min-height:70px;resize:vertical}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}

/* ── Buttons — flat, no gradients ── */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:9px 20px;border-radius:var(--radius);border:none;font-family:'Inter',sans-serif;font-size:13px;font-weight:500;cursor:pointer;transition:var(--transition);text-decoration:none}
.btn-primary{background:var(--text-bright);color:#000;font-weight:600}
.btn-primary:hover{opacity:0.85;color:#000}
.btn-primary:active{transform:scale(0.98)}
.btn-ghost{background:transparent;color:var(--text);border:1px solid var(--border)}
.btn-ghost:hover{border-color:var(--border-hover);color:var(--text-bright)}
.btn-sm{padding:6px 14px;font-size:12px;border-radius:8px}
.btn-full{width:100%}

/* ── Badges — minimal ── */
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500;letter-spacing:0.1px}
.badge-running{color:var(--text-bright);background:var(--accent-soft)}
.badge-complete{color:var(--success)}
.badge-failed{color:var(--danger)}
.badge-queued{color:var(--warning)}
.badge-running::before{content:'';width:5px;height:5px;border-radius:50%;background:var(--text-bright);animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.15}}

/* ── History / List Items ── */
.history-item{display:grid;grid-template-columns:1fr 120px 140px 100px;align-items:center;padding:13px 20px;border-bottom:1px solid var(--border);font-size:13px;transition:var(--transition)}
.history-item:hover{background:var(--accent-soft)}
.history-title{font-weight:500;color:var(--text-bright)}
.history-type{color:var(--text-muted);font-size:12px;margin-top:2px}
.history-date{color:var(--text-dim);font-size:12px;font-family:'Geist Mono',monospace}
.history-actions{display:flex;gap:6px;justify-content:flex-end}

/* ── File Rows ── */
.file-row{display:flex;align-items:center;justify-content:space-between;padding:11px 20px;border-bottom:1px solid var(--border);font-size:13px;transition:var(--transition)}
.file-row:hover{background:var(--accent-soft)}
.file-row a{color:var(--text-bright);text-decoration:none;font-family:'Geist Mono',monospace;font-size:12px}
.file-row a:hover{color:var(--text-muted)}
.file-size{color:var(--text-dim);font-size:11px;font-family:'Geist Mono',monospace}

/* ── Stat Cards ── */
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-bottom:24px}
.stat-card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;text-align:center;transition:var(--transition)}
.stat-card:hover{border-color:var(--border-hover)}
.stat-card .stat-icon{font-size:18px;margin-bottom:6px}
.stat-card .stat-val{font-size:16px;font-weight:600;color:var(--text-bright)}
.stat-card .stat-label{font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.6px;margin-top:4px;font-weight:500}
.stat-card.online .stat-val{color:var(--success)}
.stat-card.offline{opacity:0.35}

/* ── Feature Grid ── */
.feature-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px}
.feature-grid label{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:400;color:var(--text);text-transform:none;margin-bottom:0;cursor:pointer;padding:8px 10px;border-radius:8px;transition:var(--transition);border:1px solid transparent}
.feature-grid label:hover{background:var(--accent-soft);border-color:var(--border)}
.feature-grid label input{width:auto;margin:0;accent-color:#fff}
.feature-grid .feat-tag{font-size:9px;padding:2px 6px;border-radius:5px;font-weight:600;margin-left:auto;letter-spacing:0.2px}
.feat-tag.ip-risk{background:var(--danger-soft);color:var(--danger)}
.feat-tag.safe{background:var(--success-soft);color:var(--success)}
.feat-tag.banned{background:var(--warning-soft);color:var(--warning)}

/* ── Toggle / Options ── */
.toggle-section{padding:14px 18px;background:var(--bg-surface);border-radius:var(--radius);margin-top:12px;display:flex;flex-wrap:wrap;gap:18px;border:1px solid var(--border)}
.toggle-item{display:flex;align-items:center;gap:8px}
.toggle-item input{width:auto;margin:0;accent-color:#fff}
.toggle-item label{margin:0;font-size:12px;text-transform:none;color:var(--text-bright);font-weight:500}
.toggle-item .toggle-desc{font-size:11px;color:var(--text-dim)}

/* ── Login ── */
.login-wrap{min-height:100vh;display:grid;place-items:center;background:var(--bg-void)}
.login-box{text-align:center;padding:48px;width:380px;position:relative;z-index:1}
.login-box h1{font-size:24px;font-weight:700;letter-spacing:-0.03em;color:var(--text-bright);margin:24px 0 10px}
.login-box p{color:var(--text-dim);font-size:13px;margin-bottom:40px;line-height:1.7}
.google-btn{display:inline-flex;align-items:center;gap:10px;padding:12px 28px;border-radius:var(--radius);border:1px solid var(--border);background:transparent;color:var(--text-bright);font-family:'Inter',sans-serif;font-size:13px;font-weight:500;cursor:pointer;transition:var(--transition);text-decoration:none}
.google-btn:hover{border-color:var(--border-hover);background:var(--accent-soft)}
.google-btn svg{width:18px;height:18px}

/* ── Special Components ── */
.proto-frame{width:100%;height:600px;border:1px solid var(--border);border-radius:var(--radius);background:#000}
.audio-player{display:flex;align-items:center;gap:12px;padding:10px 20px;border-bottom:1px solid var(--border);font-size:13px}
.audio-player audio{height:32px;flex:1}
.audio-player .audio-name{font-family:'Geist Mono',monospace;font-size:11px;color:var(--text-bright);min-width:140px}

.cert-timeline{display:flex;gap:0;margin:16px 0}
.cert-step{flex:1;text-align:center;padding:12px 8px;position:relative}
.cert-step::after{content:'';position:absolute;top:26px;right:0;width:50%;height:2px;background:var(--border)}
.cert-step::before{content:'';position:absolute;top:26px;left:0;width:50%;height:2px;background:var(--border)}
.cert-step:first-child::before,.cert-step:last-child::after{display:none}
.cert-step .cert-dot{width:8px;height:8px;border-radius:50%;background:var(--text-bright);margin:0 auto 8px;position:relative;z-index:1}
.cert-step .cert-title{font-size:11px;font-weight:500;color:var(--text-bright)}
.cert-step .cert-sub{font-size:10px;color:var(--text-muted)}

.recon-input-group{display:flex;gap:12px;align-items:flex-end}
.recon-input-group input{margin-bottom:0;flex:1}
.recon-input-group .btn{white-space:nowrap;height:42px}
.empty-state{text-align:center;padding:48px 20px;color:var(--text-dim)}
.empty-state h3{font-size:14px;color:var(--text-muted);margin-bottom:6px;font-weight:500}
.empty-state p{font-size:13px}

/* ── Capability Grid ── */
.capability-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.cap-item{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:8px;background:transparent;border:1px solid var(--border);font-size:12px;color:var(--text);transition:var(--transition)}
.cap-item:hover{border-color:var(--border-hover);background:var(--accent-soft)}
.cap-item b{color:var(--text-bright);font-weight:500}
.cap-item .cap-tag{font-size:10px;color:var(--text-dim);margin-left:auto;font-family:'Geist Mono',monospace}

/* ── Action Cards ── */
.action-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:24px}
.action-card{display:flex;align-items:center;gap:14px;padding:16px 20px;border-radius:var(--radius-lg);border:1px solid var(--border);background:transparent;text-decoration:none;transition:var(--transition)}
.action-card:hover{border-color:var(--border-hover);background:var(--accent-soft)}
.action-card .action-icon{font-size:20px;width:40px;height:40px;border-radius:10px;display:grid;place-items:center;background:var(--accent-soft);flex-shrink:0}
.action-card .action-text{font-size:13px;font-weight:600;color:var(--text-bright)}
.action-card .action-desc{font-size:12px;color:var(--text-dim);margin-top:2px}

/* ── Greeting ── */
.greeting{margin-bottom:24px}
.greeting h2{font-size:24px;font-weight:700;letter-spacing:-0.03em;color:var(--text-bright);margin-bottom:4px}
.greeting p{font-size:13px;color:var(--text-muted);font-weight:400}
.greeting .engine-tag{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:16px;border:1px solid var(--border);font-size:11px;color:var(--text-muted);font-weight:400;margin-top:8px}
.greeting .engine-tag::before{content:'';width:4px;height:4px;border-radius:50%;background:var(--success);animation:pulse 2s ease-in-out infinite}

/* ── Pipeline Form Sections ── */
.form-section{position:relative;counter-increment:form-step}
.form-section::before{content:counter(form-step);position:absolute;left:-36px;top:24px;width:24px;height:24px;border-radius:50%;background:var(--accent-soft);border:1px solid var(--border);display:grid;place-items:center;font-size:11px;font-weight:600;color:var(--text-muted);font-family:'Geist Mono',monospace}
.form-steps{counter-reset:form-step;padding-left:36px}

/* ── Log Terminal — Grok thinking style ── */
.log-terminal{background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:0;font-family:'Geist Mono',monospace;font-size:11.5px;line-height:1.8;height:calc(100vh - 200px);overflow-y:auto;white-space:pre-wrap;color:var(--text);position:relative}
.log-terminal .log-header{position:sticky;top:0;display:flex;align-items:center;gap:10px;padding:12px 16px;background:rgba(10,10,10,0.95);border-bottom:1px solid var(--border);backdrop-filter:blur(8px);z-index:10;font-size:12px;color:var(--text-dim)}
.log-terminal .log-body{padding:16px}

/* ── Shimmer Thinking Animation ── */
@keyframes shimmer-text{0%{background-position:-200% center}100%{background-position:200% center}}
.stage-shimmer{background:linear-gradient(90deg,var(--text-dim) 25%,var(--text-bright) 50%,var(--text-dim) 75%);background-size:200% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;animation:shimmer-text 2s linear infinite}

/* ── Progress Timeline ── */
.progress-timeline{display:flex;flex-direction:column;gap:0}
.progress-step{display:flex;align-items:flex-start;gap:12px;padding:8px 0;font-size:12px;color:var(--text-muted)}
.progress-step .step-dot{width:6px;height:6px;border-radius:50%;background:var(--text-dim);margin-top:5px;flex-shrink:0}
.progress-step.active .step-dot{background:var(--text-bright);box-shadow:0 0 6px rgba(255,255,255,0.3);animation:pulse 1.8s ease-in-out infinite}
.progress-step.done .step-dot{background:var(--success)}
.progress-step.done{color:var(--text-dim)}
.progress-step.active{color:var(--text-bright)}
.progress-step .step-time{font-family:'Geist Mono',monospace;color:var(--text-dim);font-size:11px;min-width:42px}

@media(max-width:768px){
  .shell{grid-template-columns:1fr}.sidebar{display:none}.main{padding:20px 16px;max-width:100%}
  .history-item{grid-template-columns:1fr 1fr;gap:8px}.stat-grid{grid-template-columns:repeat(2,1fr)}
  .feature-grid{grid-template-columns:1fr 1fr}.capability-grid{grid-template-columns:1fr}
  .action-grid{grid-template-columns:1fr}.greeting h2{font-size:20px}
  .form-steps{padding-left:0}.form-section::before{display:none}
}
"""

ICON_DASH = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>'
ICON_PLUS = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M12 5v14m7-7H5"/></svg>'
ICON_SEARCH = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>'
ICON_FOLDER = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>'
ICON_CLOCK = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>'
ICON_GLOBE = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 014 9 15 15 0 01-4 9 15 15 0 01-4-9 15 15 0 014-9z"/></svg>'
ICON_DB = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/></svg>'
ICON_REVIEW = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg>'
ICON_SETTINGS = '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>'
GOOGLE_SVG = '<svg viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>'
FAVICON_SVG = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='white'/><text x='16' y='22' text-anchor='middle' fill='black' font-size='18' font-weight='800'>A</text></svg>"

def layout(content, page="dashboard"):
    user = current_user()
    items = [("dashboard","Dashboard",ICON_DASH,"/"),("new","New Pipeline",ICON_PLUS,"/new"),("mini-rmg","Mini RMG","🎮","/mini-rmg"),("recon","State Recon",ICON_GLOBE,"/recon"),("reviews","Reviews",ICON_REVIEW,"/reviews"),("portfolio","Portfolio","📊","/portfolio"),("history","History",ICON_CLOCK,"/history"),("files","All Files",ICON_FOLDER,"/files"),("memory","Memory","🧠","/memory"),("qdrant","Qdrant",ICON_DB,"/qdrant"),("settings","Settings",ICON_SETTINGS,"/settings")]
    if user.get("role") == "admin":
        items.append(("admin","Admin","🔒","/admin"))
    nav = '<div class="section-label">Platform</div>'
    # Impersonation banner
    if session.get("_admin_return"):
        nav = '<div style="background:var(--warning);color:#000;padding:6px 12px;font-size:10px;font-weight:700;text-align:center;margin-bottom:8px;border-radius:6px">👤 Impersonating ' + _esc(user.get("email","")) + ' · <a href="/admin/api/stop-impersonation" style="color:#000;text-decoration:underline">Stop</a></div>' + nav
    for k,l,i,h in items:
        nav += f'<a href="{h}" class="{"active" if page==k else ""}">{i} {l}</a>'
    pic = user.get("picture","") or ""
    name = user.get("name","User")
    initial = _esc(name[0].upper()) if name else "U"
    pic_tag = f'<img src="{_esc(pic)}" alt="" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'grid\'" style="width:20px;height:20px;border-radius:50%"><span style="display:none;width:20px;height:20px;border-radius:50%;background:var(--bg-card-hover);place-items:center;font-size:10px;font-weight:600;color:var(--text-muted)">{initial}</span>' if pic else f'<span style="display:inline-grid;width:20px;height:20px;border-radius:50%;background:var(--bg-card-hover);place-items:center;font-size:10px;font-weight:600;color:var(--text-muted)">{initial}</span>'
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ARKAINBRAIN</title><link rel="icon" href="{FAVICON_SVG}"><style>{BRAND_CSS}</style></head><body>
<div class="topbar"><a href="/" class="logo"><div class="logo-mark">A</div>ARKAINBRAIN <span class="version-tag">v8</span></a><a href="/logout" class="user-pill">{pic_tag}{name} · Sign Out</a></div>
<div class="shell"><nav class="sidebar">{nav}<div class="section-label" style="margin-top:auto;padding-top:40px"><span style="color:var(--text-dim);font-size:10px;letter-spacing:0.5px">ArkainGames.com</span></div></nav><main class="main">{content}</main></div></body></html>'''

# ─── AUTH ───
@app.route("/login")
def login_page():
    return f'''<!DOCTYPE html><html><head><title>ARKAINBRAIN</title><link rel="icon" href="{FAVICON_SVG}"><style>{BRAND_CSS}</style></head><body>
<div class="login-wrap"><div class="login-box"><div class="logo-mark" style="width:44px;height:44px;font-size:20px;margin:0 auto;border-radius:12px">A</div><h1>ARKAINBRAIN</h1><p>AI-powered slot game intelligence.</p><a href="/auth/google" class="google-btn">{GOOGLE_SVG} Continue with Google</a><div style="margin-top:32px;font-size:11px;color:var(--text-dim)">ArkainGames.com · v5</div></div></div></body></html>'''

@app.route("/auth/google")
def google_login():
    return google.authorize_redirect(url_for("google_callback", _external=True))

@app.route("/auth/callback")
def google_callback():
    try:
        token = google.authorize_access_token()
        info = token.get("userinfo") or google.userinfo()
        db = get_db()
        db.execute("INSERT INTO users (id,email,name,picture) VALUES (?,?,?,?) ON CONFLICT(email) DO UPDATE SET name=excluded.name,picture=excluded.picture",
            (str(uuid.uuid4()), info["email"], info.get("name",""), info.get("picture","")))
        db.commit()
        row = db.execute("SELECT * FROM users WHERE email=?", (info["email"],)).fetchone()
        session.permanent = True  # 30-day session — survives browser close
        session["user"] = {"id":row["id"],"email":row["email"],"name":row["name"],"picture":row["picture"],"role":row.get("role","user")}
        # Update last active
        try:
            db.execute("UPDATE users SET last_active_at=? WHERE id=?", (datetime.now().isoformat(), row["id"]))
            db.commit()
        except Exception:
            pass
        logger.info(f"Login: {info['email']} → user_id={row['id']} role={row.get('role','user')}")
        return redirect("/")
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return f"Auth error: {e}", 500

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")

# ─── DASHBOARD ───
@app.route("/")
@login_required
def dashboard():
    user = current_user()
    db = get_db()
    recent = db.execute("SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 8", (user["id"],)).fetchall()
    rows = ""
    running_ids = []
    for job in recent:
        jid = job["id"]
        status = job["status"]
        stage = job["current_stage"] or ""
        bc = {"running":"badge-running","complete":"badge-complete","failed":"badge-failed"}.get(status,"badge-queued")
        tl = "Slot Pipeline" if job["job_type"]=="slot_pipeline" else "State Recon"
        dt = job["created_at"][:16].replace("T"," ") if job["created_at"] else ""
        stage_html = f'<span class="stage-shimmer" style="font-size:11px;margin-left:4px">{stage}</span>' if status == "running" and stage else ""
        act = f'<a href="/job/{jid}/files" class="btn btn-ghost btn-sm">Files</a>' if status=="complete" and job["output_dir"] else (f'<a href="/job/{jid}/logs" class="btn btn-ghost btn-sm" style="border-color:var(--border-hover);color:var(--text-bright)">Watch Live</a>' if status=="running" else "")
        rows += f'<div class="history-item" id="job-{jid}"><div><div class="history-title">{_esc(job["title"])}</div><div class="history-type">{tl}</div></div><div><span class="badge {bc}" id="badge-{jid}">{status}</span>{stage_html}</div><div class="history-date">{dt}</div><div class="history-actions" id="act-{jid}">{act}</div></div>'
        if status in ("running", "queued"):
            running_ids.append(jid)
    if not rows:
        rows = '<div class="empty-state"><h3>No pipelines yet</h3><p>Launch a Slot Pipeline or State Recon to get started.</p></div>'
    fname = user.get("name","").split()[0] if user.get("name") else "Operator"
    # Check for pending reviews
    review_banner = ""
    try:
        from tools.web_hitl import get_pending_reviews
        pending = get_pending_reviews()
        if pending:
            review_banner = f'<a href="/reviews" class="card" style="border-color:var(--border-hover);display:flex;align-items:center;gap:14px;text-decoration:none"><span class="badge badge-running" style="font-size:13px;padding:6px 14px">{len(pending)}</span><div><div style="font-weight:500;color:var(--text-bright);font-size:13px">Pipeline waiting for your review</div><div style="font-size:12px;color:var(--text-muted)">Click to approve, reject, or give feedback</div></div></a>'
    except Exception as e:
        logger.debug(f"Review banner: {e}")

    # API status checks
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_serper = bool(os.getenv("SERPER_API_KEY"))
    has_elevenlabs = bool(os.getenv("ELEVENLABS_API_KEY"))
    has_qdrant = bool(os.getenv("QDRANT_URL"))
    has_resend = bool(os.getenv("RESEND_API_KEY"))

    db_label = 'PostgreSQL' if USE_POSTGRES else 'SQLite'
    q_label = 'Redis Queue' if USE_REDIS else 'Subprocess'
    api_cards = f'''<div class="stat-grid">
        <div class="stat-card {'online' if has_openai else 'offline'}"><div class="stat-icon">🧠</div><div class="stat-val">{'●' if has_openai else '○'}</div><div class="stat-label">GPT-5 Tier 3</div></div>
        <div class="stat-card {'online' if has_serper else 'offline'}"><div class="stat-icon">🔍</div><div class="stat-val">{'●' if has_serper else '○'}</div><div class="stat-label">Serper Search</div></div>
        <div class="stat-card {'online' if has_elevenlabs else 'offline'}"><div class="stat-icon">🔊</div><div class="stat-val">{'●' if has_elevenlabs else '○'}</div><div class="stat-label">ElevenLabs</div></div>
        <div class="stat-card online"><div class="stat-icon">🐘</div><div class="stat-val">●</div><div class="stat-label">{db_label}</div></div>
        <div class="stat-card {'online' if USE_REDIS else 'offline'}"><div class="stat-icon">⚡</div><div class="stat-val">{'●' if USE_REDIS else '○'}</div><div class="stat-label">{q_label}</div></div>
        <div class="stat-card {'online' if has_qdrant else 'offline'}"><div class="stat-icon">🗃️</div><div class="stat-val">{'●' if has_qdrant else '○'}</div><div class="stat-label">Qdrant DB</div></div>
        <div class="stat-card {'online' if has_resend else 'offline'}"><div class="stat-icon">📧</div><div class="stat-val">{'●' if has_resend else '○'}</div><div class="stat-label">Email Alerts</div></div>
    </div>'''

    # Count totals
    db2 = get_db()
    db2.execute("SELECT COUNT(*) as c FROM jobs WHERE user_id=%s", [user["id"]])
    total_jobs = (db2.fetchone() or {"c": 0})["c"]
    db2.execute("SELECT COUNT(*) as c FROM jobs WHERE user_id=%s AND status='complete'", [user["id"]])
    completed_jobs = (db2.fetchone() or {"c": 0})["c"]

    return layout(f'''
    <div class="greeting">
        <h2>Welcome back, {fname}</h2>
        <p>What would you like to build today?</p>
        <div class="engine-tag">GPT-5 Tier 3 · 6 Agents · OODA Convergence</div>
    </div>
    {review_banner}
    {api_cards}
    <div class="action-grid">
        <a href="/new" class="action-card"><div class="action-icon">🎰</div><div><div class="action-text">New Slot Pipeline</div><div class="action-desc">Concept → certified game package</div></div></a>
        <a href="/mini-rmg" class="action-card"><div class="action-icon">🎮</div><div><div class="action-text">Mini RMG Game</div><div class="action-desc">Crash, Plinko, Mines → playable HTML5</div></div></a>
        <a href="/recon" class="action-card"><div class="action-icon">🌐</div><div><div class="action-text">State Recon</div><div class="action-desc">AI legal research for any jurisdiction</div></div></a>
    </div>
    <div class="card"><h2>Capabilities</h2>
        <div class="capability-grid">
            <div class="cap-item">🛰️ <b>Pre-Flight Intel</b> <span class="cap-tag">trend · jurisdiction</span></div>
            <div class="cap-item">🔬 <b>Vision QA</b> <span class="cap-tag">every image</span></div>
            <div class="cap-item">📐 <b>Math Optimizer</b> <span class="cap-tag">RTP ±0.1%</span></div>
            <div class="cap-item">🎭 <b>Agent Debate</b> <span class="cap-tag">OODA loop</span></div>
            <div class="cap-item">👤 <b>Player Behavior</b> <span class="cap-tag">5K sessions</span></div>
            <div class="cap-item">🔒 <b>Patent Scanner</b> <span class="cap-tag">IP check</span></div>
            <div class="cap-item">🎮 <b>HTML5 Prototype</b> <span class="cap-tag">playable</span></div>
            <div class="cap-item" style="{'opacity:0.35' if not has_elevenlabs else ''}">{'🔊' if has_elevenlabs else '🔇'} <b>Sound Design</b> <span class="cap-tag">{'on' if has_elevenlabs else '<a href=/settings style=color:var(--danger)>setup</a>'}</span></div>
            <div class="cap-item">📋 <b>Cert Planner</b> <span class="cap-tag">lab · cost</span></div>
            <div class="cap-item">⚔️ <b>Adversarial QA</b> <span class="cap-tag">devil's advocate</span></div>
            <div class="cap-item">📍 <b>Geo Research</b> <span class="cap-tag">region scoring</span></div>
            <div class="cap-item" style="{'opacity:0.35' if not has_resend else ''}">{'📧' if has_resend else '📭'} <b>Email Alerts</b> <span class="cap-tag">{'on' if has_resend else '<a href=/settings style=color:var(--danger)>setup</a>'}</span></div>
        </div>
    </div>
    <div class="card" style="padding:0;overflow:hidden"><div style="padding:16px 20px 8px"><h2 style="margin-bottom:0">Recent Activity</h2></div>{rows}</div>
    <script>
    // Auto-refresh running jobs every 4 seconds
    const runningIds = {json.dumps(running_ids)};
    if (runningIds.length > 0) {{
        const poll = setInterval(() => {{
            let remaining = 0;
            runningIds.forEach(jid => {{
                fetch('/api/status/' + jid).then(r => r.json()).then(d => {{
                    const badge = document.getElementById('badge-' + jid);
                    if (!badge) return;
                    if (d.status !== badge.textContent) {{
                        badge.textContent = d.status;
                        badge.className = 'badge badge-' + (d.status === 'complete' ? 'complete' : d.status === 'failed' ? 'failed' : d.status === 'running' ? 'running' : 'queued');
                        if (d.status === 'complete' || d.status === 'failed') {{
                            setTimeout(() => location.reload(), 1000);
                        }}
                    }}
                    if (d.status === 'running' || d.status === 'queued') remaining++;
                }}).catch(() => {{}});
            }});
            if (remaining === 0) clearInterval(poll);
        }}, 4000);
    }}
    </script>''', "dashboard")

# ─── NEW PIPELINE ───
@app.route("/new")
@login_required
def new_pipeline():
    has_elevenlabs = bool(os.getenv("ELEVENLABS_API_KEY"))
    el_note = "" if has_elevenlabs else ' <span class="feat-tag ip-risk">No API key</span>'
    return layout(f'''
    <div class="greeting" style="margin-bottom:20px">
        <h2 style="font-size:20px">New Slot Pipeline</h2>
        <p>Describe your concept. Six agents research, design, model, illustrate, and certify it.</p>
    </div>
    <form action="/api/pipeline" method="POST">
    <div class="card"><h2>🎰 Game Concept</h2>
    <label>Theme / Concept</label><input name="theme" placeholder="e.g. Ancient Egyptian curse with escalating darkness" required style="font-size:15px;padding:14px 16px">
    <div class="row2"><div><label>Target Jurisdictions</label><input name="target_markets" placeholder="e.g. Georgia, Texas, UK, Malta" value="Georgia, Texas">
    <p style="font-size:10px;color:var(--text-muted);margin-top:-12px;margin-bottom:12px">US states, countries, or regulated markets. Auto-recon for unknown states.</p>
    </div>
    <div><label>Volatility</label><select name="volatility"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option><option value="very_high">Very High</option></select></div></div></div>

    <div class="card"><h2>📐 Math & Grid</h2>
    <div class="row3"><div><label>Target RTP %</label><input type="number" name="target_rtp" value="96.0" step="0.1" min="85" max="99"></div><div><label>Grid Cols</label><input type="number" name="grid_cols" value="5"></div><div><label>Grid Rows</label><input type="number" name="grid_rows" value="3"></div></div>
    <div class="row3"><div><label>Ways / Lines</label><input type="number" name="ways_or_lines" value="243"></div><div><label>Max Win Multiplier</label><input type="number" name="max_win_multiplier" value="5000"></div><div><label>Art Style</label><input name="art_style" value="Cinematic realism"></div></div></div>

    <div class="card"><h2>⚡ Features & Mechanics</h2>
    <div class="feature-grid">
        <label><input type="checkbox" name="features" value="free_spins" checked> Free Spins <span class="feat-tag safe">✓ Safe</span></label>
        <label><input type="checkbox" name="features" value="multipliers" checked> Multipliers <span class="feat-tag safe">✓ Safe</span></label>
        <label><input type="checkbox" name="features" value="expanding_wilds"> Expanding Wilds <span class="feat-tag safe">✓ Safe</span></label>
        <label><input type="checkbox" name="features" value="cascading_reels"> Cascading Reels <span class="feat-tag safe">Low IP</span></label>
        <label><input type="checkbox" name="features" value="mystery_symbols"> Mystery Symbols <span class="feat-tag safe">✓ Safe</span></label>
        <label><input type="checkbox" name="features" value="walking_wilds"> Walking Wilds <span class="feat-tag safe">Low IP</span></label>
        <label><input type="checkbox" name="features" value="cluster_pays"> Cluster Pays <span class="feat-tag safe">Low IP</span></label>
        <label><input type="checkbox" name="features" value="hold_and_spin"> Hold & Spin <span class="feat-tag ip-risk">Med IP</span></label>
        <label><input type="checkbox" name="features" value="bonus_buy"> Bonus Buy <span class="feat-tag banned">UK/SE ban</span></label>
        <label><input type="checkbox" name="features" value="progressive_jackpot"> Progressive Jackpot <span class="feat-tag ip-risk">+cost</span></label>
        <label><input type="checkbox" name="features" value="megaways"> Megaways™ <span class="feat-tag ip-risk">License req</span></label>
        <label><input type="checkbox" name="features" value="split_symbols"> Split Symbols <span class="feat-tag safe">Low IP</span></label>
    </div>
    <p style="font-size:10px;color:var(--text-muted);margin-top:12px">IP risk tags are pre-flight estimates. Patent Scanner verifies during execution.</p>
    <div style="margin-top:16px"><label>Competitor References</label><input name="competitor_references" placeholder="e.g. Book of Dead, Legacy of Dead, Sweet Bonanza">
    <label>Special Requirements</label><textarea name="special_requirements" placeholder="e.g. Must support mobile portrait mode, needs 5+ free spin retriggers, dark moody atmosphere..."></textarea></div></div>

    <div class="card"><h2>🤖 Pipeline Intelligence</h2>
    <div class="toggle-section">
        <div class="toggle-item"><input type="checkbox" name="enable_recon" value="on" checked id="recon"><label for="recon">🌐 Auto State Recon</label><span class="toggle-desc">Research unknown state laws</span></div>
        <div class="toggle-item"><input type="checkbox" name="enable_prototype" value="on" checked id="proto"><label for="proto">🎮 HTML5 Prototype</label><span class="toggle-desc">Playable demo</span></div>
        <div class="toggle-item"><input type="checkbox" name="enable_sound" value="on" {'checked' if has_elevenlabs else ''} id="snd"><label for="snd">🔊 Sound Design{el_note}</label><span class="toggle-desc">ElevenLabs SFX</span></div>
        <div class="toggle-item"><input type="checkbox" name="enable_cert_plan" value="on" checked id="cert"><label for="cert">📋 Cert Planning</label><span class="toggle-desc">Lab + timeline + cost</span></div>
        <div class="toggle-item"><input type="checkbox" name="enable_patent_scan" value="on" checked id="pat"><label for="pat">🔒 Patent/IP Scan</label><span class="toggle-desc">Mechanic conflicts</span></div>
    </div></div>

    <div class="card"><h2>⚙️ Execution Mode</h2>
    <div style="display:flex;gap:24px;align-items:center;margin-bottom:16px">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0"><input type="radio" name="exec_mode" value="auto" checked style="width:auto;margin:0;accent-color:#fff" onchange="document.getElementById('variantOpts').style.display='none'"> <span style="text-transform:none;font-size:13px;color:var(--text-bright);font-weight:500">Auto</span><span style="font-size:11px;color:var(--text-dim);margin-left:4px">fully autonomous</span></label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0"><input type="radio" name="exec_mode" value="interactive" style="width:auto;margin:0;accent-color:#fff" onchange="document.getElementById('variantOpts').style.display='none'"> <span style="text-transform:none;font-size:13px;color:var(--text-bright);font-weight:500">Interactive</span><span style="font-size:11px;color:var(--text-dim);margin-left:4px">review at each stage</span></label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0"><input type="radio" name="exec_mode" value="variants" style="width:auto;margin:0;accent-color:#fff" onchange="document.getElementById('variantOpts').style.display='flex'"> <span style="text-transform:none;font-size:13px;color:var(--text-bright);font-weight:500">A/B Variants</span><span style="font-size:11px;color:var(--text-dim);margin-left:4px">2-5 parallel versions</span></label>
    </div>
    <div id="variantOpts" style="display:none;align-items:center;gap:12px;padding:12px;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:8px">
        <label style="font-size:12px;color:var(--text-muted);margin:0">Variants:</label>
        <select name="variant_count" style="width:60px;font-size:13px;padding:4px 8px;background:var(--bg-card);color:var(--text);border:1px solid var(--border);border-radius:6px">
            <option value="2">2</option><option value="3" selected>3</option><option value="4">4</option><option value="5">5</option></select>
        <span style="font-size:11px;color:var(--text-dim)">Conservative / Aggressive / Hybrid / Premium / Jackpot</span>
    </div></div>
    <button type="submit" id="launchBtn" class="btn btn-primary btn-full" style="padding:14px;font-size:14px;border-radius:var(--radius-lg)">Launch Pipeline &rarr;</button>
    <script>document.getElementById('launchBtn').addEventListener('click',function(e){{var m=document.querySelector('input[name=exec_mode]:checked').value;if(m==='variants'){{this.form.action='/api/variants'}}else{{if(m==='interactive'){{var h=document.createElement('input');h.type='hidden';h.name='interactive';h.value='on';this.form.appendChild(h)}}this.form.action='/api/pipeline'}}}});</script>
    </form>''', "new")

# ─── MINI RMG GAME (Phase 7) ───

GAME_TYPE_INFO = {
    "crash": {"icon": "🚀", "name": "Crash", "desc": "Exponential curve — cash out before it crashes", "he": "1–5%"},
    "plinko": {"icon": "⚪", "name": "Plinko", "desc": "Drop a ball through pegs into multiplier slots", "he": "1–4%"},
    "mines": {"icon": "💣", "name": "Mines", "desc": "Reveal gems, avoid mines — cash out anytime", "he": "1–5%"},
    "dice": {"icon": "🎲", "name": "Dice", "desc": "Roll over/under a target number", "he": "1% fixed"},
    "wheel": {"icon": "🎡", "name": "Wheel Spin", "desc": "Spin the wheel for multiplier prizes", "he": "2–8%"},
    "hilo": {"icon": "🃏", "name": "Hi-Lo", "desc": "Guess higher or lower — build a streak", "he": "2–4%"},
    "chicken": {"icon": "🐔", "name": "Chicken Cross", "desc": "Cross lanes avoiding hazards — cash out anytime", "he": "2–5%"},
    "scratch": {"icon": "🎫", "name": "Scratch Card", "desc": "Scratch to reveal prize multipliers", "he": "5–40%"},
}


@app.route("/mini-rmg")
@login_required
def mini_rmg_page():
    """Mini RMG game creation form."""
    game_cards = ""
    for gt, info in GAME_TYPE_INFO.items():
        game_cards += (
            f'<label class="game-type-card" style="display:flex;gap:10px;padding:12px;border-radius:8px;'
            f'border:2px solid var(--border);cursor:pointer;transition:all .15s;background:var(--bg-card)">'
            f'<input type="radio" name="game_type" value="{gt}" {"checked" if gt=="crash" else ""} '
            f'style="display:none" onchange="this.closest(\'.game-type-card\').parentNode.querySelectorAll(\'.game-type-card\').forEach(c=>c.style.borderColor=\'var(--border)\');this.closest(\'.game-type-card\').style.borderColor=\'var(--accent)\'">'
            f'<span style="font-size:28px">{info["icon"]}</span>'
            f'<div style="flex:1"><div style="font-weight:600;font-size:13px">{info["name"]}</div>'
            f'<div style="font-size:11px;color:var(--text-dim)">{info["desc"]}</div>'
            f'<div style="font-size:10px;color:var(--accent);margin-top:2px">House Edge: {info["he"]}</div></div>'
            f'</label>'
        )

    return layout(f'''
    <h2 class="page-title">🎮 Mini RMG Game</h2>
    <p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">
        Create a provably fair mini-game with playable HTML5 output, math certification, and optional Web3 contracts.
    </p>
    <form method="POST" action="/api/mini-rmg" class="card" style="padding:20px;display:flex;flex-direction:column;gap:16px">

        <div>
            <label class="input-label" style="display:block;font-size:12px;font-weight:600;margin-bottom:8px">Game Type</label>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px">
                {game_cards}
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div>
                <label class="input-label" style="display:block;font-size:12px;font-weight:600;margin-bottom:4px">Game Theme / Name</label>
                <input name="theme" type="text" value="Rocket Launch" required
                    style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg-input);color:var(--text);font-size:13px">
            </div>
            <div>
                <label class="input-label" style="display:block;font-size:12px;font-weight:600;margin-bottom:4px">House Edge %</label>
                <input name="house_edge" type="number" value="3" min="0.5" max="40" step="0.1"
                    style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg-input);color:var(--text);font-size:13px">
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div>
                <label class="input-label" style="display:block;font-size:12px;font-weight:600;margin-bottom:4px">Max Multiplier</label>
                <input name="max_multiplier" type="number" value="1000" min="10" max="100000"
                    style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg-input);color:var(--text);font-size:13px">
            </div>
            <div>
                <label class="input-label" style="display:block;font-size:12px;font-weight:600;margin-bottom:4px">Options</label>
                <label style="display:flex;align-items:center;gap:8px;padding:10px 0;font-size:13px;cursor:pointer">
                    <input type="checkbox" name="web3_mode"> 🔗 Generate Web3 smart contracts (Solidity + Chainlink VRF)
                </label>
            </div>
        </div>

        <button type="submit" class="play-btn" style="padding:14px;border-radius:10px;border:none;
            background:linear-gradient(135deg,var(--accent),#22c55e);color:#fff;font-size:15px;font-weight:700;cursor:pointer">
            🎮 Generate Mini RMG Game
        </button>
    </form>''', "mini-rmg")


@app.route("/api/mini-rmg", methods=["POST"])
@login_required
def api_launch_mini_rmg():
    """Launch a Mini RMG pipeline job."""
    user = current_user()
    limit_err = _check_job_limit(user["id"])
    if limit_err:
        return limit_err
    job_id = str(uuid.uuid4())[:8]
    game_type = request.form.get("game_type", "crash")
    theme = request.form.get("theme", "Mini Game").strip()
    house_edge = float(request.form.get("house_edge", 3)) / 100.0
    max_mult = float(request.form.get("max_multiplier", 1000))
    web3 = request.form.get("web3_mode") == "on"

    params = {
        "game_type": game_type,
        "theme": theme,
        "house_edge": house_edge,
        "max_multiplier": max_mult,
        "web3_mode": web3,
    }

    db = get_db()
    db.execute(
        "INSERT INTO jobs (id,user_id,job_type,title,params,status) VALUES (?,?,?,?,?,?)",
        (job_id, user["id"], "mini_rmg", f"🎮 {theme} ({game_type})", json.dumps(params), "queued")
    )
    db.commit()
    enqueue_job("mini_rmg", job_id, json.dumps(params))
    return redirect(f"/job/{job_id}/logs")


# ─── STATE RECON ───
@app.route("/recon")
@login_required
def recon_page():
    return layout(f'''
    <h2 class="page-title">{ICON_GLOBE} State Recon</h2>
    <p class="page-subtitle">Point at any US state. AI agents research laws, find loopholes, design compliant games.</p>
    <div class="card"><h2>{ICON_SEARCH} Research a State</h2><form action="/api/recon" method="POST"><label>US State Name</label><div class="recon-input-group"><input name="state" placeholder="e.g. North Carolina" required><button type="submit" class="btn btn-primary">Launch Recon</button></div></form></div>
    <div class="card"><h2>Pipeline Stages</h2><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;text-align:center;padding:12px 0">
    <div><div style="font-size:22px;margin-bottom:6px">&#128269;</div><div style="font-size:12px;font-weight:600;color:var(--text-bright)">Legal Research</div><div style="font-size:11px;color:var(--text-dim)">Statutes, case law, AG opinions</div></div>
    <div><div style="font-size:22px;margin-bottom:6px">&#9878;&#65039;</div><div style="font-size:12px;font-weight:600;color:var(--text-bright)">Definition Analysis</div><div style="font-size:11px;color:var(--text-dim)">Element mapping, loophole ID</div></div>
    <div><div style="font-size:22px;margin-bottom:6px">&#127918;</div><div style="font-size:12px;font-weight:600;color:var(--text-bright)">Game Architecture</div><div style="font-size:11px;color:var(--text-dim)">Compliant mechanics design</div></div>
    <div><div style="font-size:22px;margin-bottom:6px">&#128203;</div><div style="font-size:12px;font-weight:600;color:var(--text-bright)">Defense Brief</div><div style="font-size:11px;color:var(--text-dim)">Courtroom-ready mapping</div></div></div></div>''', "recon")

# ─── HISTORY ───
@app.route("/history")
@login_required
def history_page():
    user = current_user()
    db = get_db()
    jobs = db.execute("SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user["id"],)).fetchall()
    rows = ""
    for job in jobs:
        jid,status = job["id"], job["status"]
        bc = {"running":"badge-running","complete":"badge-complete","failed":"badge-failed"}.get(status,"badge-queued")
        tl = "Slot" if job["job_type"]=="slot_pipeline" else ("Recon" if job["job_type"]=="state_recon" else ("Iterate" if job["job_type"]=="iterate" else ("Variants" if job["job_type"]=="variant_parent" else ("Variant" if job["job_type"]=="variant" else job["job_type"]))))
        dt = job["created_at"][:16].replace("T"," ") if job["created_at"] else ""
        if job["job_type"] == "variant_parent":
            act = f'<a href="/job/{jid}/variants" class="btn btn-ghost btn-sm">Compare</a>' if status in ("running","complete") else ""
        elif status=="complete":
            act = f'<a href="/job/{jid}/files" class="btn btn-ghost btn-sm">Files</a>'
        elif status=="running":
            act = f'<a href="/job/{jid}/logs" class="btn btn-ghost btn-sm" style="border-color:var(--border-hover);color:var(--text-bright)">Watch Live</a>'
        else:
            act = ""
        err = f'<div style="font-size:11px;color:var(--danger);margin-top:2px">{job["error"][:80]}...</div>' if job["error"] else ""
        rows += f'<div class="history-item"><div><div class="history-title">{_esc(job["title"])}</div><div class="history-type">{tl}{err}</div></div><div><span class="badge {bc}">{status}</span></div><div class="history-date">{dt}</div><div class="history-actions">{act}</div></div>'
    if not rows: rows = '<div class="empty-state"><h3>No history yet</h3></div>'
    return layout(f'<h2 class="page-title" style="margin-bottom:24px">{ICON_CLOCK} Pipeline History</h2><div class="card" style="padding:0;overflow:hidden">{rows}</div>', "history")

# ─── FILES (Phase 5A: Enhanced File Management) ───
@app.route("/files")
@login_required
def files_page():
    user = current_user()
    search_q = request.args.get("q", "").strip()
    ext_filter = request.args.get("ext", "").strip().lower()

    # Build job→dir mapping for this user
    db = get_db()
    db.execute(
        "SELECT id, title, output_dir, status, created_at, job_type FROM jobs "
        "WHERE user_id=? AND output_dir IS NOT NULL ORDER BY created_at DESC",
        (user["id"],)
    )
    jobs = db.fetchall()

    if search_q or ext_filter:
        # Search mode — find files matching query across all jobs
        results = []
        for j in jobs:
            op = Path(j["output_dir"])
            if not op.exists():
                continue
            for f in op.rglob("*"):
                if not f.is_file():
                    continue
                if ext_filter and f.suffix.lower().lstrip(".") != ext_filter:
                    continue
                if search_q and search_q.lower() not in f.name.lower() and search_q.lower() not in str(f.relative_to(op)).lower():
                    continue
                results.append({
                    "job_id": j["id"], "job_title": j["title"],
                    "path": str(f.relative_to(op)), "url": f"/job/{j['id']}/dl/{f.relative_to(op)}",
                    "size": f"{f.stat().st_size/1024:.1f} KB", "ext": f.suffix.lower(),
                    "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                })
        rows = "".join(
            f'<div class="file-row"><div style="flex:1;min-width:0"><a href="{r["url"]}" style="display:block;overflow:hidden;text-overflow:ellipsis">{_esc(r["path"])}</a>'
            f'<span style="font-size:10px;color:var(--text-dim)">{_esc(r["job_title"])}</span></div>'
            f'<span class="file-size">{r["size"]}</span></div>' for r in results[:200]
        )
        if not rows:
            rows = f'<div class="empty-state"><h3>No files match "{_esc(search_q or ext_filter)}"</h3></div>'
        count_label = f'{len(results)} result{"s" if len(results)!=1 else ""}'
    else:
        # Default: job-grouped folder view
        rows = ""
        for j in jobs:
            op = Path(j["output_dir"])
            if not op.exists():
                continue
            fc = sum(1 for _ in op.rglob("*") if _.is_file())
            ts = sum(f.stat().st_size for f in op.rglob("*") if f.is_file())
            sz = f"{ts/1024:.0f} KB" if ts < 1048576 else f"{ts/1048576:.1f} MB"
            tl = {"slot_pipeline": "Slot", "state_recon": "Recon", "iterate": "Iterate", "variant": "Variant"}.get(j.get("job_type", ""), "Job")
            dt = (j.get("created_at") or "")[:10]
            rows += (
                f'<div class="file-row" style="gap:12px">'
                f'<a href="/job/{j["id"]}/files" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">{ICON_FOLDER} {_esc(j["title"])}</a>'
                f'<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--accent-soft);color:var(--text-muted)">{tl}</span>'
                f'<span class="file-size">{fc} files · {sz}</span>'
                f'<span class="file-size">{dt}</span>'
                f'<a href="/job/{j["id"]}/download-zip" class="btn btn-ghost btn-sm" title="Download all as ZIP" style="padding:4px 10px;font-size:11px">ZIP ↓</a>'
                f'</div>'
            )
        if not rows:
            rows = '<div class="empty-state"><h3>No output files yet</h3><p>Launch a pipeline to generate files.</p></div>'
        count_label = f'{len(jobs)} pipeline{"s" if len(jobs)!=1 else ""}'

    # Extension filter quick-links
    ext_tags = ""
    for ext, label in [("pdf","PDF"),("json","JSON"),("html","HTML"),("csv","CSV"),("png","Images"),("mp3","Audio")]:
        active = "background:var(--accent-mid);color:var(--text-bright)" if ext_filter == ext else ""
        ext_tags += f'<a href="/files?ext={ext}&q={_esc(search_q)}" style="font-size:10px;padding:3px 10px;border-radius:12px;border:1px solid var(--border);color:var(--text-muted);text-decoration:none;{active}">{label}</a> '
    if ext_filter:
        ext_tags += f'<a href="/files?q={_esc(search_q)}" style="font-size:10px;padding:3px 10px;color:var(--danger);text-decoration:none">✕ Clear</a>'

    return layout(f'''
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
        <h2 class="page-title">{ICON_FOLDER} All Files</h2>
        <span style="font-size:12px;color:var(--text-dim)">{count_label}</span>
    </div>
    <div class="card" style="padding:12px 16px;margin-bottom:12px">
        <form action="/files" method="GET" style="display:flex;gap:10px;align-items:center;margin:0">
            <input name="q" value="{_esc(search_q)}" placeholder="Search files by name..." style="margin:0;flex:1;padding:8px 14px" autocomplete="off">
            <input type="hidden" name="ext" value="{_esc(ext_filter)}">
            <button type="submit" class="btn btn-ghost btn-sm">{ICON_SEARCH} Search</button>
        </form>
        <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap">{ext_tags}</div>
    </div>
    <div class="card" style="padding:0;overflow:hidden">{rows}</div>''', "files")

@app.route("/files/<path:subpath>")
@login_required
def browse_files(subpath):
    target = OUTPUT_DIR / subpath
    if not target.exists(): return "Not found", 404
    if target.is_file(): return send_from_directory(target.parent, target.name)
    files = [{"path":str(f.relative_to(target)),"url":f"/files/{f.relative_to(OUTPUT_DIR)}","size":f"{f.stat().st_size/1024:.1f} KB","ext":f.suffix.lower()} for f in sorted(target.rglob("*")) if f.is_file()]
    rows = ""
    for f in files:
        icon = {"pdf":"📄","json":"📋","html":"🌐","png":"🖼️","jpg":"🖼️","csv":"📊","mp3":"🔊","wav":"🔊"}.get(f["ext"].lstrip("."), "📁")
        rows += f'<div class="file-row"><a href="{f["url"]}">{icon} {f["path"]}</a><span class="file-size">{f["size"]}</span></div>'
    return layout(f'''<div style="margin-bottom:20px"><a href="/files" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Back to All Files</a></div>
    <h2 style="font-size:18px;font-weight:700;color:var(--text-bright);margin-bottom:16px">{_esc(subpath)}</h2>
    <div class="card" style="padding:0;overflow:hidden">{rows}</div>''', "files")

# ─── ZIP DOWNLOAD (Phase 5A) ───
@app.route("/job/<job_id>/download-zip")
@login_required
def job_download_zip(job_id):
    """Stream the entire job output folder as a ZIP file."""
    db = get_db()
    db.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
    job = db.fetchone()
    if not job or not job.get("output_dir"):
        return "Not found", 404
    op = Path(job["output_dir"])
    if not op.exists():
        return "Output directory no longer exists", 404

    # Build zip in memory
    buf = io.BytesIO()
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (job.get("title") or "export"))
    zip_name = f"arkainbrain_{safe_title}_{job_id}.zip"

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(op.rglob("*")):
            if f.is_file():
                arcname = str(f.relative_to(op))
                zf.write(f, arcname)

    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )

# ─── JOB FILES ───
@app.route("/job/<job_id>/files")
@login_required
def job_files(job_id):
    db = get_db(); job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or not job["output_dir"]: return "Not found", 404
    op = Path(job["output_dir"])
    if not op.exists(): return layout('<div class="card"><p style="color:var(--text-muted)">Output no longer exists.</p></div>')

    # Collect all files
    all_files = sorted(op.rglob("*"))
    files = [{"path":str(f.relative_to(op)),"url":f"/job/{job_id}/dl/{f.relative_to(op)}","size":f"{f.stat().st_size/1024:.1f} KB","ext":f.suffix.lower()} for f in all_files if f.is_file()]

    # Prototype section
    proto_html = ""
    proto_files = [f for f in files if f["path"].startswith("07_prototype") and f["ext"] == ".html"]
    if proto_files:
        proto_html = f'''<div class="card"><h2>🎮 Playable Prototype</h2>
            <iframe src="{proto_files[0]['url']}" class="proto-frame" title="Game Prototype"></iframe>
            <div style="margin-top:8px;text-align:center"><a href="{proto_files[0]['url']}" target="_blank" class="btn btn-ghost btn-sm">Open in new tab ↗</a></div></div>'''

    # Audio section
    audio_html = ""
    audio_files = [f for f in files if f["path"].startswith("04_audio") and f["ext"] in (".mp3", ".wav")]
    if audio_files:
        audio_rows = ""
        for af in audio_files:
            name = Path(af["path"]).stem
            audio_rows += f'<div class="audio-player"><span class="audio-name">{name}</span><audio controls preload="none" src="{af["url"]}"></audio><span class="file-size">{af["size"]}</span></div>'
        audio_html = f'<div class="card"><h2>🔊 AI Sound Design ({len(audio_files)} sounds)</h2><div style="max-height:400px;overflow-y:auto">{audio_rows}</div></div>'

    # Cert plan section
    cert_html = ""
    cert_file = op / "05_legal" / "certification_plan.json"
    if cert_file.exists():
        try:
            cert = json.loads(cert_file.read_text())
            markets = list(cert.get("per_market", {}).keys())
            timeline = cert.get("total_timeline", {})
            cost = cert.get("total_cost", {})
            lab = cert.get("recommended_lab", {})
            flags = cert.get("critical_flags", [])

            flags_html = "".join(f'<div style="padding:6px 10px;background:#ef444415;border-radius:6px;font-size:12px;color:var(--danger);margin-bottom:4px">⚠️ {fl}</div>' for fl in flags)

            cert_html = f'''<div class="card"><h2>📋 Certification Plan</h2>
                <div class="row3" style="margin-bottom:16px">
                    <div><label>Recommended Lab</label><div style="font-size:16px;font-weight:600;color:var(--text-bright)">{lab.get("name","TBD")}</div><div style="font-size:11px;color:var(--text-muted)">Covers {lab.get("covers_markets",0)}/{len(markets)} markets</div></div>
                    <div><label>Timeline (Parallel)</label><div style="font-size:16px;font-weight:700;color:var(--text-bright)">{timeline.get("parallel_testing_weeks","?")} weeks</div><div style="font-size:11px;color:var(--text-muted)">vs {timeline.get("sequential_testing_weeks","?")}w sequential</div></div>
                    <div><label>Total Cost Estimate</label><div style="font-size:16px;font-weight:700;color:var(--warning)">{cost.get("estimated_range","TBD")}</div></div>
                </div>
                {flags_html}
                <div style="margin-top:12px"><a href="/job/{job_id}/dl/05_legal/certification_plan.json" class="btn btn-ghost btn-sm">Download full plan JSON ↓</a></div></div>'''
        except Exception as e:
            logger.debug(f"Cert plan card: {e}")

    # Patent scan section
    patent_html = ""
    patent_file = op / "00_preflight" / "patent_scan.json"
    if patent_file.exists():
        try:
            pscan = json.loads(patent_file.read_text())
            risk = pscan.get("risk_assessment", {})
            risk_level = risk.get("overall_ip_risk", "UNKNOWN")
            risk_color = {"HIGH":"var(--danger)","MEDIUM":"var(--warning)","LOW":"var(--success)"}.get(risk_level, "var(--text-muted)")
            hits = pscan.get("known_patent_hits", [])
            hits_rows = []
            for h in hits:
                risk_str = h.get("risk", "")
                rc = "var(--danger)" if risk_str.startswith("HIGH") else ("var(--warning)" if "MEDIUM" in risk_str else "var(--text-muted)")
                hits_rows.append(f'<div style="padding:6px 10px;background:var(--bg-input);border-radius:6px;font-size:12px;margin-bottom:4px"><b>{h.get("mechanic","")}</b> — {h.get("holder","")} <span style="color:{rc}">({risk_str})</span></div>')
            hits_html = "".join(hits_rows)

            patent_html = f'''<div class="card"><h2>🔒 Patent/IP Scan</h2>
                <div style="margin-bottom:12px"><span style="font-size:16px;font-weight:700;color:{risk_color}">{risk_level} RISK</span>
                <span style="font-size:12px;color:var(--text-muted);margin-left:8px">{risk.get("patent_conflicts",0)} conflicts, {risk.get("trademark_similar_names",0)} trademark matches</span></div>
                {hits_html if hits_html else '<div style="font-size:12px;color:var(--success)">No known patent conflicts detected.</div>'}
            </div>'''
        except Exception as e:
            logger.debug(f"Patent scan card: {e}")

    # Revenue projection card (Phase 5)
    revenue_html = ""
    rev_file = op / "08_revenue" / "revenue_projection.json"

    # Geographic Market Research card (Phase 3)
    geo_html = ""
    geo_file = op / "01_research" / "geo_research.json"
    if geo_file.exists():
        try:
            geo = json.loads(geo_file.read_text())
            state = geo.get("state", "")
            sp = geo.get("state_profile", {})
            legal = sp.get("legal_status", "unknown").replace("_", " ").title()
            ggr = sp.get("annual_ggr_billions", 0)
            regions = geo.get("ranked_regions", [])
            top = geo.get("top_recommendation")

            reg_rows = ""
            for r in regions[:4]:
                score = r.get("composite_score", 0)
                sc = "var(--success)" if score >= 70 else ("var(--warning)" if score >= 40 else "var(--text-muted)")
                density = r.get("casino_density", "—").replace("_", " ").title()
                reg_rows += f'''<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:var(--bg-input);border-radius:6px;margin-bottom:4px;font-size:12px">
                    <div style="display:flex;align-items:center;gap:8px">
                        <span style="font-size:14px;font-weight:700;color:{sc};min-width:28px">{r.get("rank","")}</span>
                        <div><div style="font-weight:600;color:var(--text-bright)">{r.get("region","")}</div>
                        <div style="font-size:10px;color:var(--text-muted)">{r.get("pop",0):,} pop · {density} density</div></div>
                    </div>
                    <span style="font-weight:700;color:{sc}">{score}/100</span>
                </div>'''

            top_reason = _esc(top.get("placement_rationale", "")) if top else ""

            geo_html = f'''<div class="card"><h2>&#128205; Geographic Market Analysis</h2>
                <div class="row3" style="margin-bottom:16px">
                    <div><label>State</label><div style="font-size:16px;font-weight:700;color:var(--text-bright)">{_esc(state)}</div></div>
                    <div><label>Legal Status</label><div style="font-size:14px;font-weight:600;color:var(--text-bright)">{_esc(legal)}</div></div>
                    <div><label>Annual GGR</label><div style="font-size:16px;font-weight:700;color:var(--warning)">${ggr:.1f}B</div></div>
                </div>
                <label style="margin-bottom:6px;display:block;font-size:11px">Top Regions by Composite Score</label>
                {reg_rows}
                {f'<div style="margin-top:10px;font-size:12px;color:var(--text-muted);line-height:1.5"><b>Top pick:</b> {top_reason}</div>' if top_reason else ""}
                <div style="margin-top:12px"><a href="/job/{job_id}/dl/01_research/geo_research.json" class="btn btn-ghost btn-sm">Download full report JSON ↓</a></div></div>'''
        except Exception as e:
            logger.debug(f"Geo research card: {e}")
    # Also check for multiple geo files (multiple states)
    if not geo_html:
        geo_files = list((op / "01_research").glob("geo_*.json")) if (op / "01_research").exists() else []
        if geo_files:
            try:
                cards = ""
                for gf in geo_files[:3]:
                    geo = json.loads(gf.read_text())
                    top = geo.get("top_recommendation")
                    if top:
                        cards += f'''<div style="padding:8px 12px;background:var(--bg-input);border-radius:6px;margin-bottom:4px;font-size:12px">
                            <b>{geo.get("state","")}</b>: {top.get("region","")} — score {top.get("composite_score",0)}/100
                            <span style="color:var(--text-dim)">({top.get("casino_density","").replace("_"," ")})</span></div>'''
                if cards:
                    geo_html = f'<div class="card"><h2>&#128205; Geographic Market Analysis</h2>{cards}</div>'
            except Exception as e:
                logger.debug(f"Multi-geo card: {e}")
    if rev_file.exists():
        try:
            rev = json.loads(rev_file.read_text())
            ggr_365 = rev.get("ggr_365d", 0)
            ggr_90 = rev.get("ggr_90d", 0)
            arpdau = rev.get("arpdau", 0)
            be_days = rev.get("break_even_days", "?")
            roi = rev.get("roi_365d", 0)
            hold = rev.get("hold_pct", 0)
            cannibal = rev.get("cannibalization_risk", "?")
            cannibal_c = {"low":"var(--success)","medium":"var(--warning)","high":"var(--danger)"}.get(cannibal, "var(--text-muted)")
            roi_c = "var(--success)" if roi > 0 else "var(--danger)"

            # Mini monthly chart using CSS bars
            monthly = rev.get("ggr_monthly", [])
            max_ggr = max((m.get("ggr", 0) for m in monthly), default=1) or 1
            bars = ""
            for m in monthly[:12]:
                pct = min(100, int(m.get("ggr", 0) / max_ggr * 100))
                bars += f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px"><div style="width:100%;height:{pct}px;max-height:60px;background:linear-gradient(to top,rgba(255,255,255,0.05),rgba(255,255,255,0.15));border-radius:3px 3px 0 0"></div><span style="font-size:9px;color:var(--text-dim)">{m.get("month","")}</span></div>'

            # Market breakdown (top 3)
            mkt_rows = ""
            for mk in rev.get("market_breakdown", [])[:3]:
                mkt_rows += f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:12px"><span style="color:var(--text-muted)">{mk.get("market","").upper()}</span><span style="color:var(--text-bright);font-family:var(--mono)">${mk.get("ggr_365d",0):,.0f}</span></div>'

            revenue_html = f'''<div class="card"><h2>&#128176; Revenue Projection</h2>
                <div class="row3" style="margin-bottom:16px">
                    <div><label>Annual GGR (365d)</label><div style="font-size:20px;font-weight:700;color:var(--text-bright)">${ggr_365:,.0f}</div></div>
                    <div><label>ARPDAU</label><div style="font-size:20px;font-weight:700;color:var(--text-bright)">${arpdau:.2f}</div></div>
                    <div><label>Hold %</label><div style="font-size:20px;font-weight:700;color:var(--text-bright)">{hold}%</div></div>
                </div>
                <div class="row3" style="margin-bottom:16px">
                    <div><label>Break-Even</label><div style="font-size:16px;font-weight:600;color:var(--warning)">{be_days} days</div></div>
                    <div><label>1-Year ROI</label><div style="font-size:16px;font-weight:600;color:{roi_c}">{roi:+.1f}%</div></div>
                    <div><label>Cannibalization</label><div style="font-size:16px;font-weight:600;color:{cannibal_c}">{cannibal.upper()}</div></div>
                </div>
                <div style="margin-bottom:16px"><label style="margin-bottom:8px;display:block">Monthly GGR Projection</label>
                    <div style="display:flex;gap:2px;align-items:flex-end;height:75px;padding:8px 0">{bars}</div></div>
                <div style="margin-bottom:12px"><label style="margin-bottom:6px;display:block">Top Markets</label>{mkt_rows}</div>
                <a href="/job/{job_id}/revenue" class="btn btn-ghost btn-sm" style="margin-top:4px">View full dashboard &rarr;</a></div>'''
        except Exception as e:
            logger.debug(f"Revenue card: {e}")

    # Engine export card (Phase 10: Production-Grade)
    export_html = ""
    export_dir = op / "09_export" if op else None
    has_exports = export_dir and export_dir.exists() and any(export_dir.glob("*.zip"))
    if job["status"] == "complete":
        existing_zips = ""
        if has_exports:
            for zf in sorted(export_dir.glob("*.zip")):
                size_kb = zf.stat().st_size / 1024
                label = zf.stem.split("_")[-2] if "_" in zf.stem else zf.stem
                existing_zips += f'<a href="/job/{job_id}/dl/09_export/{zf.name}" class="btn btn-ghost btn-sm" style="margin-right:6px;margin-bottom:6px;font-size:10px">📦 {zf.name} ({size_kb:.0f} KB) ↓</a>'

        export_html = f'''<div class="card"><h2>&#127918; Export Pipeline (Phase 10)</h2>
            <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Production-grade export packages for engines, audio middleware, and aggregator SDKs.
                <a href="/job/{job_id}/exports" style="color:var(--accent);font-size:11px;margin-left:8px;text-decoration:none">📊 Export Dashboard →</a>
            </p>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;margin-bottom:12px">
                <a href="/api/job/{job_id}/export?format=unity" class="btn btn-primary" style="font-size:11px;padding:8px 12px;text-align:left">🎮 Unity Package<br><span style="font-size:9px;opacity:.7">ScriptableObjects + prefabs</span></a>
                <a href="/api/job/{job_id}/export?format=godot" class="btn btn-primary" style="font-size:11px;padding:8px 12px;text-align:left">🤖 Godot 4 Project<br><span style="font-size:9px;opacity:.7">.tscn scenes + .gd scripts</span></a>
                <a href="/api/job/{job_id}/export?format=atlas" class="btn btn-ghost" style="font-size:11px;padding:8px 12px;text-align:left">🖼️ Sprite Atlas<br><span style="font-size:9px;opacity:.7">TexturePacker JSON + anims</span></a>
                <a href="/api/job/{job_id}/export?format=audio_fmod" class="btn btn-ghost" style="font-size:11px;padding:8px 12px;text-align:left">🔊 FMOD Studio<br><span style="font-size:9px;opacity:.7">.fspro + event sheets</span></a>
                <a href="/api/job/{job_id}/export?format=audio_wwise" class="btn btn-ghost" style="font-size:11px;padding:8px 12px;text-align:left">🎧 Wwise Project<br><span style="font-size:9px;opacity:.7">.wproj + SoundBanks</span></a>
                <a href="/api/job/{job_id}/export?format=provider_gig" class="btn btn-ghost" style="font-size:11px;padding:8px 12px;text-align:left">🏢 GIG / iSoftBet<br><span style="font-size:9px;opacity:.7">Game manifest + RGS hooks</span></a>
                <a href="/api/job/{job_id}/export?format=provider_relax" class="btn btn-ghost" style="font-size:11px;padding:8px 12px;text-align:left">🏢 Relax Gaming<br><span style="font-size:9px;opacity:.7">Silver Bullet descriptor</span></a>
                <a href="/api/job/{job_id}/export?format=provider_generic" class="btn btn-ghost" style="font-size:11px;padding:8px 12px;text-align:left">📦 Generic SDK<br><span style="font-size:9px;opacity:.7">OpenAPI JSON bundle</span></a>
            </div>
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
                <a href="/api/job/{job_id}/export/batch" class="btn btn-primary" style="font-size:11px;padding:8px 16px">⚡ Download ALL Formats</a>
                <span style="font-size:10px;color:var(--text-dim)">Single ZIP with all 8 export packages</span>
            </div>
            {"<div style='margin-top:8px;border-top:1px solid var(--border);padding-top:8px'><label style='font-size:11px;color:var(--text-dim);margin-bottom:4px;display:block'>Cached exports:</label>" + existing_zips + "</div>" if existing_zips else ""}
            </div>'''

    # Regular file list — enhanced with icons, type badges, preview, bulk select
    # Fetch tags/favorites for this job
    _tag_db = get_db()
    _tag_db.execute("SELECT * FROM file_tags WHERE job_id=?", (job_id,))
    _all_tags = _tag_db.fetchall()
    _favorites = {t["file_path"] for t in _all_tags if t["tag"] == "favorite"}
    _file_tags = {}
    for t in _all_tags:
        if t["tag"] != "favorite":
            _file_tags.setdefault(t["file_path"], []).append(t["tag"])

    _ext_icons = {".pdf":"📄",".json":"📋",".html":"🌐",".png":"🖼️",".jpg":"🖼️",".jpeg":"🖼️",".gif":"🖼️",
                  ".svg":"🎨",".csv":"📊",".mp3":"🔊",".wav":"🔊",".py":"🐍",".js":"⚡",".cs":"🔷",
                  ".md":"📝",".txt":"📝",".zip":"📦",".toml":"⚙️",".yaml":"⚙️",".yml":"⚙️"}

    rows = ""
    for f in files:
        icon = _ext_icons.get(f["ext"], "📁")
        is_fav = f["path"] in _favorites
        fav_cls = "color:var(--warning)" if is_fav else "color:var(--text-dim);opacity:0.3"
        tags_html = "".join(f'<span style="font-size:9px;padding:1px 6px;border-radius:3px;background:rgba(124,106,239,0.1);color:#a78bfa;margin-left:4px">{_esc(t)}</span>' for t in _file_tags.get(f["path"], []))
        # Folder grouping display
        folder = "/".join(f["path"].split("/")[:-1])
        fname = f["path"].split("/")[-1]
        rows += (
            f'<div class="file-row ef-row" data-path="{_esc(f["path"])}" data-ext="{f["ext"]}" data-size="{f["size"]}" '
            f'style="cursor:pointer" onclick="window._preview(\'{job_id}\',\'{_esc(f["path"])}\')">'
            f'<label style="margin:0;display:flex;align-items:center;cursor:pointer" onclick="event.stopPropagation()">'
            f'<input type="checkbox" class="bulk-cb" value="{_esc(f["path"])}" style="width:auto;margin:0 10px 0 0;accent-color:#fff"></label>'
            f'<span style="font-size:14px;margin-right:8px;flex-shrink:0">{icon}</span>'
            f'<div style="flex:1;min-width:0;overflow:hidden">'
            f'<a href="{f["url"]}" onclick="event.stopPropagation()" style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_esc(fname)}</a>'
            f'<span style="font-size:10px;color:var(--text-dim)">{_esc(folder)}</span>{tags_html}</div>'
            f'<button onclick="event.stopPropagation();window._toggleFav(\'{job_id}\',\'{_esc(f["path"])}\')" style="background:none;border:none;cursor:pointer;font-size:14px;{fav_cls}" title="Favorite">★</button>'
            f'<span class="file-size" style="min-width:60px;text-align:right">{f["size"]}</span>'
            f'</div>'
        )

    # Iterate button (only for completed jobs)
    iterate_btn = ""
    if job["status"] == "complete":
        iterate_btn = f'<a href="/job/{job_id}/iterate" class="btn btn-primary" style="font-size:13px;padding:8px 20px;margin-left:12px">🔄 Iterate</a>'
    # Interactive review button (for completed pipeline jobs)
    review_btn = ""
    if job["status"] == "complete" and job["output_dir"] and job.get("job_type", "") in ("slot_pipeline", "iterate", "variant", ""):
        review_btn = f'<a href="/review/{job_id}/interactive" class="btn btn-ghost" style="font-size:13px;padding:8px 20px;margin-left:8px;border-color:var(--accent);color:var(--accent)">📋 Interactive Review</a>'
    # Variants button for variant_parent or variant jobs
    variants_btn = ""
    parent_for_variants = _rget(job, "parent_job_id") or job_id
    db_v = get_db()
    has_variants = db_v.execute("SELECT COUNT(*) as c FROM jobs WHERE parent_job_id=? AND job_type='variant'", (parent_for_variants,)).fetchone()["c"]
    if has_variants > 0:
        variants_btn = f'<a href="/job/{parent_for_variants}/variants" class="btn btn-ghost" style="font-size:13px;padding:8px 20px;margin-left:8px">🔀 Variants ({has_variants})</a>'

    # Version history + compare selector
    version_html = ""
    compare_html = ""
    db2 = get_db()
    root_id = _rget(job, "parent_job_id") or job_id
    versions = db2.execute("SELECT id,version,status,created_at FROM jobs WHERE id=? OR parent_job_id=? OR id=? ORDER BY version", (root_id, root_id, job_id)).fetchall()
    if len(versions) > 1:
        vrows = ""
        compare_opts = ""
        for v in versions:
            active = " style='color:var(--text-bright);font-weight:600'" if v["id"] == job_id else ""
            sc = {"complete":"var(--success)","running":"var(--warning)","failed":"var(--danger)"}.get(v["status"],"var(--text-dim)")
            vrows += f'<a href="/job/{v["id"]}/files"{active}>v{v["version"] or 1} <span style="color:{sc};font-size:11px">{v["status"]}</span></a> '
            if v["id"] != job_id and v["status"] == "complete":
                compare_opts += f'<option value="{v["id"]}">v{v["version"] or 1}</option>'
        version_html = f'<div style="margin-bottom:12px;font-size:12px;color:var(--text-muted)">Versions: {vrows}</div>'
        if compare_opts:
            compare_html = f'''<div style="display:inline-flex;align-items:center;gap:6px;margin-left:12px">
                <select id="cmpSel" style="font-size:11px;padding:4px 8px;background:var(--bg-card);color:var(--text);border:1px solid var(--border);border-radius:6px">{compare_opts}</select>
                <button onclick="location.href='/job/{job_id}/diff/'+document.getElementById('cmpSel').value" class="btn btn-ghost" style="font-size:11px;padding:4px 12px">Compare ↔</button></div>'''

    return layout(f'''<div style="margin-bottom:20px"><a href="/history" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Back to History</a></div>
    <div style="display:flex;align-items:center;margin-bottom:4px"><h2 style="font-size:18px;font-weight:700;color:var(--text-bright)">{_esc(job["title"])}</h2>{iterate_btn}{review_btn}{variants_btn}{compare_html}</div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
        <p style="color:var(--text-muted);font-size:12px;margin:0">{len(files)} files generated · v{_rget(job, "version") or 1}</p>
        <a href="/job/{job_id}/download-zip" class="btn btn-ghost btn-sm" style="padding:4px 12px;font-size:11px">📦 Download ZIP</a>
    </div>
    {version_html}
    {proto_html}{audio_html}{patent_html}{cert_html}{geo_html}{revenue_html}{export_html}
    <div class="card" style="padding:0;overflow:hidden">
        <div style="padding:12px 16px 8px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
            <h2 style="margin:0">📁 All Files</h2>
            <div style="display:flex;gap:6px;align-items:center" id="bulkBar">
                <span id="selCount" style="font-size:11px;color:var(--text-dim);display:none">0 selected</span>
                <button onclick="window._bulkZip('{job_id}')" id="bulkZipBtn" class="btn btn-ghost btn-sm" style="display:none;padding:3px 10px;font-size:10px">ZIP selected ↓</button>
                <button onclick="document.querySelectorAll('.bulk-cb').forEach(c=>c.checked=!c.checked);window._updBulk()" class="btn btn-ghost btn-sm" style="padding:3px 10px;font-size:10px">Select all</button>
            </div>
        </div>
        <div style="padding:4px 16px 8px;display:flex;gap:6px;flex-wrap:wrap">
            <button onclick="window._filterExt('')" class="ef-filter active" data-ext="">All</button>
            <button onclick="window._filterExt('.pdf')" class="ef-filter" data-ext=".pdf">PDF</button>
            <button onclick="window._filterExt('.json')" class="ef-filter" data-ext=".json">JSON</button>
            <button onclick="window._filterExt('.html')" class="ef-filter" data-ext=".html">HTML</button>
            <button onclick="window._filterExt('.png')" class="ef-filter" data-ext=".png">Images</button>
            <button onclick="window._filterExt('.csv')" class="ef-filter" data-ext=".csv">CSV</button>
            <button onclick="window._filterExt('.mp3')" class="ef-filter" data-ext=".mp3">Audio</button>
            <span style="border-left:1px solid var(--border);height:16px;margin:0 4px"></span>
            <button onclick="window._sortFiles('name')" class="ef-filter" title="Sort by name">A→Z</button>
            <button onclick="window._sortFiles('size')" class="ef-filter" title="Sort by size">Size</button>
            <button onclick="window._sortFiles('type')" class="ef-filter" title="Sort by type">Type</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr;min-height:300px" id="fileGrid">
            <div id="fileList" style="overflow-y:auto;max-height:600px;border-top:1px solid var(--border)">{rows}</div>
            <div id="previewPanel" style="display:none;border-top:1px solid var(--border);background:var(--bg-surface);overflow-y:auto;max-height:600px">
                <div style="padding:10px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border)">
                    <span style="font-size:11px;font-weight:600;color:var(--text-bright)">Preview</span>
                    <button onclick="window._closePreview()" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:16px">×</button>
                </div>
                <div id="previewContent" style="padding:8px"></div>
            </div>
        </div>
    </div>
    <style>
    .ef-filter{{font-size:10px;padding:3px 10px;border-radius:12px;border:1px solid var(--border);color:var(--text-muted);background:transparent;cursor:pointer;transition:all 0.15s;font-family:inherit}}
    .ef-filter:hover{{border-color:var(--border-hover);color:var(--text-bright)}}
    .ef-filter.active{{background:var(--accent-mid);color:var(--text-bright);border-color:var(--border-hover)}}
    .ef-row:hover{{background:var(--accent-soft)}}
    .ef-row.selected{{background:rgba(124,106,239,0.06);border-left:2px solid #7c6aef}}
    </style>
    <script>
    // ─── Enhanced File Browser JS ───
    window._preview = function(jid, path) {{
        var pp = document.getElementById('previewPanel');
        var pc = document.getElementById('previewContent');
        var fg = document.getElementById('fileGrid');
        pp.style.display = 'block';
        fg.style.gridTemplateColumns = '1fr 1fr';
        pc.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-dim)">Loading...</div>';
        document.querySelectorAll('.ef-row').forEach(r => r.classList.remove('selected'));
        document.querySelector('.ef-row[data-path="'+path+'"]')?.classList.add('selected');
        fetch('/job/' + jid + '/preview/' + path)
            .then(r => r.text())
            .then(h => {{ pc.innerHTML = h; }})
            .catch(() => {{ pc.innerHTML = '<p style="padding:20px;color:var(--danger)">Preview failed</p>'; }});
    }};
    window._closePreview = function() {{
        document.getElementById('previewPanel').style.display = 'none';
        document.getElementById('fileGrid').style.gridTemplateColumns = '1fr';
        document.querySelectorAll('.ef-row').forEach(r => r.classList.remove('selected'));
    }};
    window._filterExt = function(ext) {{
        document.querySelectorAll('.ef-filter[data-ext]').forEach(b => b.classList.remove('active'));
        document.querySelector('.ef-filter[data-ext="'+ext+'"]')?.classList.add('active');
        document.querySelectorAll('.ef-row').forEach(r => {{
            if (!ext || r.dataset.ext === ext || (ext==='.png' && ['.png','.jpg','.jpeg','.gif','.svg','.webp'].includes(r.dataset.ext)) || (ext==='.mp3' && ['.mp3','.wav','.ogg'].includes(r.dataset.ext)))
                r.style.display = '';
            else r.style.display = 'none';
        }});
    }};
    window._sortFiles = function(by) {{
        var list = document.getElementById('fileList');
        var rows = Array.from(list.querySelectorAll('.ef-row'));
        rows.sort(function(a,b) {{
            if (by==='name') return a.dataset.path.localeCompare(b.dataset.path);
            if (by==='type') return a.dataset.ext.localeCompare(b.dataset.ext);
            if (by==='size') return parseFloat(a.dataset.size) - parseFloat(b.dataset.size);
            return 0;
        }});
        rows.forEach(function(r){{ list.appendChild(r); }});
    }};
    window._toggleFav = function(jid, path) {{
        fetch('/api/files/favorites', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{job_id:jid,file_path:path}})}})
            .then(r => r.json()).then(d => location.reload());
    }};
    window._updBulk = function() {{
        var n = document.querySelectorAll('.bulk-cb:checked').length;
        document.getElementById('selCount').style.display = n ? '' : 'none';
        document.getElementById('selCount').textContent = n + ' selected';
        document.getElementById('bulkZipBtn').style.display = n ? '' : 'none';
    }};
    document.querySelectorAll('.bulk-cb').forEach(c => c.addEventListener('change', window._updBulk));
    window._bulkZip = function(jid) {{
        var paths = Array.from(document.querySelectorAll('.bulk-cb:checked')).map(c => c.value);
        if (!paths.length) return;
        fetch('/api/job/' + jid + '/bulk-zip', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{paths:paths}})}})
            .then(r => r.blob()).then(b => {{
                var a = document.createElement('a'); a.href = URL.createObjectURL(b);
                a.download = 'arkainbrain_selection.zip'; a.click();
            }});
    }};
    </script>''', "history")

@app.route("/job/<job_id>/dl/<path:fp>")
@login_required
def job_dl(job_id, fp):
    db = get_db(); job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or not job["output_dir"]: return "Not found", 404
    return send_from_directory(Path(job["output_dir"]), fp)


# ─── FILE TAGGING & FAVORITES (Phase 5A) ───

@app.route("/api/files/tag", methods=["POST"])
@login_required
def api_tag_file():
    """Tag a file for the component library."""
    user = current_user()
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "")
    file_path = data.get("file_path", "")
    tag = data.get("tag", "").strip().lower()
    if not all([job_id, file_path, tag]):
        return jsonify({"error": "job_id, file_path, and tag required"}), 400
    if len(tag) > 50:
        return jsonify({"error": "Tag too long (max 50 chars)"}), 400
    db = get_db()
    # Verify job belongs to user
    db.execute("SELECT id FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"]))
    if not db.fetchone():
        return jsonify({"error": "Job not found"}), 404
    tag_id = str(uuid.uuid4())[:8]
    db.execute(
        "INSERT INTO file_tags (id, job_id, file_path, tag) VALUES (?,?,?,?)",
        (tag_id, job_id, file_path, tag)
    )
    db.commit()
    return jsonify({"ok": True, "id": tag_id, "tag": tag})


@app.route("/api/files/tag", methods=["DELETE"])
@login_required
def api_untag_file():
    """Remove a tag from a file."""
    data = request.get_json(silent=True) or {}
    tag_id = data.get("id", "")
    if not tag_id:
        return jsonify({"error": "id required"}), 400
    db = get_db()
    db.execute("DELETE FROM file_tags WHERE id=?", (tag_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/job/<job_id>/tags")
@login_required
def api_job_tags(job_id):
    """Get all tags for a job's files."""
    db = get_db()
    db.execute("SELECT * FROM file_tags WHERE job_id=?", (job_id,))
    tags = db.fetchall()
    return jsonify({"tags": tags})


@app.route("/api/files/favorites", methods=["POST"])
@login_required
def api_toggle_favorite():
    """Pin/unpin a file as a favorite."""
    user = current_user()
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "")
    file_path = data.get("file_path", "")
    if not all([job_id, file_path]):
        return jsonify({"error": "job_id and file_path required"}), 400
    # Use the tagging system with special "★ favorite" tag
    db = get_db()
    db.execute(
        "SELECT id FROM file_tags WHERE job_id=? AND file_path=? AND tag='favorite'",
        (job_id, file_path)
    )
    existing = db.fetchone()
    if existing:
        db.execute("DELETE FROM file_tags WHERE id=?", (existing["id"],))
        db.commit()
        return jsonify({"ok": True, "favorited": False})
    else:
        fav_id = str(uuid.uuid4())[:8]
        db.execute(
            "INSERT INTO file_tags (id, job_id, file_path, tag) VALUES (?,?,?,?)",
            (fav_id, job_id, file_path, "favorite")
        )
        db.commit()
        return jsonify({"ok": True, "favorited": True, "id": fav_id})


@app.route("/job/<job_id>/preview/<path:fp>")
@login_required
def job_file_preview(job_id, fp):
    """Inline file preview — returns rendered HTML for the preview panel."""
    db = get_db()
    db.execute("SELECT output_dir FROM jobs WHERE id=?", (job_id,))
    job = db.fetchone()
    if not job or not job.get("output_dir"):
        return "<p style='color:var(--text-dim)'>Not found</p>", 404
    target = Path(job["output_dir"]) / fp
    if not target.exists() or not target.is_file():
        return "<p style='color:var(--text-dim)'>File not found</p>", 404

    ext = target.suffix.lower()
    size_kb = target.stat().st_size / 1024
    fname = target.name

    # Build preview based on file type
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        url = f"/job/{job_id}/dl/{fp}"
        return f'''<div style="text-align:center;padding:12px">
            <img src="{url}" style="max-width:100%;max-height:400px;border-radius:8px;border:1px solid var(--border)" alt="{_esc(fname)}">
            <div style="margin-top:8px;font-size:11px;color:var(--text-dim)">{_esc(fname)} · {size_kb:.1f} KB</div></div>'''

    elif ext == ".pdf":
        url = f"/job/{job_id}/dl/{fp}"
        return f'''<div style="padding:4px">
            <iframe src="{url}" style="width:100%;height:500px;border:1px solid var(--border);border-radius:8px;background:#fff" title="{_esc(fname)}"></iframe>
            <div style="margin-top:6px;font-size:11px;color:var(--text-dim)">{_esc(fname)} · {size_kb:.1f} KB</div></div>'''

    elif ext == ".html":
        url = f"/job/{job_id}/dl/{fp}"
        return f'''<div style="padding:4px">
            <iframe src="{url}" style="width:100%;height:500px;border:1px solid var(--border);border-radius:8px" sandbox="allow-scripts allow-same-origin" title="{_esc(fname)}"></iframe>
            <div style="margin-top:6px;font-size:11px;color:var(--text-dim)">{_esc(fname)} · {size_kb:.1f} KB</div></div>'''

    elif ext == ".json":
        try:
            raw = target.read_text(errors="replace")[:50000]
            data = json.loads(raw)
            formatted = json.dumps(data, indent=2)[:10000]
        except Exception:
            formatted = raw[:10000] if 'raw' in dir() else "Unable to read"
        return f'''<div style="padding:4px">
            <pre style="background:var(--bg-input);border:1px solid var(--border);border-radius:8px;padding:12px;font-size:11px;font-family:'Geist Mono',monospace;color:var(--text);overflow:auto;max-height:500px;white-space:pre-wrap;line-height:1.5">{_esc(formatted)}</pre>
            <div style="margin-top:6px;font-size:11px;color:var(--text-dim)">{_esc(fname)} · {size_kb:.1f} KB</div></div>'''

    elif ext == ".csv":
        try:
            lines = target.read_text(errors="replace").strip().split("\n")[:100]
            if lines:
                header = lines[0].split(",")
                th = "".join(f"<th style='padding:6px 10px;text-align:left;border-bottom:1px solid var(--border);font-size:10px;color:var(--text-muted);font-weight:600'>{_esc(h.strip())}</th>" for h in header)
                trs = ""
                for line in lines[1:50]:
                    cells = line.split(",")
                    tds = "".join(f"<td style='padding:5px 10px;border-bottom:1px solid var(--border);font-size:11px'>{_esc(c.strip())}</td>" for c in cells)
                    trs += f"<tr>{tds}</tr>"
                table = f"<table style='width:100%;border-collapse:collapse'><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"
            else:
                table = "<p style='color:var(--text-dim)'>Empty CSV</p>"
        except Exception:
            table = "<p style='color:var(--text-dim)'>Unable to parse CSV</p>"
        return f'''<div style="padding:4px;overflow-x:auto">{table}
            <div style="margin-top:6px;font-size:11px;color:var(--text-dim)">{_esc(fname)} · {len(lines)} rows · {size_kb:.1f} KB</div></div>'''

    elif ext in (".mp3", ".wav", ".ogg"):
        url = f"/job/{job_id}/dl/{fp}"
        return f'''<div style="padding:16px;text-align:center">
            <div style="font-size:32px;margin-bottom:8px">🔊</div>
            <audio controls preload="none" src="{url}" style="width:100%;max-width:400px"></audio>
            <div style="margin-top:8px;font-size:11px;color:var(--text-dim)">{_esc(fname)} · {size_kb:.1f} KB</div></div>'''

    elif ext in (".md", ".txt", ".py", ".js", ".css", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".log"):
        try:
            content = target.read_text(errors="replace")[:20000]
        except Exception:
            content = "Unable to read file"
        lang_hint = {"py": "python", "js": "javascript", "css": "css", "md": "markdown"}.get(ext.lstrip("."), "")
        return f'''<div style="padding:4px">
            <pre style="background:var(--bg-input);border:1px solid var(--border);border-radius:8px;padding:12px;font-size:11px;font-family:'Geist Mono',monospace;color:var(--text);overflow:auto;max-height:500px;white-space:pre-wrap;line-height:1.5">{_esc(content)}</pre>
            <div style="margin-top:6px;font-size:11px;color:var(--text-dim)">{_esc(fname)} · {size_kb:.1f} KB{f' · {lang_hint}' if lang_hint else ''}</div></div>'''

    else:
        url = f"/job/{job_id}/dl/{fp}"
        return f'''<div style="padding:24px;text-align:center">
            <div style="font-size:40px;margin-bottom:12px">📁</div>
            <div style="font-size:13px;color:var(--text-bright);margin-bottom:4px">{_esc(fname)}</div>
            <div style="font-size:11px;color:var(--text-dim);margin-bottom:16px">{size_kb:.1f} KB · {ext or 'unknown'}</div>
            <a href="{url}" class="btn btn-primary btn-sm" download>Download</a></div>'''


@app.route("/api/job/<job_id>/bulk-zip", methods=["POST"])
@login_required
def api_bulk_zip(job_id):
    """Download selected files from a job as a ZIP."""
    db = get_db()
    db.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
    job = db.fetchone()
    if not job or not job.get("output_dir"):
        return "Not found", 404
    op = Path(job["output_dir"])
    data = request.get_json(silent=True) or {}
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"error": "No files selected"}), 400

    buf = io.BytesIO()
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (job.get("title") or "export"))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths[:500]:  # cap at 500 files
            target = op / p
            if target.exists() and target.is_file() and str(target).startswith(str(op)):
                zf.write(target, p)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="arkainbrain_{safe_title}_selection.zip"'},
    )


# ─── ITERATE: Selective Re-Run + Parameter Tweaker (Phase 3A-3B) ───

@app.route("/job/<job_id>/iterate")
@login_required
def job_iterate(job_id):
    user = current_user()
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not job: return "Not found", 404
    if job["status"] != "complete": return redirect(f"/job/{job_id}/logs")

    params = json.loads(job["params"]) if job["params"] else {}
    op = Path(job["output_dir"]) if job["output_dir"] else None

    # Read current simulation results for before/after comparison
    sim_data = {}
    if op:
        sim_path = op / "03_math" / "simulation_results.json"
        if sim_path.exists():
            try: sim_data = json.loads(sim_path.read_text())
            except Exception as e: logger.debug(f"Sim data parse: {e}")

    # Read GDD quality audit if exists
    gdd_grade = "—"
    gdd_path = op / "02_design" / "gdd.md" if op else None
    has_gdd = gdd_path and gdd_path.exists()

    # Read convergence history
    conv_data = {}
    if op:
        conv_path = op / "02_design" / "convergence_history.json"
        if conv_path.exists():
            try: conv_data = json.loads(conv_path.read_text())
            except Exception as e: logger.debug(f"Convergence data parse: {e}")

    # Version info
    root_id = _rget(job, "parent_job_id") or job_id
    db2 = get_db()
    current_version = _rget(job, "version") or 1
    version_count = db2.execute("SELECT COUNT(*) as cnt FROM jobs WHERE id=? OR parent_job_id=?", (root_id, root_id)).fetchone()["cnt"]
    next_version = version_count + 1

    # Current params display
    cur_rtp = params.get("target_rtp", 96.0)
    cur_max_win = params.get("max_win_multiplier", 5000)
    cur_vol = params.get("volatility", "medium")
    cur_markets = params.get("target_markets", [])
    cur_features = params.get("requested_features", [])
    measured_rtp = sim_data.get("measured_rtp", "—")
    max_win_achieved = sim_data.get("max_win_achieved", "—")
    hit_freq = sim_data.get("hit_frequency_pct", sim_data.get("hit_frequency", "—"))
    vol_idx = sim_data.get("volatility_index", "—")

    # Markets available for multi-select
    all_markets = ["UK","Malta","Sweden","Ontario","New Jersey","Michigan","Pennsylvania","Curaçao","Isle of Man","Gibraltar","Georgia","Texas","North Carolina","Florida"]
    market_options = ""
    for m in all_markets:
        checked = "checked" if m.lower() in [x.lower() for x in cur_markets] else ""
        market_options += f'<label class="iter-check"><input type="checkbox" name="target_markets" value="{m}" {checked}><span>{m}</span></label>'

    # Feature options
    all_features = ["free_spins","multipliers","expanding_wilds","cascading_reels","hold_and_spin","bonus_buy","scatter_pays","jackpot_progressive","cluster_pays","megaways"]
    feature_options = ""
    for f in all_features:
        checked = "checked" if f in cur_features else ""
        label = f.replace("_"," ").title()
        feature_options += f'<label class="iter-check"><input type="checkbox" name="features" value="{f}" {checked}><span>{label}</span></label>'

    return layout(f'''
    <div style="margin-bottom:20px"><a href="/job/{job_id}/files" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Back to {_esc(job["title"])}</a></div>
    <h2 class="page-title" style="margin-bottom:4px">🔄 Iterate — {_esc(job["title"])}</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:24px">v{current_version} → v{next_version} · Re-run selected stages with new parameters</p>

    <form method="POST" action="/api/iterate" id="iterateForm">
    <input type="hidden" name="parent_job_id" value="{root_id}">
    <input type="hidden" name="source_job_id" value="{job_id}">
    <input type="hidden" name="source_output_dir" value="{job['output_dir'] or ''}">
    <input type="hidden" name="theme" value="{params.get('theme','')}">
    <input type="hidden" name="art_style" value="{params.get('art_style','')}">
    <input type="hidden" name="grid_cols" value="{params.get('grid_cols',5)}">
    <input type="hidden" name="grid_rows" value="{params.get('grid_rows',3)}">
    <input type="hidden" name="ways_or_lines" value="{params.get('ways_or_lines','243')}">

    <!-- Current Results -->
    <div class="card" style="margin-bottom:16px">
        <h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Current Results (v{current_version})</h2>
        <div class="row4">
            <div><label style="font-size:11px;color:var(--text-muted)">Measured RTP</label><div style="font-size:20px;font-weight:700;color:var(--text-bright)">{measured_rtp}{'%' if isinstance(measured_rtp,(int,float)) else ''}</div></div>
            <div><label style="font-size:11px;color:var(--text-muted)">Max Win Achieved</label><div style="font-size:20px;font-weight:700;color:var(--text-bright)">{max_win_achieved}{'x' if isinstance(max_win_achieved,(int,float)) else ''}</div></div>
            <div><label style="font-size:11px;color:var(--text-muted)">Hit Frequency</label><div style="font-size:20px;font-weight:700;color:var(--text-bright)">{hit_freq}{'%' if isinstance(hit_freq,(int,float)) else ''}</div></div>
            <div><label style="font-size:11px;color:var(--text-muted)">Volatility Index</label><div style="font-size:20px;font-weight:700;color:var(--text-bright)">{vol_idx}</div></div>
        </div>
    </div>

    <!-- Parameter Tweaker (Phase 3B) -->
    <div class="card" style="margin-bottom:16px">
        <h2 style="font-size:15px;font-weight:600;margin-bottom:16px">⚙️ Parameter Tweaker</h2>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
            <div>
                <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px">Target RTP</label>
                <div style="display:flex;align-items:center;gap:10px">
                    <input type="range" name="target_rtp" min="85" max="99" step="0.1" value="{cur_rtp}"
                           oninput="this.nextElementSibling.textContent=this.value+'%'"
                           style="flex:1;accent-color:var(--text-bright)">
                    <span style="font-family:var(--mono);font-size:14px;font-weight:600;color:var(--text-bright);min-width:50px">{cur_rtp}%</span>
                </div>
            </div>
            <div>
                <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px">Max Win Multiplier</label>
                <div style="display:flex;align-items:center;gap:10px">
                    <input type="range" name="max_win_multiplier" min="1000" max="50000" step="500" value="{cur_max_win}"
                           oninput="this.nextElementSibling.textContent=this.value+'x'"
                           style="flex:1;accent-color:var(--text-bright)">
                    <span style="font-family:var(--mono);font-size:14px;font-weight:600;color:var(--text-bright);min-width:60px">{cur_max_win}x</span>
                </div>
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
            <div>
                <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px">Volatility</label>
                <select name="volatility" class="input-field" style="height:38px">
                    <option value="low" {"selected" if cur_vol=="low" else ""}>Low</option>
                    <option value="medium" {"selected" if cur_vol=="medium" else ""}>Medium</option>
                    <option value="medium_high" {"selected" if cur_vol=="medium_high" else ""}>Medium-High</option>
                    <option value="high" {"selected" if cur_vol=="high" else ""}>High</option>
                    <option value="extreme" {"selected" if cur_vol=="extreme" else ""}>Extreme</option>
                </select>
            </div>
            <div>
                <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px">Special Requirements</label>
                <input type="text" name="special_requirements" value="{params.get('special_requirements','')}" class="input-field" placeholder="e.g. reduce free spin frequency">
            </div>
        </div>
    </div>

    <!-- Target Markets -->
    <div class="card" style="margin-bottom:16px">
        <h2 style="font-size:15px;font-weight:600;margin-bottom:12px">🌍 Target Markets</h2>
        <div style="display:flex;flex-wrap:wrap;gap:6px">{market_options}</div>
    </div>

    <!-- Features -->
    <div class="card" style="margin-bottom:16px">
        <h2 style="font-size:15px;font-weight:600;margin-bottom:12px">🎰 Features</h2>
        <div style="display:flex;flex-wrap:wrap;gap:6px">{feature_options}</div>
    </div>

    <!-- Selective Re-Run (Phase 3A) -->
    <div class="card" style="margin-bottom:16px">
        <h2 style="font-size:15px;font-weight:600;margin-bottom:12px">🔄 What to Re-Run</h2>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Select which stages to regenerate. Unselected stages keep their current output.</p>
        <div style="display:grid;gap:8px">
            <label class="iter-stage"><input type="checkbox" name="rerun_stages" value="math" checked><div><span style="font-weight:600">Math Model</span><span style="font-size:11px;color:var(--text-muted);display:block">Re-run Monte Carlo simulation with new parameters. Generates new reel strips, paytable, and sim results.</span></div></label>
            <label class="iter-stage"><input type="checkbox" name="rerun_stages" value="gdd"><div><span style="font-weight:600">GDD Patch</span><span style="font-size:11px;color:var(--text-muted);display:block">Update affected GDD sections to match new parameters (RTP budget, feature specs, volatility description).</span></div></label>
            <label class="iter-stage"><input type="checkbox" name="rerun_stages" value="art"><div><span style="font-weight:600">Art Assets</span><span style="font-size:11px;color:var(--text-muted);display:block">Regenerate all symbol images, backgrounds, and logo. Keep everything else.</span></div></label>
            <label class="iter-stage"><input type="checkbox" name="rerun_stages" value="compliance"><div><span style="font-weight:600">Compliance Review</span><span style="font-size:11px;color:var(--text-muted);display:block">Re-check regulations for changed markets or parameters. Generates new compliance report.</span></div></label>
            <label class="iter-stage"><input type="checkbox" name="rerun_stages" value="convergence"><div><span style="font-weight:600">Convergence Loop</span><span style="font-size:11px;color:var(--text-muted);display:block">Run full OODA convergence check to validate GDD ↔ Math ↔ Compliance alignment.</span></div></label>
        </div>
    </div>

    <!-- Submit -->
    <div style="display:flex;justify-content:flex-end;gap:12px;margin-bottom:40px">
        <a href="/job/{job_id}/files" class="btn btn-ghost">Cancel</a>
        <button type="submit" class="btn btn-primary" style="padding:10px 32px">🚀 Launch v{next_version}</button>
    </div>
    </form>

    <style>
        .row4 {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px }}
        .iter-check {{ display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border:1px solid var(--border); border-radius:6px; cursor:pointer; font-size:12px; transition:border-color .15s }}
        .iter-check:has(input:checked) {{ border-color:var(--text-bright); background:rgba(255,255,255,0.04) }}
        .iter-check input {{ accent-color:var(--text-bright) }}
        .iter-stage {{ display:flex; align-items:flex-start; gap:10px; padding:10px 14px; border:1px solid var(--border); border-radius:8px; cursor:pointer; transition:border-color .15s }}
        .iter-stage:has(input:checked) {{ border-color:var(--text-bright); background:rgba(255,255,255,0.03) }}
        .iter-stage input {{ margin-top:3px; accent-color:var(--text-bright) }}
        input[type="range"] {{ height:4px; background:var(--border); border-radius:2px; -webkit-appearance:none; appearance:none }}
        input[type="range"]::-webkit-slider-thumb {{ -webkit-appearance:none; width:16px; height:16px; border-radius:50%; background:var(--text-bright); cursor:pointer }}
        @media(max-width:768px) {{ .row4 {{ grid-template-columns:repeat(2,1fr) }} }}
    </style>
    ''', "history")


@app.route("/api/iterate", methods=["POST"])
@login_required
def api_iterate():
    user = current_user()
    parent_id = request.form["parent_job_id"]
    source_id = request.form["source_job_id"]
    source_output = request.form["source_output_dir"]

    # Get next version number
    db = get_db()
    version_count = db.execute("SELECT COUNT(*) as cnt FROM jobs WHERE id=? OR parent_job_id=?", (parent_id, parent_id)).fetchone()["cnt"]
    next_version = version_count + 1

    # Build iteration params
    params = {
        "theme": request.form["theme"],
        "target_markets": request.form.getlist("target_markets"),
        "volatility": request.form.get("volatility", "medium"),
        "target_rtp": float(request.form.get("target_rtp", 96)),
        "grid_cols": int(request.form.get("grid_cols", 5)),
        "grid_rows": int(request.form.get("grid_rows", 3)),
        "ways_or_lines": request.form.get("ways_or_lines", "243"),
        "max_win_multiplier": int(request.form.get("max_win_multiplier", 5000)),
        "art_style": request.form.get("art_style", "Cinematic realism"),
        "requested_features": request.form.getlist("features"),
        "special_requirements": request.form.get("special_requirements", ""),
    }

    iterate_config = {
        "source_job_id": source_id,
        "source_output_dir": source_output,
        "rerun_stages": request.form.getlist("rerun_stages"),
        "parent_job_id": parent_id,
        "version": next_version,
    }

    job_id = str(uuid.uuid4())[:8]
    db.execute(
        "INSERT INTO jobs (id, user_id, job_type, title, params, status, parent_job_id, version) VALUES (?,?,?,?,?,?,?,?)",
        (job_id, user["id"], "iterate", f"{params['theme']} v{next_version}",
         json.dumps({**params, "_iterate": iterate_config}), "queued", parent_id, next_version)
    )
    db.commit()

    enqueue_job("iterate", job_id, json.dumps({**params, "_iterate": iterate_config}))
    return redirect(f"/job/{job_id}/logs")


def _load_job_metrics(output_dir):
    """Load key metrics from a job output dir for comparison."""
    od = Path(output_dir) if output_dir else None
    data = {"rtp":"—","max_win":"—","hit_freq":"—","vol_idx":"—","gdd_words":0,"symbols":0,"compliance":"—","gdd_sections":[],"rtp_breakdown":{},"ggr_365d":"—","arpdau":"—","roi_365d":"—","break_even_days":"—"}
    if not od or not od.exists(): return data
    sim_path = od / "03_math" / "simulation_results.json"
    if sim_path.exists():
        try:
            sim = json.loads(sim_path.read_text())
            data["rtp"]=sim.get("measured_rtp","—"); data["max_win"]=sim.get("max_win_achieved","—")
            data["hit_freq"]=sim.get("hit_frequency_pct",sim.get("hit_frequency","—")); data["vol_idx"]=sim.get("volatility_index","—")
            data["rtp_breakdown"]=sim.get("rtp_breakdown",{})
        except Exception as e: logger.debug(f"Sim metrics: {e}")
    pt_path = od / "03_math" / "paytable.csv"
    if pt_path.exists():
        try:
            import csv as _csv, io as _io
            data["symbols"] = max(0, sum(1 for _ in _csv.reader(_io.StringIO(pt_path.read_text()))) - 1)
        except Exception as e: logger.debug(f"Paytable parse: {e}")
    gdd_path = od / "02_design" / "gdd.md"
    if gdd_path.exists():
        try:
            gdd_text = gdd_path.read_text(encoding="utf-8", errors="replace")
            data["gdd_words"] = len(gdd_text.split())
            import re as _re; data["gdd_sections"] = _re.findall(r'^## .+', gdd_text, _re.MULTILINE)
        except Exception as e: logger.debug(f"GDD parse: {e}")
    comp_path = od / "05_legal" / "compliance_report.json"
    if comp_path.exists():
        try: data["compliance"] = json.loads(comp_path.read_text()).get("overall_status","—")
        except Exception as e: logger.debug(f"Compliance parse: {e}")
    rev_path = od / "08_revenue" / "revenue_projection.json"
    if rev_path.exists():
        try:
            rv = json.loads(rev_path.read_text())
            data["ggr_365d"] = rv.get("ggr_365d", "—")
            data["arpdau"] = rv.get("arpdau", "—")
            data["roi_365d"] = rv.get("roi_365d", "—")
            data["break_even_days"] = rv.get("break_even_days", "—")
        except Exception as e: logger.debug(f"Revenue parse: {e}")
    return data


@app.route("/job/<job_id>/diff/<other_id>")
@login_required
def job_diff(job_id, other_id):
    user = current_user(); db = get_db()
    job_a = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    job_b = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (other_id, user["id"])).fetchone()
    if not job_a or not job_b: return "Not found", 404
    a = _load_job_metrics(job_a["output_dir"]); b = _load_job_metrics(job_b["output_dir"])
    va = _rget(job_a, "version") or 1; vb = _rget(job_b, "version") or 1

    def _dc(label, val_a, val_b, fmt="", hib=None):
        sa = f"{val_a}{fmt}" if isinstance(val_a,(int,float)) else str(val_a)
        sb = f"{val_b}{fmt}" if isinstance(val_b,(int,float)) else str(val_b)
        delta = ""
        if isinstance(val_a,(int,float)) and isinstance(val_b,(int,float)):
            d = val_b - val_a; sign = "+" if d > 0 else ""
            color = "var(--text-muted)"
            if hib is True: color = "var(--success)" if d > 0 else ("var(--danger)" if d < 0 else color)
            elif hib is False: color = "var(--danger)" if d > 0 else ("var(--success)" if d < 0 else color)
            delta = f'<span style="font-size:11px;color:{color};margin-left:4px">{sign}{d:.2f}{fmt}</span>' if d != 0 else ""
        return f'<tr><td style="font-size:12px;color:var(--text-muted);padding:6px 0">{label}</td><td style="font-family:var(--mono);font-size:13px;padding:6px 12px">{sa}</td><td style="font-family:var(--mono);font-size:13px;font-weight:600;padding:6px 12px">{sb}{delta}</td></tr>'

    rows = _dc("Measured RTP",a["rtp"],b["rtp"],"%") + _dc("Max Win",a["max_win"],b["max_win"],"x") + _dc("Hit Frequency",a["hit_freq"],b["hit_freq"],"%",True) + _dc("Volatility Index",a["vol_idx"],b["vol_idx"],"") + _dc("Symbols",a["symbols"],b["symbols"],"") + _dc("GDD Words",a["gdd_words"],b["gdd_words"],"",True) + _dc("Compliance",a["compliance"],b["compliance"],"") + _dc("Annual GGR",a.get("ggr_365d","—"),b.get("ggr_365d","—"),"",True) + _dc("ARPDAU",a.get("arpdau","—"),b.get("arpdau","—"),"",True) + _dc("1Y ROI",a.get("roi_365d","—"),b.get("roi_365d","—"),"%",True) + _dc("Break-Even",a.get("break_even_days","—"),b.get("break_even_days","—")," days",False)

    rtp_a = a.get("rtp_breakdown",{}); rtp_b = b.get("rtp_breakdown",{})
    rtp_rows = "".join(_dc(k.replace("_"," ").title(), rtp_a.get(k,0), rtp_b.get(k,0), "%") for k in sorted(set(list(rtp_a)+list(rtp_b))) if isinstance(rtp_a.get(k,0),(int,float)) and isinstance(rtp_b.get(k,0),(int,float)))
    rtp_sec = f'<div class="card" style="margin-top:16px"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">RTP Breakdown</h2><table style="width:100%;border-collapse:collapse"><tr><th></th><th style="font-size:11px;color:var(--text-muted);text-align:left;padding:4px 12px">v{va}</th><th style="font-size:11px;color:var(--text-muted);text-align:left;padding:4px 12px">v{vb}</th></tr>{rtp_rows}</table></div>' if rtp_rows else ""

    secs_a = set(a.get("gdd_sections",[])); secs_b = set(b.get("gdd_sections",[]))
    gdd_diff = ""
    if (secs_b - secs_a) or (secs_a - secs_b):
        items = "".join(f'<div style="color:var(--success);font-size:12px">+ {s}</div>' for s in secs_b - secs_a)
        items += "".join(f'<div style="color:var(--danger);font-size:12px">- {s}</div>' for s in secs_a - secs_b)
        gdd_diff = f'<div class="card" style="margin-top:16px"><h2 style="font-size:15px;font-weight:600;margin-bottom:8px">GDD Section Changes</h2>{items}</div>'

    return layout(f'''<div style="margin-bottom:20px"><a href="/job/{job_id}/files" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Back to v{va}</a></div>
    <h2 class="page-title" style="margin-bottom:4px">&#8596; Version Diff</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:24px">{_esc(job_a["title"])} — v{va} vs v{vb}</p>
    <div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Key Metrics</h2>
        <table style="width:100%;border-collapse:collapse"><tr><th></th><th style="font-size:11px;color:var(--text-muted);text-align:left;padding:4px 12px">v{va}</th><th style="font-size:11px;color:var(--text-muted);text-align:left;padding:4px 12px">v{vb}</th></tr>{rows}</table></div>
    {rtp_sec}{gdd_diff}
    <div style="display:flex;gap:12px;margin-top:24px;margin-bottom:40px">
        <a href="/job/{job_id}/files" class="btn btn-ghost" style="flex:1;text-align:center">View v{va}</a>
        <a href="/job/{other_id}/files" class="btn btn-ghost" style="flex:1;text-align:center">View v{vb}</a></div>''', "history")


@app.route("/job/<job_id>/variants")
@login_required
def job_variants(job_id):
    user = current_user(); db = get_db()
    parent = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not parent: return "Not found", 404
    variants = db.execute("SELECT * FROM jobs WHERE parent_job_id=? AND job_type='variant' ORDER BY version", (job_id,)).fetchall()
    if not variants:
        return layout(f'<div class="card"><p style="color:var(--text-muted)">No variants yet.</p><a href="/history" class="btn btn-ghost" style="margin-top:12px">Back</a></div>', "history")

    variant_data = []
    for v in variants:
        m = _load_job_metrics(v["output_dir"]); params = json.loads(v["params"]) if v["params"] else {}
        vc = params.get("_variant", {})
        variant_data.append({
            "id": v["id"], "status": v["status"],
            "label": vc.get("label", f"V{_rget(v, 'version','?')}"),
            "icon": vc.get("icon", "🎰"),
            "strategy": vc.get("strategy", ""),
            "target_audience": vc.get("target_audience", ""),
            "rtp_budget": vc.get("rtp_budget", {}),
            "metrics": m,
            "output_dir": v["output_dir"],
            "version": _rget(v, "version") or 1,
        })

    all_complete = all(vd["status"] == "complete" for vd in variant_data)

    # ── Strategy Cards ──
    strat_cards = ""
    for vd in variant_data:
        sc = {"complete":"var(--success)","running":"var(--warning)","failed":"var(--danger)"}.get(vd["status"],"var(--text-dim)")
        badge = f'<span style="font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(34,197,94,.1);color:{sc}">{vd["status"]}</span>'
        budget_bars = ""
        for k, v_pct in vd["rtp_budget"].items():
            if isinstance(v_pct, (int, float)):
                budget_bars += f'<div style="display:flex;align-items:center;gap:6px;font-size:10px"><span style="width:90px;color:var(--text-dim)">{k.replace("_"," ").title()}</span><div style="flex:1;height:6px;background:var(--bg);border-radius:3px;overflow:hidden"><div style="height:100%;width:{min(100,v_pct)}%;background:var(--accent);border-radius:3px"></div></div><span style="color:var(--text-muted);width:30px;text-align:right">{v_pct}%</span></div>'

        audience = f'<div style="font-size:10px;color:var(--accent);margin-top:4px">🎯 {vd["target_audience"]}</div>' if vd["target_audience"] else ""
        rtp_val = vd["metrics"].get("rtp", "—")
        rtp_str = f'{rtp_val}%' if isinstance(rtp_val, (int, float)) else str(rtp_val)
        max_win = vd["metrics"].get("max_win", "—")
        max_str = f'{max_win}x' if isinstance(max_win, (int, float)) else str(max_win)

        strat_cards += f'''<div class="card" style="margin-bottom:8px;position:relative">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
                <div>
                    <h3 style="font-size:14px;font-weight:700;color:var(--text-bright);margin:0">{vd["icon"]} {vd["label"]}</h3>
                    <p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;max-width:400px">{vd["strategy"]}</p>
                    {audience}
                </div>
                <div style="display:flex;gap:6px;align-items:center">
                    {badge}
                    {'<a href="/job/'+vd["id"]+'/files" class="btn btn-ghost" style="font-size:11px;padding:4px 12px">View</a>' if vd["status"]=="complete" else ''}
                    {'<a href="/review/'+vd["id"]+'/interactive" class="btn btn-ghost" style="font-size:11px;padding:4px 12px;border-color:var(--accent);color:var(--accent)">Review</a>' if vd["status"]=="complete" else ''}
                </div>
            </div>
            <div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap">
                <div style="font-size:12px"><span style="color:var(--text-dim)">RTP:</span> <span style="font-weight:700;color:var(--accent)">{rtp_str}</span></div>
                <div style="font-size:12px"><span style="color:var(--text-dim)">Max Win:</span> <span style="font-weight:700;color:var(--warning)">{max_str}</span></div>
                <div style="font-size:12px"><span style="color:var(--text-dim)">Hit Rate:</span> <span style="font-weight:600">{vd["metrics"].get("hit_freq","—")}%</span></div>
                <div style="font-size:12px"><span style="color:var(--text-dim)">Vol:</span> <span style="font-weight:600">{vd["metrics"].get("vol_idx","—")}</span></div>
            </div>
            {('<div style="margin-top:10px;display:flex;flex-direction:column;gap:3px">' + budget_bars + '</div>') if budget_bars else ''}
        </div>'''

    # ── Comparison Table ──
    header = '<th style="font-size:11px;color:var(--text-muted);padding:6px 12px;text-align:left">Metric</th>'
    for vd in variant_data:
        sc = {"complete":"var(--success)","running":"var(--warning)","failed":"var(--danger)"}.get(vd["status"],"var(--text-dim)")
        header += f'<th style="font-size:12px;padding:6px 12px;text-align:left"><span style="font-weight:600;color:var(--text-bright)">{vd["icon"]} {vd["label"]}</span></th>'

    def _vr(label,key,fmt=""):
        c = f'<td style="font-size:12px;color:var(--text-muted);padding:6px 12px">{label}</td>'
        vals = []
        for vd in variant_data:
            val = vd["metrics"].get(key,"—")
            vals.append(val)
            c += f'<td style="font-family:var(--mono);font-size:13px;padding:6px 12px">{val}{fmt if isinstance(val,(int,float)) else ""}</td>'
        return f"<tr>{c}</tr>"

    trows = _vr("RTP","rtp","%")+_vr("Max Win","max_win","x")+_vr("Hit Freq","hit_freq","%")+_vr("Volatility","vol_idx","")+_vr("Symbols","symbols","")+_vr("GDD Words","gdd_words","")+_vr("Compliance","compliance","")+_vr("Annual GGR","ggr_365d","")+_vr("ARPDAU","arpdau","")+_vr("1Y ROI","roi_365d","%")+_vr("Break-Even","break_even_days"," days")

    # ── Mix-and-Match UI ──
    mix_html = ""
    if all_complete and len(variant_data) >= 2:
        comp_selectors = ""
        from flows.variant_mixer import MIXABLE_COMPONENTS
        for comp_type, comp_info in MIXABLE_COMPONENTS.items():
            opts = "".join(f'<option value="{vd["id"]}">{vd["icon"]} {vd["label"]}</option>' for vd in variant_data)
            comp_selectors += f'''<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                <span style="font-size:16px;width:24px;text-align:center">{comp_info["icon"]}</span>
                <span style="font-size:12px;font-weight:600;width:120px;color:var(--text-bright)">{comp_info["label"]}</span>
                <select name="mix_{comp_type}" style="flex:1;padding:6px 10px;font-size:12px;background:var(--bg-card);color:var(--text);border:1px solid var(--border);border-radius:6px">
                    {opts}
                </select>
                <span style="font-size:10px;color:var(--text-dim);width:180px">{comp_info["description"]}</span>
            </div>'''

        mix_html = f'''<div class="card" style="margin-top:16px;border-color:var(--accent)">
            <h2 style="font-size:15px;font-weight:700;margin-bottom:4px">🔀 Mix-and-Match</h2>
            <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Combine the best components from each variant into a hybrid game.</p>
            <form method="POST" action="/api/variants/{job_id}/mix">
                {comp_selectors}
                <button type="submit" class="btn btn-primary" style="margin-top:12px;width:100%;padding:12px">🧬 Create Hybrid Game</button>
            </form>
        </div>'''

    return layout(f'''<div style="margin-bottom:20px"><a href="/history" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; History</a></div>
    <h2 class="page-title" style="margin-bottom:4px">&#128256; Variant Comparison</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:24px">{_esc(parent["title"])} — {len(variant_data)} variants{" (all complete)" if all_complete else ""}
        <a href="/job/{job_id}/variants/compare" style="color:var(--accent);font-size:11px;margin-left:12px;text-decoration:none">📈 Open Interactive Charts →</a>
    </p>

    <div style="margin-bottom:16px">{strat_cards}</div>

    <div class="card" style="overflow-x:auto"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">📊 Side-by-Side Comparison</h2>
        <table style="width:100%;border-collapse:collapse"><tr>{header}</tr>{trows}</table></div>

    {mix_html}

    <div style="margin-top:24px;margin-bottom:40px"><a href="/history" class="btn btn-ghost">Back</a></div>''', "history")


@app.route("/api/variants", methods=["POST"])
@login_required
def api_launch_variants():
    user = current_user()
    limit_err = _check_job_limit(user["id"])
    if limit_err: return limit_err
    variant_count = max(2, min(int(request.form.get("variant_count", 3)), 5))
    base_params = {"theme":request.form["theme"],"target_markets":[m.strip() for m in request.form.get("target_markets","Georgia, Texas").split(",")],"volatility":request.form.get("volatility","medium"),"target_rtp":float(request.form.get("target_rtp",96)),"grid_cols":int(request.form.get("grid_cols",5)),"grid_rows":int(request.form.get("grid_rows",3)),"ways_or_lines":request.form.get("ways_or_lines","243"),"max_win_multiplier":int(request.form.get("max_win_multiplier",5000)),"art_style":request.form.get("art_style","Cinematic realism"),"requested_features":request.form.getlist("features"),"competitor_references":[r.strip() for r in request.form.get("competitor_references","").split(",") if r.strip()],"special_requirements":request.form.get("special_requirements",""),"enable_recon":request.form.get("enable_recon")=="on"}

    parent_id = str(uuid.uuid4())[:8]; db = get_db()
    db.execute("INSERT INTO jobs (id,user_id,job_type,title,params,status,current_stage) VALUES (?,?,?,?,?,?,?)",
        (parent_id,user["id"],"variant_parent",f"{base_params['theme']} (variants)",json.dumps(base_params),"running",f"Generating {variant_count} variant strategies"))
    db.commit()

    # Phase 9: Use strategy engine for divergent variants
    from flows.variant_strategy import generate_variant_strategies, build_variant_params
    strategies = generate_variant_strategies(base_params["theme"], base_params, variant_count)

    variant_ids = []
    for i, strat in enumerate(strategies):
        vid = str(uuid.uuid4())[:8]; variant_ids.append(vid)
        vp = build_variant_params(base_params, strat, i)
        label = strat.get("label", f"Variant {i+1}")
        icon = strat.get("icon", "🎰")

        db2 = get_db()
        db2.execute("INSERT INTO jobs (id,user_id,job_type,title,params,status,parent_job_id,version) VALUES (?,?,?,?,?,?,?,?)",
            (vid,user["id"],"variant",f"{icon} {base_params['theme']} — {label}",json.dumps(vp),"queued",parent_id,i+1))
        db2.commit()
        enqueue_job("pipeline", vid, json.dumps(vp))

    db3 = get_db()
    db3.execute("UPDATE jobs SET params=?,current_stage=? WHERE id=?",
        (json.dumps({**base_params,"_variant_ids":variant_ids,"_strategies":[s.get("label","") for s in strategies]}),f"{variant_count} variants running",parent_id))
    db3.commit()
    return redirect(f"/job/{parent_id}/variants")


@app.route("/api/variants/<parent_id>/mix", methods=["POST"])
@login_required
def api_mix_variants(parent_id):
    """Create a hybrid game by mixing components from different variants."""
    from flows.variant_mixer import create_hybrid, build_hybrid_params, MIXABLE_COMPONENTS
    user = current_user()
    limit_err = _check_job_limit(user["id"])
    if limit_err: return limit_err

    db = get_db()
    parent = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (parent_id, user["id"])).fetchone()
    if not parent: return "Not found", 404

    # Get all variant jobs
    variant_rows = db.execute("SELECT * FROM jobs WHERE parent_job_id=? AND job_type='variant' AND status='complete'", (parent_id,)).fetchall()
    variants = {}
    for v in variant_rows:
        params = json.loads(v["params"]) if v["params"] else {}
        vc = params.get("_variant", {})
        variants[v["id"]] = {
            "output_dir": v["output_dir"],
            "params": params,
            "label": vc.get("label", f"V{v['version']}"),
        }

    # Parse selections from form
    selections = {}
    for comp_type in MIXABLE_COMPONENTS:
        vid = request.form.get(f"mix_{comp_type}")
        if vid and vid in variants:
            selections[comp_type] = vid

    if not selections:
        return redirect(f"/job/{parent_id}/variants")

    # Create hybrid job
    base_params = json.loads(parent["params"]) if parent["params"] else {}
    hybrid_id = str(uuid.uuid4())[:8]

    slug = "".join(c if c.isalnum() else "_" for c in base_params.get("theme", "hybrid").lower())[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = str(Path(os.getenv("OUTPUT_DIR", "./output")) / f"hybrid_{slug}_{ts}")

    # Create the hybrid by copying components
    manifest = create_hybrid(selections, variants, base_params, output_dir)

    # Build hybrid params for potential re-run
    hybrid_params = build_hybrid_params(base_params, selections, variants)
    hybrid_params["_hybrid"]["manifest"] = manifest

    # Insert hybrid job
    source_labels = ", ".join(f"{MIXABLE_COMPONENTS.get(k,{}).get('icon','')} {variants.get(v,{}).get('label',v)}" for k,v in selections.items())
    db.execute(
        "INSERT INTO jobs (id,user_id,job_type,title,params,status,parent_job_id,output_dir,completed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (hybrid_id, user["id"], "hybrid", f"🧬 Hybrid: {base_params.get('theme','')}",
         json.dumps(hybrid_params), "complete", parent_id, output_dir, datetime.now().isoformat())
    )
    db.commit()

    logger.info(f"Created hybrid {hybrid_id} from {len(selections)} components: {source_labels}")
    return redirect(f"/job/{hybrid_id}/files")


@app.route("/api/variants/<parent_id>/components")
@login_required
def api_variant_components(parent_id):
    """Get available components for each variant (for mix-and-match UI)."""
    from flows.variant_mixer import get_variant_components
    db = get_db()
    user = current_user()
    variants = db.execute(
        "SELECT id, output_dir, params, version FROM jobs WHERE parent_job_id=? AND job_type='variant' AND status='complete' AND user_id=?",
        (parent_id, user["id"])
    ).fetchall()

    result = {}
    for v in variants:
        params = json.loads(v["params"]) if v["params"] else {}
        vc = params.get("_variant", {})
        result[v["id"]] = {
            "label": vc.get("label", f"V{v['version']}"),
            "icon": vc.get("icon", "🎰"),
            "components": get_variant_components(v["output_dir"]),
        }
    return jsonify(result)


@app.route("/job/<job_id>/variants/compare")
@login_required
def job_variants_compare_spa(job_id):
    """Serve React SPA variant comparison dashboard."""
    user = current_user(); db = get_db()
    parent = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not parent: return "Not found", 404

    variants = db.execute("SELECT * FROM jobs WHERE parent_job_id=? AND job_type='variant' ORDER BY version", (job_id,)).fetchall()
    variant_data = []
    for v in variants:
        m = _load_job_metrics(v["output_dir"])
        params = json.loads(v["params"]) if v["params"] else {}
        vc = params.get("_variant", {})
        variant_data.append({
            "id": v["id"], "status": v["status"],
            "label": vc.get("label", f"V{_rget(v, 'version', '?')}"),
            "icon": vc.get("icon", "🎰"),
            "strategy": vc.get("strategy", ""),
            "target_audience": vc.get("target_audience", ""),
            "rtp_budget": vc.get("rtp_budget", {}),
            "metrics": m,
        })

    spa_path = Path(__file__).parent / "static" / "review-app" / "variant-compare.html"
    if not spa_path.exists():
        return "Comparison app not found", 500

    base_params = json.loads(parent["params"]) if parent["params"] else {}
    html = spa_path.read_text(encoding="utf-8")
    html = html.replace("__VARIANTS__", json.dumps(variant_data, default=str))
    html = html.replace("__PARENT_ID__", job_id)
    html = html.replace("__THEME__", _esc(base_params.get("theme", "Variants")))
    return html


@app.route("/api/variants/preview-strategies", methods=["POST"])
@login_required
def api_preview_strategies():
    """Preview what variant strategies would be generated (before launching)."""
    from flows.variant_strategy import generate_variant_strategies
    body = request.get_json(silent=True) or {}
    theme = body.get("theme", request.form.get("theme", "Slot Game"))
    count = int(body.get("count", request.form.get("variant_count", 3)))
    base_params = {
        "theme": theme,
        "target_rtp": float(body.get("target_rtp", 96)),
        "volatility": body.get("volatility", "medium"),
        "max_win_multiplier": int(body.get("max_win_multiplier", 5000)),
        "requested_features": body.get("requested_features", []),
    }
    strategies = generate_variant_strategies(theme, base_params, count, use_llm=False)
    return jsonify([{
        "label": s.get("label"), "icon": s.get("icon"),
        "strategy": s.get("strategy"), "volatility": s.get("volatility"),
        "rtp_budget": s.get("rtp_budget"), "max_win_multiplier": s.get("max_win_multiplier"),
        "features": s.get("features", [])[:5], "target_audience": s.get("target_audience"),
    } for s in strategies])


# ─── REVENUE DASHBOARD (Phase 5B) ───

@app.route("/job/<job_id>/revenue")
@login_required
def job_revenue(job_id):
    user = current_user(); db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not job: return "Not found", 404
    op = Path(job["output_dir"]) if job["output_dir"] else None
    rev_file = op / "08_revenue" / "revenue_projection.json" if op else None
    if not rev_file or not rev_file.exists():
        return layout(f'<div class="card"><p style="color:var(--text-muted)">No revenue projection available for this job.</p><a href="/job/{job_id}/files" class="btn btn-ghost" style="margin-top:12px">Back</a></div>', "history")

    try:
        rev = json.loads(rev_file.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return layout(f'<div class="card"><p style="color:var(--text-muted)">Revenue data is corrupted. Re-run the pipeline to regenerate.</p><a href="/job/{job_id}/files" class="btn btn-ghost" style="margin-top:12px">Back</a></div>', "history")

    # ── Hero metrics ──
    hero = f'''<div class="row3" style="margin-bottom:24px">
        <div class="stat-card"><div class="stat-val" style="font-size:24px">${rev.get("ggr_365d",0):,.0f}</div><div class="stat-label">Annual GGR (365d)</div></div>
        <div class="stat-card"><div class="stat-val" style="font-size:24px">${rev.get("arpdau",0):.2f}</div><div class="stat-label">ARPDAU</div></div>
        <div class="stat-card"><div class="stat-val" style="font-size:24px">{rev.get("hold_pct",0)}%</div><div class="stat-label">Effective Hold</div></div>
    </div>
    <div class="row3" style="margin-bottom:24px">
        <div class="stat-card"><div class="stat-val" style="font-size:20px">{rev.get("break_even_days","?")} days</div><div class="stat-label">Break-Even</div></div>
        <div class="stat-card"><div class="stat-val" style="font-size:20px;color:{"var(--success)" if rev.get("roi_365d",0)>0 else "var(--danger)"}">{rev.get("roi_365d",0):+.1f}%</div><div class="stat-label">1-Year ROI</div></div>
        <div class="stat-card"><div class="stat-val" style="font-size:20px">{rev.get("daily_active_users",0):,}</div><div class="stat-label">Projected DAU</div></div>
    </div>'''

    # ── GGR Period Cards ──
    periods = f'''<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px">
        <div style="padding:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;text-align:center">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">30-Day</div>
            <div style="font-size:18px;font-weight:700;color:var(--text-bright)">${rev.get("ggr_30d",0):,.0f}</div></div>
        <div style="padding:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;text-align:center">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">90-Day</div>
            <div style="font-size:18px;font-weight:700;color:var(--text-bright)">${rev.get("ggr_90d",0):,.0f}</div></div>
        <div style="padding:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;text-align:center">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">180-Day</div>
            <div style="font-size:18px;font-weight:700;color:var(--text-bright)">${rev.get("ggr_180d",0):,.0f}</div></div>
        <div style="padding:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;text-align:center">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">365-Day</div>
            <div style="font-size:18px;font-weight:700;color:var(--text-bright)">${rev.get("ggr_365d",0):,.0f}</div></div>
    </div>'''

    # ── Monthly GGR Chart (CSS bar chart) ──
    monthly = rev.get("ggr_monthly", [])
    max_ggr = max((m.get("ggr", 0) for m in monthly), default=1) or 1
    bars = ""
    for m in monthly[:12]:
        pct = min(100, int(m.get("ggr", 0) / max_ggr * 100))
        ggr_val = m.get("ggr", 0)
        bars += f'''<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px">
            <span style="font-size:9px;color:var(--text-dim);font-family:var(--mono)">${ggr_val:,.0f}</span>
            <div style="width:100%;height:{max(4, pct)}px;max-height:80px;background:linear-gradient(to top,rgba(255,255,255,0.08),rgba(255,255,255,0.2));border-radius:4px 4px 0 0"></div>
            <span style="font-size:10px;color:var(--text-muted)">M{m.get("month","")}</span>
            <span style="font-size:9px;color:var(--text-dim)">{m.get("dau",0):,} DAU</span></div>'''
    chart = f'''<div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:16px">Monthly GGR Projection</h2>
        <div style="display:flex;gap:4px;align-items:flex-end;height:120px;padding:24px 0 0">{bars}</div></div>'''

    # ── Market Breakdown ──
    mkt_rows = ""
    for mk in rev.get("market_breakdown", []):
        cap = mk.get("captured_players", 0)
        annual = mk.get("ggr_365d", 0)
        pct = mk.get("pct_of_total", 0)
        bar_w = max(2, int(pct))
        mkt_rows += f'''<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
            <div style="width:60px;font-size:12px;font-weight:600;color:var(--text-bright)">{mk.get("market","").upper()}</div>
            <div style="flex:1;height:6px;background:var(--bg-input);border-radius:3px;overflow:hidden"><div style="width:{bar_w}%;height:100%;background:rgba(255,255,255,0.2);border-radius:3px"></div></div>
            <div style="width:90px;text-align:right;font-family:var(--mono);font-size:12px;color:var(--text-bright)">${annual:,.0f}</div>
            <div style="width:50px;text-align:right;font-size:11px;color:var(--text-muted)">{pct}%</div>
            <div style="width:80px;text-align:right;font-size:11px;color:var(--text-dim)">{cap:,} players</div></div>'''
    markets_card = f'<div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Market Breakdown</h2>{mkt_rows}</div>'

    # ── Sensitivity Analysis ──
    sens_rows = ""
    for s in rev.get("sensitivity", []):
        is_current = s.get("delta_pct", 0) == 0
        bg = "background:rgba(255,255,255,0.03)" if is_current else ""
        fw = "font-weight:700" if is_current else ""
        dc = "var(--success)" if s.get("delta_pct", 0) > 0 else ("var(--danger)" if s.get("delta_pct", 0) < 0 else "var(--text-muted)")
        marker = " ← current" if is_current else ""
        sens_rows += f'<tr style="{bg}"><td style="padding:6px 12px;font-family:var(--mono);font-size:12px;{fw}">{s.get("rtp",0)}%{marker}</td><td style="padding:6px 12px;font-family:var(--mono);font-size:12px">{s.get("hold_pct",0)}%</td><td style="padding:6px 12px;font-family:var(--mono);font-size:12px">${s.get("ggr_365d",0):,.0f}</td><td style="padding:6px 12px;font-size:12px;color:{dc}">{s.get("delta_pct",0):+.1f}%</td></tr>'
    sensitivity_card = f'''<div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Sensitivity Analysis — What if RTP changes?</h2>
        <table style="width:100%;border-collapse:collapse"><tr><th style="font-size:11px;color:var(--text-muted);padding:6px 12px;text-align:left">RTP</th><th style="font-size:11px;color:var(--text-muted);padding:6px 12px;text-align:left">Hold %</th><th style="font-size:11px;color:var(--text-muted);padding:6px 12px;text-align:left">Annual GGR</th><th style="font-size:11px;color:var(--text-muted);padding:6px 12px;text-align:left">Delta</th></tr>{sens_rows}</table></div>'''

    # ── Benchmark Comparison ──
    bench_rows = ""
    for b in rev.get("benchmarks", []):
        sim_bar = max(2, int(b.get("similarity_pct", 0)))
        bench_rows += f'''<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
            <div style="width:120px;font-size:12px;font-weight:500;color:var(--text-bright)">{b.get("title","")}</div>
            <div style="width:60px;font-size:11px;color:var(--text-dim)">{b.get("volatility","")}</div>
            <div style="width:60px;font-size:11px;color:var(--text-muted)">{b.get("rtp",0)}%</div>
            <div style="flex:1;height:4px;background:var(--bg-input);border-radius:2px"><div style="width:{sim_bar}%;height:100%;background:rgba(255,255,255,0.2);border-radius:2px"></div></div>
            <div style="width:50px;text-align:right;font-size:11px;color:var(--text-muted)">{b.get("similarity_pct",0)}%</div>
            <div style="width:50px;text-align:right;font-size:11px;color:var(--text-dim)">{b.get("performance_vs_ours","")}</div></div>'''
    benchmark_card = f'<div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Benchmark Comparison</h2>{bench_rows}</div>'

    # ── Investment Breakdown ──
    dev_cost = rev.get("total_dev_cost", 0)
    cert_cost = rev.get("cert_cost", 0)
    feature_cost = dev_cost - 45000 - 12000 - 5000 - cert_cost  # Reverse-calculate feature cost
    invest_card = f'''<div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Investment Analysis</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
            <div style="padding:8px;border:1px solid var(--border);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">Base Dev</div><div style="font-size:14px;font-weight:600;color:var(--text-bright)">$45,000</div></div>
            <div style="padding:8px;border:1px solid var(--border);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">Features</div><div style="font-size:14px;font-weight:600;color:var(--text-bright)">${max(0,feature_cost):,.0f}</div></div>
            <div style="padding:8px;border:1px solid var(--border);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">Art + Audio</div><div style="font-size:14px;font-weight:600;color:var(--text-bright)">$17,000</div></div>
            <div style="padding:8px;border:1px solid var(--border);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">Certification</div><div style="font-size:14px;font-weight:600;color:var(--text-bright)">${cert_cost:,.0f}</div></div>
        </div>
        <div style="margin-top:12px;padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;display:flex;justify-content:space-between">
            <div><div style="font-size:11px;color:var(--text-muted)">Total Investment</div><div style="font-size:18px;font-weight:700;color:var(--text-bright)">${dev_cost:,.0f}</div></div>
            <div style="text-align:right"><div style="font-size:11px;color:var(--text-muted)">Net Profit (Year 1)</div><div style="font-size:18px;font-weight:700;color:{"var(--success)" if rev.get("ggr_365d",0)-dev_cost>0 else "var(--danger)"}">${rev.get("ggr_365d",0)-dev_cost:,.0f}</div></div>
        </div></div>'''

    # ── Operator Scenarios ──
    op_rows = ""
    for ops in rev.get("operator_scenarios", []):
        op_rows += f'''<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
            <div style="width:80px;font-size:12px;font-weight:600;color:var(--text-bright)">{ops.get("type","").replace("_"," ").title()}</div>
            <div style="flex:1;font-family:var(--mono);font-size:13px;color:var(--text-bright)">${ops.get("ggr_365d",0):,.0f}</div>
            <div style="font-size:11px;color:var(--text-muted)">Margin: {ops.get("margin_pct",0)}%</div></div>'''
    ops_card = f'<div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Operator Type Scenarios</h2>{op_rows}</div>'

    # ── Risk + Vol Profile ──
    cannibal = rev.get("cannibalization_risk", "?")
    cannibal_c = {"low":"var(--success)","medium":"var(--warning)","high":"var(--danger)"}.get(cannibal, "var(--text-muted)")
    risk_card = f'''<div class="card"><h2 style="font-size:15px;font-weight:600;margin-bottom:12px">Risk Profile</h2>
        <div style="margin-bottom:12px"><label style="font-size:11px">Cannibalization Risk</label><div style="font-size:16px;font-weight:600;color:{cannibal_c}">{cannibal.upper()}</div></div>
        <div style="margin-bottom:12px"><label style="font-size:11px">Theme Appeal</label><div style="font-size:16px;font-weight:600;color:var(--text-bright)">{rev.get("theme_appeal",1.0)}x</div></div>
        <div><label style="font-size:11px">Volatility Profile</label><p style="font-size:12px;color:var(--text-muted);margin-top:4px">{rev.get("volatility_profile","")}</p></div></div>'''

    return layout(f'''
    <div style="margin-bottom:20px"><a href="/job/{job_id}/files" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Back to {_esc(job["title"])}</a></div>
    <h2 class="page-title" style="margin-bottom:4px">&#128176; Revenue Dashboard</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:24px">{_esc(job["title"])} — Financial Projections</p>
    {hero}{periods}{chart}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div>{markets_card}{invest_card}{ops_card}</div>
        <div>{sensitivity_card}{benchmark_card}{risk_card}</div>
    </div>
    <div style="margin:24px 0 40px"><a href="/job/{job_id}/files" class="btn btn-ghost">Back to files</a></div>''', "history")


# ─── ENGINE EXPORT (Phase 6B) ───

@app.route("/api/job/<job_id>/export")
@login_required
def api_export(job_id):
    """Generate and download engine export package (Phase 10: all formats)."""
    user = current_user(); db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not job or not job["output_dir"]:
        return "Not found", 404

    fmt = request.args.get("format", "unity").lower()

    # Phase 10: Accept all new formats
    from tools.export_formats import EXPORT_FORMATS
    valid_formats = set(EXPORT_FORMATS.keys()) | {"unity", "godot", "generic"}
    if fmt not in valid_formats:
        return f"Invalid format. Use: {', '.join(sorted(valid_formats))}", 400

    od = Path(job["output_dir"])

    # Check if pre-generated ZIP exists
    export_dir = od / "09_export"
    if export_dir.exists():
        for zf_path in export_dir.glob("*.zip"):
            if fmt in zf_path.name.lower():
                _record_export(user["id"], job_id, fmt, str(zf_path), zf_path.stat().st_size)
                return send_from_directory(zf_path.parent, zf_path.name, as_attachment=True,
                                            download_name=zf_path.name)

    # Generate on the fly
    try:
        from tools.export_engine import generate_export_v2
        params = json.loads(job["params"]) if job["params"] else {}
        export_params = {
            "grid_cols": params.get("grid_cols", 5),
            "grid_rows": params.get("grid_rows", 3),
            "ways_or_lines": params.get("ways_or_lines", 243),
            "target_rtp": params.get("target_rtp", 96.0),
            "max_win": params.get("max_win_multiplier", 5000),
            "max_win_multiplier": params.get("max_win_multiplier", 5000),
            "volatility": params.get("volatility", "medium"),
            "art_style": params.get("art_style", "Cinematic realism"),
            "target_markets": params.get("target_markets", []),
            "features": params.get("requested_features", []),
        }
        zip_path = generate_export_v2(
            output_dir=str(od), format=fmt,
            game_title=job["title"], game_params=export_params,
        )
        zp = Path(zip_path)
        _record_export(user["id"], job_id, fmt, zip_path, zp.stat().st_size)
        return send_from_directory(zp.parent, zp.name, as_attachment=True,
                                    download_name=zp.name)
    except Exception as e:
        logger.error(f"Export failed for {job_id} format={fmt}: {e}")
        return f"Export failed: {e}", 500


def _record_export(user_id, job_id, fmt, file_path, file_size, file_count=0):
    """Record export in history table."""
    try:
        import zipfile as _zf
        if file_count == 0 and file_path and Path(file_path).exists():
            try:
                with _zf.ZipFile(file_path) as z: file_count = len(z.namelist())
            except Exception: pass
        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO export_history (id,job_id,user_id,format,file_path,file_size,file_count,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4())[:8], job_id, user_id, fmt, str(file_path), file_size, file_count, "complete", datetime.now().isoformat())
        )
        db.commit()
    except Exception as e:
        logger.debug(f"Export history record failed: {e}")


@app.route("/api/job/<job_id>/export/batch")
@login_required
def api_export_batch(job_id):
    """Generate all export formats and download as a single mega-ZIP."""
    user = current_user(); db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not job or not job["output_dir"]:
        return "Not found", 404

    from tools.export_formats import EXPORT_FORMATS
    from tools.export_engine import generate_export_v2
    import zipfile

    od = Path(job["output_dir"])
    params = json.loads(job["params"]) if job["params"] else {}
    export_params = {
        "grid_cols": params.get("grid_cols", 5), "grid_rows": params.get("grid_rows", 3),
        "ways_or_lines": params.get("ways_or_lines", 243), "target_rtp": params.get("target_rtp", 96.0),
        "max_win": params.get("max_win_multiplier", 5000), "max_win_multiplier": params.get("max_win_multiplier", 5000),
        "volatility": params.get("volatility", "medium"), "art_style": params.get("art_style", "Cinematic realism"),
        "target_markets": params.get("target_markets", []), "features": params.get("requested_features", []),
    }

    # Selected formats (or all)
    selected = request.args.get("formats", "").split(",")
    selected = [f.strip() for f in selected if f.strip() in EXPORT_FORMATS]
    if not selected:
        selected = list(EXPORT_FORMATS.keys())

    slug = "".join(c if c.isalnum() else "_" for c in (job.get("title") or "export").lower())[:30]
    batch_dir = od / "09_export"
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_zip_path = batch_dir / f"{slug}_all_exports.zip"

    results = {}
    with zipfile.ZipFile(batch_zip_path, "w", zipfile.ZIP_DEFLATED) as mega:
        for fmt in selected:
            try:
                zip_path = generate_export_v2(
                    output_dir=str(od), format=fmt,
                    game_title=job["title"], game_params=export_params,
                )
                zp = Path(zip_path)
                mega.write(zp, f"exports/{zp.name}")
                results[fmt] = {"ok": True, "size": zp.stat().st_size}
                _record_export(user["id"], job_id, fmt, zip_path, zp.stat().st_size)
            except Exception as e:
                logger.warning(f"Batch export {fmt} failed: {e}")
                results[fmt] = {"ok": False, "error": str(e)}

    _record_export(user["id"], job_id, "batch_all", str(batch_zip_path), batch_zip_path.stat().st_size)

    return send_from_directory(batch_zip_path.parent, batch_zip_path.name,
                                as_attachment=True, download_name=batch_zip_path.name)


@app.route("/api/job/<job_id>/export/preview")
@login_required
def api_export_preview(job_id):
    """Preview what each export format would generate without downloading."""
    from tools.export_formats import EXPORT_FORMATS

    user = current_user(); db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not job or not job["output_dir"]:
        return jsonify({"error": "Not found"}), 404

    od = Path(job["output_dir"])

    # Check available source data
    sources = {
        "paytable_csv": (od / "03_math" / "paytable.csv").exists(),
        "paytable_json": (od / "03_math" / "paytable.json").exists(),
        "reel_strips": any((od / "03_math" / f).exists() for f in ["BaseReels.csv", "reel_strips.csv", "reelstrips.json"]),
        "gdd": any((od / "02_design" / f).exists() for f in ["gdd.md", "game_design_document.md"]),
        "simulation": (od / "03_math" / "simulation_results.json").exists(),
        "art_assets": (od / "04_art").exists() and any((od / "04_art").glob("*.png")),
        "compliance": (od / "05_legal").exists(),
        "revenue": (od / "08_revenue").exists(),
    }

    # Check existing exports
    export_dir = od / "09_export"
    existing = {}
    if export_dir.exists():
        for zf in export_dir.glob("*.zip"):
            for fmt_key in EXPORT_FORMATS:
                if fmt_key in zf.name.lower():
                    existing[fmt_key] = {"path": zf.name, "size": zf.stat().st_size, "cached": True}

    # Check export history
    history = db.execute(
        "SELECT format, created_at, file_size FROM export_history WHERE job_id=? ORDER BY created_at DESC",
        (job_id,)
    ).fetchall()
    history_map = {}
    for h in history:
        if h["format"] not in history_map:
            history_map[h["format"]] = {"last_exported": h["created_at"], "size": h["file_size"]}

    formats = {}
    for fmt_key, fmt_info in EXPORT_FORMATS.items():
        formats[fmt_key] = {
            "label": fmt_info["label"],
            "icon": fmt_info["icon"],
            "description": fmt_info["description"],
            "cached": fmt_key in existing,
            "cached_size": existing.get(fmt_key, {}).get("size", 0),
            "last_exported": history_map.get(fmt_key, {}).get("last_exported"),
        }

    return jsonify({"sources": sources, "formats": formats, "existing": existing})


@app.route("/job/<job_id>/exports")
@login_required
def job_export_dashboard(job_id):
    """Dedicated export dashboard page with all formats, previews, and history."""
    user = current_user(); db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not job or not job["output_dir"]:
        return "Not found", 404

    from tools.export_formats import EXPORT_FORMATS
    od = Path(job["output_dir"])

    # Source data availability
    has_paytable = (od / "03_math" / "paytable.csv").exists() or (od / "03_math" / "paytable.json").exists()
    has_reels = any((od / "03_math" / f).exists() for f in ["BaseReels.csv", "reel_strips.csv", "reelstrips.json"])
    has_gdd = any((od / "02_design" / f).exists() for f in ["gdd.md", "game_design_document.md"])
    has_sim = (od / "03_math" / "simulation_results.json").exists()
    has_art = (od / "04_art").exists() and any((od / "04_art").glob("*.png"))

    source_items = ""
    for label, ok in [("Paytable", has_paytable), ("Reel Strips", has_reels), ("GDD", has_gdd), ("Simulation", has_sim), ("Art Assets", has_art)]:
        color = "var(--success)" if ok else "var(--danger)"
        icon = "✅" if ok else "❌"
        source_items += f'<span style="font-size:11px;color:{color};margin-right:12px">{icon} {label}</span>'

    # Existing exports
    export_dir = od / "09_export"
    cached = {}
    if export_dir.exists():
        for zf in export_dir.glob("*.zip"):
            for fmt_key in EXPORT_FORMATS:
                if fmt_key in zf.name.lower():
                    cached[fmt_key] = {"name": zf.name, "size": zf.stat().st_size / 1024}

    # Export history
    history = db.execute(
        "SELECT format, created_at, file_size, file_count FROM export_history WHERE job_id=? ORDER BY created_at DESC LIMIT 20",
        (job_id,)
    ).fetchall()
    history_html = ""
    if history:
        hrows = ""
        for h in history:
            fmt_info = EXPORT_FORMATS.get(h["format"], {})
            icon = fmt_info.get("icon", "📦")
            label = fmt_info.get("label", h["format"])
            size_kb = (h["file_size"] or 0) / 1024
            hrows += f'<tr><td style="padding:4px 8px;font-size:11px">{icon} {label}</td><td style="padding:4px 8px;font-size:11px;color:var(--text-dim)">{h["created_at"][:16]}</td><td style="padding:4px 8px;font-size:11px;font-family:var(--mono)">{size_kb:.1f} KB</td><td style="padding:4px 8px;font-size:11px">{h["file_count"] or "?"} files</td></tr>'
        history_html = f'<div class="card" style="margin-top:16px"><h2 style="font-size:14px;font-weight:600;margin-bottom:8px">📜 Export History</h2><table style="width:100%;border-collapse:collapse">{hrows}</table></div>'

    # Format cards
    format_cards = ""
    for fmt_key, fmt_info in EXPORT_FORMATS.items():
        is_cached = fmt_key in cached
        cache_badge = f'<span style="font-size:9px;padding:2px 6px;border-radius:8px;background:rgba(34,197,94,.15);color:var(--success);margin-left:6px">cached {cached[fmt_key]["size"]:.0f}KB</span>' if is_cached else ""
        format_cards += f'''<div style="display:flex;align-items:center;justify-content:space-between;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:8px;margin-bottom:6px">
            <div style="flex:1">
                <div style="font-size:13px;font-weight:600;color:var(--text-bright)">{fmt_info["icon"]} {fmt_info["label"]}{cache_badge}</div>
                <div style="font-size:10px;color:var(--text-dim);margin-top:2px">{fmt_info["description"]}</div>
            </div>
            <a href="/api/job/{job_id}/export?format={fmt_key}" class="btn btn-ghost" style="font-size:11px;padding:6px 14px;white-space:nowrap">📥 Download</a>
        </div>'''

    return layout(f'''<div style="margin-bottom:20px"><a href="/job/{job_id}/files" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Back to Files</a></div>
    <h2 class="page-title" style="margin-bottom:4px">🎮 Export Pipeline</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:16px">{_esc(job["title"])} — Production-grade export packages</p>

    <div class="card" style="margin-bottom:12px">
        <h2 style="font-size:14px;font-weight:600;margin-bottom:8px">📦 Source Data</h2>
        <div style="display:flex;flex-wrap:wrap;gap:4px">{source_items}</div>
    </div>

    <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h2 style="font-size:14px;font-weight:600;margin:0">Available Formats ({len(EXPORT_FORMATS)})</h2>
            <a href="/api/job/{job_id}/export/batch" class="btn btn-primary" style="font-size:11px;padding:6px 14px">⚡ Download All Formats</a>
        </div>
        {format_cards}
    </div>

    {history_html}

    <div style="margin-top:24px;margin-bottom:40px"><a href="/job/{job_id}/files" class="btn btn-ghost">Back to Files</a></div>''', "history")


# ─── PORTFOLIO INTELLIGENCE (Phase 11) ───

@app.route("/portfolio")
@login_required
def portfolio_dashboard():
    """Portfolio Intelligence Dashboard — React SPA."""
    from tools.portfolio_engine import get_portfolio_overview, analyze_gaps, build_coverage_heatmap, get_trend_signals, calculate_alignment_score, capture_snapshot, get_snapshots
    from tools.market_scraper import seed_market_data, get_trend_summary

    user = current_user(); db = get_db()
    seed_market_data(db)

    overview = get_portfolio_overview(db, user["id"])
    gaps = analyze_gaps(overview)
    heatmap = build_coverage_heatmap(overview)
    trends = get_trend_signals()
    market = get_trend_summary(db)
    alignment = calculate_alignment_score(overview)
    snapshots = get_snapshots(db, user["id"], 12)

    # Auto-capture daily snapshot
    if overview.get("total_games", 0) > 0:
        today = datetime.now().strftime("%Y-%m-%d")
        existing_snap = db.execute(
            "SELECT id FROM portfolio_snapshots WHERE user_id=? AND snapshot_date=?",
            (user["id"], today)
        ).fetchone()
        if not existing_snap:
            try:
                capture_snapshot(db, user["id"], overview)
            except Exception as e:
                logger.debug(f"Auto-snapshot failed: {e}")

    spa_path = Path(__file__).parent / "static" / "portfolio" / "index.html"
    if not spa_path.exists():
        return "Portfolio dashboard not found", 500

    data = {
        "overview": overview,
        "gaps": gaps,
        "heatmap": heatmap,
        "trends": trends,
        "market": market,
        "alignment": alignment,
        "snapshots": snapshots,
    }
    html = spa_path.read_text(encoding="utf-8")
    html = html.replace("__PORTFOLIO_DATA__", json.dumps(data, default=str))
    return html


@app.route("/api/portfolio/overview")
@login_required
def api_portfolio_overview():
    """Portfolio overview as JSON."""
    from tools.portfolio_engine import get_portfolio_overview
    user = current_user(); db = get_db()
    return jsonify(get_portfolio_overview(db, user["id"]))


@app.route("/api/portfolio/gaps")
@login_required
def api_portfolio_gaps():
    """Gap analysis as JSON."""
    from tools.portfolio_engine import get_portfolio_overview, analyze_gaps
    user = current_user(); db = get_db()
    overview = get_portfolio_overview(db, user["id"])
    return jsonify(analyze_gaps(overview))


@app.route("/api/portfolio/heatmap")
@login_required
def api_portfolio_heatmap():
    """Coverage heatmap as JSON."""
    from tools.portfolio_engine import get_portfolio_overview, build_coverage_heatmap
    user = current_user(); db = get_db()
    overview = get_portfolio_overview(db, user["id"])
    return jsonify(build_coverage_heatmap(overview))


@app.route("/api/portfolio/revenue")
@login_required
def api_portfolio_revenue():
    """Revenue projections as JSON."""
    from tools.portfolio_engine import get_portfolio_overview, project_portfolio_revenue
    user = current_user(); db = get_db()
    scenario = request.args.get("scenario", "base")
    overview = get_portfolio_overview(db, user["id"])
    return jsonify(project_portfolio_revenue(overview, scenario))


@app.route("/api/portfolio/trends")
@login_required
def api_portfolio_trends():
    """Market trends as JSON."""
    from tools.portfolio_engine import get_trend_signals
    from tools.market_scraper import seed_market_data, get_trend_summary
    db = get_db()
    seed_market_data(db)
    return jsonify({"signals": get_trend_signals(), "market": get_trend_summary(db)})


@app.route("/api/portfolio/alignment")
@login_required
def api_portfolio_alignment():
    """Market alignment score — how well portfolio matches market demand."""
    from tools.portfolio_engine import get_portfolio_overview, calculate_alignment_score
    user = current_user(); db = get_db()
    overview = get_portfolio_overview(db, user["id"])
    return jsonify(calculate_alignment_score(overview))


@app.route("/api/portfolio/snapshot", methods=["POST"])
@login_required
def api_portfolio_snapshot():
    """Capture a portfolio snapshot for historical tracking."""
    from tools.portfolio_engine import capture_snapshot
    user = current_user(); db = get_db()
    snap_id = capture_snapshot(db, user["id"])
    return jsonify({"snapshot_id": snap_id, "status": "captured"})


@app.route("/api/portfolio/snapshots")
@login_required
def api_portfolio_snapshots():
    """Get historical portfolio snapshots."""
    from tools.portfolio_engine import get_snapshots
    user = current_user(); db = get_db()
    limit = int(request.args.get("limit", 30))
    return jsonify(get_snapshots(db, user["id"], limit))


@app.route("/api/portfolio/scenario", methods=["POST"])
@login_required
def api_portfolio_scenario():
    """Build a launch scenario: select games + quarter → projected revenue."""
    from tools.portfolio_engine import get_portfolio_overview, build_launch_scenario
    user = current_user(); db = get_db()
    overview = get_portfolio_overview(db, user["id"])
    body = request.get_json(silent=True) or {}
    games = body.get("games", [])
    quarter = body.get("quarter", "Q3")
    return jsonify(build_launch_scenario(overview, games, quarter))


@app.route("/portfolio/gaps")
@login_required
def portfolio_gaps_page():
    """Server-rendered gap analysis page."""
    from tools.portfolio_engine import get_portfolio_overview, analyze_gaps
    user = current_user(); db = get_db()
    overview = get_portfolio_overview(db, user["id"])
    gaps = analyze_gaps(overview)

    gap_html = ""
    if not gaps:
        gap_html = '<p style="color:var(--text-dim);font-size:13px">No gaps detected. Portfolio looks balanced!</p>'
    else:
        for g in gaps:
            sev_color = {"high": "var(--danger)", "medium": "var(--warning)", "low": "var(--accent)"}.get(g.get("severity"), "var(--text-dim)")
            gap_html += f'''<div class="card" style="margin-bottom:8px;border-left:3px solid {sev_color}">
                <div style="display:flex;gap:10px;align-items:flex-start">
                    <span style="font-size:18px">{g.get("icon","📊")}</span>
                    <div style="flex:1">
                        <div style="font-size:13px;font-weight:700;color:var(--text-bright)">{g.get("title","")}</div>
                        <div style="font-size:12px;color:var(--text-muted);margin-top:2px">{g.get("message","")}</div>
                        {"<div style='font-size:11px;color:var(--accent);margin-top:4px;font-style:italic'>💡 "+g["recommendation"]+"</div>" if g.get("recommendation") else ""}
                    </div>
                    <span style="font-size:9px;padding:2px 6px;border-radius:8px;background:rgba(255,255,255,.05);color:{sev_color};font-weight:700">{g.get("severity","")}</span>
                </div>
            </div>'''

    return layout(f'''<div style="margin-bottom:20px"><a href="/portfolio" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Portfolio Dashboard</a></div>
    <h2 class="page-title" style="margin-bottom:4px">🔍 Gap Analysis</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:16px">{overview.get("total_games",0)} games analyzed — {len(gaps)} findings</p>
    {gap_html}
    <div style="margin-top:24px;margin-bottom:40px"><a href="/portfolio" class="btn btn-ghost">Back to Portfolio</a></div>''', "portfolio")


@app.route("/portfolio/trends")
@login_required
def portfolio_trends_page():
    """Server-rendered trends page."""
    from tools.portfolio_engine import get_trend_signals
    from tools.market_scraper import seed_market_data, get_trend_summary
    db = get_db()
    seed_market_data(db)
    trends = get_trend_signals()
    market = get_trend_summary(db)

    trend_icons = {"rising": "📈", "stable": "➡️", "declining": "📉", "warning": "⚠️"}
    trend_colors = {"rising": "var(--success)", "stable": "var(--accent)", "declining": "var(--danger)", "warning": "var(--warning)"}

    trend_html = ""
    for t in trends:
        color = trend_colors.get(t.get("trend"), "var(--text-dim)")
        icon = trend_icons.get(t.get("trend"), "•")
        trend_html += f'''<div class="card" style="margin-bottom:6px;display:flex;gap:10px;align-items:flex-start">
            <span style="font-size:16px">{icon}</span>
            <div style="flex:1">
                <div style="font-size:13px;font-weight:700;color:var(--text-bright)">{t.get("name","")} <span style="font-size:10px;color:{color};margin-left:4px">{t.get("trend","")}</span></div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:2px">{t.get("signal","")}</div>
                {"<div style='font-size:11px;color:var(--accent);margin-top:3px'>💡 "+t["action"]+"</div>" if t.get("action") else ""}
            </div>
        </div>'''

    # Market share bars
    theme_bars = ""
    for t in market.get("themes", []):
        pct = t.get("market_share", 0)
        theme_bars += f'''<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:11px;width:90px;text-align:right;color:var(--text-dim)">{t["name"]}</span>
            <div style="flex:1;height:14px;background:var(--bg);border-radius:3px;overflow:hidden"><div style="height:100%;width:{pct*5}%;background:var(--accent);border-radius:3px"></div></div>
            <span style="font-size:10px;font-weight:700;width:30px">{pct}%</span>
        </div>'''

    return layout(f'''<div style="margin-bottom:20px"><a href="/portfolio" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Portfolio Dashboard</a></div>
    <h2 class="page-title" style="margin-bottom:4px">📡 Market Trends</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:16px">{market.get("total_records",0)} data points — Last updated: {market.get("last_updated","")[:10]}</p>

    <div class="card"><h2 style="font-size:14px;font-weight:600;margin-bottom:8px">📊 Theme Market Share</h2>{theme_bars}</div>

    <div style="margin-top:12px"><h2 style="font-size:14px;font-weight:600;margin-bottom:8px">📡 Trend Signals</h2>{trend_html}</div>

    <div style="margin-top:24px;margin-bottom:40px"><a href="/portfolio" class="btn btn-ghost">Back to Portfolio</a></div>''', "portfolio")


@app.route("/qdrant")
@login_required
def qdrant_status():
    try:
        from tools.qdrant_store import JurisdictionStore
        status = JurisdictionStore().get_status()
    except Exception as e:
        status = {"status":"ERROR","message":str(e),"jurisdictions":[],"total_vectors":0}
    bc = "badge-complete" if status["status"]=="ONLINE" else "badge-failed"
    jhtml = "".join(f'<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">{j}</div>' for j in status.get("jurisdictions",[])) or '<div style="color:var(--text-muted);font-size:13px;padding:12px 0">No jurisdictions yet. Run a State Recon.</div>'
    return layout(f'''
    <h2 class="page-title" style="margin-bottom:24px">{ICON_DB} Qdrant Vector Database</h2>
    <div class="card"><h2>Connection <span class="badge {bc}" style="margin-left:8px">{status["status"]}</span></h2>
    <div class="row2" style="margin-top:12px"><div><label>Total Vectors</label><div style="font-size:20px;font-weight:600;color:var(--text-bright)">{status.get("total_vectors",0)}</div></div>
    <div><label>Jurisdictions</label><div style="font-size:20px;font-weight:600;color:var(--text-bright)">{len(status.get("jurisdictions",[]))}</div></div></div></div>
    <div class="card"><h2>Researched Jurisdictions</h2>{jhtml}</div>''', "qdrant")

# ─── REVIEWS (Web HITL) ───
@app.route("/reviews")
@login_required
def reviews_page():
    from tools.web_hitl import get_pending_reviews
    pending = get_pending_reviews()
    # Also get resolved reviews
    resolved = []
    try:
        db = get_db()
        resolved = db.execute(
            "SELECT r.*, j.title as job_title FROM reviews r JOIN jobs j ON r.job_id=j.id "
            "WHERE r.status!='pending' ORDER BY r.resolved_at DESC LIMIT 20"
        ).fetchall()
    except Exception as e:
        logger.warning(f"Reviews query failed: {e}")

    pending_html = ""
    for r in pending:
        pending_html += f'''<div class="history-item" style="grid-template-columns:1fr 140px 100px">
            <div><div class="history-title">{r["title"]}</div><div class="history-type">{r["job_title"]} &middot; {r["stage"]}</div></div>
            <div class="history-date">{r["created_at"][:16] if r["created_at"] else ""}</div>
            <div class="history-actions"><a href="/review/{r["id"]}" class="btn btn-primary btn-sm">Review</a></div>
        </div>'''
    if not pending_html:
        pending_html = '<div class="empty-state"><h3>No pending reviews</h3><p>Launch a pipeline in Interactive Mode to see checkpoints here.</p></div>'

    resolved_html = ""
    for r in resolved:
        r = dict(r)
        status = "Approved" if r.get("approved") else "Rejected"
        bc = "badge-complete" if r.get("approved") else "badge-failed"
        resolved_html += f'''<div class="history-item" style="grid-template-columns:1fr 100px 140px">
            <div><div class="history-title">{r["title"]}</div><div class="history-type">{r.get("job_title","")} &middot; {r.get("feedback","")[:50]}</div></div>
            <div><span class="badge {bc}">{status}</span></div>
            <div class="history-date">{r.get("resolved_at","")[:16]}</div>
        </div>'''

    return layout(f'''
    <h2 class="page-title" style="margin-bottom:24px">{ICON_REVIEW} Pipeline Reviews</h2>
    <div class="card"><h2 style="color:var(--text-bright)">Pending Reviews <span class="badge badge-running" style="margin-left:8px">{len(pending)}</span></h2>{pending_html}</div>
    {"<div class='card'><h2>Resolved</h2>" + resolved_html + "</div>" if resolved_html else ""}''', "reviews")


@app.route("/review/<review_id>")
@login_required
def review_detail(review_id):
    from tools.web_hitl import get_review
    import json as _json
    review = get_review(review_id)
    if not review:
        return "Review not found", 404

    files = _json.loads(_rget(review, "files","[]")) if _rget(review, "files") else []
    output_dir = _rget(review, "output_dir","")

    # Build file list with download links
    files_html = ""
    if files and output_dir:
        for f in files:
            fpath = Path(output_dir) / f
            if fpath.exists():
                ext = fpath.suffix.lower()
                # Show image previews inline
                if ext in (".png",".jpg",".jpeg",".webp"):
                    files_html += f'<div style="margin:8px 0"><div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;font-family:Geist Mono,monospace">{f}</div><img src="/review/{review_id}/file/{f}" style="max-width:100%;border-radius:8px;border:1px solid var(--border)"></div>'
                else:
                    files_html += f'<div class="file-row"><a href="/review/{review_id}/file/{f}">{f}</a><span class="file-size">{fpath.stat().st_size/1024:.1f} KB</span></div>'

    if not files_html:
        files_html = '<div style="color:var(--text-muted);font-size:13px;padding:12px 0">No files to preview.</div>'

    already_resolved = review["status"] != "pending"
    form_html = ""
    if already_resolved:
        result = "Approved" if _rget(review, "approved") else "Rejected"
        form_html = f'<div class="card" style="border-color:var(--success) !important"><h2>Already {result}</h2><p style="color:var(--text-muted)">{_rget(review, "feedback","")}</p></div>'
    else:
        form_html = f'''<div class="card">
        <h2>Your Decision</h2>
        <form action="/api/review/{review_id}" method="POST">
            <label>Feedback / Art Changes / Notes</label>
            <textarea name="feedback" placeholder="e.g. Make the symbols darker, increase contrast on the wild symbol, add more gold accents..." rows="4"></textarea>
            <div style="display:flex;gap:12px;margin-top:8px">
                <button type="submit" name="action" value="approve" class="btn btn-primary" style="flex:1;padding:14px">Approve &amp; Continue</button>
                <button type="submit" name="action" value="reject" class="btn btn-ghost" style="flex:1;padding:14px;border-color:var(--danger);color:var(--danger)">Reject &amp; Revise</button>
            </div>
        </form></div>'''

    return layout(f'''
    <div style="margin-bottom:20px"><a href="/reviews" style="color:var(--text-dim);font-size:12px;text-decoration:none">&larr; Back to Reviews</a></div>
    <h2 class="page-title">{review["title"]}</h2>
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:12px">{_rget(review, "job_title","")} &middot; Stage: {review["stage"]}</p>
    <div style="margin-bottom:16px"><a href="/review/{review["job_id"]}/interactive" class="btn btn-ghost" style="font-size:12px;padding:6px 16px;border-color:var(--accent);color:var(--accent)">📋 Open Interactive Review (Phase 8)</a></div>

    <div class="card"><h2>Summary</h2><div style="font-size:13px;line-height:1.7;white-space:pre-wrap">{review["summary"]}</div></div>
    <div class="card" style="padding:0;overflow:hidden"><div style="padding:16px 16px 8px"><h2 style="margin-bottom:8px">Generated Files</h2></div>{files_html}</div>
    {form_html}''', "reviews")


@app.route("/review/<review_id>/file/<path:fp>")
@login_required
def review_file(review_id, fp):
    from tools.web_hitl import get_review
    review = get_review(review_id)
    if not review or not _rget(review, "output_dir"):
        return "Not found", 404
    return send_from_directory(Path(review["output_dir"]), fp)


@app.route("/api/review/<review_id>", methods=["POST"])
@login_required
def api_submit_review(review_id):
    from tools.web_hitl import submit_review
    action = request.form.get("action","approve")
    feedback = request.form.get("feedback","")
    approved = (action == "approve")
    submit_review(review_id, approved=approved, feedback=feedback)
    return redirect("/reviews")


# ─── INTERACTIVE REVIEW (Phase 8) ───

@app.route("/review/<job_id>/interactive")
@login_required
def interactive_review(job_id):
    """Serve the React SPA interactive review UI."""
    from api.review_routes import build_review_data, get_comments, get_section_approvals
    user = current_user()
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return "Job not found", 404

    output_dir = job["output_dir"] or ""
    params = json.loads(job["params"]) if job["params"] else {}
    target_rtp = params.get("target_rtp", 96.0)

    # Build review data
    review_data = build_review_data(job_id, output_dir, target_rtp)

    # Get comments and approvals
    comments = get_comments(db, job_id)
    approvals = get_section_approvals(db, job_id)

    # Render the React SPA template with injected data
    spa_path = Path(__file__).parent / "static" / "review-app" / "index.html"
    if not spa_path.exists():
        return "Review app not found", 500

    html = spa_path.read_text(encoding="utf-8")
    html = html.replace("__REVIEW_DATA__", json.dumps(review_data, default=str))
    html = html.replace("__JOB_ID__", job_id)
    html = html.replace("__COMMENTS__", json.dumps(comments, default=str))
    html = html.replace("__APPROVALS__", json.dumps(approvals, default=str))

    return html


@app.route("/api/review/<job_id>/data")
@login_required
def api_review_data(job_id):
    """Get review data as JSON for dynamic refresh."""
    from api.review_routes import build_review_data
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    params = json.loads(job["params"]) if job["params"] else {}
    data = build_review_data(job_id, job["output_dir"] or "", params.get("target_rtp", 96.0))
    return jsonify(data)


@app.route("/api/review/<job_id>/comment", methods=["POST"])
@login_required
def api_add_comment(job_id):
    """Add a threaded comment on a section."""
    from api.review_routes import add_comment
    user = current_user()
    body = request.get_json(silent=True) or {}
    section = body.get("section", "general")
    content = body.get("content", "").strip()
    parent_id = body.get("parent_id")
    if not content:
        return jsonify({"error": "Empty comment"}), 400
    db = get_db()
    result = add_comment(db, job_id, section, content, author=user.get("email", "User"), parent_id=parent_id)
    return jsonify(result)


@app.route("/api/review/<job_id>/comments")
@login_required
def api_get_comments(job_id):
    """Get all comments for a job."""
    from api.review_routes import get_comments
    db = get_db()
    section = request.args.get("section")
    return jsonify(get_comments(db, job_id, section))


@app.route("/api/review/<job_id>/comment/<comment_id>/resolve", methods=["POST"])
@login_required
def api_resolve_comment(job_id, comment_id):
    """Mark a comment as resolved."""
    from api.review_routes import resolve_comment
    db = get_db()
    resolve_comment(db, comment_id)
    return jsonify({"ok": True})


@app.route("/api/review/<job_id>/section-approval", methods=["POST"])
@login_required
def api_section_approval(job_id):
    """Set approval status for a GDD section."""
    from api.review_routes import set_section_approval
    user = current_user()
    body = request.get_json(silent=True) or {}
    section = body.get("section", "")
    status = body.get("status", "pending")
    role = body.get("role", "reviewer")
    feedback = body.get("feedback", "")
    if not section:
        return jsonify({"error": "No section specified"}), 400
    db = get_db()
    result = set_section_approval(db, job_id, section, status, reviewer=user.get("email", "User"), role=role, feedback=feedback)
    return jsonify(result)


@app.route("/api/review/<job_id>/section-approvals")
@login_required
def api_get_section_approvals(job_id):
    """Get all section approvals for a job."""
    from api.review_routes import get_section_approvals
    db = get_db()
    return jsonify(get_section_approvals(db, job_id))


@app.route("/api/review/<job_id>/paytable", methods=["PATCH"])
@login_required
def api_edit_paytable(job_id):
    """Edit a paytable cell. Returns updated cell + RTP estimate."""
    from api.review_routes import update_paytable_cell, quick_rtp_estimate
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or not job["output_dir"]:
        return jsonify({"error": "Job not found"}), 404
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "")
    key = body.get("key", "")
    pay = body.get("pay", 0)
    count = body.get("count", 0)
    result = update_paytable_cell(job["output_dir"], symbol, count or 0, pay)
    params = json.loads(job["params"]) if job["params"] else {}
    rtp = quick_rtp_estimate(job["output_dir"], params.get("target_rtp", 96.0))
    return jsonify({**result, "rtp": rtp})


@app.route("/api/review/<job_id>/rtp-estimate")
@login_required
def api_rtp_estimate(job_id):
    """Get current RTP estimate for a job."""
    from api.review_routes import quick_rtp_estimate
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or not job["output_dir"]:
        return jsonify({"error": "Job not found"}), 404
    params = json.loads(job["params"]) if job["params"] else {}
    return jsonify(quick_rtp_estimate(job["output_dir"], params.get("target_rtp", 96.0)))


@app.route("/api/review/<job_id>/gdd-section", methods=["PATCH"])
@login_required
def api_edit_gdd_section(job_id):
    """Edit a GDD section content."""
    from api.review_routes import save_gdd_section
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or not job["output_dir"]:
        return jsonify({"error": "Job not found"}), 404
    body = request.get_json(silent=True) or {}
    section_id = body.get("section_id", "")
    content = body.get("content", "")
    ok = save_gdd_section(job["output_dir"], section_id, content)
    return jsonify({"ok": ok})


@app.route("/api/review/<job_id>/gdd-sections")
@login_required
def api_get_gdd_sections(job_id):
    """Get parsed GDD sections."""
    from api.review_routes import parse_gdd_sections
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or not job["output_dir"]:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(parse_gdd_sections(job_id, job["output_dir"]))


@app.route("/api/review/<job_id>/diffs")
@login_required
def api_get_diffs(job_id):
    """Get OODA revision diffs."""
    from api.review_routes import get_ooda_diff
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or not job["output_dir"]:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(get_ooda_diff(job["output_dir"]))


@app.route("/api/review/<job_id>/bulk-approve", methods=["POST"])
@login_required
def api_bulk_approve(job_id):
    """Approve all sections at once and continue pipeline."""
    from api.review_routes import parse_gdd_sections, set_section_approval
    user = current_user()
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return redirect(f"/job/{job_id}/files")

    # Approve all GDD sections
    if job["output_dir"]:
        sections = parse_gdd_sections(job_id, job["output_dir"])
        for s in sections:
            set_section_approval(db, job_id, s["id"], "approved",
                                 reviewer=user.get("email", "User"), role="reviewer")

    # If there's a pending HITL review, approve it too
    try:
        from tools.web_hitl import get_pending_reviews, submit_review
        pending = get_pending_reviews(job_id)
        for r in pending:
            submit_review(r["id"], approved=True, feedback="Bulk approved via interactive review")
    except Exception:
        pass

    return redirect(f"/job/{job_id}/files")


# ─── PIPELINE MEMORY (Phase 6) ───

@app.route("/memory")
@login_required
def memory_page():
    """Pipeline memory dashboard — shows indexed runs and component library."""
    user = current_user()
    db = get_db()

    # Fetch run records
    db.execute(
        "SELECT r.*, j.title as job_title FROM run_records r "
        "LEFT JOIN jobs j ON r.job_id = j.id "
        "WHERE r.user_id = %s OR r.user_id IS NULL OR r.user_id = '' "
        "ORDER BY r.created_at DESC LIMIT 50",
        (user["id"],)
    )
    runs = db.fetchall()

    # Fetch component counts by type
    db.execute("SELECT component_type, COUNT(*) as cnt FROM component_library GROUP BY component_type")
    comp_counts = {r["component_type"]: r["cnt"] for r in db.fetchall()}

    # Fetch top components
    db.execute(
        "SELECT * FROM component_library ORDER BY times_reused DESC, avg_satisfaction DESC LIMIT 20"
    )
    components = db.fetchall()

    # Stats
    db.execute("SELECT COUNT(*) as c FROM run_records")
    total_runs = (db.fetchone() or {}).get("c", 0)
    db.execute(
        "SELECT AVG(ABS(measured_rtp - target_rtp)) as avg_delta, "
        "AVG(ooda_iterations) as avg_ooda, AVG(cost_usd) as avg_cost "
        "FROM run_records WHERE measured_rtp IS NOT NULL"
    )
    stats = db.fetchone() or {}

    # Build run rows
    run_rows = ""
    for r in runs:
        r = dict(r) if not isinstance(r, dict) else r
        rtp_delta = ""
        if r.get("measured_rtp") and r.get("target_rtp"):
            d = abs(r["measured_rtp"] - r["target_rtp"])
            color = "var(--success)" if d < 0.15 else ("var(--warning)" if d < 0.5 else "var(--danger)")
            rtp_delta = f'<span style="color:{color};font-weight:600">±{d:.2f}%</span>'
        ooda = r.get("ooda_iterations", 0)
        features = ""
        try:
            fl = json.loads(r.get("features", "[]"))
            features = ", ".join(fl[:4])
            if len(fl) > 4:
                features += f" +{len(fl)-4}"
        except Exception:
            pass
        run_rows += (
            f'<div class="file-row" style="gap:12px;padding:12px 16px">'
            f'<div style="flex:1;min-width:0">'
            f'<a href="/job/{r.get("job_id","")}/files" style="font-weight:600;display:block;overflow:hidden;text-overflow:ellipsis">{_esc(r.get("theme","") or r.get("job_title","?"))}</a>'
            f'<span style="font-size:10px;color:var(--text-dim)">{_esc(r.get("volatility",""))} · {_esc(r.get("grid",""))} · {features}</span></div>'
            f'<span style="font-size:11px;color:var(--text-muted)">{r.get("target_rtp","")}% → {r.get("measured_rtp","?")}%</span>'
            f'<span style="font-size:11px">{rtp_delta}</span>'
            f'<span style="font-size:10px;color:var(--text-dim)">{ooda} OODA</span>'
            f'<span style="font-size:10px;color:var(--text-dim)">${r.get("cost_usd",0):.2f}</span>'
            f'<span class="file-size">{(r.get("created_at","") or "")[:10]}</span>'
            f'</div>'
        )
    if not run_rows:
        run_rows = '<div class="empty-state"><h3>No runs indexed yet</h3><p>Complete a pipeline to populate memory.</p></div>'

    # Build component rows
    comp_rows = ""
    for c in components:
        c = dict(c) if not isinstance(c, dict) else c
        badge_colors = {
            "paytable": "#3b82f6", "feature_config": "#f97316",
            "rtp_budget": "#22c55e", "reel_strip": "#a855f7"
        }
        bc = badge_colors.get(c.get("component_type", ""), "var(--text-dim)")
        tags = ""
        try:
            tl = json.loads(c.get("tags", "[]"))
            tags = " ".join(f'<span style="font-size:9px;padding:1px 6px;border-radius:3px;background:rgba(124,106,239,0.1);color:#a78bfa">{_esc(t)}</span>' for t in tl[:5])
        except Exception:
            pass
        sat = c.get("avg_satisfaction") or 0
        comp_rows += (
            f'<div class="file-row" style="gap:10px;padding:10px 16px">'
            f'<span style="font-size:9px;padding:2px 8px;border-radius:4px;background:{bc}22;color:{bc};font-weight:600;min-width:80px;text-align:center">{_esc(c.get("component_type",""))}</span>'
            f'<div style="flex:1;min-width:0">'
            f'<div style="font-weight:500;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_esc(c.get("name",""))}</div>'
            f'<div style="font-size:10px;color:var(--text-dim)">{tags}</div></div>'
            f'<span style="font-size:11px;color:var(--text-muted)">{c.get("times_reused",0)}× reused</span>'
            f'<span style="font-size:11px;color:var(--text-muted)">{sat:.1f}/10</span>'
            f'</div>'
        )
    if not comp_rows:
        comp_rows = '<div class="empty-state"><h3>No components yet</h3><p>Components are auto-extracted from completed runs.</p></div>'

    avg_delta = f"±{stats.get('avg_delta', 0):.3f}%" if stats.get("avg_delta") is not None else "N/A"
    avg_ooda = f"{stats.get('avg_ooda', 0):.1f}" if stats.get("avg_ooda") is not None else "N/A"
    avg_cost = f"${stats.get('avg_cost', 0):.2f}" if stats.get("avg_cost") is not None else "N/A"
    total_comps = sum(comp_counts.values())

    return layout(f'''
    <h2 class="page-title">🧠 Pipeline Memory</h2>
    <p style="color:var(--text-muted);font-size:13px;margin-bottom:20px">
        Indexed runs, reusable components, and convergence patterns from past pipelines.
    </p>

    <div class="stat-grid" style="margin-bottom:20px">
        <div class="stat-card online"><div class="stat-icon">📊</div><div class="stat-val">{total_runs}</div><div class="stat-label">Indexed Runs</div></div>
        <div class="stat-card online"><div class="stat-icon">🧩</div><div class="stat-val">{total_comps}</div><div class="stat-label">Components</div></div>
        <div class="stat-card"><div class="stat-icon">🎯</div><div class="stat-val">{avg_delta}</div><div class="stat-label">Avg RTP Δ</div></div>
        <div class="stat-card"><div class="stat-icon">🔄</div><div class="stat-val">{avg_ooda}</div><div class="stat-label">Avg OODA Loops</div></div>
        <div class="stat-card"><div class="stat-icon">💰</div><div class="stat-val">{avg_cost}</div><div class="stat-label">Avg Cost</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px">
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:10px 14px;font-size:11px;display:flex;gap:12px;flex-wrap:wrap">
            <span>📄 Paytables: <b>{comp_counts.get("paytable",0)}</b></span>
            <span>⚡ Features: <b>{comp_counts.get("feature_config",0)}</b></span>
            <span>📊 RTP Budgets: <b>{comp_counts.get("rtp_budget",0)}</b></span>
            <span>🎰 Reel Strips: <b>{comp_counts.get("reel_strip",0)}</b></span>
        </div>
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:10px 14px;font-size:11px;color:var(--text-dim)">
            Memory is queried at pipeline start. Agents receive context from similar past runs — RTP patterns, feature configs, and convergence notes.
        </div>
    </div>

    <div class="card" style="padding:0;overflow:hidden">
        <div style="padding:14px 16px 8px"><h2>📊 Indexed Runs</h2></div>
        {run_rows}
    </div>

    <div class="card" style="padding:0;overflow:hidden;margin-top:16px">
        <div style="padding:14px 16px 8px;display:flex;align-items:center;justify-content:space-between">
            <h2>🧩 Component Library</h2>
            <span style="font-size:11px;color:var(--text-dim)">{total_comps} total</span>
        </div>
        {comp_rows}
    </div>''', "memory")


@app.route("/api/memory/search")
@login_required
def api_memory_search():
    """Search pipeline memory for similar runs."""
    q = request.args.get("q", "").strip()
    vol = request.args.get("volatility", "")
    limit = min(int(request.args.get("limit", 5)), 20)
    if not q:
        return jsonify({"error": "q param required"}), 400
    try:
        from memory.query_engine import search_similar_runs
        results = search_similar_runs(theme=q, volatility=vol, limit=limit)
        return jsonify({"results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/memory/components")
@login_required
def api_memory_components():
    """Search the component library."""
    ctype = request.args.get("type", "")
    q = request.args.get("q", "")
    vol = request.args.get("volatility", "")
    limit = min(int(request.args.get("limit", 10)), 50)
    try:
        from memory.query_engine import search_components
        results = search_components(component_type=ctype, query_text=q, volatility=vol, limit=limit)
        return jsonify({"results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/memory/stats")
@login_required
def api_memory_stats():
    """Get pipeline memory statistics."""
    db = get_db()
    db.execute("SELECT COUNT(*) as c FROM run_records")
    total = (db.fetchone() or {}).get("c", 0)
    db.execute("SELECT COUNT(*) as c FROM component_library")
    comps = (db.fetchone() or {}).get("c", 0)
    db.execute(
        "SELECT AVG(ABS(measured_rtp - target_rtp)) as avg_delta "
        "FROM run_records WHERE measured_rtp IS NOT NULL AND target_rtp IS NOT NULL"
    )
    row = db.fetchone() or {}
    return jsonify({
        "total_runs": total,
        "total_components": comps,
        "avg_rtp_delta": round(row.get("avg_delta") or 0, 3),
    })


# ─── SETTINGS ───
@app.route("/settings")
@login_required
def settings_page():
    keys = {
        "OPENAI_API_KEY": {"label": "OpenAI API Key", "icon": "🧠", "desc": "GPT-5 reasoning agents, DALL-E 3 images, Vision QA", "required": True},
        "SERPER_API_KEY": {"label": "Serper API Key", "icon": "🔍", "desc": "Web search, patent search, trend radar, competitor teardown", "required": True},
        "ELEVENLABS_API_KEY": {"label": "ElevenLabs API Key", "icon": "🔊", "desc": "AI sound effect generation (13 core game sounds)", "required": False},
        "QDRANT_URL": {"label": "Qdrant URL", "icon": "🗃️", "desc": "Vector DB for regulation storage + knowledge base", "required": False},
        "QDRANT_API_KEY": {"label": "Qdrant API Key", "icon": "🔑", "desc": "Auth for Qdrant Cloud", "required": False},
        "GOOGLE_CLIENT_ID": {"label": "Google OAuth Client ID", "icon": "🔐", "desc": "Google sign-in", "required": True},
        "GOOGLE_CLIENT_SECRET": {"label": "Google OAuth Secret", "icon": "🔐", "desc": "Google sign-in", "required": True},
        "RESEND_API_KEY": {"label": "Resend API Key", "icon": "📧", "desc": "Email notifications when pipelines complete (resend.com)", "required": False},
        "APP_BASE_URL": {"label": "App Base URL", "icon": "🌐", "desc": "Your deployment URL for email links (e.g. https://arkainbrain.up.railway.app)", "required": False},
    }

    rows = ""
    for env_key, info in keys.items():
        val = os.getenv(env_key, "")
        is_set = bool(val) and val not in ("your-openai-key", "your-serper-key", "your-elevenlabs-key", "your-qdrant-key", "your-qdrant-url", "your-google-client-id", "your-google-client-secret")
        masked = val[:8] + "..." + val[-4:] if is_set and len(val) > 12 else ("Set" if is_set else "Not configured")
        bc = "badge-complete" if is_set else ("badge-failed" if info["required"] else "badge-queued")
        status = "Connected" if is_set else ("Required" if info["required"] else "Optional")
        rows += f'''<div class="file-row" style="padding:14px 16px;gap:16px">
            <div style="display:flex;align-items:center;gap:12px;flex:1">
                <span style="font-size:20px">{info["icon"]}</span>
                <div><div style="font-weight:600;color:var(--text-bright);font-size:13px">{info["label"]}</div>
                <div style="font-size:11px;color:var(--text-muted)">{info["desc"]}</div></div>
            </div>
            <div style="font-family:'Geist Mono',monospace;font-size:11px;color:var(--text-muted);min-width:120px">{masked}</div>
            <span class="badge {bc}">{status}</span>
        </div>'''

    db_mode = "PostgreSQL" if USE_POSTGRES else "SQLite"
    q_mode = "Redis Queue" if USE_REDIS else "Subprocess"
    db_badge = "badge-complete" if USE_POSTGRES else "badge-queued"
    q_badge = "badge-complete" if USE_REDIS else "badge-queued"

    return layout(f'''
    <h2 class="page-title">{ICON_SETTINGS} Settings</h2>
    <p style="color:var(--text-muted);font-size:13px;margin-bottom:24px">API keys, infrastructure, and integrations.</p>
    <div class="card" style="padding:0;overflow:hidden"><div style="padding:16px 16px 8px"><h2>🔗 API Integrations</h2></div>{rows}</div>

    <div class="card"><h2>🏗️ Platform Status</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px">
        <div><label>Version</label><div style="font-size:18px;font-weight:700;color:var(--text-bright)">v8.0</div></div>
        <div><label>LLM Tier</label><div style="font-size:18px;font-weight:700;color:var(--success)">GPT-5 Tier 3</div></div>
        <div><label>Max Concurrent</label><div style="font-size:18px;font-weight:700;color:var(--text-bright)">{MAX_CONCURRENT_JOBS} pipelines</div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px">
        <div style="display:flex;align-items:center;gap:8px"><label style="margin:0">Database</label><span class="badge {db_badge}">{db_mode}</span></div>
        <div style="display:flex;align-items:center;gap:8px"><label style="margin:0">Queue</label><span class="badge {q_badge}">{q_mode}</span></div>
        <div style="display:flex;align-items:center;gap:8px"><label style="margin:0">Agents</label><span class="badge badge-complete">All GPT-5</span></div>
    </div>
    <div style="margin-bottom:16px;padding:12px;background:var(--bg-surface);border:1px solid var(--border);border-radius:8px">
        <label style="margin-bottom:8px;display:block">Railway Pro — 3-Service Architecture</label>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:11px">
            <div style="padding:8px;border:1px solid var(--border);border-radius:6px">
                <div style="font-weight:600;color:var(--text-bright)">web</div>
                <div style="color:var(--text-dim)">2 vCPU · 4 GB · 2 replicas</div>
                <div style="color:var(--text-dim)">Dashboard + API + SSE</div>
            </div>
            <div style="padding:8px;border:1px solid var(--border);border-radius:6px">
                <div style="font-weight:600;color:var(--text-bright)">worker</div>
                <div style="color:var(--text-dim)">8 vCPU · 16 GB · 1→5</div>
                <div style="color:var(--text-dim)">CrewAI pipeline executor</div>
            </div>
            <div style="padding:8px;border:1px solid var(--border);border-radius:6px">
                <div style="font-weight:600;color:var(--text-bright)">sim-runner</div>
                <div style="color:var(--text-dim)">4 vCPU · 8 GB · 1→10</div>
                <div style="color:var(--text-dim)">Monte Carlo simulations</div>
            </div>
        </div>
    </div>
    <div style="font-size:12px;color:var(--text-dim);line-height:1.7">
        6 GPT-5 agents (Tier 3: 800K+ TPM, all HEAVY) · 8 PDF deliverables · HTML5 prototype · AI sound design · Patent scanner · Cert planner · Revenue projections · Engine export · ZIP download · File preview · Tagging
    </div></div>

    <div class="card"><h2>📋 Quick Setup</h2>
    <pre style="background:var(--bg-input);padding:16px;border-radius:8px;font-family:'Geist Mono',monospace;font-size:11px;color:var(--text);overflow-x:auto;line-height:1.8">
# Copy .env.example to .env and fill in your keys:
cp .env.example .env

# Required:
OPENAI_API_KEY=sk-...          # OpenAI GPT-5 (Tier 3 access)
SERPER_API_KEY=...              # serper.dev (free tier: 2500 searches)

# Infrastructure (Railway auto-provides these):
DATABASE_URL=postgresql://...   # PostgreSQL (leave empty for SQLite)
REDIS_URL=redis://...           # Redis Queue (leave empty for subprocess)

# Optional:
ELEVENLABS_API_KEY=...          # elevenlabs.io ($5/mo starter for SFX)
RESEND_API_KEY=...              # resend.com (free: 100 emails/day)
QDRANT_URL=...                  # Qdrant Cloud (state recon RAG)
</pre></div>
    {_settings_notify_section()}''', "settings")


def _settings_notify_section():
    """Build the email notification toggle section for settings page."""
    try:
        user = current_user()
        db = get_db()
        db.execute("SELECT email_notify FROM users WHERE id=?", (user["id"],))
        user_row = db.fetchone()
        email_notify = user_row.get("email_notify", 1) if user_row else 1
        resend_ok = bool(os.getenv("RESEND_API_KEY", "")) and os.getenv("RESEND_API_KEY") not in ("your-resend-key", "")
        status_text = "Active" if resend_ok and email_notify else ("Disabled by you" if resend_ok else "Not configured")
        badge = "badge-complete" if resend_ok and email_notify else "badge-queued"
        checked = "checked" if email_notify else ""
        bg = "var(--success)" if email_notify else "rgba(255,255,255,0.1)"
        left = "22px" if email_notify else "3px"
        email = _esc(user.get("email", ""))
        setup_note = (
            "<div style='font-size:11px;color:var(--text-dim)'>Email service: Resend &middot; Configured via RESEND_API_KEY</div>"
            if resend_ok else
            "<div style='font-size:11px;color:var(--warning)'>&#9888;&#65039; Set RESEND_API_KEY in .env to enable. "
            "<a href='https://resend.com' target='_blank' style='color:var(--accent)'>Get a free key &rarr;</a></div>"
        )
        return f'''<div class="card"><h2>&#128276; Email Notifications</h2>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:16px">Get notified when pipelines complete or fail.</p>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;background:var(--bg-input);border-radius:8px;margin-bottom:12px">
            <div style="display:flex;align-items:center;gap:12px">
                <span style="font-size:20px">&#128231;</span>
                <div><div style="font-weight:600;color:var(--text-bright);font-size:13px">Pipeline completion emails</div>
                <div style="font-size:11px;color:var(--text-muted)">Sent to {email}</div></div>
            </div>
            <div style="display:flex;align-items:center;gap:10px">
                <span class="badge {badge}">{status_text}</span>
                <label style="position:relative;display:inline-block;width:44px;height:24px;cursor:pointer">
                    <input type="checkbox" id="email-toggle" {checked} onchange="fetch('/api/settings/email-notify',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{enabled:this.checked}})}}).then(r=>r.ok?location.reload():alert('Failed'))" style="opacity:0;width:0;height:0">
                    <span style="position:absolute;inset:0;background:{bg};border-radius:24px;transition:0.3s"></span>
                    <span style="position:absolute;height:18px;width:18px;left:{left};bottom:3px;background:#fff;border-radius:50%;transition:0.3s"></span>
                </label>
            </div>
        </div>
        {setup_note}</div>'''
    except Exception as e:
        logger.debug(f"Notify section: {e}")
        return ""


# ─── API ───

@app.route("/api/settings/email-notify", methods=["POST"])
@login_required
def api_toggle_email_notify():
    """Toggle email notification preference for current user."""
    user = current_user()
    data = request.get_json(silent=True) or {}
    enabled = 1 if data.get("enabled", True) else 0
    db = get_db()
    db.execute("UPDATE users SET email_notify=? WHERE id=?", (enabled, user["id"]))
    db.commit()
    logger.info(f"Email notify {'enabled' if enabled else 'disabled'} for {user['email']}")
    return jsonify({"ok": True, "email_notify": enabled})


@app.route("/api/pipeline", methods=["POST"])
@login_required
def api_launch_pipeline():
    user = current_user()
    limit_err = _check_job_limit(user["id"])
    if limit_err: return limit_err
    job_id = str(uuid.uuid4())[:8]
    params = {"theme":request.form["theme"],"target_markets":[m.strip() for m in request.form.get("target_markets","Georgia, Texas").split(",")],"volatility":request.form.get("volatility","medium"),"target_rtp":float(request.form.get("target_rtp",96)),"grid_cols":int(request.form.get("grid_cols",5)),"grid_rows":int(request.form.get("grid_rows",3)),"ways_or_lines":request.form.get("ways_or_lines","243"),"max_win_multiplier":int(request.form.get("max_win_multiplier",5000)),"art_style":request.form.get("art_style","Cinematic realism"),"requested_features":request.form.getlist("features"),"competitor_references":[r.strip() for r in request.form.get("competitor_references","").split(",") if r.strip()],"special_requirements":request.form.get("special_requirements",""),"enable_recon":request.form.get("enable_recon")=="on"}
    db = get_db(); db.execute("INSERT INTO jobs (id,user_id,job_type,title,params,status) VALUES (?,?,?,?,?,?)", (job_id,user["id"],"slot_pipeline",params["theme"],json.dumps(params),"queued")); db.commit()
    params["interactive"] = request.form.get("interactive") == "on"
    enqueue_job("pipeline", job_id, json.dumps(params))
    return redirect(f"/job/{job_id}/logs")

@app.route("/api/recon", methods=["POST"])
@login_required
def api_launch_recon():
    user = current_user()
    limit_err = _check_job_limit(user["id"])
    if limit_err: return limit_err
    sn = request.form["state"].strip(); job_id = str(uuid.uuid4())[:8]
    db = get_db(); db.execute("INSERT INTO jobs (id,user_id,job_type,title,params,status) VALUES (?,?,?,?,?,?)", (job_id,user["id"],"state_recon",f"Recon: {sn}",json.dumps({"state":sn}),"queued")); db.commit()
    enqueue_job("recon", job_id, sn)
    return redirect(f"/job/{job_id}/logs")

@app.route("/api/status/<job_id>")
@login_required
def api_job_status(job_id):
    # DB is the source of truth (shared across gunicorn workers + subprocesses)
    db = get_db()
    job = db.execute("SELECT status,current_stage,error FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(job))


@app.route("/api/logs/<job_id>")
@login_required
def api_log_stream(job_id):
    """Polling log endpoint — returns new lines since ?after=N.

    Replaces the old SSE generator that held a gunicorn thread for up to 90 min.
    Client polls every 2s with the line cursor. Thread is released after each response.

    Query params:
      after (int): Line number to start from (0 = beginning). Default 0.

    Returns JSON:
      {"lines": [...], "cursor": <next_after>, "done": bool, "status": "running"|"complete"|"failed"}
    """
    after = request.args.get("after", 0, type=int)
    log_path = LOG_DIR / f"{job_id}.log"

    lines = []
    done = False
    status = "running"

    # Read log file from the cursor position
    if log_path.exists():
        try:
            with open(log_path, "r", errors="replace") as f:
                all_lines = f.readlines()
                lines = [l.rstrip() for l in all_lines[after:]]
        except (IOError, OSError):
            pass
    elif after == 0:
        lines = ["Waiting for worker to start..."]

    # Check job status
    _polldb = _open_db()
    _polldb.execute("SELECT status FROM jobs WHERE id=?", (job_id,))
    job = _polldb.fetchone()
    _polldb.close()

    if job:
        status = job["status"]
        if status in ("complete", "failed"):
            done = True

    cursor = after + len(lines)
    return jsonify({"lines": lines, "cursor": cursor, "done": done, "status": status})


@app.route("/job/<job_id>/logs")
@login_required
def job_logs_page(job_id):
    db = get_db(); job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job: return "Not found", 404
    status = job["status"]
    badge_class = {"running":"badge-running","complete":"badge-complete","failed":"badge-failed"}.get(status,"badge-queued")
    files_btn = f'<a href="/job/{job_id}/files" class="btn btn-primary btn-sm">View Files</a>' if status == "complete" else ""
    stage_text = _esc(job["current_stage"] or "")
    created = job["created_at"] or ""
    shimmer_cls = "stage-shimmer" if status == "running" else ""
    timer_cls = "" if status == "running" else "stopped"

    # ── CSS (plain string) ──
    feed_css = '''<style>
    .pl-timeline{display:flex;gap:0;margin-bottom:16px;padding:10px 14px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-lg);overflow-x:auto}
    .pl-stage{flex:1;display:flex;align-items:center;gap:5px;padding:5px 6px;font-size:10px;color:var(--text-dim);white-space:nowrap;transition:all 0.4s}
    .pl-dot{width:7px;height:7px;border-radius:50%;background:var(--border);flex-shrink:0;transition:all 0.5s}
    .pl-stage.done .pl-dot{background:#22c55e;box-shadow:0 0 6px #22c55e44}
    .pl-stage.active .pl-dot{background:#7c6aef;box-shadow:0 0 10px #7c6aef88;animation:plp 1.5s ease infinite}
    .pl-stage.active{color:var(--text-bright);font-weight:600}
    .pl-stage.done{color:#22c55e}
    .pl-stage::after{content:'';flex:1;height:1px;background:var(--border);margin:0 4px}
    .pl-stage:last-child::after{display:none}
    .pl-stage.done::after{background:rgba(34,197,94,0.3)}
    @keyframes plp{0%,100%{transform:scale(1)}50%{transform:scale(1.5)}}
    .feed-timer{font-family:'Geist Mono',monospace;font-size:11px;color:var(--text-dim);display:flex;align-items:center;gap:5px}
    .tdot{width:6px;height:6px;border-radius:50%;background:#22c55e;animation:tblink 1s step-end infinite}
    .tdot.stopped{animation:none;background:var(--text-dim)}
    @keyframes tblink{50%{opacity:0.3}}
    .mbar{display:flex;gap:14px;padding:8px 14px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-lg);margin-bottom:14px;font-size:10.5px;flex-wrap:wrap}
    .mi{display:flex;align-items:center;gap:4px;color:var(--text-dim)}.mi .mv{color:var(--text-bright);font-weight:700;font-family:'Geist Mono',monospace;transition:all 0.3s}
    .mi.ok .mv{color:#22c55e}.mi.wr .mv{color:#eab308}.mi.er .mv{color:#ef4444}
    .fwrap{overflow-y:auto;height:calc(100vh - 300px);scroll-behavior:smooth;padding-right:4px}
    .fwrap::-webkit-scrollbar{width:4px}
    .fwrap::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
    .tfeed{display:flex;flex-direction:column;gap:0;padding:0 0 32px}
    .ev{padding:7px 14px;animation:evin 0.35s ease-out;font-size:12px;line-height:1.65;color:var(--text)}
    @keyframes evin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
    .ev-stage{padding:12px 16px;margin:14px 0 6px;background:linear-gradient(135deg,rgba(124,106,239,0.08),rgba(79,70,229,0.02));border:1px solid rgba(124,106,239,0.12);border-radius:10px;border-left:3px solid #7c6aef;display:flex;align-items:center;gap:10px;font-weight:600;color:var(--text-bright);flex-wrap:wrap}
    .ev-stage .sn{font-size:9px;padding:2px 7px;border-radius:4px;background:rgba(124,106,239,0.15);color:#a78bfa;font-weight:700;letter-spacing:0.5px}
    .ev-stage .sd{font-size:11px;color:var(--text-muted);font-weight:400;margin-left:auto;max-width:55%}
    .ev-ok{padding:6px 14px;border-left:2px solid rgba(34,197,94,0.3);color:#22c55e;font-weight:500;font-size:12px}
    .ev-wr{padding:6px 14px;border-left:2px solid rgba(234,179,8,0.3);color:#eab308;font-size:12px}
    .ev-er{padding:8px 14px;background:rgba(239,68,68,0.05);border:1px solid rgba(239,68,68,0.12);border-radius:8px;border-left:3px solid #ef4444;color:#ef4444;font-weight:500;margin:4px 0;font-size:12px}
    .ev-agent{display:flex;align-items:flex-start;gap:10px;padding:8px 14px;margin:3px 0}
    .aav{width:28px;height:28px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0}
    .aav-r{background:rgba(59,130,246,0.12)}.aav-m{background:rgba(249,115,22,0.12)}.aav-d{background:rgba(236,72,153,0.12)}.aav-l{background:rgba(168,85,247,0.12)}.aav-p{background:rgba(20,184,166,0.12)}.aav-q{background:rgba(239,68,68,0.12)}
    .abody{flex:1;min-width:0}
    .aname{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:2px}
    .an-r{color:#60a5fa}.an-m{color:#f97316}.an-d{color:#ec4899}.an-l{color:#a855f7}.an-p{color:#14b8a6}.an-q{color:#ef4444}
    .atask{font-size:11.5px;color:var(--text-muted)}
    .atyp{display:inline-flex;gap:3px;margin-left:6px;vertical-align:middle}
    .atyp span{width:3px;height:3px;border-radius:50%;background:currentColor;opacity:0.4;animation:atya 1.2s ease-in-out infinite}
    .atyp span:nth-child(2){animation-delay:0.15s}
    .atyp span:nth-child(3){animation-delay:0.3s}
    @keyframes atya{0%,60%,100%{opacity:0.3;transform:translateY(0)}30%{opacity:1;transform:translateY(-3px)}}
    .ev-ooda{padding:10px 14px;margin:6px 0;background:linear-gradient(135deg,rgba(249,115,22,0.06),transparent);border:1px solid rgba(249,115,22,0.1);border-radius:8px;display:flex;align-items:center;gap:10px;font-size:12px}
    .ooda-b{font-size:9px;padding:3px 7px;border-radius:4px;background:rgba(249,115,22,0.15);color:#f97316;font-weight:700;letter-spacing:0.5px}
    .ooda-s{width:12px;height:12px;border:2px solid rgba(249,115,22,0.2);border-top-color:#f97316;border-radius:50%;animation:ospin 0.8s linear infinite;flex-shrink:0}
    @keyframes ospin{to{transform:rotate(360deg)}}
    .ev-or{padding:10px 14px;margin:4px 0;border-radius:8px;display:flex;align-items:center;gap:8px;font-weight:500;font-size:12px}
    .ev-or.pass{background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.12);color:#22c55e}
    .ev-or.fail{background:rgba(249,115,22,0.06);border:1px solid rgba(249,115,22,0.12);color:#f97316}
    .ev-par{padding:10px 14px;margin:4px 0;background:rgba(79,70,229,0.03);border:1px solid rgba(79,70,229,0.08);border-radius:8px;font-size:12px}
    .ptracks{display:flex;gap:6px;margin-top:5px;flex-wrap:wrap}
    .ptrack{font-size:10px;padding:3px 8px;border-radius:4px;background:rgba(124,106,239,0.1);color:#a78bfa;display:flex;align-items:center;gap:4px}
    .pdot{width:4px;height:4px;border-radius:50%;background:#7c6aef;animation:plp 1.5s ease infinite}
    .ev-met{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;margin:2px 4px;background:rgba(124,106,239,0.06);border:1px solid rgba(124,106,239,0.1);border-radius:6px;font-size:11px}
    .ev-met .mv{color:var(--text-bright);font-weight:700;font-family:'Geist Mono',monospace}
    .ev-done{padding:18px;margin:16px 0 0;border-radius:12px;text-align:center;font-size:15px;font-weight:700}
    .ev-done.success{background:linear-gradient(135deg,rgba(34,197,94,0.1),rgba(34,197,94,0.02));border:1px solid rgba(34,197,94,0.2);color:#22c55e}
    .ev-done.fail{background:linear-gradient(135deg,rgba(239,68,68,0.1),rgba(239,68,68,0.02));border:1px solid rgba(239,68,68,0.2);color:#ef4444}
    .ev-dim{color:var(--text-dim);font-size:10.5px;padding:2px 14px}
    .ev-th{padding:8px 12px;margin:2px 14px;background:rgba(255,255,255,0.015);border-radius:6px;border:1px solid rgba(255,255,255,0.04);font-size:11px;color:var(--text-dim);font-family:'Geist Mono',monospace;line-height:1.55;max-height:80px;overflow:hidden;cursor:pointer;transition:max-height 0.3s;position:relative}
    .ev-th.exp{max-height:none}
    .ev-th::after{content:'click to expand';position:absolute;bottom:0;left:0;right:0;height:22px;background:linear-gradient(transparent,var(--bg));font-size:9px;display:flex;align-items:flex-end;justify-content:center;color:var(--text-dim);padding-bottom:2px}
    .ev-th.exp::after{display:none}
    .ev-th.short{max-height:none;cursor:default}.ev-th.short::after{display:none}
    #rawLog{font-family:'Geist Mono',monospace;font-size:10.5px;line-height:1.7;color:var(--text-dim);background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px;overflow:auto;height:calc(100vh - 300px);white-space:pre-wrap}
    </style>'''

    # ── HTML (f-string — simple interpolations only) ──
    html = f'''{feed_css}
    <div style="margin-bottom:10px"><a href="/history" style="color:var(--text-dim);font-size:12px;text-decoration:none" onmouseover="this.style.color='var(--text-bright)'" onmouseout="this.style.color='var(--text-dim)'">&larr; Back</a></div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div>
            <h2 style="font-size:18px;font-weight:600;color:var(--text-bright);margin-bottom:3px;letter-spacing:-0.02em">{_esc(job["title"])}</h2>
            <div style="font-size:12px;color:var(--text-muted);display:flex;align-items:center;gap:8px">
                <span id="jobStatus" class="badge {badge_class}">{status}</span>
                <span id="jobStage" class="{shimmer_cls}" style="font-size:12px">{stage_text}</span>
                <span class="feed-timer"><span class="tdot {timer_cls}" id="timerDot"></span> <span id="elapsed">0:00</span></span>
            </div>
        </div>
        <div style="display:flex;gap:6px" id="actionBtns">
            <button onclick="window._tRaw()" class="btn btn-ghost btn-sm" id="rawBtn" title="Toggle raw log view">raw</button>
            <button onclick="window._sBot()" class="btn btn-ghost btn-sm">&#8595;</button>
            {files_btn}
        </div>
    </div>
    <div id="jobData" data-job-id="{job_id}" data-status="{status}" data-created="{created}" style="display:none"></div>
    <div id="stageTimeline" class="pl-timeline">
        <div class="pl-stage" data-s="preflight"><span class="pl-dot"></span>Pre-flight</div>
        <div class="pl-stage" data-s="research"><span class="pl-dot"></span>Research</div>
        <div class="pl-stage" data-s="design"><span class="pl-dot"></span>Design</div>
        <div class="pl-stage" data-s="art"><span class="pl-dot"></span>Art</div>
        <div class="pl-stage" data-s="production"><span class="pl-dot"></span>Production</div>
        <div class="pl-stage" data-s="package"><span class="pl-dot"></span>Package</div>
    </div>
    <div class="mbar" id="mbar">
        <div class="mi ok">&check; <span class="mv" id="mOk">0</span> pass</div>
        <div class="mi wr">&#9888; <span class="mv" id="mWr">0</span> warn</div>
        <div class="mi er">&times; <span class="mv" id="mEr">0</span> err</div>
        <div class="mi">&#8634; <span class="mv" id="mOo">0</span> OODA</div>
        <div class="mi" style="margin-left:auto">&#9881; <span class="mv" id="mLn">0</span></div>
    </div>
    <div class="fwrap" id="fw"><div class="tfeed" id="tf"></div></div>
    <pre id="rawLog" style="display:none"></pre>'''

    # ── JS (plain string — no f-string) ──
    js = '<script src="/static/thought-feed.js"></script>'

    return layout(html + js, "history")




# ─── BACKGROUND WORKERS (Phase 5A: Redis queue with subprocess fallback) ───
# Job dispatching is now handled by config.database.enqueue_job()
# which uses Redis/RQ when available, subprocess when not.
# Legacy _spawn_worker kept as alias for any stragglers.

def _spawn_worker(job_id, job_type, *args):
    """Legacy compat — routes to enqueue_job."""
    enqueue_job(job_type, job_id, *args)


# ─── HEALTH CHECK (for Railway / load balancer monitoring) ───

@app.route("/health")
def health_check():
    """Health check — verifies web server + database + optional services."""
    try:
        db = get_db()
        db.execute("SELECT 1")
        db.fetchone()
        status = {
            "status": "ok",
            "version": "v8",
            "database": "postgresql" if USE_POSTGRES else "sqlite",
            "queue": "redis" if USE_REDIS else "subprocess",
        }
        return jsonify(status), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503


# ─── CUSTOM ERROR PAGES ───

@app.errorhandler(404)
def error_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return layout(
        '<div class="card" style="text-align:center;padding:48px">'
        '<h2 style="font-size:48px;font-weight:800;color:var(--text-bright);margin-bottom:8px">404</h2>'
        '<p style="color:var(--text-muted);margin-bottom:24px">The page you\'re looking for doesn\'t exist.</p>'
        '<a href="/" class="btn btn-primary">Go Home</a></div>'
    ), 404

@app.errorhandler(500)
def error_500(e):
    logger.error(f"500 error: {e}", exc_info=True)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return layout(
        '<div class="card" style="text-align:center;padding:48px">'
        '<h2 style="font-size:48px;font-weight:800;color:var(--text-bright);margin-bottom:8px">500</h2>'
        '<p style="color:var(--text-muted);margin-bottom:24px">Something went wrong. Try again or check your pipeline logs.</p>'
        '<div style="display:flex;gap:8px;justify-content:center">'
        '<a href="/history" class="btn btn-primary">View History</a>'
        '<a href="/" class="btn btn-ghost">Go Home</a></div></div>'
    ), 500

@app.errorhandler(429)
def error_429(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": str(e)}), 429
    return layout(
        '<div class="card" style="text-align:center;padding:48px">'
        '<h2 style="font-size:24px;font-weight:700;color:var(--text-bright);margin-bottom:8px">Too Many Jobs</h2>'
        f'<p style="color:var(--text-muted);margin-bottom:24px">You have {MAX_CONCURRENT_JOBS} jobs in progress. Please wait for one to finish.</p>'
        '<a href="/history" class="btn btn-primary">View History</a></div>'
    ), 429


if __name__ == "__main__":
    import sys
    # CLI: python web_app.py set-admin user@example.com
    if len(sys.argv) >= 3 and sys.argv[1] == "set-admin":
        email = sys.argv[2]
        with app.app_context():
            db = get_db()
            user = db.execute("SELECT id, email, role FROM users WHERE email=?", (email,)).fetchone()
            if user:
                db.execute("UPDATE users SET role='admin' WHERE id=?", (user["id"],))
                db.commit()
                print(f"✅ {email} promoted to admin (user_id={user['id']})")
            else:
                print(f"❌ User {email} not found. Available users:")
                for u in db.execute("SELECT email FROM users ORDER BY created_at DESC LIMIT 10").fetchall():
                    print(f"   {u['email']}")
        sys.exit(0)

    port = int(os.getenv("PORT", 5000))
    logger.info(f"ARKAINBRAIN — http://localhost:{port}")
    app.run(debug=os.getenv("FLASK_DEBUG","false").lower()=="true", host="0.0.0.0", port=port)
