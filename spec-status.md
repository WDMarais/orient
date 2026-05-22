# orient status — behavioral spec

Part of [orient behavioral spec](spec.md).

`orient status` — canonical read-only state display. Fetches from upstream before
showing state; no pull, no push, no state written. Same output format and suppress
rules as sync; no transient delta indicators (those are sync-only).

**Freshness fast path**: `state.toml` stores `last_synced_at` per project alongside
`last_synced_hash`. If a project was synced within the freshness window (default: 60
min, configurable) AND local HEAD still matches `last_synced_hash`, status skips the
fetch for that project and shows local state (known-good, not stale). Outside the
window or HEAD diverged → fetch. Status is always conceptually canonical; the fast
path is an implementation detail.

**Post-MVP — declared-state registry**: an explicit `orient declare <project>` verb
records "this commit on this branch is the blessed canonical state" — distinct from
"orient happened to sync here." If local state diverges from the declared hash, status
surfaces it as a soft signal ("diverged from declared state — consider syncing or
updating declaration"). Auto-updated by sync at MVP; manual declare verb is post-MVP.

Post-MVP extension: status absorbs note-level state (current phase, open threads)
once LLM artifacts are machine-readable by the CLI. Not MVP scope.

## Freshness and fetch behaviour

```
orient status (project synced 20 min ago, local HEAD matches last_synced_hash)
  → uses local state (fast path — within freshness window, known-good)
  → no fetch

orient status (project synced 90 min ago — outside default 60 min window)
  → fetches from upstream first
  → shows post-fetch state

orient status (project synced 20 min ago, local HEAD differs from last_synced_hash)
  → HEAD diverged since last sync — fetches regardless of freshness window
  → shows post-fetch state

orient status --local (explicit local-only opt-in)
  → skips fetch for all projects regardless of freshness
  → footer on every run: "showing local remote-tracking refs — run orient status for current upstream data"
```

## Happy path

```
orient status (all repos clean, up-to-date)
  → 5 projects · all up-to-date

orient status (repo-A dirty, 3 files)
  → repo-A   main · dirty (3 files)

orient status (repo-B behind 2 — remote-tracking refs show this without network call)
  → repo-B   main · behind 2

orient status (repo-C ahead 1, push=false)
  → repo-C   main · ↑1 (push off)

orient status (repo-D on feat/cli, in sync with upstream/feat, +5/-3 v main)
  → repo-D   feat/cli · +5/-3 v main

orient status (repo-E, path not found)
  → repo-E   error — path not found: ~/coding-projects/missing
```

## Targeting

Same rules as sync: exact name match, explicit targeting always shows state,
not-found errors. No `--push` flag (read-only; push not applicable).

```
orient status re-owm (clean, up-to-date)
  → re-owm   main · clean · up-to-date
  # explicit targeting always shows state

orient status unknown-project
  → error: project "unknown-project" not found in workspace.toml
```

## Non-git units

```
orient status (vault, recently modified, no backup recorded)
  → working-notes   vault · modified 2d · consider backup

orient status (vault, not recently modified)
  → no output   # suppress; not touched
```

## First-run / missing config

```
orient status (no workspace.toml)
  → orient is not configured yet.
  →
  → To get started:
  →   orient config add-project <name> <path>
  →
  → Example:
  →   orient config add-project my-project ~/coding-projects/my-project --pinned
  →
  → This creates ~/.orient/workspace.toml and adds your first project.
```

## orient status --help

```
orient status --help
  → Usage: orient status [project ...]
  →
  → Displays current state of configured projects. No network calls; no pull or push.
  → Reads git status and remote-tracking refs from local filesystem.
  →
  → Targeting:
  →   orient status              all configured projects
  →   orient status re-owm       one project (exact name match; always shows state)
  →
  → Examples:
  →   orient status
  →   orient status re-owm agent-skills
```
