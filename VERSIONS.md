# VERSIONS.md — Aonxi Claw Evolution Roadmap

## The Path to AGI Orchestration

```
v1.0  Event Bus         — agents talk via events, human approves everything
v2.0  Coordination      — agents time their actions around each other
v3.0  Self-Learning     — agents share wins/losses in real-time
v4.0  Confidence Engine — agents auto-approve based on confidence scores
v5.0  Self-Optimization — Claw rewrites its own coordination rules
v6.0  Autonomous GTM    — Claw runs the entire go-to-market autonomously
v7.0  AGI Orchestrator  — Claw discovers new agent capabilities and deploys them
```

---

## v1.0 — Event Bus (current)

**Status: SHIPPED**

What it does:
- SQLite event bus with 4 tables (events, subscriptions, agent_state, deferred)
- 20 event types across 5 agent adapters
- Sidecar JSON pattern (adapters write context files into agent directories)
- CLI: status, events, tail, deferred, emit, trigger, subs
- Deferred events (PKM publish → AROS outreach delayed 2 days)
- Async daemon with poll/schedule/health loops

What it doesn't do:
- No auto-approval. Every action still goes through existing agent logic.
- No confidence scoring. Events are processed but don't make decisions.
- Sam still reviews AROS emails, ARIA pitches, Outreach sends.

**Numbers:**
- 20 subscriptions, 6 adapters, 7 commands
- 0 API calls. $0.00/day cost.
- 19 files, 1,443 lines

---

## v2.0 — Coordination (next)

**Status: PLANNED**

What changes:
- `orchestrator/rules.py` — declarative coordination rules that chain events
- Dynamic scheduling: "PKM must complete before AROS starts"
- Dependency graph: AROS depends on PKM, ARIA depends on AROS
- Warmup intelligence: track which verticals have warmup content ready vs not
- Backpressure: if AROS has 50 unsent emails, don't generate more PKM content for that vertical

New events:
- `claw.schedule_override` — dynamically delay/advance an agent's run
- `claw.backpressure` — throttle an upstream agent
- `claw.dependency_met` — a dependency is satisfied, downstream agent can run

New rules:
```python
# Example rule: If PKM published for vertical X today, defer AROS for X by 2 days
def rule_warmup_timing(event):
    if event.type == "pkm.content_published":
        defer("claw.warmup_outreach_ready", "AROS", delay_days=2, payload=event.data)

# Example rule: If AROS pipeline > 50 unsent for vertical X, tell PKM to skip X
def rule_backpressure(event):
    if event.type == "aros.email_sent":
        pipeline = count_unsent(event.data.vertical)
        if pipeline > 50:
            emit("claw.backpressure", target="PKM", data={"vertical": X, "reason": "pipeline_full"})
```

**Target:** AROS reply rate +5% from warmup timing alone.

---

## v3.0 — Self-Learning

**Status: PLANNED**

What changes:
- Real-time MemCollab: incremental distillation on every HOT outcome (not just 2am)
- Cross-agent pattern propagation: "PURE_DATA bypass worked for AROS → inject into ARIA"
- Content performance feedback loop: PKM tracks LinkedIn engagement → feeds back to AROS/ARIA targeting
- A/B testing across agents: "Did AROS do better on days PKM published vs days it didn't?"

New capabilities:
- `adapters/memcollab_adapter.py` triggers `distill_shared_memory()` on every outcome event
- Pattern strength tracking: how many times a bypass strategy worked across agents
- Weekly learning report: "This week, OVERLOAD_AVOIDANCE + under-60-words worked 87% across AROS and Outreach"

New events:
- `memcollab.pattern_confirmed` — a pattern hit confidence threshold (>80%, >10 trajectories)
- `memcollab.pattern_invalidated` — a pattern dropped below threshold
- `claw.ab_test_result` — cross-agent A/B test completed

**Target:** 30-second learning propagation (vs 22-hour nightly). MemCollab patterns reach all agents within 1 poll cycle.

---

## v4.0 — Confidence Engine

**Status: PLANNED — this is the AGI inflection point**

What changes:
- Every action in every agent gets a **confidence score (0-100)**
- Claw maintains a **confidence threshold per action type**
- Actions above threshold → auto-approved (no human review)
- Actions below threshold → queued for Sam's review
- Threshold adjusts automatically based on outcomes

### Confidence Score Components

