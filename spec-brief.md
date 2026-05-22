# orient brief — behavioral spec

Part of [orient behavioral spec](spec.md).

`orient brief` — SOD session primer. CLI orchestrator runs Python preflight (resolves
active topics, extracts note content, counts unreviewed NOTES.md items since last
brief), then invokes Haiku via the Anthropic SDK. Haiku writes
`~/.orient/morning-brief.md` and surfaces the human-readable section in the session.

Designed for two modes with the same output format:
- **Human-in-loop**: prescriptive next step, human executes
- **Autonomous**: next step + budget scope + alarm boundary, agent dispatches

## Phase → next_action lookup table

Haiku uses this mechanically (lookup, not reasoning):

| Phase | Next action |
|---|---|
| `case-interviewer in progress` | `continue /case-interviewer` |
| `case-interviewer complete` | `/harness-writer <project> <topic>` |
| `harness-writer complete` | `/architecture-proposer <project> <topic>` |
| `architecture-proposer complete` | `/implementation-writer <project> <topic>` |
| `implementation-writer in progress` | `continue /implementation-writer` |
| `implementation-writer complete` | `/verify → /session-closer` |
| `unknown` | `open <note-path> to orient, then choose next stage` |

`sequence.py` (future): when it exists, `architecture-proposer complete` emits
`sequence.py <project> <topic>` instead. No brief format change needed.

## Output format

Frontmatter (machine-readable, drives autonomous dispatch) + human-readable prose.
Terminal shows prose only; file contains both.

`--agent-friendly` (planned): strict schema, token-compressed, disambiguation-first.
Default output is human/context-friendly.

Future: a separate Haiku `extract-signal` pass reads morning-brief.md and produces
structured dispatch JSON for `sequence.py` / `fanout.py`. Not plain serialisation —
synthesised signal. Not MVP.

## Preflight token (Python → Haiku)

Two-pass extraction:
1. **Structural pass**: metadata per topic — note path, pending/deferred counts, phase, recency
2. **Content pass**: `## Pending` and `## Deferred` verbatim from each note; NOTES.md items since `last_brief`

```
last_brief: 2026-05-21
active_topics: 4

topic: re-owm/mcp
  note: ~/.orient/notes/re-owm/mcp/2026-05-20.md
  phase: harness-writer-complete
  pending:
    - run /architecture-proposer
  deferred: (none)

topic: orient/cli
  note: ~/.orient/notes/orient/cli/2026-05-21.md
  phase: case-interviewer-in-progress
  pending:
    - finish sync cases
    - write brief cases
  deferred:
    - hub-marker equivalent → dropped

notes_since_last_brief:
  [orient]    preflight exits 0 even when note dir is unwritable
  [untagged]  sync stalled on unreachable remote, no timeout shown
```

## Output: morning-brief.md

```
---
date: 2026-05-22
last_brief: 2026-05-21
active_topics: 4
next_actions:
  - topic: re-owm/mcp
    phase: harness-writer-complete
    skill: architecture-proposer
    invocation: /architecture-proposer re-owm mcp
    priority: 1
    estimated_tokens: ~       # deferred — populated when cost estimation exists
    regression_guard: ~       # deferred — populated from harness spec when available
  - topic: orient/cli
    phase: case-interviewer-in-progress
    skill: case-interviewer
    invocation: continue /case-interviewer
    priority: 2
    estimated_tokens: ~
    regression_guard: ~
notes_unreviewed: 2
---

# Morning brief — 2026-05-22

## Do first
1. re-owm/mcp — harness-writer complete → `/architecture-proposer re-owm mcp`
2. orient/cli — case-interviewer in progress → continue `/case-interviewer`

## Quick wins (pending, one action away)
- agent-skills/session-closer: push branch to upstream

## Carrying forward
- srs-tool/core: 3 deferred items (last touched 2026-05-18)

## Unreviewed notes (2)
- [orient]    preflight exits 0 even when note dir is unwritable
- [untagged]  sync stalled on unreachable remote, no timeout shown
```

## Happy path cases

```
orient brief (4 active topics, mixed phases, 2 unreviewed notes)
  → writes morning-brief.md as above
  → terminal: prose section only (frontmatter not shown in stdout)
  → priority order: phase-transition topics first, pending-only second, deferred-heavy third

orient brief (topic with unknown phase — note exists but phase not inferrable)
  → surfaced in ## Do first:
    "<project>/<topic> — phase unclear → open <note-path> to orient, then choose next stage"
  → frontmatter: phase: unknown, invocation: null

orient brief (no active topics — all dormant beyond active_days, none pinned)
  → ## Do first: (empty)
  → "No active topics. Consider pinning a project:
      orient config add-project <name> <path> --pinned"

orient brief (pinned topic with no session notes yet)
  → surfaces regardless of activity model
  → ## Do first: "<project>/<topic> — no notes found → start a session and run /session-note close"

orient brief (no session notes anywhere — first run after config)
  → orient is configured but no session notes found.
  → Run a work session, then close it with /session-note close to begin building context.

orient brief (all topics fully up-to-date, nothing pending or deferred)
  → ## Do first: (empty — all clear)
  → "All caught up. Orient suggests: review backlog or start a new topic."

orient brief (run twice same day)
  → overwrites morning-brief.md — does not append
  → refreshes with current note state
  → last_brief frontmatter field updates to today after first run

orient brief (topic last noted >active_days ago, not pinned)
  → topic does not appear — below activity threshold

orient brief (NOTES.md absent)
  → notes_unreviewed: 0
  → ## Unreviewed notes section omitted
```

## Brief surfaces previous close reason

```
orient brief (previous session closed with reason: budget-hit)
  → surfaces in ## Do first or as a note under the topic:
    "re-owm/mcp: last session hit budget limit — review cost before resuming"

orient brief (previous session closed with reason: context-limit)
  → "re-owm/mcp: last session hit context limit — compact before resuming"
```

## Error / edge cases

```
orient brief (no workspace.toml)
  → orient is not configured yet.
  → [same richer first-run message as orient sync]

orient brief (note_root path unwritable)
  → error: cannot write to note_root: ~/.orient/notes — check permissions
```

## orient brief --help

```
orient brief --help
  → Usage: orient brief
  →
  → Reads session notes for active topics and writes ~/.orient/morning-brief.md.
  → Invokes Haiku — requires ANTHROPIC_API_KEY.
  →
  → Output:
  →   ~/.orient/morning-brief.md   frontmatter + prose (full artifact)
  →   stdout                       prose section only
  →
  → Active topics: projects with notes touched within active_days (default: 14), or pinned.
  → Priority order: phase-transition topics first, pending-only second, deferred-heavy third.
  →
  → Example:
  →   orient brief
```
