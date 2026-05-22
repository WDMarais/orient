# orient note — behavioral spec

Part of [orient behavioral spec](spec.md).

`orient note "<text>"` — appends a timestamped observation to `~/.orient/NOTES.md`.
Infers project tag from cwd if inside a configured project path; falls back to
`[untagged]`. Orient itself auto-appends soft observations during operations
(conditions worth noting that don't rise to errors or warnings).

Brief surfaces "N notes since last brief" as a low-priority item.
NOTES.md is raw/verbatim — not LLM-synthesized.

## Happy path

```
orient note "preflight exits 0 even when note dir is unwritable"
  (cwd: ~/coding-projects/orient/ — matches configured project "orient")
  → appended to ~/.orient/NOTES.md:
    2026-05-22 14:30  [orient]  preflight exits 0 even when note dir is unwritable

orient note "sync stalled on unreachable remote, no timeout shown"
  (cwd: ~/some/unrelated/path — no configured project match)
  → appended to ~/.orient/NOTES.md:
    2026-05-22 14:31  [untagged]  sync stalled on unreachable remote, no timeout shown
```

## Auto-append (orient-generated observations)

Orient appends soft observations during operations — conditions worth tracking that
don't rise to errors or warnings. The inline output is subtle; NOTES.md is the
durable record.

```
orient sync (repo has no upstream configured)
  → appends: 2026-05-22 14:32  [re-owm]  no upstream configured
  → inline during sync output: "observation logged → ~/.orient/NOTES.md"
```

## Edge cases

```
orient note "text" (NOTES.md does not exist)
  → creates ~/.orient/NOTES.md
  → appends entry

orient note "" (empty string)
  → error: note text cannot be empty

orient note "text" (ORIENT_ROOT not writable)
  → error: cannot write to ~/.orient/NOTES.md — check permissions
```

## orient note --help

```
orient note --help
  → Usage: orient note "<text>"
  →
  → Appends a timestamped observation to ~/.orient/NOTES.md.
  → Project tag inferred from current directory; [untagged] if outside a configured project.
  → Notes are surfaced in orient brief as low-priority items; reviewed and resolved manually.
  →
  → Examples:
  →   orient note "sync blocked on dirty repo — check stash state"
  →   orient note "brief missed re-owm — check active_days threshold"
```
