"""
Outreach Adapter — handles events for the Aonxi Outreach agent.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AGENTS
from adapters.base_adapter import write_context_file


def on_aros_hot_reply(event):
    """AROS got a hot reply — potential case study for Outreach selling Aonxi."""
    data = event.get("data", {})
    write_context_file(AGENTS["OUTREACH"], "claw_case_studies.json", {
        "latest": {
            "company": data.get("prospect", ""),
            "vertical": data.get("vertical", ""),
            "timestamp": event.get("created_at", ""),
            "usable": f"A {data.get('vertical', 'business')} just replied HOT to autonomous outreach",
        }
    })
    return {"action": "case_study_logged"}


def on_aria_investor_committed(event):
    """ARIA got investor commitment — major social proof for Outreach."""
    data = event.get("data", {})
    write_context_file(AGENTS["OUTREACH"], "claw_social_proof.json", {
        "investment": {
            "investor": data.get("investor", ""),
            "amount": data.get("amount", 0),
            "timestamp": event.get("created_at", ""),
        }
    })
    return {"action": "social_proof_updated"}


def on_memcollab_memory_distilled(event):
    """MemCollab pattern update."""
    data = event.get("data", {})
    write_context_file(AGENTS["OUTREACH"], "claw_memcollab_updates.json", {
        f"{data.get('defense_mode', 'unknown')}_{data.get('vertical', 'all')}": {
            "strength": data.get("strength", 0),
            "bypass_strategy": data.get("bypass_strategy", ""),
        }
    })
    return {"action": "memcollab_context_updated"}
