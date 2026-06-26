# orient diff — behavioral spec

Part of [orient behavioral spec](spec.md).

Persist and compare a topic's diffs over time. Generic, ZDR-safe (zero API),
**source-agnostic**. A utility, not a lifecycle edge — callable any time.

## Why

A live `git diff` only answers "what does the change look like *now*." It cannot answer
"what changed since my last review pass" or "reconstruct the diff as it stood at pass 1."
A topic accumulates **diff snapshots** so both are cheap. The headline case is multi-pass
review of someone else's PR: snapshot each pass, then compare consecutive snapshots.

## The seam (why a command, not a skill)

The diff portion of an external `pr-context.md` is mechanical *and* locally
reconstructable (the worktree already has the branch), so re-fetching it from a remote is
redundant. `orient diff` takes a diff as **input** and never learns where it came from:

- now: `git diff <base>...<head> | orient diff snapshot <project> <topic>`
- later: `owm diff <ticket> | orient diff snapshot <project> <topic>` — an external tool
  reconstructs the diff from the worktree; orient and every consumer are unchanged.

The contract is **"a unified diff arrives on stdin."** The source upgrading (hand →
`owm diff` → any other producer) never retools the command or its consumers. ZDR-clean by
construction: no API, no host Skills feature.

## Storage

```
notes/<project>/<topic>/diffs/<YYYY-MM-DDThhmmss>[__<label>].diff
```

- timestamp = capture time; lexicographic order == chronological order, so "latest" is the
  greatest filename — no symlink pointer to go stale in the synced tree.
- optional `--label <slug>` for the pass / PR / repo (`__pass2`, `__myproject-config`) —
  needed because one ticket can span repos, so the caller can snapshot each repo's diff
  under one topic.
- the diff lives here, **not inline** in `pr-context.md`; the metadata doc references the
  latest snapshot, keeping itself small.

## Commands

```
orient diff snapshot <project> <topic>
  → read a unified diff on stdin (or --from-file <path>); persist it timestamped
  → dedup: byte-identical to current latest → write nothing,
      print "no change since <ts>", exit 0   (--allow-dup overrides)
  → empty stdin → no-op, "no diff on stdin — nothing captured", exit 0 (not an error)
  → prints the snapshot path written

orient diff list <project> <topic>
  → snapshots oldest→newest: "<ts>  <label>  <N files> (+a -r)"  (stat derived on the fly)
  → none → "no diff snapshots for <project>/<topic>"

orient diff compare <project> <topic> [<a> [<b>]]
  → diff two snapshots, print the result
  → no args  → two latest  (== "what changed since my last pass")
  → one arg  → <a> vs latest
  → two args → <a> vs <b>
  → selectors: full filename | timestamp prefix | -N (Nth from latest)
  → fewer than 2 snapshots → clear message, exit 0
```

`snapshot` is kept an explicit verb so a snapshot is never written by accident.

## ZDR / emit-only

Pure filesystem + stdin; zero Anthropic calls in any mode. This is the entire reason the
diff producer is a command and not a skill — it runs in the ZDR work venue with no
asterisks.

## Relationship to existing artifacts

- `pr-context.md` — still externally produced; **orient only reads it** (invariant from
  spec-session-note.md intact). Its `## Full diff` section becomes a pointer to
  `diffs/<latest>` rather than an inline dump.
- `context.md` and the `## Open threads` sync (session close) — untouched.
- self-contained-note / rollforward invariant — unaffected; snapshots are auxiliary,
  re-derivable from their source.

## Out of scope

- *Producing* the diff (git / `owm diff` / a remote) — that is the caller's job; orient
  consumes diff text.
- Fetching PR description / open threads — externally produced, remote-specific.
- Ticket → (project, topic) resolution — only bites once an automated source feeds the
  command; not orient's concern (must not leak ticket/instance vocab into orient).
