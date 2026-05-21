# orient

Ambient context manager for LLM-driven development. Git sync is incidental
infrastructure; the purpose is generating and maintaining the context layer that
makes LLM sessions productive and cost-efficient across personal projects.

## Status

Pre-spec. Grill session complete. About to run case-interviewer to produce spec.md.

## Key files

| File | Purpose |
|---|---|
| `orient-spec-seed.md` | Settled decisions + open questions — primary input for case-interviewer |
| `orient-conceptual-notes.md` | Pipeline rationale, Claw Code comparison, parallel execution model |
| `agent-skills-pipeline.md` | Pure function reference for existing agent-skills being adapted from |
| `spec.md` | Behavioral spec — written by case-interviewer session (not yet exists) |

## What it adapts from

- `~/coding-projects/agent-skills/instance-closer/SKILL.md` — session-closer
- `~/coding-projects/agent-skills/hub-starter/SKILL.md` — brief
- `~/coding-projects/agent-skills/lib/` — note_parser.py, session_close_preflight.py

## MVP subsystems

1. `sync` — pull/push repos per config
2. `status` — repo state display
3. `config` — workspace.toml management
4. `brief` — Haiku skill, SOD context + queue
5. `session-closer` — Haiku + Python preflight, EOD note rollforward

## Env var

`ORIENT_ROOT` — config + notes root (default `~/.orient/`)
