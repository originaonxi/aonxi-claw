# Aonxi Claw — The Living Agent Orchestrator

**Where all Aonxi agents live, talk, and self-optimize to maximize revenue.**

```
Today:    7 agents running on cron. Independent. Deaf to each other.
With Claw: 7 agents alive 24/7. Talking. Coordinating. Learning in real-time.

Result:   AROS closes more deals. ARIA raises more capital.
          Every agent makes every other agent smarter — instantly, not at 2am.
```

## What Claw Does

Claw is a persistent daemon + event bus that sits **alongside** all Aonxi agents. It doesn't replace them — it makes them **aware of each other**.

| Before Claw | After Claw |
|------------|-----------|
| PKM publishes content at 6am. AROS emails at 7am. Prospect never saw the content. | PKM publishes → Claw delays AROS by 2 days → Prospect sees content → AROS references it in email. **Warm outreach.** |
| AROS closes a deal. ARIA's pitch still says "$650K ARR." | AROS closes → Claw writes updated context → ARIA's next pitch says "$668K ARR." **Live numbers.** |
| ARIA gets Sequoia interested. AROS has no idea. | ARIA hot reply → Claw writes social proof → AROS can reference "active top-tier investor conversations." |
| MemCollab learns at 2am. 22-hour delay. | HOT reply → Claw triggers incremental distillation → All agents have the new bypass pattern in <30 seconds. |
| Outreach discovers SaaS converts 3x. AROS keeps scoring SaaS normally. | Outreach signal → Claw boosts AROS ICP weights for SaaS → More SaaS prospects scored Tier A. |

## Architecture

```
                     ┌─────────────────────────────────────┐
                     │        AONXI CLAW DAEMON            │
                     │       ~/aonxi-claw/claw.py          │
                     │                                     │
                     │  poll_loop (30s) — process events   │
                     │  schedule_loop (60s) — fire deferred│
                     │  health_loop (5m) — heartbeats      │
                     │                                     │
                     │  ┌───────────────────────────────┐  │
                     │  │   EVENT BUS (SQLite claw.db)  │  │
                     │  │   events | subscriptions |    │  │
                     │  │   agent_state | deferred      │  │
                     │  └──┬────┬────┬────┬────┬────┬──┘  │
                     └─────┼────┼────┼────┼────┼────┼──────┘
                           │    │    │    │    │    │
           ┌───────────────┘    │    │    │    │    └──────────┐
           ▼                    ▼    ▼    ▼    ▼              ▼
      ┌─────────┐    ┌──────┐ ┌────────┐ ┌───┐ ┌──────────┐ ┌──────┐
      │  AROS   │    │ ARIA │ │OUTREACH│ │PKM│ │MEMCOLLAB │ │ROUTER│
      │ adapter │    │adapt.│ │adapter │ │ad.│ │ adapter  │ │adapt.│
      └────┬────┘    └──┬───┘ └───┬────┘ └─┬─┘ └────┬─────┘ └──┬───┘
           │            │         │        │        │           │
      ~/aros-agent  ~/aria   ~/outreach  ~/pkm  ~/memcollab  ~/router
      (unchanged)   (unchanged) (unchanged) (unchanged)      (unchanged)
```

**Key principle:** Claw sits ALONGSIDE, never INSIDE. Every agent still works standalone via cron if Claw is off.

## Quick Start

```bash
# 1. Start the daemon
python3 claw.py

# 2. Check status
python3 cli/claw_cli.py status

# 3. Emit a test event
python3 cli/claw_cli.py emit test.ping '{"msg": "hello"}'

# 4. Watch events live
python3 cli/claw_cli.py tail

# 5. Trigger an agent
python3 cli/claw_cli.py trigger AROS
```

## CLI Commands

```bash
claw status          # Agent heartbeats + bus stats
claw events [N]      # Last N events (default 20)
claw tail            # Live-tail events (Ctrl+C to stop)
claw deferred        # Pending deferred events
claw emit TYPE JSON  # Manually emit an event
claw trigger AGENT   # Request an agent run
claw subs            # Show active subscriptions
```

## 20 Core Events