```python
confidence = weighted_sum([
    defense_profiling_confidence,    # PKM Analyzer: how sure are we about the defense mode?
    content_quality_score,           # How well does the email/pitch score against rules?
    vertical_win_rate,               # Historical win rate for this vertical
    memcollab_pattern_strength,      # Cross-agent pattern confidence
    prospect_tier,                   # Tier A = higher baseline confidence
    signal_strength,                 # Harvester signal score
    bypass_strategy_history,         # Has this bypass worked before?
])
```

### Auto-Approval Matrix

| Action | Initial Threshold | How It Adjusts |
|--------|------------------|---------------|
| AROS send email | 85 | +1 for each reply, -3 for each bounce |
| ARIA send pitch | 90 | +2 for each meeting, -5 for each unsubscribe |
| Outreach send | 80 | Already has auto-send at 80+ (v5.0 of Outreach agent) |
| PKM publish content | 70 | +1 for each high-engagement post, -2 for low engagement |
| MemCollab distill | 75 | Auto if >10 trajectories and >80% pattern match |

### The Flywheel

```
Agent sends email (confidence: 82, auto-approved)
    → Reply comes in (HOT)
    → MemCollab distills pattern (strength: 87%)
    → Confidence for similar emails jumps to 89
    → Next similar email auto-approved at higher confidence
    → More sends → more data → more patterns → higher confidence
    → Sam reviews less and less
    → Eventually: Sam reviews 0 emails/day, system runs itself
```

### Sam's Override

Sam can always:
- Lower any threshold: "I want to review all ARIA pitches for a week"
- Raise any threshold: "Auto-send everything above 70 for SaaS"
- Veto any action: "Never auto-send to investors with >$1B AUM"
- Pause any agent: "Stop AROS for home_care vertical until I review"

New events:
- `claw.confidence_scored` — every action gets a confidence score
- `claw.auto_approved` — action was above threshold, sent automatically
- `claw.queued_for_review` — action below threshold, waiting for Sam
- `claw.threshold_adjusted` — threshold moved based on outcome data
- `claw.human_override` — Sam vetoed or approved something manually

**Target:** Sam's daily review time: 25 min → 5 min → 0 min. System runs itself.

---

## v5.0 — Self-Optimization

**Status: PLANNED**

What changes:
- Claw reads its own event history and discovers optimization opportunities
- Rules engine writes NEW rules based on observed patterns
- A/B tests coordination strategies: "Is 2-day warmup better than 3-day?"
- Dynamic ICP reweighting: Claw adjusts AROS scoring weights based on close rates
- Dynamic content calendar: Claw tells PKM which verticals to write about based on pipeline needs

### Self-Discovered Rules (examples)

```python
# Claw discovers: "AROS reply rate is 40% higher on Tuesdays"
# → Auto-generated rule:
def rule_tuesday_boost():
    if today.weekday() == 1:  # Tuesday
        emit("claw.schedule_override", target="AROS", data={"boost": True, "send_limit": 30})

# Claw discovers: "PKM content about home_care gets 3x engagement"
# → Auto-generated rule:
def rule_home_care_content_priority():
    emit("claw.agent_run_requested", target="PKM", data={"command": "warmup", "vertical": "home_care"})

# Claw discovers: "ARIA meetings convert 2x when AROS has recent deal in same vertical"
# → Auto-generated rule:
def rule_aria_after_aros_deal():
    if recent_aros_deal(vertical=V):
        emit("claw.schedule_override", target="ARIA", data={"priority_vertical": V})
```

### Meta-Learning

Claw tracks which rules produce positive outcomes and retires rules that don't work:

```
Rule: tuesday_boost
  Created: 2026-04-15 (auto-discovered)
  Triggered: 8 times
  Impact: +12% reply rate on Tuesdays vs control
  Status: ACTIVE (confidence: 91%)

Rule: 3_day_warmup (variant)
  Created: 2026-04-20 (A/B test)
  Triggered: 4 times
  Impact: -3% vs 2-day warmup
  Status: RETIRED (confidence: 78%, negative impact)
```

**Target:** Claw generates 10+ self-discovered rules per month. Zero human rule writing.

---

## v6.0 — Autonomous GTM

**Status: PLANNED**

What changes:
- Claw runs the entire go-to-market autonomously
- Budget allocation: Claw decides how many emails AROS sends per vertical based on ROI
- Channel selection: Claw decides email vs LinkedIn vs WhatsApp per prospect
- Pricing intelligence: Claw adjusts deal sizes based on vertical and company size
- Pipeline forecasting: Claw predicts monthly revenue 30/60/90 days out
- Capacity management: Claw throttles outreach when client onboarding is full

