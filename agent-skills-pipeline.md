# agent-skills — pure function model

## Skills

| Skill | Inputs | Outputs | Model | Invocation |
|---|---|---|---|---|
| `hub-starter` | hub-marker note (fallback: latest session note per ticket) + `status-cache.md` + `REVIEW_QUEUE.md` | `morning-brief.md` | Haiku | SOD, manual |
| `hub-marker` | all today's session notes (via `marker_detect.py`) | `notes/hub/YYYY-MM-DD.md`; surfaces tickets with no closer run | Haiku | EOD, manual |
| `instance-briefer` | `context.md` + latest session note for ticket | `CLAUDE.md` (cold-start artifact) | Haiku | on-demand, manual |
| `pr-fetcher` | ticket-id | `instances/<ticket>/pr-context.md` | Haiku | per-review, manual |
| `blind-reviewer` | `pr-context.md` (diff + metadata, no prior threads) | `<ticket>-review-YYYY-MM-DD.md` | Sonnet | review pass 1, manual |
| `context-reviewer` | `pr-context.md` (threads only, no diff) | triage artifact (resolved / pending / suggested responses) | Sonnet | returning review, manual |
| `instance-closer` | conversation compact + preflight token + prev session note + `pr-context.md` (optional) | `YYYY-MM-DD.md` (rolled-forward note) + `context.md` (open threads section) + `INCOMING.md` | Haiku | EOD per ticket, manual (after `/compact`) |
| `[session-checkpoint]` *(planned)* | conversation compact + prev session note | `YYYY-MM-DD.md` (initial or updated) + `context.md` | Haiku | mid-session, manual |

## Deterministic lib layer (no LLM)

| Script | Inputs | Output | Used by |
|---|---|---|---|
| `session_close_preflight.py` | ticket, project, `NOTE_ROOT` | one-line routing token: `mode:new\|append\|no-prev prev:<path> pending:<n> deferred:<n>` | `instance-closer` |
| `note_parser.py` | note path or (project, ticket) | section dict, bullet counts, latest-note path | preflight, marker_detect, hub-marker |
| `marker_detect.py` | `OWM_WORKSPACE`, `NOTE_ROOT` | `touched <ticket> <project> signals:<...>` per instance (waterfall: git-commits › instance-ran › mtime) | `hub-marker` |

## Infrastructure

| Component | Mechanism | Output | Consumed by |
|---|---|---|---|
| `owm-status-cache` | PostToolUse hook on owm lifecycle MCP calls | `status-cache.md` (~200 tokens), `status-cache.json` | `hub-starter`, `instance-briefer` |
| `pr-ism` | Bitbucket API wrapper | PR diffs + threads (via `pr-fetcher`); `REVIEW_QUEUE.md` (workspace-wide unreviewed PRs) | `pr-fetcher`, `hub-starter` |

---

## Key invariants

**Self-contained latest note** — `YYYY-MM-DD.md` latest file is always fully
self-contained. Rollforward in `instance-closer` ensures pending/deferred items
either land in Shipped or are re-stated verbatim. Nothing drops silently. Skills
never need to read note history.

**Routing token pattern** — `session_close_preflight.py` outputs one deterministic
line. `instance-closer` (Haiku) routes on a lookup table, not reasoning. Mechanical
steps cost zero judgment tokens.

**Status cache is change-relative** — cache is correct immediately after any owm
lifecycle call. Skills read `status-cache.md`; they never call owm directly inside
a session.

**Shallow SOD, deep per-ticket** — `hub-starter` is ~200 words and intentionally
surface-level. It flags stale tickets and suggests `/instance-briefer`; it never
calls it. Depth is opt-in per ticket.

**Reviewer symmetry** — both `blind-reviewer` and `context-reviewer` are
ownership-agnostic by design. `blind-reviewer` is diff-first (no thread noise);
`context-reviewer` is thread-first (no diff noise).
