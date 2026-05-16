"""
HR Nexus — Email & Calendar Utilities
Gracefully degrades if credentials not set (logs to console instead).
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from database import get_conn

logger = logging.getLogger("hr-nexus")

# ─────────────────────────────────────────────
# CONFIG FROM ENV
# ─────────────────────────────────────────────

def email_cfg():
    return {
        "sender":   os.getenv("SENDER_EMAIL") or os.getenv("GMAIL_SENDER", ""),
        "password": os.getenv("SENDER_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD", ""),
        "hr_email": os.getenv("HR_EMAIL", ""),
        "hr_name":  os.getenv("HR_NAME", "HR Manager"),
    }


# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def send_email(to: str, subject: str, body: str, html: bool = False) -> bool:
    """Send email via Gmail SMTP. Falls back to console log if credentials missing."""
    cfg = email_cfg()

    if not cfg["sender"] or not cfg["password"]:
        # Fallback: log to console so demo still works without Gmail
        logger.info("\n" + "=" * 60)
        logger.info("[EMAIL SIMULATION — set SENDER_EMAIL + SENDER_PASSWORD for real emails]")
        logger.info(f"TO:      {to}")
        logger.info(f"SUBJECT: {subject}")
        logger.info(f"BODY:\n{body[:400]}...")
        logger.info("=" * 60 + "\n")
        _log_email(to, subject, body, "simulated")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"HR Nexus <{cfg['sender']}>"
        msg["To"]      = to
        msg["Subject"] = subject
        mime_type = "html" if html else "plain"
        msg.attach(MIMEText(body, mime_type))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(cfg["sender"], cfg["password"])
            srv.sendmail(cfg["sender"], [to], msg.as_string())
        _log_email(to, subject, body, "sent")
        logger.info(f"✉️  Email sent → {to}")
        return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        _log_email(to, subject, body, f"failed: {e}")
        return False


def _log_email(to, subject, body, status):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO email_log (to_email, subject, body, status, timestamp) VALUES (?,?,?,?,?)",
            (to, subject, body[:500], status, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ─────────────────────────────────────────────
# GOOGLE CALENDAR (optional)
# ─────────────────────────────────────────────

def get_calendar_service():
    """Returns Google Calendar service or None if not configured."""
    try:
        import importlib.util
        if not importlib.util.find_spec("googleapiclient"):
            return None

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        src_dir = os.path.dirname(__file__)
        token_path = os.path.join(src_dir, "data", "token.json")
        creds_path = os.path.join(src_dir, "data", "credentials.json")

        if not os.path.exists(creds_path):
            return None

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                return None  # Can't run OAuth flow in headless Docker

        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.warning(f"Calendar service unavailable: {e}")
        return None
