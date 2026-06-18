# orient

Ambient context manager for LLM-driven development. Git sync is incidental
infrastructure; the purpose is generating and maintaining the context layer that
makes LLM sessions productive and cost-efficient across personal projects.

## Status

Implementation complete; 154/155 tests green (1 known spec gap: NOTES.md sweep on close).
Command surface migrated to the day/session lifecycle spine. `session start` scaffolds a
session with a cold brief. `day close` and `--date` backdating are specced
(spec-day-close.md, spec.md) but not yet built.

## Usage patterns

**SOD**
```
orient day start          # ranked active topics + recommended next actions
                          # read, pick topic, start Claude session with brief as context
```
`orient day start` output is a *claim* Claude audits at session start, not instructions it executes — the SOD seam is intentionally manual.

**Session start** (begin work on a topic)
```
orient session start <project> <topic>
# scaffolds today's note with rolled-forward Pending/Deferred
# prints a cold brief of where the topic left off — idempotent, safe to re-run
```

**Session close** (run inside the active Claude session)
```
orient session close <project> <topic>
# prints skeleton path + previous note
# fill Goal/Shipped/Pending/Deferred/phase — Claude has session context to help
```

**Mid-session checkpoint** (before compaction, venue swap, context limit)
```
orient session checkpoint <project> <topic>
# appends ### Checkpoint N - HH:MM to current note
```

**Quick capture** (mid-session, don't break flow)
```
orient note "observation text"   # tag inferred from cwd; lands in NOTES.md, swept into next brief
```

**Repo hygiene** (git repos only — not the notes vault)
```
orient sync               # pull/push all projects in workspace.toml
orient status             # freshness + uncommitted state across workspace
```

**Note vault sync** — opt-in: `git init ~/.orient/` and add it to workspace.toml as a project entry. `orient sync` then handles it like any other repo.

## Spec files

| File | Purpose |
|---|---|
| `spec.md` | Design invariants, subsystem index, tech recommendation |
| `spec-sync.md` | Pull/push repos per config |
| `spec-status.md` | Read-only repo state display with freshness fast path |
| `spec-note.md` | Lightweight observation capture |
| `spec-config.md` | workspace.toml management |
| `spec-brief.md` | day-start: SOD context + queue (Haiku) |
| `spec-day-close.md` | day-close: EOD aggregate → marker + pre-plan (Haiku) |
| `spec-session-note.md` | session checkpoint/close notes (preflight + Haiku sweep) |

## Architecture

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | Module layout, DAG, per-module interface — handoff to implementation-writer |

## Reference material

| File | Purpose |
|---|---|
| `orient-spec-seed.md` | Original settled decisions + open questions (pre-interview) |
| `orient-conceptual-notes.md` | Pipeline rationale, alarm taxonomy, parallel execution model |
| `lib-adaptation-notes.md` | How agent-skills/lib maps to orient's lib (thin fork, ~5 line changes) |
| `agent-skills-pipeline.md` | Pure function model for agent-skills being adapted from |

## What it adapts from

- `~/proj/agent-skills/lib/session_close_preflight.py` — preflight routing token
- `~/proj/agent-skills/lib/note_parser.py` — note parsing utilities
- Thin fork: copy, rename `ticket→topic`, update env var default to `ORIENT_ROOT/notes`

## Tech stack

Python · Typer · Pydantic · Rich · `anthropic` SDK · `tomllib` (stdlib) · `tomli-w` · `ThreadPoolExecutor`

## Env var

`ORIENT_ROOT` — config + notes root (default `~/.orient/`)
