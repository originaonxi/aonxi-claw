# ARCHITECTURE.md — Aonxi Claw

**Complete end-to-end technical specification. Any engineer can replicate this system from this document alone.**

---

## 1. System Overview

Aonxi Claw is a **persistent daemon** that connects 7 autonomous agents through a **SQLite event bus**. Agents emit events when things happen. Claw matches events to subscriptions, dispatches handlers, and writes context files that agents read on their next run.

```
                     ┌─────────────────────────────────────────────────────┐
                     │                  AONXI CLAW DAEMON                  │
                     │                                                     │
                     │   ┌─────────┐  ┌──────────┐  ┌──────────┐         │
                     │   │  POLL   │  │ SCHEDULE │  │  HEALTH  │         │
                     │   │  LOOP   │  │   LOOP   │  │   LOOP   │         │
                     │   │  (30s)  │  │  (60s)   │  │  (5min)  │         │
                     │   └────┬────┘  └────┬─────┘  └────┬─────┘         │
                     │        │            │              │               │
                     │   ┌────▼────────────▼──────────────▼───────────┐   │
                     │   │            EVENT BUS (SQLite)               │   │
                     │   │                                             │   │
                     │   │  events ──── 20 event types, JSON payloads │   │
                     │   │  subscriptions ── 20 glob-pattern subs     │   │
                     │   │  agent_state ──── heartbeats, run status   │   │
                     │   │  deferred_events ── delayed event queue    │   │
                     │   └────┬───┬───┬───┬───┬───┬────────────────┘   │
                     └────────┼───┼───┼───┼───┼───┼────────────────────┘
                              │   │   │   │   │   │
        ┌─────────────────────┘   │   │   │   │   └────────────────┐
        ▼                         ▼   ▼   ▼   ▼                   ▼
   ┌─────────┐  ┌─────────┐ ┌────────┐ ┌───┐ ┌──────────┐  ┌──────────┐
   │  AROS   │  │  ARIA   │ │OUTREACH│ │PKM│ │MEMCOLLAB │  │  ROUTER  │
   │ adapter │  │ adapter │ │adapter │ │ad.│ │ adapter  │  │ adapter  │
   │ 6 hdlrs │  │ 4 hdlrs │ │3 hdlrs │ │3h│ │ 1 hdlr  │  │ (future) │
   └────┬────┘  └────┬────┘ └───┬────┘ └─┬─┘ └────┬─────┘  └──────────┘
        │            │          │        │        │
        ▼            ▼          ▼        ▼        ▼
   ~/aros-agent  ~/aria   ~/outreach  ~/pkm  ~/memcollab
   reads:        reads:   reads:      reads:  called by:
   claw_social_  claw_    claw_case_  claw_   on_hot_outcome()
   proof.json    context  studies.    active  → distill_shared
   claw_warmup_  .json    json        _vert-    _memory()
   pending.json  claw_    claw_       icals.
   claw_icp_     content  social_     json
   boost.json    _refs.   proof.
   claw_winning  json     json
   _patterns.    claw_
   json          proof_
   claw_mem-     points.
   collab_       json
   updates.json
```

---

## 2. Event Bus — SQLite Schema

**Database:** `~/aonxi-claw/claw.db`
**Mode:** WAL (concurrent reads during writes), busy_timeout=5000ms

### 2.1 events

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,        -- 'aros.email_sent', 'aria.hot_reply', etc.
    source_agent TEXT NOT NULL,      -- 'AROS', 'ARIA', 'OUTREACH', 'PKM', 'CLAW', 'CLI'
    target_agent TEXT,               -- NULL = broadcast to all subscribers
    payload TEXT NOT NULL,           -- JSON blob
    priority INTEGER DEFAULT 5,     -- 1=critical .. 5=normal .. 9=low
    correlation_id TEXT,            -- links related events
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT,              -- NULL until consumed by subscription engine
    processed_by TEXT               -- 'CLAW:AROS,ARIA' (which handlers ran)
);
```

### 2.2 subscriptions

```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,             -- subscribing agent
    event_pattern TEXT NOT NULL,     -- glob: 'aros.*', 'pkm.content_published', '*'
    handler TEXT NOT NULL,           -- Python path: 'adapters.aros_adapter.on_content_published'
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 2.3 agent_state

