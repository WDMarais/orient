---
name: day-closer
description: End-of-day aggregate — audit each worked topic was closed, read today's notes across topics holistically, sweep the day for cross-project captures, and refine the day marker + tomorrow's pre-plan that day-starter reads. Pairs with `orient day close`, which emits today's auto-aggregated marker as the context token. Invoke as /day-closer — no project/topic.
---

# Day closer

End-of-day skill. It pairs with `orient day close`, which has already done the mechanical
half: it walked today's session notes across every project and emitted an
**auto-aggregated marker draft** as your context token — Shipped today / Open threads /
Cross-topic / Pre-plan (tomorrow) / Flags. Your job is to **audit and sharpen that draft**,
not regenerate it from scratch.

Goal: leave one marker (`<ORIENT_ROOT>/day-marker.md`) that `day-starter` can read
tomorrow without re-scanning every session note.

## Steps

1. **Confirm closes were run.** The draft's `## Flags` already lists any topic worked
   today but lacking a `## Session` block ("worked but not closed"). For each, either ask
   the user to run `orient session close <project> <topic>` (then re-run `orient day close`
   to fold it in), or confirm it was untouched and let the flag stand. Wait for their
   answer.

2. **Read today's notes holistically.** The draft's one-line syntheses are mechanical
   (Shipped bullets joined). Improve them: collapse noise, surface what actually mattered,
   and name cross-topic dependencies or shared blockers the per-topic view misses. Tighten
   `## Open threads` to what is genuinely live for tomorrow.

3. **Cross-topic sweep.** `## Cross-topic` already carries each note's `## Calls` plus the
   day's `NOTES.md` captures. Add any cross-project or speculative items that don't belong
   to a single topic. Project-local items were already swept by each `session-closer`; do
   not duplicate those here.

4. **Refine the pre-plan.** The draft orders `## Pre-plan (tomorrow)` pending-first, then
   deferred — a mechanical heuristic. Re-rank by real priority: blocked-on-you and quick
   closes first, then review/PR items, then deferred work that now has a destination and is
   due. Drop anything stale.

5. **Confirm with the user**, then save the revised marker back to
   `<ORIENT_ROOT>/day-marker.md` (keep the `---\ndate: <today>\n---` frontmatter — that is
   what `day-starter` keys on):

   > "Here's tomorrow's suggested order — adjust anything before I save?"

## Done when
- every topic worked today is either closed or confirmed-untouched;
- Shipped / Open threads / Cross-topic read as a human-written synthesis, not raw joins;
- the pre-plan is re-ranked and confirmed with the user;
- `day-marker.md` is saved with today's date, and `day-starter` can read this one file
  tomorrow.
