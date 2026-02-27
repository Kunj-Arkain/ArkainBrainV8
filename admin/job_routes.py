"""
ARKAINBRAIN — Admin Job Routes (Phase A2)

Job browser, content preview, job actions.
"""

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from flask import request, jsonify, redirect

from admin import admin_bp
from admin.decorators import admin_required, audit_log
from config.database import get_db

_esc = lambda s: str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


# ═══════════════════════════════════════════════
# Job Browser
# ═══════════════════════════════════════════════

@admin_bp.route("/jobs")
@admin_required
def admin_jobs():
    from admin.routes import admin_layout
    db = get_db()

    page = int(request.args.get("page", 1))
    per_page = 30
    status_filter = request.args.get("status", "")
    type_filter = request.args.get("type", "")
    user_filter = request.args.get("user", "")
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc")

    where = []; params = []
    if status_filter:
        where.append("j.status=?"); params.append(status_filter)
    if type_filter:
        where.append("j.job_type=?"); params.append(type_filter)
    if user_filter:
        where.append("j.user_id=?"); params.append(user_filter)
    if search:
        where.append("(j.title LIKE ? OR u.email LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    safe_sort = sort if sort in ("created_at","status","job_type","title") else "created_at"
    safe_order = "ASC" if order == "asc" else "DESC"

    total = db.execute(f"SELECT COUNT(*) as c FROM jobs j LEFT JOIN users u ON j.user_id=u.id {where_sql}", params).fetchone()["c"]
    total_pages = max(1, math.ceil(total / per_page))
    offset = (page - 1) * per_page

    jobs = db.execute(
        f"SELECT j.*, u.email, u.name as user_name FROM jobs j LEFT JOIN users u ON j.user_id=u.id "
        f"{where_sql} ORDER BY j.{safe_sort} {safe_order} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    # Summary stats
    stat_running = db.execute("SELECT COUNT(*) as c FROM jobs WHERE status IN ('queued','running')").fetchone()["c"]
    stat_today = db.execute("SELECT COUNT(*) as c FROM jobs WHERE created_at>=?", (datetime.now().strftime("%Y-%m-%d"),)).fetchone()["c"]
    stat_failed = db.execute("SELECT COUNT(*) as c FROM jobs WHERE status='failed' AND created_at>=?",
                             ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchone()["c"]

    # Get distinct types for filter
    types = [r["job_type"] for r in db.execute("SELECT DISTINCT job_type FROM jobs ORDER BY job_type").fetchall()]

    rows_html = ""
    status_cls = {"complete":"badge-active","failed":"badge-suspended","running":"badge-pro","queued":"badge-free","cancelled":"badge-user"}
    for j in jobs:
        s_cls = status_cls.get(j["status"], "badge-user")
        # Estimate output size
        size_str = ""
        if j.get("output_dir") and Path(j["output_dir"]).exists():
            try:
                total_size = sum(f.stat().st_size for f in Path(j["output_dir"]).rglob("*") if f.is_file())
                size_str = f"{total_size/1024:.0f}KB" if total_size < 1048576 else f"{total_size/1048576:.1f}MB"
            except Exception:
                size_str = "?"

        # Cost for this job
        job_cost = 0
        try:
            r = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE job_id=?", (j["id"],)).fetchone()
            job_cost = r["c"] if r else 0
        except Exception:
            pass

        params_json = json.loads(j["params"]) if j["params"] else {}
        theme = params_json.get("theme", "")[:20]

        rows_html += f"""<tr>
            <td><a href="/admin/jobs/{j['id']}" style="color:var(--accent);text-decoration:none;font-family:var(--mono);font-size:10px">{j['id'][:8]}</a></td>
            <td><a href="/admin/users/{j['user_id']}" style="color:var(--text);text-decoration:none;font-size:11px">{_esc((j.get('email','') or '')[:25])}</a></td>
            <td style="font-weight:600;font-size:11px">{_esc((j['title'] or '')[:30])}</td>
            <td><span style="font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(124,106,239,.1);color:var(--accent)">{j.get('job_type','')}</span></td>
            <td><span class="badge {s_cls}">{j['status']}</span></td>
            <td style="font-family:var(--mono);font-size:10px;color:var(--dim)">{size_str}</td>
            <td style="font-family:var(--mono);font-size:10px;color:{'var(--danger)' if job_cost>0.5 else 'var(--dim)'}">${job_cost:.3f}</td>
            <td style="color:var(--dim);font-size:10px">{(j.get('created_at','') or '')[:16]}</td>
        </tr>"""

    # Pagination
    qs = f"&q={_esc(search)}&status={status_filter}&type={type_filter}&user={user_filter}&sort={sort}&order={order}"
    pag = '<div class="pagination">'
    if page > 1: pag += f'<a href="?page={page-1}{qs}">← Prev</a>'
    pag += f'<span style="color:var(--dim)">Page {page}/{total_pages} ({total} jobs)</span>'
    if page < total_pages: pag += f'<a href="?page={page+1}{qs}">Next →</a>'
    pag += '</div>'

    return admin_layout(f"""
    <h1 class="page-title">⚡ Job Monitor</h1>
    <p class="page-sub">{total} total jobs</p>

    <div class="stat-row" style="margin-bottom:12px">
        <div class="stat-box"><div class="val" style="color:var(--warn)">{stat_running}</div><div class="lbl">Running Now</div></div>
        <div class="stat-box"><div class="val">{stat_today}</div><div class="lbl">Today</div></div>
        <div class="stat-box"><div class="val" style="color:var(--danger)">{stat_failed}</div><div class="lbl">Failed (7d)</div></div>
    </div>

    <div class="search-bar">
        <form method="get" style="display:flex;gap:6px;flex:1">
            <input type="text" name="q" placeholder="Search title or email…" value="{_esc(search)}" style="flex:1">
            <select name="status"><option value="">All Status</option>{"".join(f'<option value="{s}" {"selected" if status_filter==s else ""}>{s}</option>' for s in ['queued','running','complete','failed','cancelled'])}</select>
            <select name="type"><option value="">All Types</option>{"".join(f'<option value="{t}" {"selected" if type_filter==t else ""}>{t}</option>' for t in types)}</select>
            <input type="hidden" name="user" value="{user_filter}">
            <button type="submit" class="btn btn-primary">Filter</button>
        </form>
    </div>

    <div class="card" style="padding:0;overflow-x:auto">
        <table>
            <tr><th>ID</th><th>User</th><th>Title</th><th>Type</th><th>Status</th><th>Size</th><th>Cost</th><th>Created</th></tr>
            {rows_html}
        </table>
    </div>
    {pag}
    """, "jobs")


# ═══════════════════════════════════════════════
# Job Detail + Content Preview
# ═══════════════════════════════════════════════

@admin_bp.route("/jobs/<job_id>")
@admin_required
def admin_job_detail(job_id):
    from admin.routes import admin_layout
    db = get_db()

    job = db.execute("SELECT j.*, u.email, u.name as user_name FROM jobs j LEFT JOIN users u ON j.user_id=u.id WHERE j.id=?", (job_id,)).fetchone()
    if not job:
        return "Job not found", 404

    params = json.loads(job["params"]) if job["params"] else {}
    od = Path(job["output_dir"]) if job.get("output_dir") else None

    # Cost
    job_cost = 0; cost_events = []
    try:
        job_cost = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE job_id=?", (job_id,)).fetchone()["c"]
        cost_events = db.execute("SELECT * FROM cost_events WHERE job_id=? ORDER BY created_at", (job_id,)).fetchall()
    except Exception:
        pass

    status_cls = {"complete":"badge-active","failed":"badge-suspended","running":"badge-pro","queued":"badge-free"}.get(job["status"],"badge-user")

    # Params display
    params_html = ""
    for k, v in sorted(params.items()):
        val_str = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
        if len(val_str) > 100: val_str = val_str[:100] + "…"
        params_html += f'<tr><td style="font-weight:600;color:var(--accent);width:180px">{_esc(k)}</td><td style="font-family:var(--mono);font-size:11px">{_esc(val_str)}</td></tr>'

    # File tree
    file_tree = ""
    art_previews = ""
    gdd_preview = ""
    paytable_preview = ""
    sim_preview = ""

    if od and od.exists():
        total_size = 0
        file_count = 0
        for root, dirs, files_list in os.walk(od):
            rel_root = os.path.relpath(root, od)
            depth = rel_root.count(os.sep)
            indent = "  " * depth
            if rel_root != ".":
                file_tree += f'{indent}📁 {os.path.basename(root)}/\n'
            for fn in sorted(files_list):
                fp = Path(root) / fn
                sz = fp.stat().st_size
                total_size += sz
                file_count += 1
                sz_str = f"{sz/1024:.1f}KB" if sz < 1048576 else f"{sz/1048576:.1f}MB"
                file_tree += f'{indent}  {fn} ({sz_str})\n'

        # GDD preview
        for gdd_name in ["gdd.md", "game_design_document.md", "gdd.txt"]:
            gdd_path = od / "02_design" / gdd_name
            if gdd_path.exists():
                text = gdd_path.read_text(encoding="utf-8", errors="replace")[:3000]
                gdd_preview = f'<div class="card"><h3>📝 GDD Preview</h3><pre style="font-size:11px;color:var(--dim);white-space:pre-wrap;max-height:300px;overflow-y:auto">{_esc(text)}</pre></div>'
                break

        # Paytable preview
        for pt_name in ["paytable.csv", "paytable.json"]:
            pt_path = od / "03_math" / pt_name
            if pt_path.exists():
                text = pt_path.read_text(encoding="utf-8", errors="replace")[:2000]
                paytable_preview = f'<div class="card"><h3>📊 Paytable</h3><pre style="font-size:11px;color:var(--dim);white-space:pre-wrap;max-height:200px;overflow-y:auto">{_esc(text)}</pre></div>'
                break

        # Simulation results
        sim_path = od / "03_math" / "simulation_results.json"
        if sim_path.exists():
            try:
                sim = json.loads(sim_path.read_text())
                rtp = sim.get("measured_rtp", "?")
                hit = sim.get("hit_frequency_pct", "?")
                max_w = sim.get("max_win_achieved", "?")
                sim_preview = f'''<div class="card"><h3>🎰 Simulation Results</h3>
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:12px">
                        <div>RTP: <b style="color:var(--accent)">{rtp}%</b></div>
                        <div>Hit Rate: <b>{hit}%</b></div>
                        <div>Max Win: <b>{max_w}x</b></div>
                    </div></div>'''
            except Exception:
                pass

        # Art previews (list PNG files)
        art_dir = od / "04_art"
        if art_dir.exists():
            imgs = sorted(art_dir.glob("*.png"))[:12]
            if imgs:
                thumbs = "".join(
                    f'<div style="text-align:center;font-size:9px;color:var(--dim)">'
                    f'<div style="width:60px;height:60px;background:var(--surface);border:1px solid var(--border);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:20px">🖼️</div>'
                    f'{_esc(img.name[:12])}</div>'
                    for img in imgs
                )
                art_previews = f'<div class="card"><h3>🎨 Art Assets ({len(imgs)} images)</h3><div style="display:flex;gap:8px;flex-wrap:wrap">{thumbs}</div></div>'

        size_str = f"{total_size/1024:.0f}KB" if total_size < 1048576 else f"{total_size/1048576:.1f}MB"
    else:
        file_count = 0; size_str = "N/A"

    # Cost events table
    cost_html = ""
    if cost_events:
        for ce in cost_events[:20]:
            cost_html += f'<tr><td style="font-size:10px">{ce["event_type"]}</td><td style="font-family:var(--mono);font-size:10px">{ce.get("model","")}</td><td style="font-weight:600">${ce["cost_usd"]:.4f}</td><td style="color:var(--dim);font-size:10px">{ce.get("input_tokens",0):,}→{ce.get("output_tokens",0):,}</td><td style="color:var(--dim);font-size:10px">{ce.get("latency_ms",0)}ms</td></tr>'

    return admin_layout(f"""
    <div style="margin-bottom:12px"><a href="/admin/jobs" style="color:var(--dim);font-size:12px;text-decoration:none">← Back to Jobs</a></div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
        <div>
            <h1 class="page-title">{_esc((job['title'] or '')[:50])}</h1>
            <p class="page-sub" style="margin-bottom:0">
                <span class="badge {status_cls}">{job['status']}</span>
                <span style="margin-left:6px">{job.get('job_type','')}</span>
                · <a href="/admin/users/{job['user_id']}" style="color:var(--accent)">{_esc((job.get('email','') or '')[:30])}</a>
                · {(job.get('created_at','') or '')[:16]}
            </p>
        </div>
    </div>

    <div class="stat-row">
        <div class="stat-box"><div class="val" style="font-size:18px">{file_count}</div><div class="lbl">Files</div></div>
        <div class="stat-box"><div class="val" style="font-size:18px">{size_str}</div><div class="lbl">Total Size</div></div>
        <div class="stat-box"><div class="val" style="font-size:18px;color:var(--danger)">${job_cost:.3f}</div><div class="lbl">Cost</div></div>
        <div class="stat-box"><div class="val" style="font-size:18px">{len(cost_events)}</div><div class="lbl">API Calls</div></div>
    </div>

    <div class="card">
        <h3>🔧 Actions</h3>
        <div style="display:flex;gap:8px">
            <a href="/job/{job_id}/files" class="btn btn-sm" target="_blank">📂 View Files (User View)</a>
            {"<form method='post' action='/admin/api/jobs/"+job_id+"/cancel' style='display:inline'><button class='btn btn-sm btn-danger'>Cancel</button></form>" if job['status'] in ('queued','running') else ""}
            <form method="post" action="/admin/api/jobs/{job_id}/delete" style="display:inline" onsubmit="return confirm('Delete this job and all files?')"><button class="btn btn-sm btn-danger">🗑️ Delete</button></form>
            {"<form method='post' action='/admin/api/jobs/"+job_id+"/requeue' style='display:inline'><button class='btn btn-sm'>🔄 Re-queue</button></form>" if job['status']=='failed' else ""}
        </div>
    </div>

    {sim_preview}
    {gdd_preview}
    {paytable_preview}
    {art_previews}

    <div class="card">
        <h3>📋 Parameters</h3>
        <table>{params_html}</table>
    </div>

    {"<div class='card'><h3>💰 Cost Breakdown ("+str(len(cost_events))+" events)</h3><table><tr><th>Type</th><th>Model</th><th>Cost</th><th>Tokens</th><th>Latency</th></tr>"+cost_html+"</table></div>" if cost_html else ""}

    <div class="card">
        <h3>📁 File Tree</h3>
        <pre style="font-size:10px;color:var(--dim);max-height:300px;overflow-y:auto;white-space:pre-wrap">{_esc(file_tree) if file_tree else "No output directory"}</pre>
    </div>
    """, "jobs")


# ═══════════════════════════════════════════════
# Job Action APIs
# ═══════════════════════════════════════════════

@admin_bp.route("/api/jobs/<job_id>/cancel", methods=["POST"])
@admin_required
def admin_cancel_job(job_id):
    db = get_db()
    db.execute("UPDATE jobs SET status='cancelled', current_stage='Cancelled by admin' WHERE id=? AND status IN ('queued','running')", (job_id,))
    db.commit()
    audit_log("job_cancelled", "job", job_id)
    return redirect(f"/admin/jobs/{job_id}")


@admin_bp.route("/api/jobs/<job_id>/delete", methods=["POST"])
@admin_required
def admin_delete_job(job_id):
    import shutil
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return "Not found", 404

    # Delete output files
    if job.get("output_dir") and Path(job["output_dir"]).exists():
        try:
            shutil.rmtree(job["output_dir"])
        except Exception as e:
            pass

    db.execute("DELETE FROM cost_events WHERE job_id=?", (job_id,))
    db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    db.commit()
    audit_log("job_deleted", "job", job_id, {"title": job.get("title",""), "user_id": job.get("user_id","")})
    return redirect("/admin/jobs")


@admin_bp.route("/api/jobs/<job_id>/requeue", methods=["POST"])
@admin_required
def admin_requeue_job(job_id):
    db = get_db()
    db.execute("UPDATE jobs SET status='queued', current_stage='Re-queued by admin' WHERE id=? AND status='failed'", (job_id,))
    db.commit()
    audit_log("job_requeued", "job", job_id)
    return redirect(f"/admin/jobs/{job_id}")


# ═══════════════════════════════════════════════
# Job Stats API
# ═══════════════════════════════════════════════

@admin_bp.route("/api/jobs/stats")
@admin_required
def api_job_stats():
    """Job analytics JSON endpoint."""
    db = get_db()
    days = int(request.args.get("days", 30))
    since = (datetime.now() - timedelta(days=days)).isoformat()

    by_status = db.execute("SELECT status, COUNT(*) as c FROM jobs GROUP BY status").fetchall()
    by_type = db.execute("SELECT job_type, COUNT(*) as c FROM jobs WHERE created_at>=? GROUP BY job_type ORDER BY c DESC", (since,)).fetchall()
    by_day = db.execute("SELECT DATE(created_at) as day, COUNT(*) as c FROM jobs WHERE created_at>=? GROUP BY DATE(created_at) ORDER BY day", (since,)).fetchall()

    # Top themes
    all_jobs = db.execute("SELECT params FROM jobs WHERE created_at>=? AND params IS NOT NULL", (since,)).fetchall()
    theme_counter = {}
    for j in all_jobs:
        try:
            p = json.loads(j["params"])
            theme = p.get("theme", "")
            if theme:
                theme_counter[theme[:30]] = theme_counter.get(theme[:30], 0) + 1
        except Exception:
            pass
    top_themes = sorted(theme_counter.items(), key=lambda x: x[1], reverse=True)[:10]

    return jsonify({
        "by_status": {r["status"]: r["c"] for r in by_status},
        "by_type": {r["job_type"]: r["c"] for r in by_type},
        "by_day": [{"day": r["day"], "count": r["c"]} for r in by_day],
        "top_themes": [{"theme": t, "count": c} for t, c in top_themes],
    })
