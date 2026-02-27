"""
ARKAINBRAIN — Admin Backend

Flask blueprint providing:
- A1: User management, RBAC, audit logging
- A3: Cost tracking, LLM metering
- A2: Job monitoring, content visibility
"""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Import routes to register them on the blueprint
from admin import routes      # noqa: E402, F401  — A1: dashboard + users
from admin import cost_routes # noqa: E402, F401  — A3: cost tracking
from admin import job_routes  # noqa: E402, F401  — A2: job monitoring