```sql
CREATE TABLE agent_state (
    agent TEXT PRIMARY KEY,          -- 'AROS', 'ARIA', etc.
    last_heartbeat TEXT,             -- ISO datetime
    last_run_at TEXT,
    last_run_status TEXT,            -- 'success', 'failed', 'running'
    last_run_summary TEXT,           -- JSON: {"emails_sent": 5, "tier_a": 12}
    config TEXT                      -- JSON: agent-specific overrides
);
```

### 2.4 deferred_events

```sql
CREATE TABLE deferred_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    target_agent TEXT NOT NULL,
    payload TEXT NOT NULL,           -- JSON
    execute_after TEXT NOT NULL,     -- ISO datetime: when to fire
    created_from_event_id INTEGER,  -- which event created this deferral
    fired INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## 3. Event Processing Pipeline

```
1. Agent calls claw_client.emit("aros.deal_closed", data, source_agent="AROS")
       │
       ▼
2. INSERT INTO events (event_type, source_agent, payload)
       │
       ▼
3. poll_loop() runs every 30 seconds:
   SELECT * FROM events WHERE processed_at IS NULL ORDER BY priority, created_at
       │
       ▼
4. subscription_engine.process_event(event):
   a. match_subscriptions(event) → find all subs where fnmatch(event_type, pattern)
   b. Filter: skip if sub.agent == event.source_agent (no self-loops)
   c. Filter: if event.target_agent is set, only match that agent's subs
       │
       ▼
5. dispatch(event, matched_subscriptions):
   For each subscription:
     a. importlib.import_module("adapters.aria_adapter")
     b. getattr(module, "on_aros_deal_closed")
     c. handler({id, event_type, source_agent, data, created_at})
     d. Handler writes sidecar JSON and/or emits new events
       │
       ▼
6. ack(event_id, "CLAW:ARIA,PKM") — mark event as processed
```

---

## 4. Subscription Registry (20 subscriptions)

Registered by `claw.py → register_subscriptions()` on daemon startup:

### AROS listens to:

| Pattern | Handler | What It Does |
|---------|---------|-------------|
| `pkm.content_published` | `aros_adapter.on_content_published` | Defers outreach 2 days, writes warmup_pending.json |
| `aria.hot_reply` | `aros_adapter.on_aria_hot_reply` | Writes social_proof.json with investor interest |
| `aria.meeting_booked` | `aros_adapter.on_aria_meeting_booked` | Writes social_proof.json (stronger signal) |
| `outreach.vertical_signal` | `aros_adapter.on_outreach_vertical_signal` | Writes icp_boost.json if conversion >15% |
| `outreach.pattern_discovered` | `aros_adapter.on_outreach_pattern_discovered` | Writes winning_patterns.json |
| `memcollab.memory_distilled` | `aros_adapter.on_memcollab_memory_distilled` | Writes memcollab_updates.json |

### ARIA listens to:

| Pattern | Handler | What It Does |
|---------|---------|-------------|
| `aros.deal_closed` | `aria_adapter.on_aros_deal_closed` | Writes context.json with updated ARR |
| `pkm.content_published` | `aria_adapter.on_content_published` | Writes content_refs.json for thought leadership |
| `outreach.pattern_discovered` | `aria_adapter.on_outreach_pattern_discovered` | Writes proof_points.json if win_rate >20% |
| `memcollab.memory_distilled` | `aria_adapter.on_memcollab_memory_distilled` | Writes memcollab_updates.json |

### OUTREACH listens to:

| Pattern | Handler | What It Does |
|---------|---------|-------------|
| `aros.hot_reply` | `outreach_adapter.on_aros_hot_reply` | Writes case_studies.json |
| `aria.investor_committed` | `outreach_adapter.on_aria_investor_committed` | Writes social_proof.json |
| `memcollab.memory_distilled` | `outreach_adapter.on_memcollab_memory_distilled` | Writes memcollab_updates.json |

### PKM listens to:

| Pattern | Handler | What It Does |
|---------|---------|-------------|
| `aros.email_sent` | `pkm_adapter.on_aros_email_sent` | Writes active_verticals.json |
| `aros.deal_closed` | `pkm_adapter.on_aros_deal_closed` | Requests case study content generation |
| `aria.hot_reply` | `pkm_adapter.on_aria_hot_reply` | Writes investor_signals.json |

### MEMCOLLAB listens to:

| Pattern | Handler | What It Does |
|---------|---------|-------------|
| `aros.hot_reply` | `memcollab_adapter.on_hot_outcome` | Incremental distillation |
| `aria.hot_reply` | `memcollab_adapter.on_hot_outcome` | Incremental distillation |
| `aria.meeting_booked` | `memcollab_adapter.on_hot_outcome` | Incremental distillation |
| `aros.deal_closed` | `memcollab_adapter.on_hot_outcome` | Incremental distillation |

---

## 5. Sidecar JSON Pattern

Adapters write JSON files into agent data directories. Agents optionally read them at run start. If the file doesn't exist, agent runs normally (zero dependency on Claw).

### Write path (adapter → sidecar):

```python
# In adapters/base_adapter.py:
def write_context_file(agent_dir, filename, data):
    filepath = os.path.join(agent_dir, "data", filename)
    # Merge with existing file (preserves previous context)
    existing = json.load(open(filepath)) if os.path.exists(filepath) else {}
    existing.update(data)
    json.dump(existing, open(filepath, "w"))
