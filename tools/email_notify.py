"""
ARKAINBRAIN — Email Notification Service

Sends pipeline completion emails via Resend (https://resend.com).
Triggered by the worker when a job completes or fails.

Setup:
  1. Sign up at resend.com (free tier: 100 emails/day)
  2. Add domain or use onboarding@resend.dev for testing
  3. Set RESEND_API_KEY in .env
  4. Optionally set RESEND_FROM_EMAIL (default: onboarding@resend.dev)

Email types:
  - Pipeline complete → download link + summary stats
  - Pipeline failed → error details + retry link
  - Recon complete → state research summary
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

logger = logging.getLogger("arkainbrain.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
APP_BASE_URL = os.getenv("APP_BASE_URL", "")  # e.g. https://arkainbrain.up.railway.app


def is_enabled() -> bool:
    """Check if email notifications are configured."""
    return bool(RESEND_API_KEY and RESEND_API_KEY not in ("your-resend-key", ""))


def _send_email(to: str, subject: str, html_body: str) -> dict:
    """Send email via Resend HTTP API. Returns response dict."""
    if not is_enabled():
        logger.debug("Email not sent — RESEND_API_KEY not configured")
        return {"error": "not_configured"}

    import urllib.request
    import urllib.error

    payload = json.dumps({
        "from": RESEND_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            logger.info(f"Email sent to {to}: {result.get('id', 'ok')}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.warning(f"Resend API error {e.code}: {body}")
        return {"error": f"http_{e.code}", "detail": body}
    except Exception as e:
        logger.warning(f"Email send failed: {e}")
        return {"error": str(e)}


# ============================================================
# Email Templates
# ============================================================

_BRAND_CSS = """
    body { margin:0; padding:0; background:#060610; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
    .container { max-width:560px; margin:0 auto; padding:32px 24px; }
    .logo { font-size:18px; font-weight:800; color:#e8eaf0; letter-spacing:-0.5px; }
    .logo span { color:#7c6aef; }
    .card { background:#111128; border-radius:12px; padding:24px; margin:20px 0; border:1px solid rgba(255,255,255,0.06); }
    h1 { color:#e8eaf0; font-size:22px; font-weight:700; margin:0 0 8px; }
    p { color:#7a7898; font-size:14px; line-height:1.6; margin:0 0 12px; }
    .metric { display:inline-block; background:rgba(79,70,229,0.1); border-radius:8px; padding:10px 16px; margin:4px; text-align:center; }
    .metric-val { font-size:20px; font-weight:800; color:#e8eaf0; }
    .metric-label { font-size:10px; color:#7a7898; text-transform:uppercase; letter-spacing:0.5px; }
    .btn { display:inline-block; padding:12px 28px; border-radius:8px; text-decoration:none; font-weight:700; font-size:14px; }
    .btn-primary { background:linear-gradient(135deg,#7c6aef,#5a48c2); color:#fff; }
    .btn-secondary { background:rgba(255,255,255,0.06); color:#aaa; border:1px solid rgba(255,255,255,0.1); }
    .status-success { color:#22c55e; }
    .status-fail { color:#ef4444; }
    .footer { color:#4a4870; font-size:11px; text-align:center; margin-top:32px; }
    .footer a { color:#6366f1; text-decoration:none; }
"""


def _wrap_email(inner_html: str) -> str:
    """Wrap content in the Arkain-branded email template."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{_BRAND_CSS}</style></head>
<body><div class="container">
    <div class="logo"><span>A</span> ARKAINBRAIN</div>
    {inner_html}
    <div class="footer">
        <p>Arkain Games · AI-Powered Game Development</p>
        <p><a href="{APP_BASE_URL}">Open Dashboard</a></p>
    </div>
</div></body></html>"""


# ============================================================
# Notification Functions
# ============================================================

def notify_pipeline_complete(
    to_email: str,
    job_id: str,
    game_title: str,
    output_dir: str,
    duration_seconds: Optional[int] = None,
    stats: Optional[dict] = None,
) -> dict:
    """Send pipeline completion notification."""
    if not to_email or not is_enabled():
        return {"skipped": True}

    stats = stats or {}
    rtp = stats.get("measured_rtp", "—")
    pdfs = stats.get("pdf_count", "—")
    duration_str = f"{duration_seconds // 60}m {duration_seconds % 60}s" if duration_seconds else "—"

    job_url = f"{APP_BASE_URL}/job/{job_id}" if APP_BASE_URL else "#"
    files_url = f"{APP_BASE_URL}/files/{job_id}" if APP_BASE_URL else "#"

    inner = f"""
    <div class="card">
        <h1 class="status-success">✅ Pipeline Complete</h1>
        <p>Your game <strong>{_esc(game_title)}</strong> has finished processing.</p>
        <div style="margin:16px 0">
            <div class="metric"><div class="metric-val">{_esc(str(rtp))}%</div><div class="metric-label">Measured RTP</div></div>
            <div class="metric"><div class="metric-val">{_esc(str(pdfs))}</div><div class="metric-label">PDFs Generated</div></div>
            <div class="metric"><div class="metric-val">{_esc(duration_str)}</div><div class="metric-label">Duration</div></div>
        </div>
        <p style="margin-top:16px">
            <a href="{_esc(files_url)}" class="btn btn-primary">Download Files</a>
            <a href="{_esc(job_url)}" class="btn btn-secondary" style="margin-left:8px">View Job</a>
        </p>
    </div>
    """
    return _send_email(to_email, f"✅ {game_title} — Pipeline Complete", _wrap_email(inner))


def notify_pipeline_failed(
    to_email: str,
    job_id: str,
    game_title: str,
    error: str,
) -> dict:
    """Send pipeline failure notification."""
    if not to_email or not is_enabled():
        return {"skipped": True}

    job_url = f"{APP_BASE_URL}/job/{job_id}" if APP_BASE_URL else "#"
    error_safe = _esc(error[:300])

    inner = f"""
    <div class="card">
        <h1 class="status-fail">❌ Pipeline Failed</h1>
        <p>Your game <strong>{_esc(game_title)}</strong> encountered an error.</p>
        <div style="background:rgba(239,68,68,0.08);border-radius:8px;padding:12px;margin:12px 0;font-family:monospace;font-size:12px;color:#ef4444;word-break:break-all">
            {error_safe}
        </div>
        <p style="color:#7a7898;font-size:12px">This is usually caused by an API timeout or rate limit. You can retry from the dashboard.</p>
        <p style="margin-top:16px">
            <a href="{_esc(job_url)}" class="btn btn-primary">View Job &amp; Retry</a>
        </p>
    </div>
    """
    return _send_email(to_email, f"❌ {game_title} — Pipeline Failed", _wrap_email(inner))


def notify_recon_complete(
    to_email: str,
    job_id: str,
    state_name: str,
    summary: Optional[str] = None,
) -> dict:
    """Send state recon completion notification."""
    if not to_email or not is_enabled():
        return {"skipped": True}

    job_url = f"{APP_BASE_URL}/job/{job_id}" if APP_BASE_URL else "#"
    summary_html = f'<p>{_esc(summary[:500])}</p>' if summary else ""

    inner = f"""
    <div class="card">
        <h1 class="status-success">✅ State Recon Complete</h1>
        <p>Legal research for <strong>{_esc(state_name)}</strong> has finished.</p>
        {summary_html}
        <p style="margin-top:16px">
            <a href="{_esc(job_url)}" class="btn btn-primary">View Results</a>
        </p>
    </div>
    """
    return _send_email(to_email, f"✅ {state_name} — Recon Complete", _wrap_email(inner))


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))