### The Autonomous Loop

```
Claw wakes up at 5am.

1. Checks pipeline: 45 deals in progress, $82K weighted pipeline
2. Checks capacity: 3 client onboarding slots available
3. Decides: "We need 8 more Tier A prospects in SaaS this week"
4. Tells PKM: "Publish SaaS warmup content today"
5. Tells AROS: "After 2-day warmup, send 8 SaaS emails (auto-approve >85 confidence)"
6. Tells ARIA: "We just closed 2 SaaS deals — update pitch deck numbers"
7. Monitors replies all day
8. Hot reply comes in → updates ARIA pitch → triggers MemCollab distillation
9. End of day: reports to Sam via email

Sam's involvement: read the report. That's it.
```

**Target:** $0 → $2M ARR managed by Claw autonomously. Sam builds product, Claw runs GTM.

---

## v7.0 — AGI Orchestrator

**Status: VISION**

What changes:
- Claw discovers NEW agent capabilities it needs and builds them
- "We're losing deals at the objection handling stage → I need an Objection Handler agent"
- Claw writes the agent spec, generates the code scaffold, runs it, measures results
- Self-replicating: Claw can deploy copies of itself for different markets/verticals
- Cross-market intelligence: Claw instances share learnings across customers

### The AGI Loop

```
1. Claw analyzes its own event history for bottlenecks
2. Identifies: "45% of AROS deals stall at pricing objection"
3. Generates hypothesis: "An Objection Handler agent could handle pricing objections in real-time"
4. Writes agent spec: inputs, outputs, success metrics
5. Scaffolds the agent (using AROS/ARIA as templates)
6. A/B tests: 50% of pricing objections go to new agent, 50% follow old flow
7. Measures: new agent converts 60% of pricing objections → threshold met
8. Promotes: Objection Handler becomes permanent agent, gets Claw subscription
9. Claw now has 8 agents instead of 7

Repeat forever. The system grows itself.
```

### Confidence-Based Autonomy Scale

```
v1.0  Confidence: N/A     — events flow, humans decide everything
v2.0  Confidence: N/A     — agents coordinate timing, humans decide content
v3.0  Confidence: tracked — agents learn in real-time, humans still approve
v4.0  Confidence: 80+     — auto-approve above threshold, humans review rest
v5.0  Confidence: 85+     — self-optimizing rules, humans review exceptions
v6.0  Confidence: 90+     — autonomous GTM, humans read reports
v7.0  Confidence: 95+     — self-building agents, humans set vision
```

**The endgame:** Claw is not a tool. It's an autonomous business operator. Sam sets the strategy. Claw executes everything — finding customers, closing deals, raising capital, creating content, learning from outcomes, building new capabilities — all on confidence scores that started at 0 and climbed to 95+ through millions of real interactions.

---

## Numbers That Matter

| Version | Sam's Daily Time | Agents | Auto-Approve | Revenue Impact |
|---------|-----------------|--------|-------------|----------------|
| v1.0 | 25 min | 7 (independent) | 0% | baseline |
| v2.0 | 20 min | 7 (coordinated) | 0% | +10% (warmup timing) |
| v3.0 | 15 min | 7 (learning) | 0% | +20% (real-time patterns) |
| v4.0 | 5 min | 7 (confidence) | 60% | +40% (speed of execution) |
| v5.0 | 2 min | 7 (self-optimizing) | 85% | +60% (discovered rules) |
| v6.0 | 0 min (reads report) | 7 (autonomous) | 95% | +100% (autonomous GTM) |
| v7.0 | 0 min (sets vision) | 7+ (self-building) | 99% | unbounded |

## Cost Trajectory

| Version | Claw Cost/Day | Agent API Cost/Day | Total | Revenue/Day |
|---------|--------------|-------------------|-------|-------------|
| v1.0 | $0.00 | $2.00 | $2.00 | ~$3,500 |
| v4.0 | $0.00 | $3.00 (more sends) | $3.00 | ~$7,000 |
| v6.0 | $0.00 | $5.00 (max throughput) | $5.00 | ~$15,000 |
| v7.0 | $0.50 (self-build) | $8.00 | $8.50 | unbounded |

The cost of intelligence goes to zero. The revenue it generates does not.