```

### Read path (agent → sidecar):

```python
# In any agent (e.g., aros-agent/writer.py):
claw_proof = {}
proof_path = os.path.join(DATA_DIR, "claw_social_proof.json")
if os.path.exists(proof_path):
    claw_proof = json.load(open(proof_path))
    if claw_proof.get("investor_interest", {}).get("usable_line"):
        system_prompt += f"\nSOCIAL PROOF: {claw_proof['investor_interest']['usable_line']}"
```

### Complete Sidecar Map

| File | Written By | Read By | Contents |
|------|-----------|---------|----------|
| `~/aros-agent/data/claw_social_proof.json` | aria_adapter | AROS writer | `{investor_interest: {firm, sentiment, usable_line}}` |
| `~/aros-agent/data/claw_warmup_pending.json` | aros_adapter | AROS scheduler | `{vertical: {published_at, outreach_ready_at, hook}}` |
| `~/aros-agent/data/claw_icp_boost.json` | aros_adapter | AROS scorer | `{vertical: {boost: true, conversion_rate, sample_size}}` |
| `~/aros-agent/data/claw_winning_patterns.json` | aros_adapter | AROS writer | `{pattern: {win_rate, vertical, source}}` |
| `~/aros-agent/data/claw_memcollab_updates.json` | aros_adapter | AROS writer | `{mode_vertical: {strength, bypass_strategy}}` |
| `~/aria/data/claw_context.json` | aria_adapter | ARIA writer | `{latest_deal: {company, revenue, vertical}, pitch_update}` |
| `~/aria/data/claw_content_refs.json` | aria_adapter | ARIA writer | `{latest_content: {hook, content_type, vertical}}` |
| `~/aria/data/claw_proof_points.json` | aria_adapter | ARIA writer | `{latest_proof: {pattern, win_rate, description}}` |
| `~/aria/data/claw_memcollab_updates.json` | aria_adapter | ARIA writer | `{mode_vertical: {strength, bypass_strategy}}` |
| `~/aonxi-outreach-agent/data/claw_case_studies.json` | outreach_adapter | Outreach writer | `{latest: {company, vertical, usable}}` |
| `~/aonxi-outreach-agent/data/claw_social_proof.json` | outreach_adapter | Outreach writer | `{investment: {investor, amount}}` |
| `~/aonxi-outreach-agent/data/claw_memcollab_updates.json` | outreach_adapter | Outreach writer | `{mode_vertical: {strength, bypass_strategy}}` |
| `~/aonxi-pkm/data/claw_active_verticals.json` | pkm_adapter | PKM researcher | `{vertical: {last_outreach, source}}` |
| `~/aonxi-pkm/data/claw_investor_signals.json` | pkm_adapter | PKM atomizer | `{latest_signal: {investor, firm, sentiment}}` |

---

## 6. Client Library API

**File:** `~/aonxi-claw/claw_client.py`
**Import:** `from claw_client import emit, heartbeat, get_pending_events, ack`

### emit()

```python
emit(
    event_type: str,           # "aros.email_sent"
    data: dict,                # {"prospect": "...", "vertical": "saas"}
    source_agent: str = "UNKNOWN",
    target_agent: str = None,  # None = broadcast
    priority: int = 5,         # 1=critical, 5=normal, 9=low
    correlation_id: str = None
) -> int | None               # event ID or None if Claw DB doesn't exist
```

### heartbeat()

```python
heartbeat(
    agent_name: str,
    run_summary: dict = None,  # {"emails_sent": 5, "tier_a": 12}
    run_status: str = None     # "success", "failed", "running"
) -> None
```

### get_pending_events()

```python
get_pending_events(
    agent_name: str,
    limit: int = 20
) -> list[dict]               # [{id, event_type, source_agent, data, created_at}, ...]
```

### ack()

```python
ack(
    event_id: int,
    agent_name: str
) -> None
```

All functions handle missing DB gracefully (return None/empty list). Agents work without Claw installed.

---

## 7. Daemon Loops

### poll_loop (every 30 seconds)
1. `SELECT * FROM events WHERE processed_at IS NULL ORDER BY priority, created_at LIMIT 50`
2. For each: match subscriptions → dispatch handlers → ack

### schedule_loop (every 60 seconds)
1. `SELECT * FROM deferred_events WHERE fired = 0 AND execute_after <= now()`
2. For each: INSERT into events table → mark as fired

### health_loop (every 5 minutes)
1. `SELECT * FROM agent_state`
2. Flag agents with stale heartbeats (>26 hours)
3. Log warning (future: send alert email)

---

## 8. Deferred Events (Warmup Timing)

When PKM publishes content for a vertical:

```
t=0:   pkm.content_published {vertical: "saas", hook: "..."}
       │
       ▼
       aros_adapter.on_content_published():
         1. INSERT INTO deferred_events (
              event_type = "claw.warmup_outreach_ready",
              target_agent = "AROS",
              execute_after = now() + 2 days,
              payload = {vertical, hook, instruction}
            )
         2. Write ~/aros-agent/data/claw_warmup_pending.json
       │
       ▼
