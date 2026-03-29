"""
MemCollab Adapter — enables real-time incremental distillation.
Instead of waiting for 2am nightly cron, distills on every HOT outcome.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bus.event_store import emit as bus_emit

# Try to import MemCollab functions
sys.path.insert(0, os.path.expanduser("~/aonxi-memcollab"))
try:
    from memcollab import (
        get_all_trajectories,
        distill_shared_memory,
        write_shared_memory,
        retrieve_shared_memory,
    )
    MEMCOLLAB_AVAILABLE = True
except ImportError:
    MEMCOLLAB_AVAILABLE = False


def on_hot_outcome(event):
    """Any agent got a HOT reply or meeting — trigger incremental distillation."""
    if not MEMCOLLAB_AVAILABLE:
        return {"action": "skipped", "reason": "memcollab_not_available"}

    data = event.get("data", {})
    defense_mode = data.get("defense_mode", "")
    vertical = data.get("vertical", "")

    if not defense_mode:
        return {"action": "skipped", "reason": "no_defense_mode"}

    try:
        # Get recent trajectories for this (defense_mode, vertical) pair
        all_trajs = get_all_trajectories(limit=100)
        relevant = [t for t in all_trajs
                    if getattr(t, "defense_mode", "") == defense_mode
                    and (not vertical or getattr(t, "vertical", "") == vertical)]

        if len(relevant) < 5:
            return {"action": "skipped", "reason": f"only_{len(relevant)}_trajectories"}

        # Run incremental distillation
        memories = distill_shared_memory(relevant)
        if not memories:
            return {"action": "skipped", "reason": "no_memories_distilled"}

        best = memories[0]

        # Check if it's stronger than current
        current = retrieve_shared_memory(defense_mode, vertical)
        current_strength = current[0].get("memory_strength", 0) if current else 0

        if best.get("memory_strength", 0) > current_strength:
            write_shared_memory([best])

            # Broadcast to all agents
            bus_emit("memcollab.memory_distilled", "MEMCOLLAB", {
                "defense_mode": defense_mode,
                "vertical": vertical,
                "strength": best.get("memory_strength", 0),
                "bypass_strategy": best.get("bypass_strategy", ""),
                "source": f"incremental_from_{event.get('source_agent', 'unknown')}",
            })

            return {
                "action": "distilled",
                "defense_mode": defense_mode,
                "vertical": vertical,
                "strength": best.get("memory_strength", 0),
            }

        return {"action": "skipped", "reason": "existing_memory_stronger"}

    except Exception as e:
        return {"action": "error", "error": str(e)}
