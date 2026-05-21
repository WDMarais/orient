# orient — spec seed for case-interviewer

## What this is

`orient` is an ambient context manager for LLM-driven development. It is not
primarily a git sync tool — git sync is incidental infrastructure (the morning
"folder setup"), not the purpose. The purpose is generating and maintaining the
context layer that makes LLM sessions productive across multiple concurrent
personal projects.

Direct inspiration: the owm agent-skill ecosystem (hub-starter, instance-closer,
preflight scripts) at work, adapted for personal projects where there are no
running Odoo instances, no tickets, and no PR review routing concerns.

Also a dogfooding ground for general agent-skill patterns — the tool itself and
its skills are a test bed for the case-interviewer → harness-writer →
architecture-proposer → implementation-writer pipeline.

---

## Context: what the work setup looks like

### At work (owm ecosystem)
- owm manages Odoo dev instances: git worktrees, running processes, databases
- ~28 active instances, each bound to a ticket (`pd-448`, `cd-1787`, etc.)
- Agent skills: `hub-starter` (morning brief), `instance-closer` (session note +
  rollforward), `instance-briefer`, `pr-fetcher`, `blind-reviewer`, etc.
- Note path: `~/notes/sessions/<project>/<ticket>/YYYY-MM-DD.md`
- Morning brief reads `hub-marker` (EOD aggregation) + PR freshness + instance state
- Session closer: Python preflight script outputs deterministic routing token →
  Haiku rolls forward pending/deferred items

### Locally (orient's domain)
- ~15 active git repos under `~/coding-projects/`, no running instances
- No ticket IDs — work is organized by project + topic slug
- 3-5 concurrent inter-project streams (e.g. at implementation-writer on re-owm,
  at case-interviewer on cq simultaneously)
- Interrupt model: real-life events (student request, work showcase, token bill
  retro) not inbox pings — currently head-resident, no tooling
- Session notes exist but sparse locally; retro-export shows the well-developed
  work equivalent

---

## Core design decisions (from grill session)

### Note convention
`<project>/<topic-slug>/YYYY-MM-DD.md`

Topic slug is freeform: `dashboard`, `CLI`, `MCP` for re-owm; skill names for
agent-skills; `anki-format` or `interval-scheduler` for srs-tool. Phase of work
(case-interviewer / harness-writer / architecture-proposer / implementation-writer)
tracked in note content, not config.

### Config model
Per-machine `workspace.toml`. Separate configs for local and work machines.
Separation is a design forcing function: keeps all skill logic generic, config
is the injection point for machine-specific state.

Env var: `ORIENT_ROOT` — points to config + notes root (default `~/.orient/`).

### Activity model
Recency-inferred (~14 days = active). Lightweight pinning option.
Queue-filling model: active/pinned first, backlog fill if sparse, don't surface
dormant unless needed. Brief is opinionated ("3 things to do first"), not an
exhaustive status dump.

### File naming convention (contestable)
Proposed: `UPPERCASE.md` for control-plane files the human writes/directs
(`INCOMING.md`, `CLAUDE.md`); `lowercase-hyphen.md` for everything generated
or maintained by skills/tools (`morning-brief.md`, `context.md`, session notes).
Heuristic: if you sit down and edit it directly → caps; if something writes it
for you → lower. Fuzzy case: `context.md` (human-seeded, skill-maintained) —
leaning lowercase since it's primarily state, not a control surface. This is
ad-hoc in the current agent-skills set and worth establishing cleanly here.
**Contestable: the caps/lower split may not be the right axis; could argue for
`SCREAMING` only for true inboxes (`INCOMING.md`) and lowercase everything else.**

### CLI / skill split
CLI owns: sync, status, config management — pure Python, no LLM.
Skills own: synthesis — brief (morning), session-closer (EOD).
Clean contract: CLI writes files that skills read; skills write files that CLI
surfaces.

---

## MVP scope

