"""
ARKAINBRAIN — Admin Routes (Phase A1)

Dashboard, user management, audit log.
"""

import json
import math
from datetime import datetime, timedelta
from flask import request, jsonify, session, redirect

from admin import admin_bp
from admin.decorators import admin_required, audit_log, PLANS, get_plan_info
from config.database import get_db

_esc = lambda s: str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

# ═══════════════════════════════════════════════
# Admin Layout
# ═══════════════════════════════════════════════

ADMIN_CSS = """
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0b10;--surface:#12131a;--card:#1a1b25;--border:#252636;--accent:#7c6aef;
--success:#22c55e;--danger:#ef4444;--warn:#f59e0b;--info:#06b6d4;--text:#e2e8f0;
--dim:#94a3b8;--muted:#64748b;--radius:8px;--mono:'JetBrains Mono',monospace}
body{font-family:'Inter',-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.admin-shell{display:flex;min-height:100vh}
.admin-side{width:220px;background:var(--surface);border-right:1px solid var(--border);padding:16px 0;position:fixed;top:0;bottom:0;overflow-y:auto}
.admin-side .logo{padding:12px 20px;font-size:16px;font-weight:800;color:var(--accent);border-bottom:1px solid var(--border);margin-bottom:8px}
.admin-side a{display:flex;align-items:center;gap:10px;padding:10px 20px;font-size:12px;color:var(--dim);text-decoration:none;transition:all .15s}
.admin-side a:hover{background:rgba(124,106,239,.08);color:var(--text)}
.admin-side a.active{background:rgba(124,106,239,.15);color:var(--accent);font-weight:600;border-right:2px solid var(--accent)}
.admin-main{margin-left:220px;flex:1;padding:24px 32px;max-width:1200px}
.page-title{font-size:20px;font-weight:800;margin-bottom:4px}
.page-sub{font-size:12px;color:var(--dim);margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:12px}
.card h3{font-size:13px;font-weight:700;margin-bottom:10px;color:var(--text)}
.stat-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin-bottom:16px}
.stat-box{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}
.stat-box .val{font-size:28px;font-weight:800;color:var(--accent)}
.stat-box .lbl{font-size:10px;color:var(--dim);margin-top:2px;text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 10px;color:var(--dim);font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border)}
td{padding:8px 10px;border-bottom:1px solid var(--border);color:var(--text)}
tr:hover td{background:rgba(124,106,239,.04)}
.badge{display:inline-block;font-size:9px;padding:2px 8px;border-radius:10px;font-weight:700}
.badge-admin{background:rgba(124,106,239,.2);color:var(--accent)}
.badge-user{background:rgba(100,116,139,.15);color:var(--muted)}
.badge-free{background:rgba(100,116,139,.15);color:var(--muted)}
.badge-pro{background:rgba(34,197,94,.15);color:var(--success)}
.badge-studio{background:rgba(245,158,11,.15);color:var(--warn)}
.badge-enterprise{background:rgba(124,106,239,.2);color:var(--accent)}
.badge-suspended{background:rgba(239,68,68,.15);color:var(--danger)}
.badge-active{background:rgba(34,197,94,.15);color:var(--success)}
.btn{display:inline-block;padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:11px;cursor:pointer;text-decoration:none;transition:all .15s}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn-sm{padding:3px 8px;font-size:10px}
.btn-danger{border-color:var(--danger);color:var(--danger)}
.btn-danger:hover{background:var(--danger);color:#fff}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-primary:hover{opacity:.85}
.pagination{display:flex;gap:4px;margin-top:12px;align-items:center;font-size:11px}
.pagination a,.pagination span{padding:4px 10px;border-radius:4px;border:1px solid var(--border);color:var(--dim);text-decoration:none}
.pagination a:hover{border-color:var(--accent);color:var(--accent)}
.pagination .current{background:var(--accent);color:#fff;border-color:var(--accent)}
.search-bar{display:flex;gap:8px;margin-bottom:16px}
.search-bar input,.search-bar select{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--text);font-size:12px;outline:none}
.search-bar input:focus,.search-bar select:focus{border-color:var(--accent)}
.search-bar input{flex:1}
.alert-badge{background:var(--danger);color:#fff;font-size:9px;padding:1px 5px;border-radius:8px;margin-left:4px}
</style>
"""