| Event | Source | Who Reacts | What Happens |
|-------|--------|-----------|-------------|
| `aros.email_sent` | AROS | PKM, MemCollab | Track vertical, log trajectory |
| `aros.hot_reply` | AROS | ARIA, PKM, Outreach | Strengthen pitch, create case study |
| `aros.deal_closed` | AROS | ARIA, PKM | Update ARR in pitches, atomize story |
| `aros.icp_shift` | AROS | Outreach, PKM | Adjust targeting |
| `aria.hot_reply` | ARIA | AROS, PKM | Add social proof, create content |
| `aria.meeting_booked` | ARIA | AROS, PKM | Stronger social proof |
| `aria.investor_committed` | ARIA | AROS, PKM, Outreach | Major proof point |
| `outreach.pattern_discovered` | Outreach | AROS, ARIA | Share winning patterns instantly |
| `outreach.vertical_signal` | Outreach | AROS | Boost ICP weights for hot verticals |
| `pkm.content_published` | PKM | AROS, ARIA | Delay outreach 2 days for warmup |
| `pkm.warmup_ready` | PKM | AROS | Content warm, start outreach now |
| `memcollab.memory_distilled` | MemCollab | ALL | Real-time bypass pattern update |
| `claw.agent_run_requested` | Claw | target | Dynamic scheduling override |
| `claw.warmup_outreach_ready` | Claw | AROS | Deferred: warmup period complete |

## Agent Integration

Any agent adds ~10 lines to connect to Claw:

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/aonxi-claw"))
try:
    from claw_client import emit, heartbeat, get_pending_events, ack
    CLAW_AVAILABLE = True
except ImportError:
    CLAW_AVAILABLE = False

# At run start:
if CLAW_AVAILABLE:
    heartbeat("AROS")
    for event in get_pending_events("AROS"):
        handle(event)
        ack(event["id"], "AROS")

# After actions:
if CLAW_AVAILABLE:
    emit("aros.email_sent", {"prospect": "...", "vertical": "saas"}, source_agent="AROS")
```

Same try/except pattern already used in all agents for MemCollab and PKM bridge.

## Sidecar Pattern

Adapters write JSON context files into agent data directories. Agents check for them at run start:

| File | Agent | What It Contains |
|------|-------|-----------------|
| `claw_social_proof.json` | AROS | Investor interest from ARIA ("Sequoia is very interested") |
| `claw_warmup_pending.json` | AROS | Published content per vertical + outreach timing |
| `claw_icp_boost.json` | AROS | Hot verticals from Outreach to boost in scoring |
| `claw_winning_patterns.json` | AROS | Patterns from Outreach agent's self-learning |
| `claw_context.json` | ARIA | Latest AROS deal (updated ARR for pitches) |
| `claw_content_refs.json` | ARIA | Published PKM content for thought leadership refs |
| `claw_proof_points.json` | ARIA | Winning patterns as investor proof points |
| `claw_case_studies.json` | Outreach | AROS hot replies as case studies for selling Aonxi |

## Cost

**$0.00/day.** Pure Python + SQLite. No API calls. No cloud services. The only cost increase is if coordination triggers extra agent runs (same APIs they already use).

## File Structure

```
aonxi-claw/
├── claw.py                    # Main daemon (asyncio, 3 loops)
├── claw_client.py             # Agent-importable client
├── config.py                  # Paths, intervals, agent registry
├── schedule.yaml              # Agent run schedule
├── bus/
│   ├── event_store.py         # SQLite event CRUD (4 tables)
│   ├── subscription_engine.py # Glob-pattern event matching + dispatch
│   └── deferred.py            # Delayed event scheduling
├── adapters/
│   ├── base_adapter.py        # Sidecar file read/write helpers
│   ├── aros_adapter.py        # 6 handlers for AROS
│   ├── aria_adapter.py        # 4 handlers for ARIA
│   ├── outreach_adapter.py    # 3 handlers for Outreach
│   ├── pkm_adapter.py         # 3 handlers for PKM
│   └── memcollab_adapter.py   # Real-time incremental distillation
├── orchestrator/
│   └── (health_loop, schedule_loop, rules — future)
└── cli/
    └── claw_cli.py            # 7 CLI commands
```

## Part of the Aonxi Agent Network

| Agent | Repo | Purpose |
|-------|------|---------|
| [AROS](https://github.com/originaonxi/aros-agent) | Revenue | Autonomous revenue: prospect → score → write → send → close |
| ARIA | Capital | Autonomous investor outreach: find → verify → score → pitch → send |
| Outreach | Clients | Sells Aonxi: 24.1% reply rate, self-learning, v6.0 AGI |
| [PKM](https://github.com/originaonxi/aonxi-pkm) | Content | Knowledge capture + content flywheel, defense-targeted |
| MemCollab | Memory | Cross-agent shared memory, contrastive distillation |
| Router | Routing | Multi-model task routing (Claude/Gemini/Grok/Kimi), 75% cost reduction |
| Safeguard | Safety | Pre/post execution gates, drift detection |
| **[Claw](https://github.com/originaonxi/aonxi-claw)** | **Orchestration** | **This repo. Makes them all alive.** |
