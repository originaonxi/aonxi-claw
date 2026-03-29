"""
Deferred Events — schedule events for future delivery.
Used for coordination patterns like "publish content now, outreach in 2 days."
"""

from datetime import datetime, timedelta
from bus.event_store import defer, fire_due_deferred, get_pending_deferred


def schedule_delayed(event_type, target_agent, payload, delay_days=0, delay_hours=0, from_event_id=None):
    """Schedule an event for future delivery."""
    execute_after = datetime.now() + timedelta(days=delay_days, hours=delay_hours)
    defer(event_type, target_agent, payload, execute_after.isoformat(), from_event_id)
    return execute_after


def process_deferred():
    """Fire all deferred events that are due. Returns count fired."""
    return fire_due_deferred()


def get_pending():
    """Get all pending deferred events."""
    return get_pending_deferred()