def admin_layout(content: str, active: str = "dashboard"):
    """Wrap content in admin shell with sidebar."""
    user = session.get("user", {})
    db = get_db()

    # Alert count
    alert_count = 0
    try:
        r = db.execute("SELECT COUNT(*) as c FROM system_alerts WHERE resolved=0").fetchone()
        alert_count = r["c"] if r else 0
    except Exception:
        pass

    nav_items = [
        ("dashboard", "📊", "Dashboard", "/admin"),
        ("users", "👥", "Users", "/admin/users"),
        ("jobs", "⚡", "Jobs", "/admin/jobs"),
        ("costs", "💰", "Costs", "/admin/costs"),
        ("audit", "📜", "Audit Log", "/admin/audit"),
    ]

    nav_html = ""
    for key, icon, label, href in nav_items:
        cls = ' class="active"' if active == key else ""
        badge = f'<span class="alert-badge">{alert_count}</span>' if key == "system" and alert_count else ""
        nav_html += f'<a href="{href}"{cls}>{icon} {label}{badge}</a>'

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Admin — ArkainBrain</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{ADMIN_CSS}</head><body>
<div class="admin-shell">
<nav class="admin-side">
    <div class="logo">🔒 Admin Panel</div>
    {nav_html}
    <div style="border-top:1px solid var(--border);margin-top:12px;padding-top:12px">
        <a href="/">← Back to App</a>
    </div>
    <div style="padding:12px 20px;font-size:10px;color:var(--muted);margin-top:auto">
        {_esc(user.get('email',''))}
    </div>