### CLI commands
- `orient sync` — pull (optionally push) all repos in config. Parallel execution.
  Rich terminal output (branch, dirty, ahead/behind, pull result per repo).
- `orient status` — repo state without pulling. Same rich output.

### Skills
- `brief` (Haiku) — reads latest session note per active topic, synthesizes
  queue, produces "3 things to do first" suggestion. Should surface current phase
  (case-interviewer / harness-writer / implementation-writer) per topic as context
  for the suggestions. Invoked at session start.
- `session-closer` (Haiku + Python preflight) — preflight script outputs
  deterministic routing token (mode, previous note path, pending/deferred counts),
  Haiku rolls forward. No PR routing, no INCOMING routing — pure note rollforward.
- `[session-checkpoint]` (planned) — mid-session variant of session-closer.
  Writes initial note for the day or updates an in-progress note. Closer =
  checkpoint + "closing out" framing + broader end-of-session checks.

### Config shape (draft — ambiguity flagged for case-interviewer)
```toml
[defaults]
note_root = "~/.orient/notes"
push = false
active_days = 14

[[repos]]
path = "~/coding-projects/odoo-tooling/owm"
push = true

[[repos]]
path = "~/coding-projects/agent-skills"

[[repos]]
path = "~/coding-projects/working-notes"
push = true

[[projects]]
name = "re-owm"
repo = "~/coding-projects/odoo-tooling/re-owm"
pinned = true
```

**Ambiguity to resolve**: `[[repos]]` (sync targets) and `[[projects]]` (context/notes
targets) currently overlap — `re-owm` appears in `[[projects]]` with a `repo` field,
duplicating the sync concern. A repo can exist without a project (pure backup sync)
and a project could span multiple repos. Case-interviewer should clarify whether
these are merged (one entry per thing) or kept separate (explicit sync vs context
concerns). The current shape is inconsistent.

---

## Deferred / out of scope for MVP
- Status cache (no runtime state to cache)
- Inbox model (INCOMING.md manually for now; VPS/structured inbox is a future project)
- Dashboard (natural later evolution once note corpus is rich)
- Hub-marker equivalent (EOD aggregation — add once brief + closer are working)
- PR freshness / external interrupt signals
- Swarm fan-out: EOD closer across all active topics simultaneously; parallel brief
  reads synthesized once. Natural evolution once sequential invocation is the
  bottleneck and note corpus is rich enough to justify.
- Hierarchical parallel execution model: top orchestrator → directors per DAG
  branch → batched implementors (4 at a time, not full fan-out) with alarm
  signals + read→implement→review→tune→test loop. Git worktrees per branch,
  N+1 layer does merges with spec snapshot. See conceptual notes for full
  treatment including agent work-sizing and respawn mechanics.
- Reimplementation as `claurient` after shape is proven in use

**Note on session-checkpoint and the parallel model**: the session-checkpoint
pattern (compact → checkpoint → respawn with minimal context) is the core
mechanic that makes the parallel execution model work at the director and
orchestrator tiers. Designing it well at MVP scale (personal project session
notes) builds the foundation for the larger model. The checkpoint invariant —
"latest note is fully self-contained, nothing requires reading history" — applies
at every tier.

---

## Key files for context
- `~/coding-projects/retro-export/session-evidence/CONVENTION.md` — session note format
- `~/coding-projects/agent-skills/instance-closer/SKILL.md` — closer to adapt from
- `~/coding-projects/agent-skills/hub-starter/SKILL.md` — brief to adapt from
- `~/coding-projects/agent-skills/lib/session_close_preflight.py` — preflight to reuse/adapt
- `~/coding-projects/agent-skills/lib/note_parser.py` — shared note utilities to reuse
- `~/coding-projects/misc-scripts/git-pull-all.sh` — sync to replace
- `~/coding-projects/orient-conceptual-notes.md` — pipeline discussion, Claw Code comparison, swarm model