t=2d:  schedule_loop fires deferred event:
         INSERT INTO events ("claw.warmup_outreach_ready", "CLAW", "AROS", ...)
       │
       ▼
       AROS picks up event on next run:
         get_pending_events("AROS") → [{type: "claw.warmup_outreach_ready", ...}]
         AROS writer references: "You may have seen the recent discussion about {vertical}..."
```

---

## 9. Real-Time MemCollab (Incremental Distillation)

**Before Claw:** MemCollab distills at 2am. 22-hour delay.
**With Claw:** Distills on every HOT outcome. <30 second delay.

```
aros.hot_reply event
    │
    ▼
memcollab_adapter.on_hot_outcome():
    1. get_all_trajectories(limit=100)  ← existing MemCollab function
    2. Filter to matching (defense_mode, vertical) pair
    3. If ≥5 trajectories:
       a. distill_shared_memory(relevant)  ← existing function, pure math, 0 API cost
       b. If new memory > current strength:
          write_shared_memory([best])  ← existing function
          emit("memcollab.memory_distilled", {...})
    │
    ▼
All agents receive memcollab.memory_distilled:
    Write claw_memcollab_updates.json into each agent's data dir
    │
    ▼
Next agent run reads updated bypass patterns — learned in <30 seconds
```

---

## 10. Running Claw

### Development
```bash
cd ~/aonxi-claw
python3 claw.py          # Foreground, Ctrl+C to stop
```

### Production (macOS launchd)
```xml
<!-- ~/Library/LaunchAgents/com.aonxi.claw.plist -->
<dict>
    <key>Label</key><string>com.aonxi.claw</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/anmolsam/aonxi-claw/claw.py</string>
    </array>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/Users/anmolsam/logs/claw.log</string>
    <key>StandardErrorPath</key><string>/Users/anmolsam/logs/claw_error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>/usr/bin:/bin:/Users/anmolsam/Library/Python/3.9/bin</string>
    </dict>
