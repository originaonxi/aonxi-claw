"""
Aonxi Claw — Configuration.
"""

import os
from pathlib import Path

CLAW_DIR = Path(__file__).parent
DB_PATH = str(CLAW_DIR / "claw.db")
LOG_DIR = os.path.expanduser("~/logs")

# Poll intervals (seconds)
POLL_INTERVAL = 30        # Check for new events
SCHEDULE_INTERVAL = 60    # Check agent schedules
HEALTH_INTERVAL = 300     # Check heartbeats (5 min)

# Agent registry — paths to each agent
AGENTS = {
    "AROS": os.path.expanduser("~/aros-agent"),
    "ARIA": os.path.expanduser("~/aria"),
    "OUTREACH": os.path.expanduser("~/aonxi-outreach-agent"),
    "PKM": os.path.expanduser("~/aonxi-pkm"),
    "MEMCOLLAB": os.path.expanduser("~/aonxi-memcollab"),
    "ROUTER": os.path.expanduser("~/aonxi-router"),
    "SAFEGUARD": os.path.expanduser("~/aonxi-safeguard"),
}

# SMTP for health alerts
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "")

# Deferred event defaults
WARMUP_DELAY_DAYS = 2     # Days between PKM publish and AROS outreach
