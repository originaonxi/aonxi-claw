#!/usr/bin/env python3
"""
Claw CLI — inspect and control the Aonxi Claw event bus.

Commands:
  claw status          Show agent states + event bus stats
  claw events [N]      Show last N events (default 20)
  claw tail            Live-tail events (poll every 2s)
  claw deferred        Show pending deferred events
  claw emit TYPE JSON  Manually emit an event
  claw trigger AGENT   Request an agent run
  claw subs            Show active subscriptions
"""

import sys
import os
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bus import event_store


def cmd_status():
    s = event_store.stats()
    states = event_store.get_agent_states()

    print("━" * 60)
    print("  AONXI CLAW — STATUS")
    print("━" * 60)
    print(f"  Events total:     {s['total_events']}")
    print(f"  Unprocessed:      {s['unprocessed']}")
    print(f"  Events today:     {s['events_today']}")
    print(f"  Subscriptions:    {s['total_subscriptions']}")
    print(f"  Agents:           {s['agents_registered']}")
    print(f"  Deferred pending: {s['deferred_pending']}")

    if states:
        print(f"\n{'─' * 60}")
        print(f"  {'AGENT':<12} {'HEARTBEAT':<22} {'STATUS':<10} {'LAST RUN'}")
        print(f"  {'─'*12} {'─'*22} {'─'*10} {'─'*22}")
        for a in states:
            hb = (a.get("last_heartbeat") or "never")[:19]
            status = a.get("last_run_status") or "?"
            lr = (a.get("last_run_at") or "never")[:19]
            print(f"  {a['agent']:<12} {hb:<22} {status:<10} {lr}")

    print("━" * 60)


def cmd_events(limit=20):
    events = event_store.get_recent(limit=limit)
    print("━" * 60)
    print(f"  LAST {limit} EVENTS")
    print("━" * 60)

    if not events:
        print("  (no events)")
    else:
        for e in events:
            ts = (e.get("created_at") or "")[:19]
            src = e.get("source_agent", "?")
            tgt = e.get("target_agent") or "*"
            etype = e.get("event_type", "?")
            processed = "done" if e.get("processed_at") else "PENDING"
            payload = e.get("payload", "{}")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    pass

            # Truncate payload for display
            payload_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)
            if len(payload_str) > 60:
                payload_str = payload_str[:57] + "..."

            print(f"  [{ts}] {src:>8} → {tgt:<8} | {etype:<30} [{processed}]")
            print(f"         {payload_str}")
            print()

    print("━" * 60)


def cmd_tail():
    print("  AONXI CLAW — LIVE TAIL (Ctrl+C to stop)")
    print("━" * 60)

    last_id = 0
    events = event_store.get_recent(limit=1)
    if events:
        last_id = events[0].get("id", 0)

    try:
        while True:
            events = event_store.get_recent(limit=10)
            new_events = [e for e in events if e.get("id", 0) > last_id]
            new_events.reverse()  # oldest first

            for e in new_events:
                ts = (e.get("created_at") or "")[:19]
                src = e.get("source_agent", "?")
                tgt = e.get("target_agent") or "*"
                etype = e.get("event_type", "?")
                print(f"  [{ts}] {src} → {tgt} | {etype}")
                last_id = max(last_id, e.get("id", 0))

            time.sleep(2)
    except KeyboardInterrupt:
        print("\n  Stopped.")


def cmd_deferred():
    from bus.deferred import get_pending
    pending = get_pending()
    print("━" * 60)
    print(f"  DEFERRED EVENTS ({len(pending)} pending)")
    print("━" * 60)

    if not pending:
        print("  (none)")
    else:
        for d in pending:
            print(f"  ID {d['id']} | {d['event_type']} → {d['target_agent']}")
            print(f"    Fires after: {d['execute_after']}")
            payload = d.get("payload", "{}")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    pass
            payload_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)
            if len(payload_str) > 80:
                payload_str = payload_str[:77] + "..."
            print(f"    Payload: {payload_str}")
            print()

    print("━" * 60)


def cmd_emit(event_type, payload_json):
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        print(f"  ERROR: Invalid JSON: {payload_json}")
        return

    eid = event_store.emit(event_type, "CLI", payload)
    print(f"  Emitted event {eid}: {event_type}")


def cmd_trigger(agent):
    eid = event_store.emit("claw.agent_run_requested", "CLI", {"reason": "manual_trigger"}, target_agent=agent, priority=1)
    print(f"  Triggered {agent} (event {eid})")


def cmd_subs():
    subs = event_store.get_subscriptions()
    print("━" * 60)
    print(f"  SUBSCRIPTIONS ({len(subs)})")
    print("━" * 60)

    if not subs:
        print("  (none — run claw.py to register default subscriptions)")
    else:
        for s in subs:
            active = "ON" if s.get("active") else "OFF"
            print(f"  [{active}] {s['agent']:<12} listens to {s['event_pattern']:<30} → {s['handler']}")

    print("━" * 60)


def main():
    parser = argparse.ArgumentParser(description="Aonxi Claw CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show agent states + bus stats")

    ev = sub.add_parser("events", help="Show recent events")
    ev.add_argument("limit", nargs="?", type=int, default=20)

    sub.add_parser("tail", help="Live-tail events")
    sub.add_parser("deferred", help="Show pending deferred events")

    em = sub.add_parser("emit", help="Manually emit an event")
    em.add_argument("event_type", help="e.g., test.ping")
    em.add_argument("payload", help="JSON payload")

    tr = sub.add_parser("trigger", help="Request an agent run")
    tr.add_argument("agent", help="e.g., AROS, ARIA, PKM")

    sub.add_parser("subs", help="Show active subscriptions")

    args = parser.parse_args()

    event_store.init()

    if args.command == "status":
        cmd_status()
    elif args.command == "events":
        cmd_events(args.limit)
    elif args.command == "tail":
        cmd_tail()
    elif args.command == "deferred":
        cmd_deferred()
    elif args.command == "emit":
        cmd_emit(args.event_type, args.payload)
    elif args.command == "trigger":
        cmd_trigger(args.agent)
    elif args.command == "subs":
        cmd_subs()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
