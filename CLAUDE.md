# orient

Ambient context manager for LLM-driven development. Git sync is incidental
infrastructure; the purpose is generating and maintaining the context layer that
makes LLM sessions productive and cost-efficient across personal projects.

## Status

Spec complete. Next pipeline step: `/harness-writer` against the spec files.

## Spec files

| File | Purpose |
|---|---|
| `spec.md` | Design invariants, subsystem index, tech recommendation |
| `spec-sync.md` | Pull/push repos per config |
| `spec-status.md` | Read-only repo state display with freshness fast path |
| `spec-note.md` | Lightweight observation capture |
| `spec-config.md` | workspace.toml management |
| `spec-brief.md` | SOD context + queue (Haiku skill) |
| `spec-session-note.md` | Checkpoint/close session notes (Haiku + preflight) |

## Reference material

| File | Purpose |
|---|---|
| `orient-spec-seed.md` | Original settled decisions + open questions (pre-interview) |
| `orient-conceptual-notes.md` | Pipeline rationale, alarm taxonomy, parallel execution model |
| `lib-adaptation-notes.md` | How agent-skills/lib maps to orient's lib (thin fork, ~5 line changes) |
| `agent-skills-pipeline.md` | Pure function model for agent-skills being adapted from |

## What it adapts from

- `~/coding-projects/agent-skills/lib/session_close_preflight.py` — preflight routing token
- `~/coding-projects/agent-skills/lib/note_parser.py` — note parsing utilities
- Thin fork: copy, rename `ticket→topic`, update env var default to `ORIENT_ROOT/notes`

## Tech stack

Python · Typer · Pydantic · Rich · `anthropic` SDK · `tomllib` (stdlib) · `tomli-w` · `ThreadPoolExecutor`

## Env var

`ORIENT_ROOT` — config + notes root (default `~/.orient/`)
