# orient — conceptual notes

Companion to `orient-spec-seed.md`. Not behavioral spec — these are the "why and
where" behind the design decisions, and open questions worth tracking.

---

## What this pipeline is actually for

The agent-skills system at work solves a specific problem: multiple parallel Odoo
ticket streams × LLM cold-start cost = significant daily overhead. The pipeline is
a token efficiency + context continuity system. Its three jobs:

1. **Context continuity** — rollforward invariant ensures nothing is lost between
   sessions. Latest note is always canonical; never read history.
2. **Token efficiency** — expensive operations (status reads, PR fetches, review
   passes) are routed outside working sessions via pre-built artifacts.
3. **Cold-start cost** — any ticket can be picked up cheaply via a purpose-built
   CLAUDE.md artifact.

orient extends this to personal projects, with different constraints (no running
instances, no ticket IDs, no PR review routing) but the same structural goals.

The secondary motivation: this is also an agentic architecture exploration. The
pipeline is both a workflow tool and a test bed for figuring out what the right
patterns are — partly for personal productivity, partly as a demonstration of
mature LLM-driven development practice.

**Context-switching as opportunity, not just cost.** The pipeline isn't primarily
about minimizing the cost of bad context management — it's about discovering what
you can do *with* good context management. Parallel streams become an asset
(breadth, cross-project connections) if the infrastructure supports them.

---

## Claw Code and the swarm model

Claw Code (open-source Rust+Python rewrite of Claude Code) uses sub-agent "swarms":
parallel subtasks in isolated contexts with shared memory (artifacts). Autonomous
by default; ULTRAPLAN mode adds browser-based human approval for extended planning.

The swarm model's property cluster is high-value:
- Minimal context per agent
- Clean artifact-based handoffs
- No context bleed between agents
- Budget consciousness

**This property cluster is already latent in the agent-skills pipeline.** The
pipeline is sequential rather than parallel, but the shape is the same: each skill
runs in minimal context with a clean artifact handoff. blind-reviewer has zero prior
session context by design. The preflight routing token is a handoff protocol.
Status-cache prevents context bleed from owm into working sessions.

What Claw Code adds over the current model: parallelism and autonomous chaining.

---

## Disagreement: the Discord single-ping model

Claw Code's autonomous model tends toward "give the swarm a goal, let it run."
This skips the invariant-specification stages entirely — parallel autonomous agents
working toward an underspecified goal. Fine for "add a button"; falls apart for
anything with subtle behavioral contracts.

The case-interviewer → harness-writer → architecture-proposer chain is the gate
that single-ping loses. Specifically **harness-writer**: a swarm can't be
meaningfully evaluated without a test suite to run against. The test suite *is*
the shared invariant that makes parallel implementation safe. Without it, you get
fast convergence toward something, with no guarantee of what.

The single-ping model is also strongly decoupled in a directional sense — you
don't specify behavioral direction, only a goal. case-interviewer at minimum makes
you articulate the imagined behavioral spec; harness-writer encodes it as
executable invariants.

---

## How the models compose

These aren't competing approaches — they layer cleanly:

- **Pipeline stages** (case-interviewer → harness-writer → architecture-proposer)
  are the human-in-the-loop behavioral specification mechanism. Necessarily
  sequential: each stage depends on the previous.

