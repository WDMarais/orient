# orient session-note — behavioral spec

Part of [orient behavioral spec](spec.md).

One operation, two modes. Invoked as `/session-note checkpoint` (mid-session) or
`/session-note close` (terminal). Shared: preflight routing, rollforward invariant,
note format. Distinct: close adds `## Session` GC sweep that checkpoint never writes.

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
- cost: ~$N.NN (estimated)
- duration: ~Nh
- model: haiku
```

Omit empty sections. `## Session` is close-only. `## Calls` is omit-if-empty; it is the input feed for future cross-project synthesis (brief) and the SRS pipeline — capture non-obvious decisions with brief rationale and a revisit condition.

## Checkpoint mode

```
/session-note checkpoint (project: orient, topic: cli; no note today; prev note has 2 pending, 1 deferred)
  → preflight: mode:new prev:<path> pending:2 deferred:1
  → reads prev Pending + Deferred; rolls forward
  → writes ~/.orient/notes/orient/cli/2026-05-22.md

/session-note checkpoint (today's note already exists)
  → preflight: mode:append line:<n> pass:<n> prev:<path>
  → appends ### Checkpoint <n> — <HH:MM> to existing note
  → does not overwrite

/session-note checkpoint (no previous note exists)
  → preflight: mode:no-prev
  → writes fresh note from session context only — no rollforward

/session-note checkpoint (note dir unwritable)
  → preflight: error:no-note-dir path:<path>
  → surfaces error; does not proceed
```

## Close mode

The "GC step" — terminal, thorough. Rolls forward state, writes `## Session` section
with reason, cost, duration and model. Sweeps session for NOTES.md items.

```
/session-note close (no note today; prev note has 2 pending, 1 deferred)
  → preflight: mode:new prev:<path> pending:2 deferred:1
  → writes full note with rollforward
  → appends ## Session:
      reason: natural-end
      cost: ~$0.42 (estimated)
      duration: ~2h
      model: haiku
  → sweeps for NOTES.md items; appends any found to ~/.orient/NOTES.md

/session-note close (today's note already exists — checkpoint ran earlier)
  → preflight: mode:append line:<n> pass:<n>
  → appends ### Close — <HH:MM> with GC sweep + ## Session
  → does not re-run rollforward

/session-note close reason:budget-hit
  → ## Session: reason: budget-hit
  → brief next morning surfaces: "<project>/<topic>: last session hit budget limit — review before resuming"

/session-note close reason:context-limit
  → ## Session: reason: context-limit
  → brief surfaces: "<project>/<topic>: last session hit context limit — compact before resuming"

/session-note close (no previous note, no today note)
  → preflight: mode:no-prev
  → writes fresh note from session context; still writes ## Session
  → no rollforward

/session-note close (all prev Pending completed this session)
  → all prev Pending appear in Shipped
  → ## Pending omitted

/session-note close (prev Deferred untouched this session)
  → all prev Deferred re-stated verbatim in today's Deferred
  → never dropped silently
```

## NOTES.md sweep (close only)

```
/session-note close (session contained items flagged for NOTES.md)
  → appends to ~/.orient/NOTES.md with timestamp + project tag
  → triggers: "add to notes", "worth remembering", explicit NOTES mention in session

/session-note close (no NOTES.md items found)
  → sweep runs silently; nothing appended
```

## Preflight edge cases (both modes)

```
/session-note (preflight: mode:ambiguous reason:<detail>)
  → surfaces reason verbatim
  → suggests re-running with Sonnet
  → does not proceed

/session-note (preflight output unrecognised)
  → prints raw output verbatim; stops
```

## /session-note --help

```
/session-note --help
  → Usage: /session-note <mode>
  →
  → checkpoint  Write or update today's note; continue session
  → close       Terminal: full note + GC sweep + ## Session section
  →
  → Both modes: rollforward Pending/Deferred from previous note. Nothing drops silently.
  → Close only:  ## Session (reason, cost, duration), NOTES.md sweep
  →
  → Reason values for close:
  →   natural-end | budget-hit | context-limit | human-stepped-away
  →
  → Examples:
  →   /session-note checkpoint
  →   /session-note close reason:budget-hit
  →   /session-note close reason:natural-end
```