</nav>
<main class="admin-main">{content}</main>
</div></body></html>"""


# ═══════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════

@admin_bp.route("/")
@admin_required
def admin_dashboard():
    db = get_db()
    now = datetime.now()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    total_users = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    new_users_week = db.execute("SELECT COUNT(*) as c FROM users WHERE created_at>=?", (week_ago,)).fetchone()["c"]
    new_users_month = db.execute("SELECT COUNT(*) as c FROM users WHERE created_at>=?", (month_ago,)).fetchone()["c"]
    active_7d = db.execute("SELECT COUNT(*) as c FROM users WHERE last_active_at>=?", (week_ago,)).fetchone()["c"]

    total_jobs = db.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]
    jobs_running = db.execute("SELECT COUNT(*) as c FROM jobs WHERE status IN ('queued','running')").fetchone()["c"]
    jobs_complete = db.execute("SELECT COUNT(*) as c FROM jobs WHERE status='complete'").fetchone()["c"]
    jobs_failed = db.execute("SELECT COUNT(*) as c FROM jobs WHERE status='failed'").fetchone()["c"]
    jobs_today = db.execute("SELECT COUNT(*) as c FROM jobs WHERE created_at>=?", (now.strftime("%Y-%m-%d"),)).fetchone()["c"]
    jobs_week = db.execute("SELECT COUNT(*) as c FROM jobs WHERE created_at>=?", (week_ago,)).fetchone()["c"]

    # Cost totals
    cost_today = 0; cost_week = 0; cost_month = 0; cost_all = 0
    try:
        cost_today = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE created_at>=?", (now.strftime("%Y-%m-%d"),)).fetchone()["c"]
        cost_week = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE created_at>=?", (week_ago,)).fetchone()["c"]
        cost_month = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE created_at>=?", (month_ago,)).fetchone()["c"]
        cost_all = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events").fetchone()["c"]
    except Exception:
        pass

    # Plan distribution
    plan_rows = db.execute("SELECT plan, COUNT(*) as c FROM users GROUP BY plan ORDER BY c DESC").fetchall()
    plan_html = "".join(f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:12px"><span class="badge badge-{r["plan"]}">{r["plan"]}</span><span style="font-weight:700">{r["c"]}</span></div>' for r in plan_rows)

    # Recent jobs
    recent = db.execute("SELECT j.*, u.email FROM jobs j LEFT JOIN users u ON j.user_id=u.id ORDER BY j.created_at DESC LIMIT 8").fetchall()
    recent_html = ""
    status_cls = {"complete": "badge-active", "failed": "badge-suspended", "running": "badge-pro", "queued": "badge-free"}
    for j in recent:
        s_cls = status_cls.get(j["status"], "badge-user")
        recent_html += f'<tr><td><a href="/admin/jobs/{j["id"]}" style="color:var(--accent);text-decoration:none">{_esc((j["title"] or "")[:35])}</a></td><td>{_esc((j["email"] or "")[:25])}</td><td><span class="badge {s_cls}">{j["status"]}</span></td><td style="color:var(--dim)">{(j["created_at"] or "")[:16]}</td></tr>'

    return admin_layout(f"""
    <h1 class="page-title">📊 Admin Dashboard</h1>
    <p class="page-sub">System overview — {now.strftime("%B %d, %Y %H:%M")}</p>

    <div class="stat-row">
        <div class="stat-box"><div class="val">{total_users}</div><div class="lbl">Total Users</div></div>
        <div class="stat-box"><div class="val" style="color:var(--success)">{new_users_week}</div><div class="lbl">New This Week</div></div>
        <div class="stat-box"><div class="val">{active_7d}</div><div class="lbl">Active (7d)</div></div>
        <div class="stat-box"><div class="val">{total_jobs}</div><div class="lbl">Total Jobs</div></div>
        <div class="stat-box"><div class="val" style="color:var(--warn)">{jobs_running}</div><div class="lbl">Running Now</div></div>
        <div class="stat-box"><div class="val" style="color:var(--danger)">${cost_month:.2f}</div><div class="lbl">Cost (30d)</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="card">
            <h3>⚡ Jobs</h3>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
                <div>Today: <b>{jobs_today}</b></div><div>This week: <b>{jobs_week}</b></div>
                <div>Complete: <b style="color:var(--success)">{jobs_complete}</b></div><div>Failed: <b style="color:var(--danger)">{jobs_failed}</b></div>
            </div>
        </div>
        <div class="card">
            <h3>💰 Costs</h3>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
                <div>Today: <b>${cost_today:.2f}</b></div><div>This week: <b>${cost_week:.2f}</b></div>
                <div>This month: <b>${cost_month:.2f}</b></div><div>All time: <b>${cost_all:.2f}</b></div>
            </div>
        </div>
    </div>

    <div style="display:grid;grid-template-columns:2fr 1fr;gap:12px">
        <div class="card">
            <h3>Recent Jobs</h3>
            <table><tr><th>Title</th><th>User</th><th>Status</th><th>Created</th></tr>{recent_html}</table>
        </div>
        <div class="card">
            <h3>Plan Distribution</h3>
            {plan_html if plan_html else '<div style="color:var(--dim);font-size:12px">No users yet</div>'}
        </div>
    </div>
    """, "dashboard")


# ═══════════════════════════════════════════════
# User Management
# ═══════════════════════════════════════════════

@admin_bp.route("/users")
@admin_required
def admin_users():
    db = get_db()
    page = int(request.args.get("page", 1))
    per_page = 25
    search = request.args.get("q", "").strip()
    plan_filter = request.args.get("plan", "")
    role_filter = request.args.get("role", "")
    sort = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc")

    where = []
    params = []
    if search:
        where.append("(email LIKE ? OR name LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if plan_filter:
        where.append("plan=?")
        params.append(plan_filter)
    if role_filter:
        where.append("role=?")
        params.append(role_filter)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    safe_sort = sort if sort in ("email","name","plan","role","created_at","last_active_at","monthly_jobs_used") else "created_at"
    safe_order = "ASC" if order == "asc" else "DESC"

    total = db.execute(f"SELECT COUNT(*) as c FROM users {where_sql}", params).fetchone()["c"]
    total_pages = max(1, math.ceil(total / per_page))
    offset = (page - 1) * per_page

    users = db.execute(
        f"SELECT u.*, (SELECT COUNT(*) FROM jobs WHERE user_id=u.id) as job_count "
        f"FROM users u {where_sql} ORDER BY {safe_sort} {safe_order} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    rows_html = ""
    for u in users:
        plan_cls = f"badge-{u['plan'] or 'free'}"
        role_cls = "badge-admin" if u.get("role") == "admin" else "badge-user"
        status = "suspended" if u.get("is_suspended") else "active"
        status_cls = "badge-suspended" if u.get("is_suspended") else "badge-active"
        last_active = (u.get("last_active_at") or "never")[:10]
        rows_html += f"""<tr>
            <td><a href="/admin/users/{u['id']}" style="color:var(--accent);text-decoration:none">{_esc((u['email'] or '')[:30])}</a></td>
            <td>{_esc((u.get('name') or '')[:20])}</td>
            <td><span class="badge {role_cls}">{u.get('role','user')}</span></td>
            <td><span class="badge {plan_cls}">{u.get('plan','free')}</span></td>
            <td style="font-family:var(--mono)">{u.get('monthly_jobs_used',0)}/{u.get('monthly_job_limit',10)}</td>
            <td>{u.get('job_count',0)}</td>
            <td><span class="badge {status_cls}">{status}</span></td>
            <td style="color:var(--dim)">{last_active}</td>
            <td style="color:var(--dim)">{(u.get('created_at') or '')[:10]}</td>
        </tr>"""

    # Pagination
    pag = '<div class="pagination">'
    if page > 1:
        pag += f'<a href="?page={page-1}&q={_esc(search)}&plan={plan_filter}&role={role_filter}&sort={sort}&order={order}">← Prev</a>'
    for p in range(1, total_pages + 1):
        if abs(p - page) < 4 or p == 1 or p == total_pages:
            cls = "current" if p == page else ""
            pag += f'<a href="?page={p}&q={_esc(search)}&plan={plan_filter}&role={role_filter}&sort={sort}&order={order}" class="{cls}">{p}</a>'
        elif abs(p - page) == 4:
            pag += '<span>…</span>'
    if page < total_pages:
        pag += f'<a href="?page={page+1}&q={_esc(search)}&plan={plan_filter}&role={role_filter}&sort={sort}&order={order}">Next →</a>'
    pag += f'<span style="margin-left:8px;color:var(--dim)">{total} users</span></div>'

    return admin_layout(f"""
    <h1 class="page-title">👥 User Management</h1>
    <p class="page-sub">{total} total users</p>

    <div class="search-bar">
        <form method="get" style="display:flex;gap:8px;flex:1">
            <input type="text" name="q" placeholder="Search email or name…" value="{_esc(search)}" style="flex:1">
            <select name="plan"><option value="">All Plans</option>{"".join(f'<option value="{p}" {"selected" if plan_filter==p else ""}>{p.title()}</option>' for p in PLANS)}</select>
            <select name="role"><option value="">All Roles</option><option value="admin" {"selected" if role_filter=="admin" else ""}>Admin</option><option value="user" {"selected" if role_filter=="user" else ""}>User</option></select>
            <input type="hidden" name="sort" value="{sort}"><input type="hidden" name="order" value="{order}">
            <button type="submit" class="btn btn-primary">Search</button>
        </form>
        <a href="/admin/users/export?q={_esc(search)}&plan={plan_filter}" class="btn" style="white-space:nowrap">📥 Export CSV</a>
    </div>

    <div class="card" style="padding:0;overflow-x:auto">
        <table>
            <tr><th>Email</th><th>Name</th><th>Role</th><th>Plan</th><th>Usage</th><th>Jobs</th><th>Status</th><th>Last Active</th><th>Joined</th></tr>
            {rows_html}
        </table>
    </div>
    {pag}
    """, "users")


@admin_bp.route("/users/export")
@admin_required
def admin_users_export():
    """Export user list as CSV."""
    db = get_db()
    search = request.args.get("q", "")
    plan_filter = request.args.get("plan", "")

    where = []; params = []
    if search:
        where.append("(email LIKE ? OR name LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if plan_filter:
        where.append("plan=?"); params.append(plan_filter)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    users = db.execute(
        f"SELECT u.*, (SELECT COUNT(*) FROM jobs WHERE user_id=u.id) as job_count FROM users u {where_sql} ORDER BY created_at DESC",
        params
    ).fetchall()

    import io, csv
    from flask import Response
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email","name","role","plan","jobs_used","job_limit","total_jobs","status","last_active","created"])
    for u in users:
        w.writerow([u["email"], u.get("name",""), u.get("role","user"), u.get("plan","free"),
                     u.get("monthly_jobs_used",0), u.get("monthly_job_limit",10), u.get("job_count",0),
                     "suspended" if u.get("is_suspended") else "active",
                     (u.get("last_active_at") or "")[:10], (u.get("created_at") or "")[:10]])

    audit_log("users_exported", "system", None, {"count": len(users)})
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=users_{datetime.now().strftime('%Y%m%d')}.csv"})


# ═══════════════════════════════════════════════
# User Detail
# ═══════════════════════════════════════════════

@admin_bp.route("/users/<user_id>")
@admin_required
def admin_user_detail(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return "User not found", 404

    jobs = db.execute("SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user_id,)).fetchall()
    job_count = db.execute("SELECT COUNT(*) as c FROM jobs WHERE user_id=?", (user_id,)).fetchone()["c"]

    # Cost for this user
    user_cost = 0
    try:
        user_cost = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE user_id=?", (user_id,)).fetchone()["c"]
    except Exception:
        pass

    # Audit log for this user
    audits = db.execute("SELECT * FROM admin_audit_log WHERE target_id=? ORDER BY created_at DESC LIMIT 10", (user_id,)).fetchall()

    status = "suspended" if user.get("is_suspended") else "active"
    status_cls = "badge-suspended" if user.get("is_suspended") else "badge-active"

    jobs_html = ""
    for j in jobs:
        s_cls = {"complete":"badge-active","failed":"badge-suspended","running":"badge-pro"}.get(j["status"],"badge-free")
        jobs_html += f'<tr><td><a href="/admin/jobs/{j["id"]}" style="color:var(--accent);text-decoration:none">{_esc((j["title"] or "")[:40])}</a></td><td><span class="badge {s_cls}">{j["status"]}</span></td><td>{j.get("job_type","")}</td><td style="color:var(--dim)">{(j.get("created_at") or "")[:16]}</td></tr>'

    audit_html = ""
    for a in audits:
        audit_html += f'<tr><td>{_esc(a["action"])}</td><td style="color:var(--dim)">{(a.get("created_at") or "")[:16]}</td><td style="color:var(--dim);font-size:10px">{_esc((a.get("details") or "")[:60])}</td></tr>'

    return admin_layout(f"""
    <div style="margin-bottom:16px"><a href="/admin/users" style="color:var(--dim);font-size:12px;text-decoration:none">← Back to Users</a></div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
        {"<img src='"+_esc(user.get('picture',''))+"' style='width:48px;height:48px;border-radius:50%;border:2px solid var(--border)'>" if user.get('picture') else '<div style="width:48px;height:48px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;color:#fff">'+_esc((user.get('name','?')[0]).upper())+'</div>'}
        <div>
            <h1 class="page-title">{_esc(user.get('name','') or user['email'])}</h1>
            <p class="page-sub" style="margin-bottom:0">{_esc(user['email'])} · <span class="badge badge-{user.get('role','user')}">{user.get('role','user')}</span> · <span class="badge badge-{user.get('plan','free')}">{user.get('plan','free')}</span> · <span class="badge {status_cls}">{status}</span></p>
        </div>
    </div>

    <div class="stat-row">
        <div class="stat-box"><div class="val">{job_count}</div><div class="lbl">Total Jobs</div></div>
        <div class="stat-box"><div class="val">{user.get('monthly_jobs_used',0)}/{user.get('monthly_job_limit',10)}</div><div class="lbl">Month Usage</div></div>
        <div class="stat-box"><div class="val" style="color:var(--danger)">${user_cost:.2f}</div><div class="lbl">Total Cost</div></div>
        <div class="stat-box"><div class="val" style="font-size:14px">{(user.get('last_active_at') or 'never')[:10]}</div><div class="lbl">Last Active</div></div>
    </div>

    <div class="card">
        <h3>🔧 Actions</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
            <form method="post" action="/admin/api/users/{user_id}/plan" style="display:flex;gap:4px">
                <select name="plan" style="background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:4px 8px;color:var(--text);font-size:11px">
                    {"".join(f'<option value="{p}" {"selected" if user.get("plan")==p else ""}>{p.title()} ({"$"+str(PLANS[p]["price"])+"/mo" if PLANS[p]["price"] else "Custom" if p=="enterprise" else "Free"})</option>' for p in PLANS)}
                </select>
                <button type="submit" class="btn btn-sm">Change Plan</button>
            </form>
            <form method="post" action="/admin/api/users/{user_id}/role" style="display:flex;gap:4px">
                <select name="role" style="background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:4px 8px;color:var(--text);font-size:11px">
                    <option value="user" {"selected" if user.get("role")!="admin" else ""}>User</option>
                    <option value="admin" {"selected" if user.get("role")=="admin" else ""}>Admin</option>
                </select>
                <button type="submit" class="btn btn-sm">Change Role</button>
            </form>
            {"<form method='post' action='/admin/api/users/"+user_id+"/unsuspend'><button type='submit' class='btn btn-sm btn-primary'>Unsuspend</button></form>" if user.get("is_suspended") else "<form method='post' action='/admin/api/users/"+user_id+"/suspend'><button type='submit' class='btn btn-sm btn-danger'>Suspend</button></form>"}
            <a href="/admin/api/users/{user_id}/impersonate" class="btn btn-sm" style="color:var(--warn)">👤 Impersonate</a>
        </div>
    </div>

    <div class="card">
        <h3>⚡ Recent Jobs ({job_count} total)</h3>
        <table><tr><th>Title</th><th>Status</th><th>Type</th><th>Created</th></tr>{jobs_html}</table>
        {f'<div style="margin-top:8px"><a href="/admin/jobs?user={user_id}" class="btn btn-sm">View All →</a></div>' if job_count > 20 else ""}
    </div>

    {"<div class='card'><h3>📜 Admin Actions</h3><table><tr><th>Action</th><th>Date</th><th>Details</th></tr>"+audit_html+"</table></div>" if audit_html else ""}
    """, "users")


# ═══════════════════════════════════════════════
# User Action APIs
# ═══════════════════════════════════════════════

@admin_bp.route("/api/users/<user_id>/plan", methods=["POST"])
@admin_required
def admin_change_plan(user_id):
    db = get_db()
    new_plan = request.form.get("plan", "free")
    if new_plan not in PLANS:
        return "Invalid plan", 400
    plan_info = PLANS[new_plan]

    old = db.execute("SELECT plan FROM users WHERE id=?", (user_id,)).fetchone()
    db.execute("UPDATE users SET plan=?, monthly_job_limit=?, plan_started_at=? WHERE id=?",
               (new_plan, plan_info["monthly_jobs"], datetime.now().isoformat(), user_id))
    db.commit()
    audit_log("plan_changed", "user", user_id, {"old": old["plan"] if old else None, "new": new_plan})
    return redirect(f"/admin/users/{user_id}")


@admin_bp.route("/api/users/<user_id>/role", methods=["POST"])
@admin_required
def admin_change_role(user_id):
    db = get_db()
    new_role = request.form.get("role", "user")
    if new_role not in ("user", "admin"):
        return "Invalid role", 400
    old = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    db.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
    db.commit()
    audit_log("role_changed", "user", user_id, {"old": old["role"] if old else None, "new": new_role})
    return redirect(f"/admin/users/{user_id}")


@admin_bp.route("/api/users/<user_id>/suspend", methods=["POST"])
@admin_required
def admin_suspend_user(user_id):
    db = get_db()
    reason = request.form.get("reason", "Admin action")
    db.execute("UPDATE users SET is_suspended=1, suspension_reason=? WHERE id=?", (reason, user_id))
    db.commit()
    audit_log("user_suspended", "user", user_id, {"reason": reason})
    return redirect(f"/admin/users/{user_id}")


@admin_bp.route("/api/users/<user_id>/unsuspend", methods=["POST"])
@admin_required
def admin_unsuspend_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_suspended=0, suspension_reason=NULL WHERE id=?", (user_id,))
    db.commit()
    audit_log("user_unsuspended", "user", user_id)
    return redirect(f"/admin/users/{user_id}")


@admin_bp.route("/api/users/<user_id>/impersonate")
@admin_required
def admin_impersonate(user_id):
    db = get_db()
    target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not target:
        return "User not found", 404

    admin_user = session.get("user", {})
    audit_log("user_impersonated", "user", user_id)

    # Store original admin session to restore later
    session["_admin_return"] = dict(admin_user)
    session["user"] = {"id": target["id"], "email": target["email"],
                        "name": target.get("name", ""), "picture": target.get("picture", ""),
                        "role": target.get("role", "user")}
    return redirect("/")


@admin_bp.route("/api/stop-impersonation")
def stop_impersonation():
    admin_return = session.pop("_admin_return", None)
    if admin_return:
        session["user"] = admin_return
    return redirect("/admin/users")


# ═══════════════════════════════════════════════
# Audit Log
# ═══════════════════════════════════════════════

@admin_bp.route("/audit")
@admin_required
def admin_audit():
    db = get_db()
    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page

    total = db.execute("SELECT COUNT(*) as c FROM admin_audit_log").fetchone()["c"]
    total_pages = max(1, math.ceil(total / per_page))

    logs = db.execute(
        "SELECT a.*, u.email as admin_email FROM admin_audit_log a LEFT JOIN users u ON a.admin_id=u.id ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()

    rows = ""
    for l in logs:
        rows += f"""<tr>
            <td style="color:var(--dim)">{(l.get('created_at') or '')[:19]}</td>
            <td>{_esc(l.get('admin_email','system'))}</td>
            <td><span style="font-weight:600">{_esc(l['action'])}</span></td>
            <td>{_esc(l.get('target_type','') or '')}:{_esc((l.get('target_id','') or '')[:12])}</td>
            <td style="font-size:10px;color:var(--dim);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_esc((l.get('details','') or '')[:80])}</td>
            <td style="color:var(--dim);font-size:10px">{_esc(l.get('ip_address','') or '')}</td>
        </tr>"""

    pag_html = '<div class="pagination">'
    if page > 1: pag_html += f'<a href="?page={page-1}">← Prev</a>'
    pag_html += f'<span style="color:var(--dim)">Page {page}/{total_pages} ({total} entries)</span>'
    if page < total_pages: pag_html += f'<a href="?page={page+1}">Next →</a>'
    pag_html += '</div>'

    return admin_layout(f"""
    <h1 class="page-title">📜 Audit Log</h1>
    <p class="page-sub">{total} admin actions recorded</p>
    <div class="card" style="padding:0;overflow-x:auto">
        <table><tr><th>Time</th><th>Admin</th><th>Action</th><th>Target</th><th>Details</th><th>IP</th></tr>{rows}</table>
    </div>
    {pag_html}
    """, "audit")
