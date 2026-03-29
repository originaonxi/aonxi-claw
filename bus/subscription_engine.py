"""
Subscription Engine — matches events to handlers using glob patterns.
"""

import fnmatch
import importlib
import json
from bus.event_store import get_subscriptions, ack


def match_subscriptions(event):
    """Find all subscriptions that match this event. Returns list of (subscription, handler_func)."""
    subs = get_subscriptions(active_only=True)
    matches = []

    event_type = event.get("event_type", "")
    target = event.get("target_agent")

    for sub in subs:
        pattern = sub["event_pattern"]

        # Match event type against pattern (glob)
        if not fnmatch.fnmatch(event_type, pattern):
            continue

        # If event has a target, only deliver to that agent's subscriptions
        if target and sub["agent"] != target:
            continue

        # Don't deliver to the source agent (no self-loops)
        if sub["agent"] == event.get("source_agent"):
            continue

        matches.append(sub)

    return matches


def dispatch(event, subscriptions):
    """Call each subscription's handler with the event. Returns results."""
    results = []

    for sub in subscriptions:
        handler_path = sub["handler"]
        try:
            # Import handler: "adapters.aros_adapter.on_content_published"
            module_path, func_name = handler_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler_func = getattr(module, func_name)

            # Parse payload
            payload = event.get("payload", "{}")
            if isinstance(payload, str):
                payload = json.loads(payload)

            # Call handler
            result = handler_func({
                "id": event["id"],
                "event_type": event["event_type"],
                "source_agent": event["source_agent"],
                "target_agent": event.get("target_agent"),
                "data": payload,
                "created_at": event.get("created_at"),
                "correlation_id": event.get("correlation_id"),
            })

            results.append({
                "subscription": sub["id"],
                "agent": sub["agent"],
                "handler": handler_path,
                "status": "ok",
                "result": result,
            })
        except Exception as e:
            results.append({
                "subscription": sub["id"],
                "agent": sub["agent"],
                "handler": handler_path,
                "status": "error",
                "error": str(e),
            })

    return results


def process_event(event):
    """Match, dispatch, and ack a single event. Returns dispatch results."""
    subs = match_subscriptions(event)

    if not subs:
        # No subscribers — ack it so it doesn't pile up
        ack(event["id"], "CLAW:no_subscribers")
        return []

    results = dispatch(event, subs)

    # Ack the event
    handlers = [r["agent"] for r in results if r["status"] == "ok"]
    ack(event["id"], f"CLAW:{','.join(handlers) if handlers else 'dispatch_attempted'}")

    return results
