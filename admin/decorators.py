"""
Admin decorators and utilities.
"""

import json
import uuid
import logging
from datetime import datetime
from functools import wraps
from flask import session, redirect, url_for, request, g

logger = logging.getLogger("arkainbrain.admin")


def _current_user():
    return session.get("user", {})


def admin_required(f):
    """Decorator: require authenticated admin user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _current_user()
        if not user or not user.get("id"):
            return redirect("/login")
        if user.get("role") != "admin":
            return "Forbidden — admin access required", 403
        # Update last_active
        try:
            from config.database import get_db
            db = get_db()
            db.execute("UPDATE users SET last_active_at=? WHERE id=?",
                       (datetime.now().isoformat(), user["id"]))
            db.commit()
        except Exception:
            pass
        return f(*args, **kwargs)
    return decorated


def audit_log(action: str, target_type: str = None, target_id: str = None,
              details: dict = None):
    """Record an admin action in the audit log."""
    try:
        from config.database import get_db
        user = _current_user()
        db = get_db()
        db.execute(
            "INSERT INTO admin_audit_log (id, admin_id, action, target_type, target_id, details, ip_address, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4())[:12], user.get("id", "system"), action,
             target_type, target_id,
             json.dumps(details) if details else None,
             request.remote_addr if request else None,
             datetime.now().isoformat())
        )
        db.commit()
        logger.info(f"AUDIT: {action} {target_type}:{target_id} by {user.get('email','?')}")
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")


# Plan definitions
PLANS = {
    "free":       {"label": "Free",       "price": 0,    "monthly_jobs": 10,   "features": ["basic"]},
    "pro":        {"label": "Pro",        "price": 49,   "monthly_jobs": 100,  "features": ["basic", "priority", "export_all", "variants"]},
    "studio":     {"label": "Studio",     "price": 199,  "monthly_jobs": 500,  "features": ["basic", "priority", "export_all", "variants", "api", "web3"]},
    "enterprise": {"label": "Enterprise", "price": None, "monthly_jobs": 99999, "features": ["all"]},
}


def get_plan_info(plan_name: str) -> dict:
    return PLANS.get(plan_name, PLANS["free"])
