# orient sync — behavioral spec

Part of [orient behavioral spec](spec.md).

`orient sync` — resolves each configured project toward its goal state (parity with
upstream for git repos; backup-current for non-git units). Runs in parallel across
all projects. Output is a state snapshot, not an action log: boring states suppress,
interesting states surface.

**Internal state model**: `~/.orient/state.toml` stores `last_synced_hash` (git: local
HEAD observed at the last sync, written by the sync command; non-git: mtime or content
hash) and `last_synced_at` (timestamp) per project. Their *only* consumer is the **status
freshness fast path** (`should_fetch`, spec-status.md): if HEAD still matches
`last_synced_hash` and we are inside the freshness window, `status` skips the fetch.

> **Naming caveat.** `last_synced_hash` holds *local HEAD at last sync*, not a
> local↔upstream parity point. The name implies a parity/sync point; that misreading is
> what the abandoned pre/post-hash suppression model (below) was built on. Renaming it
> `last_local_head` would prevent the confusion. The stored value is correct for its one
> real consumer.

**Suppression is computed from current state, not from a stored-hash delta.** A git repo
is suppressed only when it is genuinely boring: clean, `ahead == 0`, `behind == 0`, not
diverged, no error, and nothing was pulled or pushed this run. Standing gaps
(`↑N (push off)`, `dirty`, `diverged`, `behind — pull blocked`) fail that test and so
surface on **every run** until the condition clears. A transient action (a `+N` pull this
run) surfaces the run it happens and falls silent the next, because next run there is
nothing left to do.

> The original spec described a `pre = stored hash` / `post = hash after sync` delta,
> suppressing when `pre == post`. That model was **never implemented** and is retired:
> keyed on local HEAD it would suppress every standing gap (an idle repo always sits at
> its own HEAD), hiding exactly the conditions a user must keep seeing.

**Detection precondition (the failure this spec corrects).** Ahead/behind is only
computable if orient can resolve an upstream to compare against. It resolves the
configured tracking ref (`@{u}`) first and **falls back to `origin/<branch>`** when no
tracking ref is set — a common state for branches pushed without `-u` or created locally.
Without that fallback, a repo with a remote but no tracking ref resolves nothing, reports
`ahead == 0 / behind == 0`, and is silently suppressed as "up-to-date" while sitting
arbitrarily far ahead of — or diverged from — its remote. Only when `origin/<branch>`
also does not exist is the repo genuinely upstream-less.

## First-run / missing config

```
orient sync (no workspace.toml found)
  → orient is not configured yet.
  →
  → To get started:
  →   orient config add-project <name> <path>
  →
  → Example:
  →   orient config add-project my-project ~/proj/my-project --pinned
  →
  → This creates ~/.orient/workspace.toml and adds your first project.

orient sync (workspace.toml exists but no [[projects]] entries)
  → no projects configured.
  →
  → Add your first project:
  →   orient config add-project <name> <path>
  →
  → Example:
  →   orient config add-project my-project ~/proj/my-project --pinned
```

## Happy path — git repos

```
orient sync (all repos clean, up-to-date)
  → no output
  # goal state maintained; pre-hash == post-hash for all; nothing to surface

orient sync (repo-A behind 3 commits, clean; pull succeeds)
  → repo-A   main · +3 · clean
  # transient delta shown; pre-hash != post-hash this run

orient sync (same repo-A, immediately after)
  → no output
  # pre-hash == post-hash; delta suppressed

orient sync (repo-B, push=true, local ahead 1 commit, clean)
  → repo-B   main · ↑1 pushed · clean

orient sync (repo-C, push=false, local ahead 1 commit, clean)
  → repo-C   main · ↑1 (push off)
  # gap: local leads upstream but push is disabled

orient sync (repo-D, dirty, up-to-date)
  → repo-D   main · dirty (3 files)
  # goal gap: uncommitted changes

orient sync (repo-E, dirty, behind 2 commits)
  → repo-E   main · dirty · behind 2 — pull blocked
  # cannot auto-resolve; surfaced for user to resolve manually
```

## Feature branch — contextual collapse

Orient's feature branch display intentionally omits the full triplet
(local/feat vs upstream/feat vs upstream/base) used in owm. That triplet addresses
multi-reviewer/multi-ticket fragmentation and merge-delay visibility in a team context.
Orient's personal project model is canonical-chunk-then-push: one developer, no
concurrent multi-machine work on the same project, semi-freeze until upstream
validation rather than parallel review routing. The simplified display is correct
by design, not an omission.



```
orient sync (repo-F on feat/cli; local in sync with upstream/feat; feat is +5/-3 v main)
  → repo-F   feat/cli · +5/-3 v main
  # local↔upstream-feat collapsed (in sync); only feat↔base delta shown

orient sync (repo-F on feat/cli; local behind upstream/feat by 2)
  → repo-F   feat/cli · behind 2 (upstream changed)
  # local↔upstream-feat not in sync; feat↔base not shown until resolved
```

## Diverged

```
orient sync (repo-G, both ahead and behind — cannot fast-forward)
  → repo-G   main · diverged — manual merge required
```

## Error states — git repos

```
orient sync (remote unreachable)
  → repo-H   main · error — remote unreachable

orient sync (auth failure)
  → repo-H   main · error — auth failed

orient sync (path not found in filesystem)
  → repo-H   error — path not found: ~/proj/missing
```

## Non-git units

