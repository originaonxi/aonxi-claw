"""
AROS Adapter — handles events targeted at AROS.
Key coordination: receives warmup timing from PKM, social proof from ARIA.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AGENTS, WARMUP_DELAY_DAYS
from bus.event_store import emit
from bus.deferred import schedule_delayed
from adapters.base_adapter import write_context_file


def on_content_published(event):
    """PKM published content — delay AROS outreach to that vertical by 2 days."""
    data = event.get("data", {})
    vertical = data.get("vertical", "")
    hook = data.get("hook", "")
    content_type = data.get("content_type", "linkedin_post")

    if not vertical:
        return {"action": "skipped", "reason": "no_vertical"}

    # Schedule deferred outreach signal
    execute_at = schedule_delayed(
        event_type="claw.warmup_outreach_ready",
        target_agent="AROS",
        payload={
            "vertical": vertical,
            "warmup_hook": hook,
            "content_type": content_type,
            "instruction": f"Reference recent content about {vertical} in outreach. Hook: '{hook[:80]}'",
        },
        delay_days=WARMUP_DELAY_DAYS,
        from_event_id=event.get("id"),
    )

    # Also write immediate context for AROS to know about the upcoming warmup
    write_context_file(AGENTS["AROS"], "claw_warmup_pending.json", {
        vertical: {
            "content_published_at": event.get("created_at", ""),
            "outreach_ready_at": execute_at.isoformat(),
            "hook": hook,
        }
    })

    return {"action": "deferred_outreach", "vertical": vertical, "outreach_at": execute_at.isoformat()}


def on_aria_hot_reply(event):
    """ARIA got a hot reply — AROS can use this as social proof."""
    data = event.get("data", {})
    write_context_file(AGENTS["AROS"], "claw_social_proof.json", {
        "investor_interest": {
            "firm": data.get("firm", ""),
            "sentiment": data.get("sentiment", ""),
            "timestamp": event.get("created_at", ""),
            "usable_line": "We're in active conversations with top-tier investors.",
        }
    })
    return {"action": "social_proof_updated"}


def on_aria_meeting_booked(event):
    """ARIA booked a meeting — stronger social proof for AROS."""
    data = event.get("data", {})
    write_context_file(AGENTS["AROS"], "claw_social_proof.json", {
        "investor_meeting": {
            "firm": data.get("firm", ""),
            "date": data.get("date", ""),
            "timestamp": event.get("created_at", ""),
            "usable_line": f"We just booked with {data.get('firm', 'a top-tier investor')}.",
        }
    })
    return {"action": "social_proof_upgraded"}


def on_outreach_vertical_signal(event):
    """Outreach discovered a hot vertical — AROS should boost ICP weights."""
    data = event.get("data", {})
    vertical = data.get("vertical", "")
    conversion_rate = data.get("conversion_rate", 0)
    sample_size = data.get("sample_size", 0)

    if conversion_rate > 0.15 and sample_size >= 20:
        write_context_file(AGENTS["AROS"], "claw_icp_boost.json", {
            vertical: {
                "boost": True,
                "conversion_rate": conversion_rate,
                "sample_size": sample_size,
                "source": "OUTREACH",
                "timestamp": event.get("created_at", ""),
            }
        })
        return {"action": "icp_boosted", "vertical": vertical, "rate": conversion_rate}

    return {"action": "skipped", "reason": "insufficient_signal"}


def on_outreach_pattern_discovered(event):
    """Outreach discovered a winning pattern — AROS can use it."""
    data = event.get("data", {})
    write_context_file(AGENTS["AROS"], "claw_winning_patterns.json", {
        data.get("pattern", "unknown"): {
            "win_rate": data.get("win_rate", 0),
            "vertical": data.get("vertical", ""),
            "source": "OUTREACH",
            "timestamp": event.get("created_at", ""),
        }
    })
    return {"action": "pattern_shared"}


def on_memcollab_memory_distilled(event):
    """MemCollab distilled a new pattern — update AROS context."""
    data = event.get("data", {})
    write_context_file(AGENTS["AROS"], "claw_memcollab_updates.json", {
        f"{data.get('defense_mode', 'unknown')}_{data.get('vertical', 'all')}": {
            "strength": data.get("strength", 0),
            "bypass_strategy": data.get("bypass_strategy", ""),
            "timestamp": event.get("created_at", ""),
        }
    })
    return {"action": "memcollab_context_updated"}
