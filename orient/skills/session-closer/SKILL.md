---
name: session-closer
description: Finish today's orient session note from the live session — fill Goal/Shipped, reconcile the rolled-forward Pending/Deferred, set the ## Session phase, and sweep the conversation for items flagged for NOTES.md. The mechanical `orient session close` has already run preflight and written the skeleton; this is the judgment half. Invoke as /session-closer <project> <topic>.
---

# Session closer

`orient session close <project> <topic>` has already run. It routed preflight, wrote
the skeleton note at `<ORIENT_ROOT>/notes/<project>/<topic>/YYYY-MM-DD.md` with the
previous note's Pending and Deferred restated verbatim, and stubbed a `## Session`
block. The context token above carries the concrete date, note path, previous-note
contents, and the NOTES.md sweep target.

Your job is the judgment the command cannot do: read this session and finish the note.

Core invariant: the latest note file is fully self-contained — `day-starter` and
`topic-briefer` only ever read it, never history. Leave nothing implicit.

## Finish the note

Edit the skeleton the command wrote (its path is in the token). Keep the title line
exactly `# YYYY-MM-DD - <project>/<topic>` — ASCII " - ", never an em-dash.

**## Goal** — one line: the intent for this session.

**## Shipped** — a bullet per thing actually completed (commits, decisions, unblocked
items). Always name the specific files/artifacts touched, not just the work: "wrote
orient/skill.py", not "wrote the skill module".

**Reconcile Pending / Deferred (the core step — nothing drops silently).** The skeleton
already restated the previous note's Pending and Deferred. For each rolled-forward item,
search this session for evidence:

- Pending item completed → move it to `## Shipped`.
- Pending item still one action away → leave it in `## Pending`.
- Deferred item addressed → move it to `## Shipped`.
- Deferred item still punted → leave it in `## Deferred` (update its destination if it changed).
- Uncertain → leave it where it is. Never delete an item without evidence it was resolved.

Add genuinely new items from this session to the right section. Pending = imminent, one
action away. Deferred = consciously punted with a destination.

**## Session** — fill the block the command stubbed:
- `reason:` keep what the command set (it reflects how the session ended).
- `phase:` the dev phase this session reached, if the topic follows the dev pipeline
  (case-interviewer / harness-writer / architecture-proposer / implementation-writer);
  otherwise leave blank.
- add `recommended_next_phase:` only if this session completed a phase and the next is known.

## NOTES.md sweep

Scan **this session** for anything flagged for the notes vault — phrases like "add to
notes", "worth remembering", "park this", or an explicit NOTES.md mention.

The sweep target in the context token is mechanically resolved — use it as given:
- append each flagged item to the `file:` path from the token (this project's `NOTES.md`);
- one line per item, formatted exactly as the token's `append ... as:` line shows —
  `<date> <HH:MM> [<project>] <text>` — the date and `[<project>]` tag are already fixed
  for you, so supply only the time and the item text;
- create the file if it is absent; if nothing is flagged, do nothing (stay silent).

This sweep is **project-local** — only items relevant to this project/topic. Genuinely
cross-project or speculative observations are the hub's domain (day close), not yours.

## Topic context artifacts (mechanical — already done)

If this topic carries a `pr-context.md`, `orient session close` has already mirrored its
`## Open threads` section into the topic's `context.md` (touching only that section). The
context token lists whichever artifacts exist. This is mechanical — you do not edit
`context.md`; just reference the open threads if they bear on the note you are finishing.

This is the half `orient session close` cannot do: the command sees only the filesystem,
never the conversation. You see the conversation — so the sweep is yours.

## Done when
- Goal and Shipped are filled from this session;
- every rolled-forward Pending/Deferred item is either moved to Shipped (with evidence)
  or restated verbatim — none deleted silently;
- the `## Session` phase reflects where the session landed;
- NOTES.md-flagged items are appended to the vault with the concrete date/tag from the
  token, or nothing is appended if none were flagged.
