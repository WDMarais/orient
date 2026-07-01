# orient — stigmergy as the coordination frame

Companion to `orient-conceptual-notes.md`. This is the "what orient *is*, structurally"
note: the named model that the notes-tree design has been groping toward all along.
Not behavioral spec — a lens for making future decisions about the notes tree sharper.

**Stigmergy**: indirect coordination where agents organise by modifying a shared
environment rather than talking directly. One agent's action leaves a trace that
stimulates the next action — by the same agent later, or a different one — so the trace
is simultaneously *memory of past work* and *guide to what to do next*.

That last clause is a one-sentence statement of orient's note format: Shipped is the
memory, Pending/Deferred is the guide, the note is the trace.

---

## orient is a stigmergic medium

Sessions never message each other. A fresh session — a brand-new LLM instance with zero
memory of anything prior — coordinates with every session that came before it *only* by
reading and writing the notes tree. There is no direct channel and there is no shared
agent-internal state; the filesystem is the entire communication substrate. That is the
stigmergic topology in full.

**The self-contained-note invariant is a stigmergy requirement in disguise.** "The latest
note is always fully self-contained; nothing drops silently" is exactly the constraint
that an agent must be able to act from the *current state of the environment alone*, with
no history and no handoff. A stateless reader has to act correctly off the deposited mark.
The invariant wasn't derived from swarm theory, but it's the same requirement arrived at
independently — which is a good sign the design is coherent rather than arbitrary.

---

## Two trace types: sematectonic vs marker-based

The literature splits traces two ways, and orient does both:

- **Sematectonic** — the trace *is* the work. The diff, the code in the worktree, the
  half-built state; the work's own condition signals what to do next.
- **Marker-based** — a signal *distinct* from the work, deposited only to steer. Session
  notes, the day marker, NOTES.md, the `## Session` reason flags. Pure pheromone — a mark
  whose only job is to point.

This resolves the intuition that orient's agents "talk more directly" than ants. They
don't talk directly at all — there's no direct channel. What makes it *feel* direct is
that orient's markers are **high-bandwidth and structured** (typed sections, reason codes
like `budget-hit → review before resuming`) rather than the scalar gradient an ant lays.
It's richer markers, not closer contact.

---

## Multi-channel pheromone, and where decay already lives

The trace isn't one binary mark — it's several channels of different weight and, crucially,
different natural decay:

| channel | strength | decay |
|---|---|---|
| planner mention | weak | slow — just sits in the marker |
| touches / refactors | strong | **self-decaying** — timestamped (mtime/git) |
| pending tasks | strong | persistent until cleared (rollforward) |
| alarm (reason flags) | event | sticky until acknowledged |

The decay term people reach for when they ask "should orient prune stale stuff?" is
**already present** — it lives in the recency-bearing channels. "No touches in a week" is
decay that happened for free, no pruning logic required. The right question isn't "should
orient decay?" but "what's the half-life of each channel?" — and that's mostly already
implicit in which signals are timestamped versus persistent.

