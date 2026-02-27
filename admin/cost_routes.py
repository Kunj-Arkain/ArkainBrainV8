"""
ARKAINBRAIN — Admin Cost Routes (Phase A3)

Cost tracking dashboard, per-user costs, per-job costs, rate management.
"""

import json
import math
from datetime import datetime, timedelta
from flask import request, jsonify

from admin import admin_bp
from admin.decorators import admin_required, audit_log
from config.database import get_db

_esc = lambda s: str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


@admin_bp.route("/costs")
@admin_required
def admin_costs():
    from tools.cost_tracker import get_cost_summary, get_top_spenders, get_cost_per_job, seed_cost_rates
    from admin.routes import admin_layout

    db = get_db()
    seed_cost_rates(db)

    days = int(request.args.get("days", 30))
    summary = get_cost_summary(db, days=days)
    spenders = get_top_spenders(db, days=days)
    job_costs = get_cost_per_job(db, days=days)

    now = datetime.now()
    today_cost = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE created_at>=?",
                            (now.strftime("%Y-%m-%d"),)).fetchone()["c"]
    week_cost = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events WHERE created_at>=?",
                           ((now - timedelta(days=7)).isoformat(),)).fetchone()["c"]
    all_time = db.execute("SELECT COALESCE(SUM(cost_usd),0) as c FROM cost_events").fetchone()["c"]
    total_calls = db.execute("SELECT COUNT(*) as c FROM cost_events").fetchone()["c"]
    total_tokens = db.execute("SELECT COALESCE(SUM(input_tokens+output_tokens),0) as c FROM cost_events").fetchone()["c"]

    # Daily burn rate
    daily_avg = summary["total_usd"] / max(days, 1)
    projected_monthly = daily_avg * 30

    # Provider bars
    provider_html = ""
    max_cost = max((p["cost"] for p in summary["by_provider"]), default=1) or 1
    prov_colors = {"openai": "var(--success)", "anthropic": "var(--accent)", "compute": "var(--warn)"}
    for p in summary["by_provider"]:
        pct = (p["cost"] / max_cost) * 100
        color = prov_colors.get(p["provider"], "var(--info)")
        provider_html += f"""<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:11px;width:80px;text-align:right;color:var(--dim)">{_esc(p['provider'])}</span>
            <div style="flex:1;height:18px;background:var(--surface);border-radius:3px;overflow:hidden"><div style="height:100%;width:{pct}%;background:{color};border-radius:3px"></div></div>
            <span style="font-size:11px;font-weight:700;width:70px;text-align:right">${p['cost']:.4f}</span>
            <span style="font-size:9px;color:var(--dim);width:50px">{p['calls']} calls</span>
        </div>"""

    # Model breakdown
    model_html = ""
    for m in summary["by_model"][:10]:
        tokens_k = (m["input_tokens"] + m["output_tokens"]) / 1000
        model_html += f'<tr><td style="font-family:var(--mono);font-size:11px">{_esc(m["model"])}</td><td style="font-weight:700">${m["cost"]:.4f}</td><td>{m["calls"]}</td><td style="color:var(--dim)">{tokens_k:.1f}K</td></tr>'

    # Top spenders
    spender_html = ""
    for i, s in enumerate(spenders[:10]):
        spender_html += f'<tr><td>{i+1}</td><td><a href="/admin/users/{s["user_id"]}" style="color:var(--accent);text-decoration:none">{_esc(s["email"][:30])}</a></td><td><span class="badge badge-{s["plan"]}">{s["plan"]}</span></td><td style="font-weight:700">${s["cost"]:.4f}</td><td>{s["calls"]}</td><td style="color:var(--dim)">{s["tokens"]:,}</td></tr>'

    # Per-job costs
    job_html = ""
    for j in job_costs[:10]:
        job_html += f'<tr><td><a href="/admin/jobs/{j["job_id"]}" style="color:var(--accent);text-decoration:none">{_esc((j["title"] or "")[:30])}</a></td><td>{_esc(j.get("type",""))}</td><td style="font-weight:700">${j["cost"]:.4f}</td><td>{j["calls"]}</td><td style="color:var(--dim)">{j["tokens"]:,}</td></tr>'

    # Daily chart (CSS bars)
    daily_html = ""
    max_day = max((d["cost"] for d in summary["by_day"]), default=0.01) or 0.01
    for d in summary["by_day"][-30:]:
        pct = (d["cost"] / max_day) * 100
        daily_html += f"""<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:1px;min-width:12px">
            <div style="font-size:7px;color:var(--dim)">${d['cost']:.2f}</div>
            <div style="width:100%;height:{max(pct,2)}%;background:var(--accent);border-radius:2px 2px 0 0;min-height:2px"></div>
            <div style="font-size:6px;color:var(--muted);writing-mode:vertical-rl;transform:rotate(180deg);max-height:25px;overflow:hidden">{d['day'][5:]}</div>
        </div>"""

    # Period selector
    period_tabs = ""
    for d in [7, 30, 90]:
        cls = "btn-primary" if days == d else ""
        period_tabs += f'<a href="?days={d}" class="btn btn-sm {cls}">{d}d</a>'

    return admin_layout(f"""
    <h1 class="page-title">💰 Cost Tracking</h1>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">
        <p class="page-sub" style="margin:0;flex:1">{total_calls:,} API calls tracked</p>
        <div style="display:flex;gap:4px">{period_tabs}</div>
    </div>

    <div class="stat-row">
        <div class="stat-box"><div class="val" style="color:var(--danger)">${today_cost:.2f}</div><div class="lbl">Today</div></div>
        <div class="stat-box"><div class="val" style="color:var(--warn)">${week_cost:.2f}</div><div class="lbl">This Week</div></div>
        <div class="stat-box"><div class="val">${summary['total_usd']:.2f}</div><div class="lbl">{days} Day Total</div></div>
        <div class="stat-box"><div class="val">${all_time:.2f}</div><div class="lbl">All Time</div></div>
        <div class="stat-box"><div class="val" style="font-size:18px">${projected_monthly:.2f}</div><div class="lbl">Projected Monthly</div></div>
        <div class="stat-box"><div class="val" style="font-size:18px">{total_tokens:,}</div><div class="lbl">Total Tokens</div></div>
    </div>

    <div class="card">
        <h3>📈 Daily Spend ({days}d)</h3>
        <div style="display:flex;align-items:flex-end;height:120px;gap:2px;padding:4px 0">{daily_html if daily_html else '<div style="color:var(--dim);font-size:12px">No cost data yet</div>'}</div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="card">
            <h3>🏢 By Provider</h3>
            {provider_html if provider_html else '<div style="color:var(--dim);font-size:12px">No data</div>'}
        </div>
        <div class="card">
            <h3>🤖 By Model</h3>
            <table><tr><th>Model</th><th>Cost</th><th>Calls</th><th>Tokens</th></tr>{model_html}</table>
        </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="card">
            <h3>👤 Top Spenders ({days}d)</h3>
            <table><tr><th>#</th><th>User</th><th>Plan</th><th>Cost</th><th>Calls</th><th>Tokens</th></tr>{spender_html}</table>
        </div>
        <div class="card">
            <h3>⚡ Most Expensive Jobs ({days}d)</h3>
            <table><tr><th>Job</th><th>Type</th><th>Cost</th><th>Calls</th><th>Tokens</th></tr>{job_html}</table>
        </div>
    </div>
    """, "costs")


