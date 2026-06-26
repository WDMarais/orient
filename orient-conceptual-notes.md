# orient — conceptual notes

Companion to `orient-spec-seed.md`. Not behavioral spec — these are the "why and
where" behind the design decisions, and open questions worth tracking.

See also `orient-conceptual-notes-stigmergy.md` — the named coordination model behind
the notes tree (traces as memory + guide, multi-channel pheromone + decay, priority ×
actionability, "don't duplicate the environment's pheromone").

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

## Weekly synthesis pass

Session notes accumulate per-session, but a week's worth of session notes is 600+
lines of discourse. The natural next level of the temporal hierarchy:

```
session-closer → session note (per session)
day-closer     → daily hub marker (per day, reads session notes)
week-closer    → weekly pointer index (per week, reads session notes)
```

The weekly pass reads the week's session notes and produces a durable **pointer
index** — not a summary, but card-catalog entries with enough signal to know
whether to follow the pointer:

```
- had a back-and-forth on X; decided A for <reason>; details in [abc.md]
- read up on Y; immediately relevant to [ticket]; durable content in [note.md]
```

The pointer entry format matters: "decided A for reason X" tells you immediately
whether this thread is relevant to what you're looking for now. A summary tries to
convey everything at reduced fidelity; a pointer entry is optimized for triage.

**Session notes become navigational layer.** After the weekly pass, session notes
are provenance — still there if you need full depth, but no longer the primary
lookup target. The weekly index is what you hand an agent for "find anything on X
from early May": bounded file count, structured pointer format, cheap scan.

**Constraint propagates to session-closer.** The weekly pass can only produce
useful pointers if session notes name specific files in Shipped bullets. "worked
on pr-ism" is a dead pointer; "wrote `working-notes/pr-ism-rewrite-plan.md`" is
a live one. session-closer should treat Shipped bullets as index entries for a
downstream weekly pass — file paths required, not optional.

**Hub/day/week hierarchy.** If week-closer/week-starter are added alongside the
existing hub-closer/hub-starter, "hub" as a name becomes ambiguous (hub of what
— a day? a week?). The natural temporal rename: hub-starter → day-starter,
hub-closer → day-closer. "Hub" is a metaphor; the files are YYYY-MM-DD.md — it
IS a day-level artifact. The temporal hierarchy is cleaner as day/week/session
than hub/week/session.

**Why week is the right ceiling.** Month and quarter serve a different job —
retrospective and planning, not lookup. They're better written with intent as
philosophy-layer notes (see below) than generated mechanically from weekly indexes.
A monthly index would be a pointer-to-a-pointer with no added resolution; an agent
scanning 4 weekly files answers "find anything on X from last month" in 30 seconds
without one.

---

## Two layers: lookup vs. judgment

The note hierarchy has two structurally different layers with different consumers
and different write disciplines:

**Lookup layer (session → day → week):** mechanical, pointer-based, generated
from the notes below them. Consumer: an agent (or you) doing "where did we discuss
X." The week index is the right ceiling — beyond that you're adding pointer-to-pointer
indirection with no added resolution, and humans don't naturally think in month/quarter
units for code lookup.

**Philosophy layer (working notes, DESIGN.md-style):** written with intent, not
generated. Evergreen until something fundamentally changes. Consumer: an agent (or
you) opening a fresh session on a project after weeks away — needs enough context
to reason in the right spirit, not just find a file.

The philosophy layer's format is what makes it work. Broad strokes + rationale +
one concrete grounding example:

> "We use unique domains per instance because Odoo places session cookies at the
> domain level — if two instances share a domain, logging into one logs you out of
> the other."

That's more useful than a paragraph on the architecture, because it gives you enough
context to generalise to novel cases without having read the full spec. The concrete
example does most of the load: it tells you the *shape* of the problem, so when you
hit something adjacent you can reason from it rather than re-deriving from scratch.

**When to write each.** You don't write a philosophy note because you finished a
sprint — you write it when you've made a design decision whose rationale won't be
obvious from the code and will matter the next time someone (or an agent) touches
that area. This is the "resolved turns as dead weight" corollary applied to
documentation: the deliberation is noise; the rationale + one grounding example is
what's worth keeping.

**Analogy to spec+harness vs DESIGN.md in owm.** spec + harness = the lookup/
verifiable layer (specific, indexable, checkable). DESIGN.md = the philosophy layer
(broad strokes, rationale, concrete example). The lookup layer tells you what the
system does; the philosophy layer tells you why it works the way it does — enough
to make good decisions in the same spirit without reading all the specs.

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

## Context-switching as generative, not just costly

### The cognitive model

Humans are good at integrating many weak signals into a judgment under partial
information. Bad at sustained serial context — holding multiple detailed threads
simultaneously. Multi-stream work at the right challenge level is deliberate
practice for exactly the right skill.