- **Swarm model** is the execution model *within* implementation-writer. Once
  architecture-proposer has produced the dependency DAG, the bottom layer of
  independent modules is exactly where parallel swarms belong.
  implementation-writer already gestures at this ("implement modules bottom-up
  in DAG order") — parallel swarms collapse the sequential queue into a fan-out
  where the DAG allows it.

The gate is harness-writer. You can't safely parallelize implementation until
you have a test suite. Once you do, independent modules in the DAG are safe to
spawn in parallel with minimal per-agent context (module spec + interfaces only).

---

## Implications for orient

orient's brief + closer are sequential single-agent invocations at MVP. That's
appropriate — the note corpus is small, the tasks are lightweight.

Natural later evolution:
- **EOD fan-out**: run session-closer across all active topics simultaneously
  rather than per-topic sequential invocations.
- **Brief synthesis from parallel reads**: hub-starter equivalent reads N topic
  notes in parallel, synthesizes once. Cheap parallelism with no dependency
  ordering needed.

Neither of these is MVP scope. Flag for when the note corpus is rich enough that
sequential invocation becomes the bottleneck.

---

## Hierarchical parallel execution model

### Structure

The case-interviewer → harness-writer → architecture-proposer pipeline produces
a dependency DAG with typed interface contracts per edge. That DAG is the input
to a hierarchical parallel execution model:

```
top orchestrator
  → spawns N-1 directors (one per independent DAG branch)
      → each director batches work and dispatches implementors
          → implementors implement, test, report back
      → director synthesizes: inconsistencies, interface ambiguities, clarifications
      → 2-3 pass loop, then reports up
  → top orchestrator integrates reports, merges worktrees, adjudicates ambiguities
```

Git worktrees provide isolation during parallel work. The N+1 layer does merges,
runs integration tests, and writes a spec snapshot at each merge point — a
verified-as-built record, not a design doc.

### Meaningful chunks, not full fan-out

A director with 20 things to implement does not dispatch all 20 at once. It spots
clusters (related tasks, likely interface overlap) and dispatches 4 at a time. The
first batch is a probe — you learn things that improve subsequent batches. Batch
size is a tuning parameter: too small = sequential, too large = coordination
overhead and runaway cost.

Per batch, agents run a loop appropriate to the task:
`read → implement → review → tune → test` (or `read → test → implement → tune`
for TDD). The ordering is task-specific, not fixed.

### Alarm signals and alarm taxonomy

Agents have an explicit escalation path rather than running until done or failing
silently. But alarms are not a flat list — they split into two structurally
different categories:

**Escalating alarms** (require human or higher-tier judgment — cannot be
mechanically resolved):
- Interface ambiguity discovered mid-implementation
- Scope materially larger than estimated (and affects interface contracts)
- Unexpected dependency that changes the DAG
- Test failure after N retry attempts with no clear path forward
- Conflicting requirements between modules that architecture-proposer didn't catch

**Self-managing alarms** (mechanical resolution — no human needed):
- Context window approaching limit → compact + respawn with synthesis note
- Token budget threshold reached for this agent → checkpoint, surface cost summary
  to director, continue in fresh context
- Batch cost exceeding estimate → director adjusts next batch size, does not escalate
  unless cumulative project cost threshold crossed

The distinction matters for the alarm routing model: flat escalation buries the
human in noise. The director's job is to absorb self-managing alarms autonomously
and only surface escalating alarms upward. The human's decision surface should
contain only items that genuinely require judgment.

**Cost and context consumption are first-class, not implicit.** The $990/7-week
figure at work is concrete evidence that cost discipline bolted on after the fact
is the common failure mode. Specific thresholds (tokens-before-alarm, batch cost
budgets) surface organically on a medium-to-large project — but the structural
point (alarm taxonomy, which tier pays which cost, self-managing vs escalating)
needs to be designed in from the start, not added later.

Cost alarm ownership by tier:
- Leaf/implementor: no cost concern — atomic tasks are cheap
- Director: primary cost management tier — batch sizing, context compaction,
  per-batch cost tracking
- Orchestrator: project-level cost budget; escalates to human only if cumulative
  cost crosses a project threshold (not per-agent noise)

### Agent work-sizing and context clear + respawn

The respawn problem is the session-checkpoint pattern applied recursively at every
tier. Each tier's "state" is different, but the mechanic is the same: compact to
synthesis, checkpoint, respawn with minimal context.

| Tier | Work unit | Turns | Context concern | Respawn needs |
|---|---|---|---|---|
| Leaf | "write this one test" | 2-3 | Trivial — task fits in input | N/A — atomic |
| Implementor | "implement this module against these tests" | 10-20 | Grows with test failure history | File state + tried approaches + remaining tests |
| Director | "implement this section, monitor, synthesize" | Many + sub-reports | Heavy — sub-agent reports accumulate | Batch completion state + synthesis-so-far + open alarms |
| Orchestrator | DAG integration, merge coordination | Many | Heaviest | DAG merge state + director summaries + decision surface |

The "5 turns, then checkpoint" model is interesting for directors: agent runs for N
turns, at each turn checks alarm conditions, at turn N (or on alarm) synthesizes
what was done + what remains + issues found → reports to director. A micro-session
with its own checkpoint. The director respawns the agent with the synthesis as
context if more work remains.

The leaf and implementor tiers are cheap and almost stateless — getting them right
is mostly a context-scoping problem (give them only what they need). The director
and orchestrator tiers are where context management is load-bearing, and where the
session-checkpoint pattern becomes essential infrastructure rather than nice-to-have.

### Pipeline tuning toward parallelizability

The current skills aren't oriented toward parallel execution — they produce good
artifacts but don't explicitly plan for fan-out. Tuning:

- **case-interviewer**: elicit subsystem boundaries early. "What are the
  independently testable pieces?" as a standard question.
- **harness-writer**: write tests per module boundary, not just top-level
  integration. If a module can't be tested in isolation, the DAG boundary is wrong.
- **architecture-proposer**: add an explicit parallelization plan section —
  which branches are independent, merge order, typed interface contracts per edge.
  Makes orchestrator dispatch mechanical rather than judgment-driven.
- **implementation-writer**: already a good director — scoped to one DAG node,
  knows its interfaces, runs its test suite. Add: explicit alarm output format and
  batch dispatch capability.

### The human re-engagement point

The model assumes the human steps back after architecture-proposer. The pipeline's
value is that you *don't* fully step back — your behavioral invariants are encoded
in the harness. You re-engage at synthesis reports: "here are the N ambiguities
requiring judgment, here are proposed resolutions, approve or redirect." Not a
status dump — a decision surface. The quality of that decision surface is what
determines whether the human stays usefully in the loop or gets buried in noise.

### Re-owm as the worked example

```
config/schema (no deps)
    ↓
state/data layer
    ↓
core: workspace + instance + repo management
    ↓
CLI ──┬── MCP server ──┬── Dashboard   (independent, parallel)
      └────────────────┴──────────────→ integration
```

First natural fan-out: CLI, MCP, Dashboard all depend only on core interfaces,
not on each other. A director for the CLI layer with ~15 commands would batch:

- Batch 1: core instance commands (start/stop/status) — establishes the command
  pattern that subsequent batches follow
- Batch 2: workspace commands — build on batch 1 interfaces
- Batch 3: sync/diff/compare — depend on 1+2
- Batch 4: utility commands (help, version, config validate) — mostly independent

---

## External cost monitoring (not agent design)

A simple external monitor — cron job polling the Anthropic usage API, email/ping
at $10 increments and daily aggregate-to-date summary — would have caught the
$990/7-week situation early. This is not part of the agent execution model; it's
dumb infrastructure that sits outside the system. Key point: cost visibility needs
to exist *outside* the system being monitored. An agent burning tokens is not
well-positioned to notice it's burning tokens.

Dashboard/metrics design proper is deferred — no project shape yet, and the
relevant metrics are inferable from the shape once it exists.

## Open questions

- **Token budget discipline**: the $990/7-week figure at work is a concrete data
  point. orient should track cost per invocation from the start — not to optimize
  prematurely, but to have the data when it matters. Haiku for mechanical tasks
  (closer, brief) is already the right call; question is whether any orient skill
  ever warrants Sonnet.

- **Where does the swarm gate sit in the pipeline?** harness-writer is the current
  answer (test suite = shared invariant). Is there a lighter-weight gate for
  smaller tasks that don't warrant a full harness? Or is "if it doesn't warrant a
  harness, it doesn't warrant a swarm" the right rule?

- **File naming convention**: `UPPERCASE.md` for human-maintained control-plane
  files; `lowercase-hyphen.md` for generated/skill-maintained artifacts. Contested:
  could argue caps only for true inboxes (`INCOMING.md`) and lowercase everything
  else. Orient is the right place to establish this cleanly.
