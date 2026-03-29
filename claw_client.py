"""
Claw Client — importable by any agent.
Provides fire-and-forget event emission and pending event retrieval.

Usage from any agent:
    sys.path.insert(0, os.path.expanduser("~/aonxi-claw"))
    from claw_client import emit, heartbeat, get_pending_events, ack
"""

import sqlite3
import json
import os
from datetime import datetime

CLAW_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claw.db")


def _conn():
    if not os.path.exists(CLAW_DB):
        return None
    conn = sqlite3.connect(CLAW_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def emit(event_type, data, source_agent="UNKNOWN", target_agent=None, priority=5, correlation_id=None):
    """Fire-and-forget event into the Claw bus.

    Args:
        event_type: e.g., 'aros.email_sent', 'aria.hot_reply', 'pkm.content_published'
        data: dict payload
        source_agent: 'AROS', 'ARIA', 'OUTREACH', 'PKM', etc.
        target_agent: specific agent or None for broadcast
        priority: 1=critical, 5=normal, 9=low
    """
    conn = _conn()
    if not conn:
        return None
    try:
        conn.execute(
            """INSERT INTO events (event_type, source_agent, target_agent, payload, priority, correlation_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_type, source_agent, target_agent, json.dumps(data), priority, correlation_id)
        )
        conn.commit()
        eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return eid
    except Exception:
        conn.close()
        return None


def heartbeat(agent_name, run_summary=None, run_status=None):
    """Signal that an agent is alive. Call at start and end of runs."""
    conn = _conn()
    if not conn:
        return
    try:
        now = datetime.now().isoformat()
        existing = conn.execute("SELECT agent FROM agent_state WHERE agent = ?", (agent_name,)).fetchone()
        if existing:
            updates = ["last_heartbeat = ?"]
            params = [now]
            if run_summary is not None:
                updates.append("last_run_summary = ?")
                params.append(json.dumps(run_summary))
                updates.append("last_run_at = ?")
                params.append(now)
            if run_status is not None:
                updates.append("last_run_status = ?")
                params.append(run_status)
            params.append(agent_name)
            conn.execute(f"UPDATE agent_state SET {', '.join(updates)} WHERE agent = ?", params)
        else:
            conn.execute(
                "INSERT INTO agent_state (agent, last_heartbeat, last_run_status, last_run_summary) VALUES (?, ?, ?, ?)",
                (agent_name, now, run_status or "alive", json.dumps(run_summary or {}))
            )
        conn.commit()
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def get_pending_events(agent_name, limit=20):
    """Pull unprocessed events targeted at this agent."""
    conn = _conn()
    if not conn:
        return []
    try:
        rows = conn.execute(
            """SELECT id, event_type, source_agent, payload, priority, correlation_id, created_at
               FROM events
               WHERE processed_at IS NULL AND (target_agent = ? OR target_agent IS NULL)
               AND source_agent != ?
               ORDER BY priority ASC, created_at ASC LIMIT ?""",
            (agent_name, agent_name, limit)
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["data"] = json.loads(d["payload"])
            except (json.JSONDecodeError, TypeError):
                d["data"] = {}
            result.append(d)
        return result
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []


def ack(event_id, agent_name):
    """Mark an event as processed by this agent."""
    conn = _conn()
    if not conn:
        return
    try:
        conn.execute(
            "UPDATE events SET processed_at = datetime('now'), processed_by = ? WHERE id = ?",
            (agent_name, event_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
