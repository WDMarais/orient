# orient — top-level and environment

Part of [orient behavioral spec](spec.md).

Human-facing by default. Output is readable, contextual, and UX-considered.
`--agent-friendly` (planned, not MVP) opts into strict schema, token compression, and
disambiguation-over-readability for automation contexts where humans aren't in the loop.
Applies to any command that produces output: sync, status, config show, brief.
LLMs spawning with orient context arrive knowing the surface and don't need discovery.

## orient (no subcommand)

```
orient
  → Usage: orient <command> [args]
  →
  → Commands:
  →   sync          Pull/push configured projects
  →   status        Show project state without syncing
  →   note          Capture an observation to NOTES.md
  →   config        Manage workspace.toml
  →   brief         Generate morning brief (Haiku)
  →   session-note  Write session note — checkpoint or close (Haiku)
  →
  → Config: ~/.orient/workspace.toml  (ORIENT_ROOT=~/.orient)
  →
  → Run "orient <command> --help" for command-specific help.

orient --help
  → same as orient (no subcommand)

orient --version
  → orient 0.1.0
```

## Critical environment errors (all commands)

```
orient sync (ANTHROPIC_API_KEY not set; command requires Haiku)
  → error: ANTHROPIC_API_KEY not set — required for orient brief and orient session-note
  → sync, status, config, and note do not require it

orient brief (ANTHROPIC_API_KEY set but invalid — API returns auth error)
  → error: Anthropic API authentication failed — check ANTHROPIC_API_KEY

orient sync (ORIENT_ROOT set but path does not exist)
  → error: ORIENT_ROOT path not found: /custom/path
  → create the directory or unset ORIENT_ROOT to use the default (~/.orient)
```
