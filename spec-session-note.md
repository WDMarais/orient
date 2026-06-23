# orient session — behavioral spec

Part of [orient behavioral spec](spec.md).

Three edges, one note machinery. Invoked as `orient session start` (scaffold + cold
brief at session open), `orient session checkpoint` (mid-session marker), or
`orient session close` (terminal). Shared: preflight routing, rollforward invariant,
note format. Distinct: start surfaces a cold brief and is idempotent (never adds a
checkpoint marker); close adds the `## Session` GC sweep that the others never write.

**Rollforward invariant**: the latest note for any topic is always fully
self-contained. Nothing drops silently. Pending items either land in Shipped or
re-appear verbatim in Pending. Deferred items re-appear verbatim or with updated
destination.

**Preflight** (Python, adapted from `session_close_preflight.py`):
- Input: project, topic, mode (checkpoint|close)
- Resolves note path under `ORIENT_ROOT/notes/<project>/<topic>/YYYY-MM-DD.md`
- Output token: same structure as instance-closer preflight
  (`mode:new`, `mode:append`, `mode:no-prev`, `mode:ambiguous`, `error:*`)

## Note format

```markdown
# YYYY-MM-DD — <project>/<topic>

## Goal
<one line: session intent>

## Shipped
- <completed items>

## Pending
- <imminent, one action away — re-stated verbatim from previous if still in flight>

## Deferred
- <item> → <destination: NOTES.md, separate topic, or dropped>

## Time sink
- <what took longer than expected>

## Calls                      ← omit if empty
- Chose X over Y because Z — worth revisiting if [condition]

## Session                    ← close mode only; checkpoint never writes this
- reason: <natural-end | budget-hit | context-limit | human-stepped-away>
- phase: <pipeline stage at close — e.g. harness-writer-complete>
- recommended_next_phase: <override — omit if standard pipeline applies>
- cost: ~$N.NN (estimated)
- duration: ~Nh
- model: haiku
```

Omit empty sections. `## Session` is close-only. `## Calls` is omit-if-empty; it is the input feed for future cross-project synthesis (brief) and the SRS pipeline — capture non-obvious decisions with brief rationale and a revisit condition.

## Start mode

Session open: scaffold today's note (if absent) with rolled-forward Pending/Deferred,
and surface a **cold brief** of where the topic left off. Mechanical (no Haiku).
Idempotent — re-running when today's note exists re-surfaces context without adding a
marker or overwriting. Writes no `## Session` (it is not a close).

```
orient session start (no note today; prev note has pending/deferred)
  → preflight: mode:new prev:<path>
  → writes today's skeleton with rollforward (no ## Session)
  → prints cold brief:
      --- resuming <project>/<topic> (last note <date>) ---
      Goal / Pending (n) / Deferred (n)

orient session start (no previous note, no today note)
  → preflight: mode:no-prev
  → writes fresh empty skeleton
  → prints: fresh start - no prior notes for <project>/<topic>

orient session start (today's note already exists)
  → preflight: mode:append
  → does NOT add a checkpoint marker; does NOT overwrite
  → prints: session already started today: <path>  + cold brief

orient session start (prev closed with reason budget-hit / context-limit)
  → cold brief flags it: [!] last session: budget-hit - review before resuming
```

## Checkpoint mode

```
orient session checkpoint (project: orient, topic: cli; no note today; prev note has 2 pending, 1 deferred)
  → preflight: mode:new prev:<path> pending:2 deferred:1
  → reads prev Pending + Deferred; rolls forward
  → writes ~/.orient/notes/orient/cli/2026-05-22.md

orient session checkpoint (today's note already exists)
  → preflight: mode:append line:<n> pass:<n> prev:<path>
  → appends ### Checkpoint <n> — <HH:MM> to existing note
  → does not overwrite

orient session checkpoint (no previous note exists)
  → preflight: mode:no-prev
  → writes fresh note from session context only — no rollforward

orient session checkpoint (note dir unwritable)
  → preflight: error:no-note-dir path:<path>
  → surfaces error; does not proceed
```

## Close mode

The "GC step" — terminal, thorough. Rolls forward state, writes `## Session` section
with reason, cost, duration and model. Sweeps session for NOTES.md items.

