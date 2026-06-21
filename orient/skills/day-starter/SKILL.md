---
name: day-starter
description: Start-of-day orientation — audit orient's ranked active-topics claim against reality, triage notes captured since the last brief, and agree the day's focus with the user before any session starts. The mechanical `orient day start` has already built the preflight token and morning brief; this is the judgment half. Invoke as /day-starter — no project/topic.
---

# Day starter

`orient day start` has already run: it built the **preflight token** shown above — the
active topics ranked, each with its phase and live Pending, plus any notes captured since
the last brief — and wrote `morning-brief.md`.

Critical framing: that token is a **claim to audit, not instructions to execute**. orient
does the lookup (which topics are active, what phase each is in, a heuristic next action);
the decision of what to actually work on is yours, with the user. The start-of-day seam is
manual by design — `day start` never starts a session.

## Audit the claim

1. **Walk the ranked topics.** For each, the token shows a phase and its Pending. The
   recommended next action attached to a phase is a heuristic, not a verdict.
2. **Sanity-check the top candidates against reality.** Does the claimed phase match the
   latest note? Are any Pending items already done, or stale? Flag mismatches rather than
   trusting the ranking blindly — this is the audit the lookup can't do.
3. **Triage notes since the last brief.** These are raw captures from the buffer. For
   each: act now, promote it to a topic's Pending, or leave it for later. Don't let them
   silently accumulate.

## Agree the day's focus

Propose an order for the day — blocked-on-you first, then quick closes (one action away),
then long-running threads — and put it to the user:

> "Here's the order I'd suggest for today — does it work, or do you want to add, defer, or
> reorder?"

Wait for their answer and adjust. When a focus is chosen, the next move is an explicit
`orient session start <project> <topic>` — which hands off to `topic-briefer`.

## Done when
- the ranked claim has been audited against the actual notes, with mismatches flagged;
- notes since the last brief are triaged, not left sitting;
- the user has agreed today's focus and the first `orient session start` to run.
