"""
PKM Adapter — handles events from/to the PKM agent.
Key coordination: publishes content → defers AROS outreach by 2 days.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AGENTS, WARMUP_DELAY_DAYS
from bus.event_store import emit
from bus.deferred import schedule_delayed
from adapters.base_adapter import write_context_file


def on_aros_email_sent(event):
    """AROS sent an email — PKM can track vertical activity for content targeting."""
    data = event.get("data", {})
    vertical = data.get("vertical", "")
    if vertical:
        write_context_file(AGENTS["PKM"], "claw_active_verticals.json", {
            vertical: {"last_outreach": event.get("created_at", ""), "source": "AROS"}
        })
    return {"action": "tracked_vertical", "vertical": vertical}


def on_aros_deal_closed(event):
    """AROS closed a deal — PKM should atomize this into a case study."""
    data = event.get("data", {})
    emit("claw.agent_run_requested", "CLAW", {
        "reason": "deal_closed_content",
        "command": "warmup",
        "vertical": data.get("vertical", ""),
        "context": f"New deal: {data.get('company', '')} at ${data.get('revenue', 0):,.0f}",
    }, target_agent="PKM", priority=3)
    return {"action": "requested_pkm_case_study"}


def on_aria_hot_reply(event):
    """ARIA got a hot reply — PKM should create content about investor interest."""
    data = event.get("data", {})
    write_context_file(AGENTS["PKM"], "claw_investor_signals.json", {
        "latest_signal": {
            "investor": data.get("investor", ""),
            "firm": data.get("firm", ""),
            "sentiment": data.get("sentiment", ""),
            "timestamp": event.get("created_at", ""),
        }
    })
    return {"action": "logged_investor_signal"}
