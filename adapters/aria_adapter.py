"""
ARIA Adapter — handles events targeted at ARIA.
Key coordination: AROS deal → stronger pitch, PKM content → thought leadership refs.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AGENTS
from adapters.base_adapter import write_context_file


def on_aros_deal_closed(event):
    """AROS closed a deal — ARIA pitch gets stronger ARR number."""
    data = event.get("data", {})
    write_context_file(AGENTS["ARIA"], "claw_context.json", {
        "latest_deal": {
            "company": data.get("company", ""),
            "revenue": data.get("revenue", 0),
            "vertical": data.get("vertical", ""),
            "timestamp": event.get("created_at", ""),
        },
        "pitch_update": f"Just closed {data.get('company', 'a new customer')} in {data.get('vertical', 'our target market')}. ARR growing.",
    })
    return {"action": "pitch_strengthened"}


def on_content_published(event):
    """PKM published thought leadership — ARIA can reference it."""
    data = event.get("data", {})
    write_context_file(AGENTS["ARIA"], "claw_content_refs.json", {
        "latest_content": {
            "hook": data.get("hook", ""),
            "content_type": data.get("content_type", ""),
            "vertical": data.get("vertical", ""),
            "timestamp": event.get("created_at", ""),
        }
    })
    return {"action": "content_ref_updated"}


def on_outreach_pattern_discovered(event):
    """Outreach found a winning pattern — ARIA can use it for investor pitches."""
    data = event.get("data", {})
    if data.get("win_rate", 0) > 0.2:
        write_context_file(AGENTS["ARIA"], "claw_proof_points.json", {
            "latest_proof": {
                "pattern": data.get("pattern", ""),
                "win_rate": data.get("win_rate", 0),
                "description": f"Our outreach agent just hit {data.get('win_rate', 0):.0%} on {data.get('pattern', 'a new approach')}",
                "timestamp": event.get("created_at", ""),
            }
        })
        return {"action": "proof_point_added"}
    return {"action": "skipped", "reason": "win_rate_too_low"}


def on_memcollab_memory_distilled(event):
    """MemCollab distilled a new pattern — update ARIA context."""
    data = event.get("data", {})
    write_context_file(AGENTS["ARIA"], "claw_memcollab_updates.json", {
        f"{data.get('defense_mode', 'unknown')}_{data.get('vertical', 'all')}": {
            "strength": data.get("strength", 0),
            "bypass_strategy": data.get("bypass_strategy", ""),
            "timestamp": event.get("created_at", ""),
        }
    })
    return {"action": "memcollab_context_updated"}
