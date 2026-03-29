#!/usr/bin/env python3
"""
Aonxi Claw — The Living Agent Orchestrator
============================================
A persistent daemon that makes all Aonxi agents alive and talking.

3 async loops:
  poll_loop     — process new events every 30s
  schedule_loop — fire deferred events every 60s
  health_loop   — check agent heartbeats every 5m

Run: python3 claw.py
Stop: Ctrl+C or launchctl unload
"""

import asyncio
import signal
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import POLL_INTERVAL, SCHEDULE_INTERVAL, HEALTH_INTERVAL
from bus.event_store import init as init_db, get_unprocessed, subscribe, stats, get_agent_states
from bus.subscription_engine import process_event
from bus.deferred import process_deferred


VERSION = "1.0"
RUNNING = True


def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}", flush=True)


def register_subscriptions():
    """Register all default event subscriptions."""

    # AROS listens to:
    subscribe("AROS", "pkm.content_published", "adapters.aros_adapter.on_content_published")
    subscribe("AROS", "aria.hot_reply", "adapters.aros_adapter.on_aria_hot_reply")
    subscribe("AROS", "aria.meeting_booked", "adapters.aros_adapter.on_aria_meeting_booked")
    subscribe("AROS", "outreach.vertical_signal", "adapters.aros_adapter.on_outreach_vertical_signal")
    subscribe("AROS", "outreach.pattern_discovered", "adapters.aros_adapter.on_outreach_pattern_discovered")
    subscribe("AROS", "memcollab.memory_distilled", "adapters.aros_adapter.on_memcollab_memory_distilled")

    # ARIA listens to:
    subscribe("ARIA", "aros.deal_closed", "adapters.aria_adapter.on_aros_deal_closed")
    subscribe("ARIA", "pkm.content_published", "adapters.aria_adapter.on_content_published")
    subscribe("ARIA", "outreach.pattern_discovered", "adapters.aria_adapter.on_outreach_pattern_discovered")
    subscribe("ARIA", "memcollab.memory_distilled", "adapters.aria_adapter.on_memcollab_memory_distilled")

    # OUTREACH listens to:
    subscribe("OUTREACH", "aros.hot_reply", "adapters.outreach_adapter.on_aros_hot_reply")
    subscribe("OUTREACH", "aria.investor_committed", "adapters.outreach_adapter.on_aria_investor_committed")
    subscribe("OUTREACH", "memcollab.memory_distilled", "adapters.outreach_adapter.on_memcollab_memory_distilled")

    # PKM listens to:
    subscribe("PKM", "aros.email_sent", "adapters.pkm_adapter.on_aros_email_sent")
    subscribe("PKM", "aros.deal_closed", "adapters.pkm_adapter.on_aros_deal_closed")
    subscribe("PKM", "aria.hot_reply", "adapters.pkm_adapter.on_aria_hot_reply")

    # MEMCOLLAB listens to (real-time distillation):
    subscribe("MEMCOLLAB", "aros.hot_reply", "adapters.memcollab_adapter.on_hot_outcome")
    subscribe("MEMCOLLAB", "aria.hot_reply", "adapters.memcollab_adapter.on_hot_outcome")
    subscribe("MEMCOLLAB", "aria.meeting_booked", "adapters.memcollab_adapter.on_hot_outcome")
    subscribe("MEMCOLLAB", "aros.deal_closed", "adapters.memcollab_adapter.on_hot_outcome")

    _log(f"Registered 20 subscriptions across 5 agents")


async def poll_loop():
    """Process unprocessed events every POLL_INTERVAL seconds."""
    while RUNNING:
        try:
            events = get_unprocessed(limit=50)
            if events:
                for event in events:
                    try:
                        results = process_event(event)
                        if results:
                            for r in results:
                                status = r.get("status", "?")
                                agent = r.get("agent", "?")
                                if status == "ok":
                                    _log(f"  {event['event_type']} → {agent}: OK")
                                else:
                                    _log(f"  {event['event_type']} → {agent}: ERROR {r.get('error', '')[:60]}")
                    except Exception as e:
                        _log(f"  Event {event.get('id')} processing error: {e}")
        except Exception as e:
            _log(f"Poll loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


async def schedule_loop():
    """Fire deferred events every SCHEDULE_INTERVAL seconds."""
    while RUNNING:
        try:
            fired = process_deferred()
            if fired:
                _log(f"Fired {fired} deferred event(s)")
        except Exception as e:
            _log(f"Schedule loop error: {e}")

        await asyncio.sleep(SCHEDULE_INTERVAL)


async def health_loop():
    """Check agent heartbeats every HEALTH_INTERVAL seconds."""
    while RUNNING:
        try:
            states = get_agent_states()
            stale = []
            now = datetime.now()
            for s in states:
                hb = s.get("last_heartbeat")
                if hb:
                    try:
                        hb_time = datetime.fromisoformat(hb)
                        age_hours = (now - hb_time).total_seconds() / 3600
                        if age_hours > 26:  # More than 26 hours since last heartbeat
                            stale.append(f"{s['agent']} ({age_hours:.0f}h)")
                    except (ValueError, TypeError):
                        pass

            if stale:
                _log(f"STALE AGENTS: {', '.join(stale)}")
        except Exception as e:
            _log(f"Health loop error: {e}")

        await asyncio.sleep(HEALTH_INTERVAL)


async def main():
    global RUNNING

    print()
    print("━" * 58)
    print(f"  AONXI CLAW v{VERSION} — Living Agent Orchestrator")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("━" * 58)

    # Init database
    init_db()
    _log("Database initialized")

    # Register subscriptions (idempotent — duplicates are OK, matched by pattern)
    register_subscriptions()

    # Show stats
    s = stats()
    _log(f"Bus: {s['total_events']} events, {s['unprocessed']} pending, {s['deferred_pending']} deferred")

    # Start loops
    _log(f"Starting loops: poll={POLL_INTERVAL}s, schedule={SCHEDULE_INTERVAL}s, health={HEALTH_INTERVAL}s")
    print("━" * 58)
    print()

    def shutdown(sig, frame):
        global RUNNING
        _log("Shutting down...")
        RUNNING = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    await asyncio.gather(
        poll_loop(),
        schedule_loop(),
        health_loop(),
    )

    _log("Claw stopped.")


if __name__ == "__main__":
    asyncio.run(main())
