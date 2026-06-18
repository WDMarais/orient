# orient topic — behavioral spec

Part of [orient behavioral spec](spec.md).

The active-topics registry: an explicit "I'm working on this" set, persisted in
state.toml as `active_topics = ["project/topic", ...]`. Independent of note recency
and day-close markers — it is how a topic stays surfaced by `day start` even with no
notes and no marker (cold start), and how you seed intent before starting work.

Two ways a topic becomes active:
- **Implicit**: `orient session start <project> <topic>` auto-marks it.
- **Explicit**: `orient topic mark <project> <topic>` seeds a topic ahead of starting.

Removed by `orient topic drop`, or by `day close` when a topic's threads are all
cleared (see [spec-day-close.md](spec-day-close.md)).

## Commands

```
orient topic mark <project> <topic>
  → adds project/topic to the registry
  → "marked active: <project>/<topic>"   (or "already active: ..." if present)

orient topic drop <project> <topic>
  → removes it
  → "dropped: <project>/<topic>"          (or "not active: ..." if absent)

orient topic list
  → one project/topic per line, in registry order
  → empty: "no active topics" + hint to mark one
```

## Persistence

A state.toml top-level key, preserved across every state write — sync, brief, and
session-note must not clobber it:

```
active_topics = ["orient/day-close", "re-owm/mcp"]

[project.owm]
last_synced_hash = "..."
last_synced_at = "..."
```

Mutations are read-modify-write through the same atomic tmp→rename + single-backup
mechanism as the rest of state.toml.

## day start consumption

`day start` ranks the union of: active registry ∪ recent-note topics ∪ pinned
projects ∪ latest marker open-threads. A registry topic appears regardless of note
recency. Each surfaced topic carries its `orient session start <project> <topic>`
invocation — `day start` never auto-starts (the SOD seam stays manual). See
[spec-brief.md](spec-brief.md).
