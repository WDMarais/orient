# orient day-close — behavioral spec

Part of [orient behavioral spec](spec.md).

The EOD keystone. Aggregates the day's session notes into a single **day marker** and a
**pre-plan** for tomorrow, then archives. `day close` is what makes `day start` (the
morning brief) non-empty: without a marker to consume, `day start` has nothing to rank
(the "No active topics" empty state). Adapted from agent-skills `hub-closer` +
`marker_detect`, generalized to orient's project-generic note tree.

Haiku tier: aggregation across notes and the pre-plan heuristic are synthesis, so
`day close` pays for a single direct API call (same tier as `day start`).

**Loop invariant.** `day close` writes the marker `day start` reads next. The pair is the
only cross-day state handoff: a lost marker is re-derivable from the dated session notes +
`state.toml`, never from conversation.

## What it reads

- All session notes dated `<date>` under the workspace `note_root`
  (`<note_root>/<project>/<topic>/<date>.md`), across every project — ticket and
  non-ticket alike.
- Each note's `## Shipped`, `## Pending`, `## Deferred`, `## Calls`, `## Session`.
- **Touched-but-unclosed signal** (ported from `marker_detect`): topics with activity
  dated `<date>` (git commits since midnight, note-dir mtime) that have **no** `<date>.md`
  close note — surfaced as a flag, not silently dropped.

## What it writes

Mirrors the `brief.py` current-file + archive pattern:

- Current marker: `ORIENT_ROOT/day-marker.md` (frontmatter carries `date:`)
- Archive: prior marker rolled to `ORIENT_ROOT/day-markers/<prior-date>.md`
- `state.toml`: `last_day_close` date pointer advances (frontier rule below)

### Marker format

```markdown
---
date: YYYY-MM-DD
---

## Shipped today
- <project>/<topic>: <one-line synthesis from Shipped>

## Open threads
- <project>/<topic>: <Pending/Deferred still live — carried for tomorrow>

## Cross-topic
- <observations spanning topics; from ## Calls and NOTES.md sweep>

## Pre-plan (tomorrow)
1. <ordered next actions — heuristic below>

## Flags
- <project>/<topic>: worked but not closed (no close note for <date>)
- <project>/<topic>: last session hit budget-hit / context-limit — review before resuming
```

**Pre-plan heuristic** (ordering, not prescription — `day start` re-audits it):
Pending-first (unblock imminent work) → review/PR items → active Deferred (has a
destination and is due) → planned-but-untouched. Empty sections omitted.

## Date override (backdating)

Carries `--date YYYY-MM-DD` with the same contract as `session close` (see the spec.md
"Writing date is overridable; the frontier is not" invariant). For `day close` the
override is marker-level: it selects **which day's notes** are aggregated and **which
marker filename** is written.

```
orient day close --date 2026-06-17 (today is 2026-06-18; forgot to close yesterday)
  → aggregates notes dated 2026-06-17 only
  → writes marker dated 2026-06-17
  → frontier check:
      • no marker dated > 2026-06-17 exists → becomes current day-marker.md,
        prior archived; state.last_day_close → 2026-06-17
      • a later marker already exists (frontier ahead) → writes directly to
        day-markers/2026-06-17.md; current day-marker.md and state.last_day_close
        UNCHANGED (backfill behind the frontier does not regress state)

orient day close --date 2026-06-17 (a 2026-06-17 marker already exists)
  → archives the existing 2026-06-17 marker, regenerates (re-runnable; convergent
    not byte-identical, per the artifact invariant)

orient day close --date 2026-06-20 (today is 2026-06-18)
  → error:future-date given:2026-06-20 today:2026-06-18
  → does not proceed
```

`day start` consumes whatever marker is current, and its since-window keys on dates, so a
backfilled-then-promoted marker feeds the next morning brief correctly without special
casing.

## Edge cases

```
orient day close (no session notes dated today)
  → no marker content to synthesize
  → still writes a marker with Flags only (any touched-but-unclosed topics),
    or a single "nothing closed today" line — never a silent no-op (explicit invariant)

orient day close (notes exist but all Pending completed, nothing carried)
  → Open threads omitted; Pre-plan falls through to Deferred/untouched

orient day close (note_root unreadable / not configured)
  → error surfaced with fix hint; does not proceed
```

## orient day close --help

```
orient day close --help
  → Usage: orient day close [--date YYYY-MM-DD]
  →
  → Aggregate today's session notes into the day marker + tomorrow's pre-plan.
  → Feeds `orient day start`. Single Haiku call.
  →
  →   --date YYYY-MM-DD   Backdate the close (forgot to close on the day). Selects which
  →                       day's notes are aggregated and the marker filename. Never moves
  →                       the frontier backward; future dates are rejected.
  →
  → Examples:
  →   orient day close
  →   orient day close --date 2026-06-17
```