The calibration matters:
- **Too rote**: no real engagement, no training signal
- **Too complex**: can't follow multiple threads, needs further decomposition
- **Sweet spot**: executive-level judgment calls — non-obvious, require pattern
  recognition, but holdable in parallel

orient's natural activity model (3-5 concurrent streams at different pipeline
phases — case-interviewer on one, implementation-writer on another) is accidentally
well-calibrated for this. Each phase requires different cognitive engagement; the
switching between them may reinforce both rather than degrading either.

### Cross-project synthesis

The brief shouldn't just surface "what to work on and what's pending" — it could
optionally surface *what class of judgment calls is likely today* given active
projects and current phases. "re-owm/dashboard is at architecture-proposer —
expect interface contract decisions. cq is at harness-writer — expect edge case
elicitation." That's a richer briefing artifact than a status dump.

### The SRS feed-forward pipeline (promising, hard)

```
multi-stream work → judgment calls surfaced in real context
    → judgment call extractor (skill) processes session notes
    → extracts: decision, options considered, what made it non-obvious, resolution
    → problem-instantiation-tool parameterizes into a reusable template
    → srs-tool schedules spaced repetition
    → flashcard: "given context X, options A/B/C — what do you do and why?"
```

**The decomposition problem**: session notes capture *what happened* (Shipped,
Pending, Deferred) not *why the judgment went the way it did*. The `## Time sink`
section is the closest — implicitly "I misjudged this." A dedicated `## Calls`
section in the note format — non-obvious decisions worth revisiting, with brief
rationale — would make extraction tractable without requiring a skill to infer
judgment calls from outcomes.

**The generalization problem**: practice problems anchored to specific instances
aren't useful. "Should I use a worktree here?" is too narrow. "Given these
constraints on parallel work and isolation requirements, what's the right branching
strategy?" is a flashcard. problem-instantiation-tool's parameterization is the
right mechanism: the template abstracts the specifics, instantiation fills them
back in at practice time with variation.

**Connection to existing tools**: srs-tool and problem-instantiation-tool already
exist and handle the scheduling and parameterization layers. The missing pieces are
(a) the `## Calls` capture in session notes and (b) a judgment-call extractor skill
that reads notes and produces templates for problem-instantiation-tool. The pipeline
is completable; the "but how though" is mostly in the extractor + template design.

### Post-session hook for decision capture

A PostSession hook in the agent harness could capture decision-pattern signal
without requiring explicit `## Calls` entries. Two input streams:

- **Structured** (`## Calls` in session notes) — high quality, requires discipline
- **Inferred** (session shape: clarification rounds, redirect rate, back-and-forth
  length per decision, response thoroughness) — free, lower fidelity, no discipline
  required

Hook writes structured signal to a log. A terminal-usage-patterns-style consumer
reads the corpus over time and surfaces: what decision types recur, where judgment
gets spent, what triggers redirects, whether decision quality correlates with
session phase or project type.

The two layers are independent: hook + log is infrastructure, analysis consumer is
a separate tool. Same pattern as owm-status-cache — hook writes, consumers read,
no tight coupling. The consumer doesn't need to exist when the hook is built.

This is to-be-specced when the agent harness shape is clearer. Flag for then.

### Long-term upskilling sidecar

orient produces decision artifacts as a natural side-effect of the pipeline:
`## Calls` in session notes, design invariants in specs, key decisions in
ARCHITECTURE.md outputs. Over time these accumulate a corpus of design reasoning
and operator judgment that's currently lost after the session ends.

A general mechanism — not coupled to any specific SRS tool — to surface that
corpus back as upskilling signal is worth building toward. Taking SRS principles
into account: spaced repetition, varied instantiation, retrieval over re-reading.
Concretely: "here's a design decision from re-owm/dashboard three weeks ago —
what would you do differently now, and why?"

The connection is one-directional: orient produces, the sidecar consumes. orient
doesn't need to know the sidecar exists. The data structures that enable it should
be kept in mind as orient matures — specifically, keeping `## Calls` and a future
`## Decisions` section in architecture outputs in a consistent extractable format.

Wire when both ends are stable enough to have a real contract. Don't couple to
srs-tool specifically — the right consumer may be a separate tool or a different
mechanism entirely.

### Implication for orient's session note format

The existing CONVENTION.md format (Goal / Shipped / Pending / Deferred / Time sink)
doesn't capture judgment calls. Proposed addition:

```
## Calls
- Chose X over Y because Z — worth revisiting if [condition]
```

Omit if empty. This section is the input to the SRS feed-forward pipeline and
feeds the cross-project synthesis brief. Should be surfaced in the case-interviewer
session — it changes the behavioral spec for session-closer (which writes the note)
and brief (which could surface Calls items as practice prompts).

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