```
orient session close (no note today; prev note has 2 pending, 1 deferred)
  → preflight: mode:new prev:<path> pending:2 deferred:1
  → writes full note with rollforward
  → appends ## Session:
      reason: natural-end
      cost: ~$0.42 (estimated)
      duration: ~2h
      model: haiku
  → sweeps for NOTES.md items; appends any found to ~/.orient/NOTES.md

orient session close (today's note already exists — checkpoint ran earlier)
  → preflight: mode:append line:<n> pass:<n>
  → appends ### Close — <HH:MM> with GC sweep + ## Session
  → does not re-run rollforward

orient session close reason:budget-hit
  → ## Session: reason: budget-hit
  → brief next morning surfaces: "<project>/<topic>: last session hit budget limit — review before resuming"

orient session close reason:context-limit
  → ## Session: reason: context-limit
  → brief surfaces: "<project>/<topic>: last session hit context limit — compact before resuming"

orient session close (no previous note, no today note)
  → preflight: mode:no-prev
  → writes fresh note from session context; still writes ## Session
  → no rollforward

orient session close (all prev Pending completed this session)
  → all prev Pending appear in Shipped
  → ## Pending omitted

orient session close (prev Deferred untouched this session)
  → all prev Deferred re-stated verbatim in today's Deferred
  → never dropped silently
```

## Date override (backdating)

Both modes default the written date to the system clock. `--date YYYY-MM-DD` overrides
it — for the common case of closing a session you neglected to close on the day it
happened, without today becoming the date the work is recorded under. See the
spec.md "Writing date is overridable; the frontier is not" invariant.

Override changes only the written date: the note filename `<date>.md` and the
`# <date> — <project>/<topic>` header. Intra-note timestamps (checkpoint/close `HH:MM`)
remain real capture time — the date moves, the clock does not lie about when you typed.

```
orient session close <project> <topic> --date 2026-06-17 (today is 2026-06-18; no note for the 17th)
  → preflight resolves prev relative to the OVERRIDDEN date:
      previous note = latest note strictly before 2026-06-17 (NOT the latest overall)
  → mode:new prev:<…/2026-06-16.md> pending:n deferred:n
  → writes …/<project>/<topic>/2026-06-17.md with rollforward from the 16th
  → state last-note pointer: unchanged if a note dated > 2026-06-17 already exists
    for this topic (backfill behind the frontier does not regress state)

orient session close <project> <topic> --date 2026-06-17 (a 2026-06-17 note/checkpoint already exists)
  → preflight: mode:append — appends ### Close — <HH:MM> to the 17th's note
  → never clobbers the existing dated note

orient session close <project> <topic> --date 2026-06-20 (today is 2026-06-18)
  → error:future-date given:2026-06-20 today:2026-06-18
  → does not proceed (explicit over implicit; you cannot close the future)
```

Applies identically to `checkpoint` (backdated mid-session marker), though backdating a
checkpoint is rare. `day close` carries the same `--date` flag with marker-level
semantics — see [spec-day-close.md](spec-day-close.md).

## NOTES.md sweep (close only)

```
orient session close (session contained items flagged for NOTES.md)
  → appends to ~/.orient/NOTES.md with timestamp + project tag
  → triggers: "add to notes", "worth remembering", explicit NOTES mention in session

orient session close (no NOTES.md items found)
  → sweep runs silently; nothing appended
```

## Topic context artifacts (close only)

A topic directory may hold two per-topic markdown artifacts alongside its dated notes:

- `pr-context.md` — fetched PR state (diff, description, `## Open threads`). Written by
  some external producer; orient only ever reads it.
- `context.md` — the topic's cold-start doc. orient owns one section of it.

On close, the mechanical command mirrors `pr-context.md`'s `## Open threads` section into
`context.md` — **touching only that section**; everything else in `context.md` is
preserved (it is otherwise human/tool curated). Deterministic, filesystem-only, no Haiku.

```
orient session close (pr-context.md present with ## Open threads)
  → context.md gains/replaces its ## Open threads from pr-context.md (other sections kept)
  → idempotent: re-running with unchanged pr-context.md rewrites nothing

orient session close (no pr-context.md, or it has no ## Open threads)
  → sync is a silent no-op; context.md is left untouched
```

This does not affect the rollforward invariant: the dated note remains fully
self-contained. `context.md` is a convenience artifact, re-derivable from `pr-context.md`.

## Preflight edge cases (both modes)

```
orient session (preflight: mode:ambiguous reason:<detail>)
  → surfaces reason verbatim
  → suggests re-running with Sonnet
  → does not proceed

orient session (preflight output unrecognised)
  → prints raw output verbatim; stops
```

## orient session --help

```
orient session --help
  → Usage: orient session <edge>
  →
  → start       Scaffold today's note + cold brief of where the topic left off
  → checkpoint  Write or update today's note; continue session
  → close       Terminal: full note + GC sweep + ## Session section
  →
  → All edges: rollforward Pending/Deferred from previous note. Nothing drops silently.
  → Start only:  cold brief, idempotent, no marker, no ## Session
  → Close only:  ## Session (reason, cost, duration), NOTES.md sweep
  →
  → Reason values for close:
  →   natural-end | budget-hit | context-limit | human-stepped-away
  →
  → Examples:
  →   orient session start orient cli
  →   orient session checkpoint
  →   orient session close reason:budget-hit
```