The alarm channel deserves naming as its own type: `budget-hit` / `context-limit` aren't
trail pheromone (they don't say "good route this way"), they're *alarm* pheromone —
"danger, review before resuming." Different semantics, different decay (sticky), shouldn't
be lumped with the trail signals.

**The mismatch between channels is itself signal.** A topic with a strong planner mark and
zero execution marks after a week isn't just a faint trail — it's "planned and didn't do,"
which is a more useful thing to surface than raw strength. The gradient *between* pheromone
types carries information the sum doesn't.

**Evaporation = cessation of reinforcement + a decay term, not deletion.** Archive is the
hard version (ρ=1, removed from circulation). "Stop renewing for next days" is the soft
version, and it only truly fades because the timestamped channels self-decay — stopping
deposition on a channel with no decay (planner, pending) leaves the mark at full strength.
The leak to watch is the **abandoned-but-not-archived** topic kept faintly alive by its
persistent channels.

---

## Ranking: priority × actionability, not priority

The natural ACO move — reinforce the strongest path — looks like it inverts for orient (a
stuck high-priority ticket "should get louder"), but the sharper read is that ACO actually
*fits*: the colony reinforces the path the ants **get through**, not the path to the most
valuable food. A high-priority/low-actionability ticket is a route to good food no ant can
currently walk. Pouring effort onto it because the destination is valuable is sunk cost
dressed up as prioritisation.

So the ranking signal is **priority × you-actionability**, and "stuck" splits in two:

- **Self-unblockable snag** — the next step is *yours* (read the spec, make the call, write
  the failing test). Surface it: the unblock *is* the actionable step.
- **Externally blocked** — the next step is someone else's (a merge, a decision, a reply).
  Low actionability; correctly fades. Head-banging here reinforces a path no ant can cross.

---

## Don't duplicate the environment

The wider world is *also* a stigmergic medium. The manager breathing down your neck about
project X, the deadline, the ticket SLA, the Slack ping — all traces deposited by other
systems. So orient should carry **only the channels the broader environment doesn't already
broadcast**. Duplicating the org's alarm pheromone inside orient is redundant deposition:
noise competing with the signal orient uniquely provides. (This is the same shape as the
companion note's "cost visibility needs to exist *outside* the system being monitored" —
the monitor belongs in a different medium than the thing it watches.)

This narrows the one trail orient uniquely must not let evaporate. It isn't "high-priority
blocked" — the environment already handles the loud ones. It's the item that is
**self-actionable AND matters AND nothing else is reminding you**. The third condition is
orient's whole edge.

It follows that **orient is a leading indicator, and its value is *before* the external
alarm fires.** By the time the manager is on you about X, you don't need orient to tell
you — but the point of orient is that you shouldn't have drifted into that state. It catches
the quiet self-actionable high-value thing while it's still quiet, so the lagging external
alarm never has to. Once the org's pheromone is loud, orient's job on that item is already
done, or already failed.

---

## Explore/exploit, and why broad cheap deposition compounds

`day start` today is pure *exploit* — it surfaces the known-active set. There are no
explore ants, so the failure mode is tunnel-vision on the loud topics while a
cold-but-relevant one quietly rots until you happen to notice. The manual "huh, haven't
touched X in a week" is that explore behaviour done by hand; the feature would be a
low-frequency "haven't looked at X in a month — keep or drop?" surfacing that doesn't
depend on you happening to notice.

Broad cheap deposition isn't a compromise against focus — it's the better policy, and it's
good stigmergy. Lay five trails, let the ones with traction reinforce themselves, don't
march ants into the one that isn't returning signal. "Five medium-priority tickets set up
and pushed" beats "head-banging one high-priority ticket where actionability is low." And
it's only dominant *because* orient + owm make the setup cost so low — the DAG chains make
fanning out cheaper than committing, so fanning out wins.

**The deposits compound — pre-built trails create future traversability.** Explorative and
refactor work isn't wasted even when it doesn't pay off immediately; it's sematectonic
deposition that lowers the cost of a future path. The grounding example:

> A good week is ~20h high-priority dev + ~20h explorative/refactor. In week 3 a
> high-priority loan feature lands — and you go "oh, I did extensive refactors adjacent to
> that in weeks 1–2; I'm well up to speed on it *now*." The explore ants from weeks 1–2
> had already laid the trail the week-3 food appeared on, so the route to it is short.

That's option value: broad cheap deposition now buys serendipitous readiness later. The
boundary (below) is that this only holds when deposition is genuinely cheap — otherwise
"explore" is just avoidance with a nicer name.

---

## Where the metaphor breaks (carry these boundaries)

- **Swarm emergence doesn't transfer.** Classic stigmergy has no central planner — global
  behaviour emerges from local rules. orient deliberately keeps a human orchestrator: you
  rank, you pick the topic, `day start` is a claim you audit rather than an instruction it
  executes. Transfer the indirect-coordination-via-medium half; do **not** chase "let
  coordination emerge, drop the ranking layer."
- **Reinforce-the-best is conditional.** Reinforce the *traversable* path, yes — but don't
  let a self-unblockable high-value item fade on actionability grounds (a few minutes of
  your action makes it traversable), and *do* let externally-blocked items fade.
- **Explore-is-free is conditional.** Pre-deposited trails compound only when setup is
  cheap. Without the DAG/tooling making deposition low-cost, scattering effort is dilution,
  not option value.

---

## Recognition cards (seeds)

Recognition-direction (cue = the *situation*, not the term), each with its boundary. Staged
here; port into the SRS pipeline (`## Calls` → card is the natural intake).

- **Coordinating stateless workers.** *Cue:* independent agents/sessions must coordinate but
  can't hold shared memory and don't message each other. *Card:* stigmergy — coordinate
  through self-sufficient traces in a shared medium; each trace must let a stateless reader
  act (→ self-contained-note invariant). *Not when:* the task needs real-time direct
  negotiation.
- **"Should this signal live in my tool?"** *Cue:* tempted to add a priority/urgency/alarm
  signal. *Card:* only carry channels the wider environment doesn't already broadcast loudly;
  duplicating the org's pheromone is noise. Monitor belongs in a different medium than the
  thing it watches.
- **Prioritising a stubborn item.** *Cue:* high-priority thing, no progress on it. *Card:*
  rank on priority × *actionability*; reinforce the traversable path, not the valuable-but-
  blocked destination. If YOU are the snag → act; if external → let it fade, the environment
  will alarm.
- **"Is this exploratory work avoidance?"** *Cue:* refactors/exploration with no immediate
  payoff. *Card:* pre-deposited trails lower future traversal cost — explore ants buy option
  value, not waste. *Boundary:* only when deposition is genuinely cheap (tooling makes setup
  low-cost); otherwise it IS avoidance.
- **Stale-but-still-showing.** *Cue:* an item stopped being relevant but keeps surfacing.
  *Card:* evaporation = cessation of reinforcement + a decay term; cessation alone isn't
  enough. Lean on self-decaying timestamped signals over manual pruning. Watch the
  abandoned-but-not-archived leak.

*Substrate-reasoning cluster (from the srs-tool / Bitter Lesson thread — scale vs.
structure, not coordination):*

- **Which of search/learning does this substrate scale?** *Cue:* deciding whether to
  lean on raw scale/compute or on hand-built structure for some agent or substrate.
  *Card:* identify the substrate's scalable resource — if it's compute (frontier
  training), lean into search/learning and the Bitter Lesson applies; if it's fixed
  (a human's working memory, a single LLM session), the scalable resource is
  accumulated cache, so offload to structure. *Boundary:* the two aren't symmetric —
  don't apply frontier "just scale it" logic to a fixed-compute substrate.
- **Is this reward signal manufacturable at scale?** *Cue:* considering whether to
  automate / RL / self-play a task. *Card:* the scale-eats-knowledge engine wins where
  a clean cheap reward exists (verifiable domains — code, formal math) and stalls where
  it doesn't (taste, pedagogy, open judgment); the bottleneck is the reward, not the
  compute. *Boundary:* an enumerable/verifiable domain is exactly where hand-authoring
  is both most tractable *and* most automatable — double-edged.
- **Working memory degrades with load on every substrate.** *Cue:* tempted to fix a
  context/attention problem by enlarging the window or holding more at once. *Card:*
  working memory is the permanently-scarce resource on every substrate that matters
  (human brain, single LLM session); offload to external cache and scope the task.
  *Boundary:* bigger *nominal* capacity (a 10M window) doesn't remove the need —
  effective reasoning-per-token still falls with fill.

---

## Open questions (the decay knobs)

- Does `day start` ranking carry a **recency decay** so quiet topics auto-sink (the soft
  (1−ρ) term), or do marked topics surface at full prominence until manually dropped?
- Should **active-topics auto-drop** after N quiet days (a decay constant on the registry),
  or is manual drop/archive the only exit?
- Is the **explore surfacing** ("haven't looked at X in a month — keep/drop?") worth a real
  feature, given the tunnel-vision failure mode it guards against?