</dict>
```

```bash
# Load (start daemon, auto-restart on crash)
launchctl load ~/Library/LaunchAgents/com.aonxi.claw.plist

# Unload (stop daemon)
launchctl unload ~/Library/LaunchAgents/com.aonxi.claw.plist

# Check status
launchctl list | grep claw
```

---

## 11. File-by-File Specification

| File | Lines | Purpose |
|------|-------|---------|
| `claw.py` | 130 | Main daemon: init DB, register subs, run 3 async loops |
| `claw_client.py` | 120 | Agent-importable: emit, heartbeat, get_pending_events, ack |
| `config.py` | 30 | Paths, intervals (30s/60s/5m), agent registry, constants |
| `schedule.yaml` | 25 | Declarative agent schedule with dependencies |
| `bus/event_store.py` | 260 | SQLite CRUD: emit, get_unprocessed, ack, heartbeat, defer, stats |
| `bus/subscription_engine.py` | 85 | Glob-pattern matching, handler dispatch via importlib |
| `bus/deferred.py` | 25 | Schedule + fire deferred events |
| `adapters/base_adapter.py` | 35 | write_context_file, read_context_file helpers |
| `adapters/aros_adapter.py` | 100 | 6 handlers: content_published, aria_hot, aria_meeting, vertical_signal, pattern, memcollab |
| `adapters/aria_adapter.py` | 65 | 4 handlers: aros_deal, content_published, pattern, memcollab |
| `adapters/outreach_adapter.py` | 45 | 3 handlers: aros_hot, aria_committed, memcollab |
| `adapters/pkm_adapter.py` | 50 | 3 handlers: aros_sent, aros_deal, aria_hot |
| `adapters/memcollab_adapter.py` | 70 | 1 handler: on_hot_outcome → incremental distillation |
| `cli/claw_cli.py` | 170 | 7 commands: status, events, tail, deferred, emit, trigger, subs |
| **Total** | **1,443** | **19 files** |

---

## 12. Cost

| Component | API Calls | Cost/Day |
|-----------|----------|----------|
| Claw daemon | 0 | $0.00 |
| Event bus (SQLite) | 0 | $0.00 |
| Subscription engine | 0 | $0.00 |
| Incremental MemCollab | 0 (pure math) | $0.00 |
| Sidecar file I/O | 0 | $0.00 |
| **Total Claw cost** | **0** | **$0.00** |

Claw adds zero cost. The only cost increase is if coordination triggers extra agent runs, which use the same APIs they already use.

---

## 13. Replication Guide

```bash
# 1. Clone
git clone https://github.com/originaonxi/aonxi-claw.git ~/aonxi-claw

# 2. No dependencies needed (stdlib only: sqlite3, asyncio, json, fnmatch, importlib)

# 3. Init the database
cd ~/aonxi-claw && python3 -c "from bus.event_store import init; init()"

# 4. Start daemon
python3 claw.py

# 5. Test: emit an event
python3 cli/claw_cli.py emit test.ping '{"msg": "hello"}'

# 6. Check it worked
python3 cli/claw_cli.py events

# 7. Connect an agent (add ~10 lines to any Python agent):
#    sys.path.insert(0, os.path.expanduser("~/aonxi-claw"))
#    from claw_client import emit, heartbeat
#    heartbeat("MY_AGENT")
#    emit("my_agent.event_name", {"data": "here"}, source_agent="MY_AGENT")
```
