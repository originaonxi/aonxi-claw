"""
Event Store — SQLite-backed event bus.
All inter-agent communication flows through here.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init():
    """Create all tables. Safe to call multiple times."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            source_agent TEXT NOT NULL,
            target_agent TEXT,
            payload TEXT NOT NULL,
            priority INTEGER DEFAULT 5,
            correlation_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            processed_at TEXT,
            processed_by TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_events_unprocessed
            ON events(target_agent, processed_at) WHERE processed_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_events_type
            ON events(event_type, created_at);
        CREATE INDEX IF NOT EXISTS idx_events_source
            ON events(source_agent, created_at);

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            event_pattern TEXT NOT NULL,
            handler TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_state (
            agent TEXT PRIMARY KEY,
            last_heartbeat TEXT,
            last_run_at TEXT,
            last_run_status TEXT,
            last_run_summary TEXT,
            config TEXT
        );

        CREATE TABLE IF NOT EXISTS deferred_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            target_agent TEXT NOT NULL,
            payload TEXT NOT NULL,
            execute_after TEXT NOT NULL,
            created_from_event_id INTEGER,
            fired INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_deferred_pending
            ON deferred_events(execute_after, fired) WHERE fired = 0;
    """)
    conn.commit()
    conn.close()


# ── Events ──

def emit(event_type, source_agent, payload, target_agent=None, priority=5, correlation_id=None):
    """Insert an event into the bus. Returns event ID."""
    conn = _conn()
    conn.execute(
        """INSERT INTO events (event_type, source_agent, target_agent, payload, priority, correlation_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (event_type, source_agent, target_agent, json.dumps(payload), priority, correlation_id)
    )
    conn.commit()
    eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return eid


def get_unprocessed(target_agent=None, limit=50):
    """Get unprocessed events, optionally filtered by target agent."""
    conn = _conn()
    if target_agent:
        rows = conn.execute(
            """SELECT * FROM events
               WHERE processed_at IS NULL AND (target_agent = ? OR target_agent IS NULL)
               ORDER BY priority ASC, created_at ASC LIMIT ?""",
            (target_agent, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM events WHERE processed_at IS NULL
               ORDER BY priority ASC, created_at ASC LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def ack(event_id, processed_by):
    """Mark event as processed."""
    conn = _conn()
    conn.execute(
        "UPDATE events SET processed_at = datetime('now'), processed_by = ? WHERE id = ?",
        (processed_by, event_id)
    )
    conn.commit()
    conn.close()


def get_recent(limit=20, event_type=None, source_agent=None):
    """Get recent events for display."""
    conn = _conn()
    sql = "SELECT * FROM events WHERE 1=1"
    params = []
    if event_type:
        sql += " AND event_type LIKE ?"
        params.append(f"%{event_type}%")
    if source_agent:
        sql += " AND source_agent = ?"
        params.append(source_agent)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_event_counts(hours=24):
    """Get event counts by type for the last N hours."""
    conn = _conn()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """SELECT event_type, source_agent, COUNT(*) as cnt
           FROM events WHERE created_at > ?
           GROUP BY event_type, source_agent ORDER BY cnt DESC""",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Subscriptions ──

def subscribe(agent, event_pattern, handler):
    """Register an agent's interest in events matching a pattern."""
    conn = _conn()
    conn.execute(
        "INSERT INTO subscriptions (agent, event_pattern, handler) VALUES (?, ?, ?)",
        (agent, event_pattern, handler)
    )
    conn.commit()
    conn.close()


def get_subscriptions(active_only=True):
    """Get all subscriptions."""
    conn = _conn()
    sql = "SELECT * FROM subscriptions"
    if active_only:
        sql += " WHERE active = 1"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Agent State ──

def heartbeat(agent, run_summary=None, run_status=None):
    """Update agent heartbeat."""
    conn = _conn()
    now = datetime.now().isoformat()
    existing = conn.execute("SELECT agent FROM agent_state WHERE agent = ?", (agent,)).fetchone()
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
        params.append(agent)
        conn.execute(f"UPDATE agent_state SET {', '.join(updates)} WHERE agent = ?", params)
    else:
        conn.execute(
            "INSERT INTO agent_state (agent, last_heartbeat, last_run_status, last_run_summary) VALUES (?, ?, ?, ?)",
            (agent, now, run_status or "unknown", json.dumps(run_summary or {}))
        )
    conn.commit()
    conn.close()


def get_agent_states():
    """Get all agent states."""
    conn = _conn()
    rows = conn.execute("SELECT * FROM agent_state ORDER BY agent").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Deferred Events ──

def defer(event_type, target_agent, payload, execute_after, from_event_id=None):
    """Schedule an event for future delivery."""
    conn = _conn()
    conn.execute(
        """INSERT INTO deferred_events (event_type, target_agent, payload, execute_after, created_from_event_id)
           VALUES (?, ?, ?, ?, ?)""",
        (event_type, target_agent, json.dumps(payload), execute_after, from_event_id)
    )
    conn.commit()
    conn.close()


def fire_due_deferred():
    """Fire all deferred events that are past their execute_after time. Returns count fired."""
    conn = _conn()
    now = datetime.now().isoformat()
    due = conn.execute(
        "SELECT * FROM deferred_events WHERE fired = 0 AND execute_after <= ?",
        (now,)
    ).fetchall()

    fired = 0
    for d in due:
        d = dict(d)
        conn.execute(
            """INSERT INTO events (event_type, source_agent, target_agent, payload, priority)
               VALUES (?, 'CLAW', ?, ?, 3)""",
            (d["event_type"], d["target_agent"], d["payload"])
        )
        conn.execute("UPDATE deferred_events SET fired = 1 WHERE id = ?", (d["id"],))
        fired += 1

    if fired:
        conn.commit()
    conn.close()
    return fired


def get_pending_deferred():
    """Get all unfired deferred events."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM deferred_events WHERE fired = 0 ORDER BY execute_after ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Stats ──

def stats():
    """Overall event bus stats."""
    conn = _conn()
    s = {}
    s["total_events"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    s["unprocessed"] = conn.execute("SELECT COUNT(*) FROM events WHERE processed_at IS NULL").fetchone()[0]
    s["total_subscriptions"] = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE active = 1").fetchone()[0]
    s["agents_registered"] = conn.execute("SELECT COUNT(*) FROM agent_state").fetchone()[0]
    s["deferred_pending"] = conn.execute("SELECT COUNT(*) FROM deferred_events WHERE fired = 0").fetchone()[0]
    s["events_today"] = conn.execute(
        "SELECT COUNT(*) FROM events WHERE created_at > datetime('now', '-1 day')"
    ).fetchone()[0]
    conn.close()
    return s
