---
name: topic-briefer
description: Orient a session on a project/topic before work begins — read the latest note in full, confirm where things stand, heed any close-time alarm, and pick the single next concrete action. The mechanical `orient session start` has already scaffolded today's note and emitted the cold brief; this is the judgment half. Invoke as /topic-briefer <project> <topic>.
---

# Topic briefer

`orient session start <project> <topic>` has already run: it scaffolded today's note
(rolling Pending/Deferred forward from the last note) and printed the **cold brief**
shown above this skill body — the previous note's Goal, Pending, Deferred, and any
close-time alarm.

Your job is the judgment the command can't do: turn that cold brief into orientation and
a chosen next step, before any work starts.

Relies on `session-closer`'s invariant: the latest note is fully self-contained. Read
only it, never history.

## Get oriented

1. **Read the latest note in full** (the cold brief is a summary; the note is the
   source). Confirm the topic's Goal and the shape of what shipped last.
2. **Treat rolled-forward Pending as the candidate next actions** — these are imminent,
   one step away. Deferred items are consciously punted; don't pick them up unless you're
   deliberately un-deferring one.
3. **Heed any alarm** the cold brief flags (`[!] last session: budget-hit` → review
   before resuming; `context-limit` → compact before resuming). Resolve it first.
4. **Check the project's live state** if the next action depends on it — `git status` /
   recent commits in the project repo — so orientation matches reality, not just the note.

## Choose the next action

State, in one line, the single concrete next step for this session before diving in
(e.g. "wire discover_skills into the CLI, then run the skill tests"). One action, not a
plan. orient deliberately does **not** pick this for you — the start-of-session seam is
manual by design; you decide, having read the note.

## Done when
- you can say what this topic is and what its Goal is, from the latest note;
- you know which Pending items are live and whether any alarm needs handling first;
- you have named the one next concrete action, and only then begin work.
