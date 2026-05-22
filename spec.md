# orient — behavioral spec

## Design invariants

**Explicit over implicit.** Missing config, missing paths, and unconfigured state are
errors — not silent no-ops or best-effort defaults. Orient always tells the user what
is wrong and how to fix it. It never silently proceeds with assumed state.

**State-not-action output.** Command output describes the current state of each
project, not the operations performed. Actions are implied by state transitions.

**Suppress boring, surface interesting.** Output contains only entries with
noteworthy state. All-boring runs produce a summary line confirming the run
completed; they do not produce per-project noise.

**Provider-agnostic artifact boundary.** Orient produces artifacts (brief frontmatter,
session notes, preflight tokens) and consumes cost/time summaries. How an orchestrator
dispatches those artifacts — parallelisation, rate limiting, provider selection
(Anthropic / Codex / local LLMs) — is not orient's concern. Orient's own Haiku calls
(brief, session-note) are single direct API calls; no orchestration needed at that tier.
Multi-provider routing and fanout strategy belong to the orchestrator layer
(`sequence.py`, `fanout.py`) that consumes orient's outputs.

**State vs artifact distinction.** `~/.orient/state.toml` holds durable operational
knowledge orient uses for local machine-level decisions: `last_synced_hash` and
`last_synced_at` per project, `last_brief` date, last session-note path per topic.
`last_synced_at` drives the status freshness fast path: if a project was synced within
the freshness window (default 60 min) and local HEAD still matches `last_synced_hash`,
status skips the upstream fetch for that project. State is never passed
to agents wholesale — only pared-down pre-processed extracts (preflight tokens, brief
frontmatter fields). Artifacts (morning-brief.md, session notes) are pure and
re-runnable: running brief twice produces convergent but not deterministically
identical output. Any artifact should be re-derivable from state + notes if lost.
State must be durable against artifact-level failures; artifacts must not depend on
each other's integrity.

**State write mechanism.** PostToolUse-style mechanical hook writes state atomically
after each completed operation (sync, brief, session-note). State is always current
relative to the last successful run. MVP: state file + single backup, alarm if
primary is corrupted. Post-MVP target: 6-snapshot rolling buffer; ≥4/6 corrupted →
escalating alarm + pause (requires human judgment — not self-managing). Design the
single-backup MVP to be non-breaking when extended to 6-snapshot.

**Dual-tier budget responsibility.** Orient is budget-aware at the suggestion tier:
it considers remaining budget when producing `next_actions` and does not generate
dispatch inputs that will obviously be blocked. The orchestrator enforces budget
limits mechanically as a secondary guard — if a spurious over-budget request arrives
anyway, the orchestrator blocks it. Orient owns awareness and judicious suggestion;
the orchestrator owns enforcement. Neither tier substitutes for the other.

**Help is first-class.** Every command's `--help` accurately reflects available
options, guardrails, and concrete examples. Help text is co-located with
implementation and updated alongside it.

---

## Subsystems

| Subsystem | File | Purpose |
|---|---|---|
| orient | [spec-orient.md](spec-orient.md) | Top-level help, version, critical env errors |
| sync | [spec-sync.md](spec-sync.md) | Pull/push repos per config |
| status | [spec-status.md](spec-status.md) | Repo state display without sync |
| note | [spec-note.md](spec-note.md) | Lightweight observation capture |
| config | [spec-config.md](spec-config.md) | workspace.toml management |
| brief | [spec-brief.md](spec-brief.md) | SOD context + queue (Haiku skill) |
| session-note | [spec-session-note.md](spec-session-note.md) | Checkpoint/close session notes (Haiku + preflight) |

---

## Technology recommendation

**Constraints that emerged from the interview:**

- Pure Python for CLI (sync, status, config, note, state) — deterministic, no LLM, fast
- Haiku via Anthropic SDK for brief and session-note — already decided
- `session_close_preflight.py` and `note_parser.py` exist and are directly reusable —
  strong pull toward Python continuity
- TOML config and state (`workspace.toml`, `state.toml`) — `tomllib` is stdlib in Python 3.11+
- Terminal output with contextual collapse and column alignment
- PostToolUse hook pattern for state writes — Python subprocess
- Provider-agnostic artifact boundary — no external runtime dependency required at MVP

**Axes that don't push hard:**

- **Parsing/grammar complexity**: none — TOML config, markdown notes, line-format
  preflight tokens. No algebraic types or parser combinators needed.
- **Performance**: N≤15 repos; parallel git pulls are the bottleneck, not language
  runtime. `ThreadPoolExecutor` from stdlib is sufficient.
- **Type safety**: meaningful but not dominant. Pydantic at config parse time catches
  the classes of errors that surfaced in the interview (duplicate names, invalid
  `activity_model`, wrong types). Runtime type safety is not load-bearing.

**Recommendation: Python throughout.**

| Concern | Choice | Rationale |
|---|---|---|
| CLI framework | Typer | `--help` generation satisfies help-is-first-class with minimal boilerplate; subcommand structure maps cleanly |
| Config validation | Pydantic | Consistent with re-owm precedent; catches duplicate names, invalid fields at parse time |
| Terminal output | Rich | Contextual collapse, column alignment, suppress-boring patterns map to Rich table/live primitives |
| LLM calls | `anthropic` SDK direct | Brief and session-note are single calls; no orchestration layer needed at MVP |
| Lib layer | Thin fork from agent-skills/lib | Copy, rename `ticket→topic`, update env var default to `ORIENT_ROOT/notes`. ~5 lines of changes; independent note trees mean divergence risk is low (parser is format-agnostic, unknown sections are silently skipped). Extract to shared package if and when note format becomes a genuine cross-tool protocol requiring byte-for-byte sync across consumers. Not warranted at MVP scale. |
| State reads | `tomllib` (stdlib) | Python 3.11+; zero dependency |
| State writes | `tomli-w` | Minimal single dependency for TOML serialisation |
| Parallelism | `ThreadPoolExecutor` | stdlib; sufficient for N≤15 sync targets |

No tension between axes. Python is the path of least resistance given the existing
lib layer, re-owm's Pydantic schema precedent, and the `anthropic` SDK being
Python-native.
