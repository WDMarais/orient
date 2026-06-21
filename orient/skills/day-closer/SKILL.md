---
name: day-closer
description: End-of-day aggregate — confirm each worked topic was closed, read today's notes across topics holistically, sweep the day for cross-project/hub-level captures, and write a hub marker with tomorrow's pre-plan that day-starter reads. Pairs with `orient day close` (mechanical half pending). Invoke as /day-closer — no project/topic.
---

# Day closer

End-of-day skill. It pairs with `orient day close`, whose mechanical half is not built
yet (see spec-day-close.md) — so for now there is no context token: gather the inputs
yourself. When `day close` lands it will hand you today's note list and the topics still
missing a close.

Goal: leave one hub-level marker that `day-starter` can read tomorrow without re-scanning
every session note.

## Steps

1. **Confirm closes were run.** Find today's session notes across projects
   (`<ORIENT_ROOT>/notes/<project>/<topic>/<today>.md`). For any topic marked active and
   worked today but lacking a closed note (no `## Session` block), flag it and ask the
   user to run `orient session close <project> <topic>`, or confirm it was untouched and
   skip it. Wait for their answer.

2. **Read today's notes holistically.** Across all of today's notes, build a cross-topic
   picture: what shipped, what's Pending (one action away) per topic, what's Deferred and
   where, and any cross-topic dependencies or shared blockers.

3. **Hub NOTES.md sweep (the global half).** This is the day-closer's domain. Sweep the
   day for items flagged as cross-project or speculative — the ones that don't belong to
   any single topic — and append them to the **hub** capture vault (`notes/hub/NOTES.md`
   under the hub namespace), tagged `[hub]`. Project-local items were already swept by
   each `session-closer`; do not duplicate those here.

4. **Write the hub marker** for today (a hub-level note, `notes/hub/<today>.md`):

   ```
   # <today> - hub

   ## Shipped today
   - <project>/<topic>: <one line>

   ## Open threads
   - <project>/<topic>: <pending — one action away>
   - <project>/<topic>: <deferred, with destination>

   ## Cross-topic notes
   - <dependencies / shared blockers / patterns — omit if none>

   ## Pre-plan
   1. <project>/<topic> - <why first: blocked-on-you, quick close, ...>
   2. ...
   ```

   Keep the title line `# <today> - hub` (ASCII " - "). Omit empty sections.

5. **Confirm the pre-plan with the user** before saving:

   > "Here's tomorrow's suggested order — adjust anything before I save?"

   Update `## Pre-plan` to match their answer.

## Done when
- every topic worked today is either closed or confirmed-untouched;
- cross-project/hub items are swept to `notes/hub/NOTES.md`, project items left to their
  session-closers;
- `notes/hub/<today>.md` is written with Shipped / Open threads / Pre-plan;
- the pre-plan is confirmed, and `day-starter` can read this one file tomorrow.