```
orient sync (vault, not recently modified; pre-mtime == post-mtime)
  → no output
  # untouched; suppress

orient sync (vault, modified since last seen; no backup recorded)
  → working-notes   vault · modified 2d · consider backup

orient sync (vault, modified since last seen; suggest_backup=false)
  → working-notes   vault · modified 2d
  # touched, surfaced; suggestion suppressed by config

orient sync (vault, modified since last seen; backup recorded as recent)
  → no output
  # touched but backed up; backup goal state maintained; suppress
```

## Parallel execution and error handling

```
orient sync (3 repos succeed, 1 remote unreachable)
  → repo-A   main · +3 · clean
  → repo-C   main · ↑1 (push off)
  → repo-H   main · error — remote unreachable
  # parallel; independent; errors collected and surfaced at end
```

## All-suppressed

```
orient sync (all repos clean + up-to-date; all non-git units untouched or backed up)
  → 5 projects · all up-to-date
  → → ~/.orient/morning-brief.md
  # summary line confirms sync ran; pointer to on-disk summary for next-step prompting

orient sync (one repo ↑8 on main with push off; all others clean + up-to-date)
  → orient   main · ↑8 (push off — update config to push default branch)
  → 9 projects · all up-to-date
  →   → ~/.orient/morning-brief.md
  # standing gap surfaces EVERY run until pushed; never folded into "all up-to-date".
  # summary counts only the suppressed-boring rest, so the gap stays visible.
```

## --push flag (per-run override)

```
orient sync --push (repo-F on feat/cli, push=false in config)
  → repo-F   feat/cli · ↑1 pushed · clean
  # --push promotes sidecar/feature branches for this run only

orient sync --push (repo-C on main, push=false in config)
  → repo-C   main · ↑1 (push off — update config to push default branch)
  # --push does not override push=false on default branch
  # prevents accidentally pushing to main across many repos without config review
```

## Project targeting

Exact name match required. No fuzzy/partial matching built in. External fzf hook
populating from configured project names is the intended ergonomic extension.
Explicit targeting always shows state regardless of suppress-boring rule.

```
orient sync re-owm (re-owm is configured; clean and up-to-date)
  → re-owm   main · clean · up-to-date
  # explicit targeting always shows state

orient sync re-owm agent-skills (both configured; agent-skills is boring)
  → re-owm        main · +3 · clean
  → agent-skills  main · clean · up-to-date
  # both shown; explicit set overrides suppression

orient sync unknown-project
  → error: project "unknown-project" not found in workspace.toml

orient sync re-owm (dirty, push=true, ahead 2 commits)
  → re-owm   main · ↑2 pushed · dirty (1 file)
  # commits pushed; dirty working tree surfaced separately
```

## Opt-in facilitation — dirty + behind

Default: surface state and stop. User resolves manually. Opt-in alternatives
configurable per project or globally:

```
orient sync (repo dirty, behind; auto_commit=true)
  → commits dirty state: "IN PROGRESS: <branch> <timestamp>"
  → pulls upstream
  → repo-E   main · +2 · IN-PROGRESS commit preserved

orient sync (repo dirty, behind; side_branch=true)
  → pulls upstream to local branch `upstream-sync-YYYY-MM-DD`
  → leaves dirty working tree untouched
  → repo-E   main · dirty · side branch created: upstream-sync-2026-05-22 — merge when ready
```

## orient sync --help

```
orient sync --help
  → Usage: orient sync [project ...] [flags]
  →
  → Resolves each configured project toward its goal state.
  → Runs in parallel. Output is current state, not a log of actions taken.
  →
  → Flags:
  →   --push   Push sidecar/feature branches this run (overrides push=false for non-default branches)
  →
  → Targeting:
  →   orient sync                  sync all configured projects
  →   orient sync re-owm           sync one project (exact name match)
  →   orient sync re-owm srs-tool  sync two projects
  →
  → Guardrails:
  →   --push does not override push=false on default branches (main/master).
  →   Dirty repos that are also behind are surfaced and stopped — not auto-resolved.
  →   Use auto_commit=true or side_branch=true in config for opt-in facilitation.
  →
  → Examples:
  →   orient sync
  →   orient sync re-owm --push
  →   orient sync agent-skills srs-tool
```

## Design note — silent suppression of un-tracked branches (2026-06-20)

**Symptom.** `orient sync` reported `10 projects · all up-to-date` while the orient repo
itself was 9 ahead / 3 behind `origin/main` — diverged, not even fast-forwardable.

**Cause.** orient's `main` had a remote and a live `origin/main`, but **no upstream
tracking ref** (`@{u}` → "no upstream configured for branch 'main'"). Both `sync` and
`status` computed ahead/behind only inside `if tracking:`, so the counts stayed 0, the
current-state suppression test passed, and the repo was hidden. `last_synced_hash` was
never involved — git suppression does not read it (`prior_state` is unused in
`_sync_git`). The original spec's pre/post-hash story was a red herring; the real
dependency is the tracking ref.

**Resolution.** Resolve the upstream via `@{u}` with a fallback to `origin/<branch>`
(shared `_upstream_ref` helper used by both `sync` and `status`). orient now surfaces as
`diverged — manual merge required` every run until resolved. The behind-side pull was
switched from `git pull --ff-only` (which needs a tracking ref) to a post-fetch
`git merge --ff-only <ref>`, so a tracking-less but fast-forwardable repo still advances.

**Why no test caught it.** `make_remote_pair` builds repos with `git clone`, which always
configures tracking. The harness never produced the tracking-less state. Added a
no-tracking fixture and detection tests on both the sync and status paths.

**Deferred.** Rename `last_synced_hash` → `last_local_head` (state.toml schema + reads in
spec-status.md / spec.md + tests). Clarifying, not behavioural; not blocking.