# ═══════════════════════════════════════════════
# Cost API Endpoints
# ═══════════════════════════════════════════════

@admin_bp.route("/api/costs/summary")
@admin_required
def api_cost_summary():
    from tools.cost_tracker import get_cost_summary
    db = get_db()
    days = int(request.args.get("days", 30))
    user_id = request.args.get("user_id")
    return jsonify(get_cost_summary(db, user_id=user_id, days=days))


@admin_bp.route("/api/costs/top-spenders")
@admin_required
def api_top_spenders():
    from tools.cost_tracker import get_top_spenders
    db = get_db()
    days = int(request.args.get("days", 30))
    return jsonify(get_top_spenders(db, days=days))


@admin_bp.route("/api/costs/per-job")
@admin_required
def api_cost_per_job():
    from tools.cost_tracker import get_cost_per_job
    db = get_db()
    days = int(request.args.get("days", 30))
    return jsonify(get_cost_per_job(db, days=days))


@admin_bp.route("/api/costs/rates")
@admin_required
def api_cost_rates():
    """View current cost rates."""
    from tools.cost_tracker import DEFAULT_RATES
    db = get_db()
    rows = db.execute("SELECT * FROM cost_rates ORDER BY provider, model").fetchall()
    return jsonify({
        "db_rates": [dict(r) for r in rows],
        "defaults": {f"{k[0]}:{k[1]}": v for k, v in DEFAULT_RATES.items()},
    })


@admin_bp.route("/api/costs/rates", methods=["POST"])
@admin_required
def api_update_cost_rate():
    """Update a cost rate."""
    import uuid as _uuid
    db = get_db()
    data = request.get_json(silent=True) or {}
    provider = data.get("provider")
    model = data.get("model")
    if not provider or not model:
        return jsonify({"error": "provider and model required"}), 400

    db.execute(
        "INSERT OR REPLACE INTO cost_rates (id, provider, model, input_cost_per_1k, output_cost_per_1k, image_cost, effective_from) VALUES (?,?,?,?,?,?,?)",
        (str(_uuid.uuid4())[:8], provider, model,
         data.get("input_cost_per_1k", 0), data.get("output_cost_per_1k", 0),
         data.get("image_cost", 0), datetime.now().isoformat())
    )
    db.commit()
    audit_log("cost_rate_updated", "system", model, {"provider": provider, **data})
    return jsonify({"status": "updated"})
