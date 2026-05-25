# orient config — behavioral spec

Part of [orient behavioral spec](spec.md).

`orient config` — manages `workspace.toml` under `ORIENT_ROOT` (`~/.orient/` default).
Human edits TOML directly; config commands validate, display, and scaffold — never
act as a key-value setter. Help output is first-class: surfaces available options,
guardrails, and concrete examples co-located with each subcommand.

## orient config (no subcommand)

```
orient config
  → Available subcommands:
      validate     Lint workspace.toml — errors and warnings
      show         Display effective config with defaults resolved and paths expanded
      add-project  Scaffold a new [[projects]] entry
      path         Print the config file path

    Examples:
      orient config validate
      orient config add-project my-project ~/proj/my-project --pinned
      orient config show
      $EDITOR $(orient config path)

    Config: ~/.orient/workspace.toml  (ORIENT_ROOT=~/.orient)
```

## orient config validate

```
orient config validate (valid config, all paths exist)
  → OK — 4 projects, all paths valid

orient config validate (duplicate project name)
  → error: duplicate project name "re-owm" — appears at entries 1 and 3

orient config validate (project path not found)
  → warning: project "re-owm" — path not found: ~/proj/re-owm

orient config validate (unknown key in [[projects]] entry)
  → warning: unknown key "typo_key" in project "re-owm" — will be ignored

orient config validate (invalid activity_model value)
  → error: unknown activity_model "weekly" — valid values: recency

orient config validate (TOML syntax error)
  → error: TOML parse error at line 7: expected value, found newline

orient config validate (workspace.toml not found)
  → error: config not found: ~/.orient/workspace.toml
  → run "orient config add-project <name> <path>" to create it

orient config validate --json (valid)
  → {"ok": true, "errors": [], "warnings": []}

orient config validate --json (invalid)
  → {"ok": false, "errors": ["duplicate project name..."], "warnings": []}
  → exits non-zero
```

## orient config show

```
orient config show
  → ORIENT_ROOT: ~/.orient  (default)
  → Config:      ~/.orient/workspace.toml
  →
  → [defaults]
  →   note_root      = ~/.orient/notes
  →   push           = false
  →   active_days    = 14
  →   activity_model = recency
  →
  → Projects (4):
  →   re-owm         ~/proj/re-owm        pinned  push=false
  →   agent-skills   ~/proj/agent-skills          push=true
  →   working-notes  ~/proj/working-notes         push=true   vault
  →   orient         ~/proj/orient                push=false

orient config show --json
  → machine-readable effective config with all defaults resolved and paths expanded
```

## orient config add-project

```
orient config add-project re-owm ~/proj/re-owm
  → appended to ~/.orient/workspace.toml:
      [[projects]]
      name = "re-owm"
      path = "~/proj/re-owm"
  → project "re-owm" added

orient config add-project re-owm ~/proj/re-owm --push --pinned
  → appended:
      [[projects]]
      name   = "re-owm"
      path   = "~/proj/re-owm"
      push   = true
      pinned = true

orient config add-project re-owm ~/proj/re-owm (name already exists)
  → error: project "re-owm" already exists — edit workspace.toml directly to modify

orient config add-project re-owm ~/proj/nonexistent
  → error: path not found: ~/proj/nonexistent

orient config add-project re-owm ~/proj/re-owm (workspace.toml absent)
  → creates ~/.orient/workspace.toml with [defaults] block and the new [[projects]] entry
  → created ~/.orient/workspace.toml
  → project "re-owm" added
```

### orient config add-project --help

```
orient config add-project --help
  → Usage: orient config add-project <name> <path> [flags]
  →
  → Appends a [[projects]] entry to workspace.toml. Creates workspace.toml if absent.
  → Validates: name must be unique, path must exist on disk.
  →
  → Flags:
  →   --push      Enable push to upstream on sync (default: false)
  →   --pinned    Pin project — always surfaces in brief regardless of last-touched date
  →
  → Guardrails:
  →   Name must be unique across all configured projects.
  →   To modify an existing project, edit workspace.toml directly:
  →     $EDITOR $(orient config path)
  →
  → Examples:
  →   orient config add-project re-owm ~/proj/re-owm
  →   orient config add-project working-notes ~/notes --push --pinned
```

## orient config path

```
orient config path
  → ~/.orient/workspace.toml

orient config path (ORIENT_ROOT set to custom path)
  → /custom/path/workspace.toml

orient config path (config not yet created)
  → ~/.orient/workspace.toml  (not yet created)
```
