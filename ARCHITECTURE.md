# Architecture

## Module layout

```
orient/
├── __init__.py
├── __main__.py          # entry point: python -m orient
├── cli.py               # Typer app — all subcommands; terminal node
├── config.py            # workspace.toml management; ProjectEntry, EffectiveConfig, ValidationResult
├── state.py             # state.toml management; ProjectState
├── note.py              # NOTES.md append/parse; NoteEntry, infer_tag
├── status.py            # compute_status, should_fetch, StatusResult
├── sync.py              # sync_project, sync_all, SyncResult
├── preflight.py         # run_preflight, PreflightResult
├── session_note.py      # parse_note, run_session_note, ParsedNote, SessionSection
├── brief.py             # build_preflight_token, get_next_action, run_brief, BriefFrontmatter
└── lib/
    ├── __init__.py
    ├── note_parser.py   # fork of agent-skills/lib/note_parser.py  (~5 line changes)
    └── preflight.py     # fork of agent-skills/lib/session_close_preflight.py (~3 line changes)

tests/
├── conftest.py
├── test_config.py
├── test_state.py        # not yet written — state.toml schema tests
├── test_note.py
├── test_status.py
├── test_sync.py
├── test_brief.py
└── test_session_note.py
```

## Shared types

No dedicated `types.py` module. Each type lives in the module that owns it:

| Type | Module | Consumed by |
|---|---|---|
| `ProjectEntry` | `orient.config` | sync, status, note, brief, session_note, cli |
| `EffectiveConfig` | `orient.config` | cli |
| `ValidationResult` | `orient.config` | cli |
| `DefaultsConfig` | `orient.config` | cli, brief |
| `ProjectState` | `orient.state` | sync, status, preflight |
| `NoteEntry` | `orient.note` | brief (notes_since_last_brief) |
| `SyncResult` | `orient.sync` | cli |
| `StatusResult` | `orient.status` | cli |
| `PreflightResult` | `orient.preflight` | session_note, cli |
| `ParsedNote` | `orient.session_note` | (tests, cli) |
| `SessionSection` | `orient.session_note` | brief (phase extraction) |
| `TopicPreflight` | `orient.brief` | (internal to brief) |
| `PreflightToken` | `orient.brief` | (internal to brief) |
| `TopicAction` | `orient.brief` | cli |
| `BriefFrontmatter` | `orient.brief` | cli |

## Implementation order (DAG)

1. `orient.lib.note_parser` — leaf; fork, ~5 line changes; unblocks brief + session_note
2. `orient.lib.preflight` — leaf; fork, ~3 line changes; unblocks orient.preflight
3. `orient.config` — leaf (tomllib + Pydantic only); unblocks everything else
4. `orient.state` — depends on (3); unblocks status, sync, preflight
5. `orient.note` — depends on (3); unblocks sync, brief
6. `orient.status` — depends on (3), (4); parallel with (7)
7. `orient.sync` — depends on (3), (4), (5); parallel with (6)
8. `orient.preflight` — depends on (2), (3), (4)
9. `orient.session_note` — depends on (1), (8); parallel with (10)
10. `orient.brief` — depends on (1), (3), (4), (5); parallel with (9)
11. `orient.cli` — terminal; depends on all

## Per-module interface

---

### orient.lib.note_parser

Fork of `agent-skills/lib/note_parser.py`. Rename `ticket` → `topic`; resolve note root
from `ORIENT_ROOT/notes` instead of `NOTE_ROOT` env var.

```python
def parse_sections(text: str) -> dict[str, str]
    # Split markdown into {section_name: content} for each ## heading.

def extract_section(text: str, section: str) -> Optional[str]
    # Return content of a single named ## section; None if absent.

def count_bullets(section_text: str) -> int
    # Count "- item" lines in a section body.

def parse_bullets(section_text: str) -> list[str]
    # Return each "- item" stripped of the leading "- ".

def parse_kv_bullets(section_text: str) -> dict[str, str]
    # Parse "- key: value" lines → {"key": "value"}.
    # Used for ## Session extraction (reason, phase, model, etc.).

def find_latest_note(note_root: Path, project: str, topic: str) -> Optional[Path]
    # Return most recent YYYY-MM-DD.md under note_root/project/topic/, or None.
```

Spec gaps: none blocking this module.

---

### orient.lib.preflight

Fork of `agent-skills/lib/session_close_preflight.py`. Rename `ticket` → `topic`;
resolve note root from `orient_root / "notes"` rather than `NOTE_ROOT` env var directly.
Adapt from CLI script to callable function returning a raw routing dict consumed by
`orient.preflight`.

```python
def route(
    project: str,
    topic: str,
    mode: str,          # "checkpoint" | "close"
    note_root: Path,
) -> dict[str, Any]
    # Returns routing dict with keys: mode, prev_path, pending_count, deferred_count,
    # append_line, append_pass, error. orient.preflight wraps this into PreflightResult.
```

Design decision: the original agent-skills script outputs line tokens to stdout (for
PostToolUse hook consumption). This fork converts to a Python-native function return.
No subprocess boundary — orient.preflight calls route() directly.

Spec gaps: none blocking this module.

---

### orient.config

Pydantic models + tomllib reads + tomli-w writes.

```python
# --- Types ---

class ActivityModel(str, Enum):
    recency = "recency"

class UnitType(str, Enum):
    git = "git"
    vault = "vault"

class ProjectEntry(BaseModel):
    name: str
    path: str               # tilde-expanded to absolute at parse time (see Gap: tilde expansion)
    push: bool = False
    pinned: bool = False
    unit_type: UnitType = UnitType.git
    auto_commit: bool = False
    side_branch: bool = False
    suggest_backup: bool = True

class DefaultsConfig(BaseModel):
    note_root: str = ""     # derived from orient_root / "notes" if absent
    push: bool = False
    active_days: int = 14
    activity_model: ActivityModel = ActivityModel.recency
    freshness_window: int = 60   # minutes; drives status freshness fast path

class EffectiveConfig(BaseModel):
    orient_root: str
    config_path: str
    defaults: DefaultsConfig
    projects: list[ProjectEntry]

@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

# --- Functions ---

def validate_workspace(workspace_path: Path) -> ValidationResult
    # Errors: duplicate name, invalid activity_model, TOML syntax error, file not found.
    # Warnings: path not found on disk, unknown key in [[projects]] entry.

def load_effective_config(orient_root: Path) -> EffectiveConfig
    # Parses workspace.toml; applies defaults; expands tildes in all project paths.
    # Raises with first-run guidance message if workspace.toml absent.

def add_project_entry(
    workspace_path: Path,
    name: str,
    path: str,
    push: bool = False,
    pinned: bool = False,
) -> None
    # Appends [[projects]] entry. Creates workspace.toml with [defaults] block if absent.
    # Validates: name unique, path exists on disk (after tilde expansion).
    # Does not validate activity_model or other existing entries — that is validate_workspace's job.

def config_path(orient_root: Path) -> Path
    # Returns orient_root / "workspace.toml". Pure computation — no I/O.
```

Design decisions:
- Tilde expansion at parse time: `Path(raw_path).expanduser().resolve()`. Stored path in
  TOML may contain `~`; EffectiveConfig always contains absolute paths.
- `ValidationResult.ok` is False only on errors; warnings leave ok=True.
- `add_project_entry` creates workspace.toml with a canonical `[defaults]` block when
  absent — not a minimal file. This ensures `config show` always has a complete view.

Spec gaps:
- `freshness_window` is not in the existing `make_workspace` conftest helper; the helper
  will need updating to emit it when non-default tests require it. Not a blocker.

---

### orient.state

tomllib reads; tomli-w writes; atomic write pattern (tmp → rename).

```python
@dataclass
class ProjectState:
    last_synced_hash: str   # git repo: commit SHA; vault: "mtime:<ISO-8601>"
    last_synced_at: str     # ISO-8601 timestamp of last successful sync

def load_state(orient_root: Path) -> dict[str, ProjectState]
    # Reads state.toml; returns {} if file absent (first run).
    # Falls back to .state.toml.bak if primary is corrupt; surfaces alarm if both fail.

def save_state(orient_root: Path, states: dict[str, ProjectState]) -> None
    # Writes atomically: write to state.toml.tmp, rename over state.toml.
    # Keeps state.toml.bak as single backup (copy before rename).

def update_project_state(orient_root: Path, project_name: str, state: ProjectState) -> None
    # Load → patch one entry → save. Used after each sync/status operation.
```

state.toml schema:
```toml
[project.re-owm]
last_synced_hash = "abc123def456..."
last_synced_at   = "2026-05-24T10:00:00+00:00"

[project.working-notes]
last_synced_hash = "mtime:2026-05-24T09:30:00+00:00"
last_synced_at   = "2026-05-24T09:30:00+00:00"
```

Design decisions:
- Single-backup MVP. Non-breaking extension to 6-snapshot rolling buffer post-MVP
  (save_state signature is stable; buffer management is internal).
- Vault mtime hash format: `"mtime:<ISO-8601>"` — deterministic, human-readable,
  sortable. "Modified" = current mtime of vault directory ≠ stored mtime value.

Spec gaps: none blocking this module.

---

### orient.note

```python
@dataclass
class NoteEntry:
    date: str   # YYYY-MM-DD
    time: str   # HH:MM
    tag: str    # project name or "untagged"
    text: str

def append_note(text: str, cwd: Path, orient_root: Path) -> NoteEntry
    # Infers tag, formats entry, appends to NOTES.md (creates if absent).
    # Raises with "cannot write to ~/.orient/NOTES.md — check permissions" if unwritable.
    # text="" raises with "note text cannot be empty".

def infer_tag(cwd: Path, configs: list[ProjectEntry]) -> str
    # Returns project name if cwd is at or under a configured project path; else "untagged".
    # Exact path prefix match (Path.is_relative_to). First match wins; configs in order.

def parse_notes_md(path: Path) -> list[NoteEntry]
    # Parses NOTES.md line-by-line. Each line: "YYYY-MM-DD HH:MM  [tag]  text".
    # Returns entries in file order. Skips malformed lines silently.
```

Internal:
```python
def _format_entry(entry: NoteEntry) -> str
    # "YYYY-MM-DD HH:MM  [tag]  text\n"  (two spaces between each field)
```

Spec gaps:
- Auto-append triggers beyond "no upstream configured" are not specified for MVP.
  `orient.sync` calls `append_note()` for the documented trigger; others added as needed.

---

### orient.status

```python
@dataclass
class StatusResult:
    name: str
    branch: str = "main"
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    dirty_count: int = 0
    diverged: bool = False
    error: Optional[str] = None
    suppressed: bool = False
    fetched: bool = False          # True if a network fetch was performed this run
    ahead_of_base: int = 0         # commits feat branch is ahead of default branch
    behind_of_base: int = 0        # commits feat branch is behind default branch
    modified: bool = False         # vault: directory mtime changed since last_synced_hash
    backup_recent: bool = False    # vault: backup recorded as recent

def compute_status(
    config: ProjectEntry,
    prior_state: Optional[ProjectState] = None,
    local_only: bool = False,
    freshness_window_minutes: int = 60,
) -> StatusResult
    # local_only=True: skip fetch, set fetched=False always.
    # Suppression: suppressed=True when all of: not dirty, ahead==0, behind==0,
    #   not diverged, not modified, no error. Explicit targeting overrides this in cli.py.

def should_fetch(
    prior_state: Optional[ProjectState],
    current_head: str,
    freshness_window_minutes: int = 60,
) -> bool
    # True if: no prior state, OR outside freshness window, OR HEAD differs from stored hash.
    # Pure predicate — no I/O.
```

Design decisions:
- `ahead_of_base` / `behind_of_base` field names are settled here. Status and sync both
  use the same names (StatusResult and SyncResult are kept separate despite shared fields).
- `compute_status` does not write state — it is read-only. State writes belong to sync.

Spec gaps: none blocking this module.

---

### orient.sync

```python
@dataclass
class SyncResult:
    name: str
    branch: str = "main"
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    dirty_count: int = 0
    pushed: bool = False
    diverged: bool = False
    error: Optional[str] = None
    suppressed: bool = False
    modified: bool = False
    backup_recent: bool = False
    auto_commit_message: Optional[str] = None   # set when auto_commit=True facilitation ran
    side_branch_name: Optional[str] = None       # set when side_branch=True facilitation ran
    ahead_of_base: int = 0
    behind_of_base: int = 0

def sync_project(
    config: ProjectEntry,
    prior_state: Optional[ProjectState] = None,
    push_override: bool = False,
    orient_root: Optional[Path] = None,
) -> SyncResult
    # orient_root required for auto-append to NOTES.md (no-upstream-configured trigger).
    # push_override promotes feat/sidecar branches only — never overrides push=False on default branch.

def sync_all(
    configs: list[ProjectEntry],
    prior_states: dict[str, ProjectState],
    push_override: bool = False,
    orient_root: Optional[Path] = None,
) -> list[SyncResult]
    # Runs sync_project in parallel via ThreadPoolExecutor.
    # One project's error does not cancel others.
    # Results returned in config order (not completion order).
```

Design decisions:
- `auto_commit_message` and `side_branch_name` remain on SyncResult (no separate
  FacilitationResult). They're Optional and only set when the facilitation path ran.
- `push_override=True` on default branch: result is `pushed=False`; rendering shows
  `(push off — update config to push default branch)`.
- Vault "modified" detection: compare current directory mtime against
  `prior_state.last_synced_hash` (format: `"mtime:<ISO>"`).

Spec gaps:
- Exact vault backup recency detection ("backup_recent") mechanism is not specified.
  Implementation decision: treat `backup_recent=True` when `prior_state` has a recent
  `last_synced_at` AND `last_synced_hash` matches current mtime (vault was touched but
  a sync already recorded it as up-to-date). Revisit if backup tooling evolves.

---

### orient.preflight

Wraps `orient.lib.preflight.route()` into the public API.

```python
@dataclass
class PreflightResult:
    mode: str               # "new" | "append" | "no-prev" | "ambiguous" | "error:<detail>"
    prev_path: Optional[str] = None
    pending_count: int = 0
    deferred_count: int = 0
    append_line: Optional[int] = None   # line number to append after (for append mode)
    append_pass: Optional[int] = None   # checkpoint count for today
    error: Optional[str] = None         # human-readable detail for ambiguous/error modes

def run_preflight(
    project: str,
    topic: str,
    mode: str,              # "checkpoint" | "close"
    orient_root: Path,
) -> PreflightResult
```

Ambiguous mode sub-cases (communicated via `error` field, `mode="ambiguous"`):
- `"unexpectedly-empty"` — note directory exists but contains zero `.md` files
- `"multiple-today:<n>"` — n > 1 files dated today; surface count, suggest manual synthesis
- `"unrecognised"` — other unexpected filesystem state

Error modes (`mode="error:<detail>"`):
- `"error:no-note-dir path:<path>"` — note directory not writable or cannot be created

Spec gaps: none blocking this module.

---

### orient.session_note

```python
@dataclass
class SessionSection:
    reason: str                             # "natural-end"|"budget-hit"|"context-limit"|"human-stepped-away"
    phase: str = ""                         # pipeline stage at close; required (Convention K)
    recommended_next_phase: Optional[str] = None  # overrides lookup table in brief if set
    cost: Optional[str] = None
    duration: Optional[str] = None
    model: str = "haiku"                    # hardcoded at MVP

@dataclass
class ParsedNote:
    date: str
    topic: str                              # "project/topic"
    goal: Optional[str] = None
    shipped: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    session: Optional[SessionSection] = None
    checkpoint_count: int = 0

def parse_note(path: Path) -> ParsedNote
    # Parses a session note file using orient.lib.note_parser.
    # checkpoint_count = number of "### Checkpoint" headings found.
    # session is None if ## Session section is absent (checkpoint notes).

def run_session_note(
    project: str,
    topic: str,
    mode: str,                              # "checkpoint" | "close"
    orient_root: Path,
    reason: str = "natural-end",
    client: Optional[anthropic.Anthropic] = None,  # injectable; defaults to anthropic.Anthropic()
) -> None
    # 1. Calls run_preflight() to get routing token.
    # 2. On ambiguous/error: surfaces message to stdout, exits non-zero; does not proceed.
    # 3. Builds Haiku prompt with preflight token + rollforward content.
    # 4. Calls Haiku via client; writes note to disk.
    # 5. Close mode only: appends ## Session block; sweeps for NOTES.md items.
    # Note: orient_root / "notes" / project / topic / YYYY-MM-DD.md is the note path.
```

Design decisions:
- `run_session_note` accepts an injectable `client` for test isolation. Tests pass a
  `StubHaikuClient` that returns a deterministic note body (enabling sweep logic tests).
- `## Session` format (updated from spec to include phase fields):
  ```
  - reason: natural-end
  - phase: harness-writer-complete
  - recommended_next_phase: case-interviewer   ← omit if not set
  - cost: ~$0.42 (estimated)
  - duration: ~2h
  - model: haiku
  ```
- CLI arg shape: `orient session-note <mode> <project> <topic> [reason:<reason>]`
  (positional args; reason is optional trailing positional).

Spec gaps:
- `TestNotesSweep.test_close_appends_flagged_items_to_notes_md`: Haiku-driven; tested
  via StubHaikuClient returning deterministic sweep output. The Haiku judgment about
  what to flag is not asserted — only the parsing and write path.
- `test_ambiguous_mode`: ambiguous trigger is now defined (see preflight module above);
  fixture can manufacture `multiple-today` state by creating two note files.
- `test_unrecognised_preflight_output`: invariant documented in test; no injection
  mechanism. Stays as documentation.

---

### orient.brief

```python
@dataclass
class TopicPreflight:
    topic: str                              # "project/topic"
    note_path: str
    phase: str
    recommended_next_phase: Optional[str] = None
    pending: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)

@dataclass
class PreflightToken:
    last_brief: str                         # YYYY-MM-DD
    active_topics: int
    topics: list[TopicPreflight]
    notes_since_last_brief: list[str]       # raw NoteEntry text lines

@dataclass
class TopicAction:
    topic: str
    phase: str
    skill: str
    invocation: str
    priority: int

@dataclass
class BriefFrontmatter:
    date: str
    last_brief: str
    active_topics: int
    next_actions: list[TopicAction]
    notes_unreviewed: int

# Phase → next_action lookup table (mechanical; no reasoning)
_PHASE_TABLE: dict[str, tuple[str, str]] = {
    "case-interviewer-in-progress":   ("case-interviewer",    "continue /case-interviewer"),
    "case-interviewer-complete":      ("harness-writer",      "/harness-writer {project} {topic}"),
    "harness-writer-complete":        ("architecture-proposer", "/architecture-proposer {project} {topic}"),
    "architecture-proposer-complete": ("implementation-writer", "/implementation-writer {project} {topic}"),
    "implementation-writer-in-progress": ("implementation-writer", "continue /implementation-writer"),
    "implementation-writer-complete": ("verify",              "/verify → /session-closer"),
}

def build_preflight_token(
    orient_root: Path,
    last_brief_date: Optional[str] = None,
    active_days: int = 14,
) -> PreflightToken
    # Two-pass extraction:
    # 1. Structural pass: find latest note per topic; extract phase, pending count, deferred count.
    # 2. Content pass: extract ## Pending and ## Deferred verbatim; filter NOTES.md by date.
    # Active topics: projects with notes touched within active_days, OR pinned=True.
    # Pinned + no notes: included with phase="no-notes".

def get_next_action(
    phase: str,
    project: str,
    topic: str,
    recommended_next_phase: Optional[str] = None,
) -> TopicAction
    # recommended_next_phase overrides _PHASE_TABLE lookup if set.
    # Unknown phase: skill="unknown", invocation="open <note-path> to orient, then choose next stage".

def parse_brief_frontmatter(brief_path: Path) -> BriefFrontmatter
    # Parses YAML frontmatter block (between opening and closing ---).
    # next_actions deserialized as list[TopicAction].

def run_brief(
    orient_root: Path,
    client: Optional[anthropic.Anthropic] = None,  # injectable; defaults to anthropic.Anthropic()
) -> None
    # 1. Calls build_preflight_token().
    # 2. Builds Haiku prompt with token.
    # 3. Calls Haiku via client; writes morning-brief.md (overwrites if exists).
    # 4. Prints prose section to stdout (content after closing ---).
    # 5. Updates state: last_brief date in state.toml after successful write.
```

Design decisions:
- Priority ordering in `next_actions`: phase-transition topics first (priority 1+),
  in-progress topics second, deferred-heavy third. `get_next_action` assigns priority
  based on phase category; `run_brief` sorts by priority before writing frontmatter.
- `run_brief` accepts injectable `client` for test isolation (same pattern as session_note).
- `recommended_next_phase` is surfaced to Haiku in the preflight token; `get_next_action`
  uses it to override the mechanical lookup table. Haiku does not reason about it — the
  override is communicated verbatim.

Spec gaps:
- `test_stdout_shows_prose_not_frontmatter`: assertion is loose (`"---" not in output`).
  Tighten during CLI implementation by asserting output starts after the closing `---\n`.

---

### orient.cli

Typer app. All user-facing error messages and rendering live here. Modules return typed
result objects; cli.py converts them to Rich output.

```python
app: typer.Typer   # root app

# Subcommands registered on app:
# sync, status, note, brief, session-note
# config is a Typer sub-app with: validate, show, add-project, path

# CLI arg shape for session-note:
# orient session-note <mode> <project> <topic> [reason:<reason>]
# mode: "checkpoint" | "close"
```

Design decisions:
- `ORIENT_ROOT` env var resolved once at command invocation; passed down to all module
  calls. Default: `~/.orient`.
- Explicit project targeting (sync/status): when project names are given as positional
  args, `suppressed=True` results are still shown (override suppression). cli.py handles
  this — modules do not know about targeting.
- All-suppressed path: cli.py counts suppressed results; if all suppressed, prints
  `"N projects · all up-to-date"` + pointer to `morning-brief.md`.
- Rich table/panel rendering: one row per unsuppressed project. Column alignment handled
  by Rich.
- `ANTHROPIC_API_KEY` checked at invocation time for brief and session-note; friendly
  error if absent.

Spec gaps:
- `orient --version` value: `"orient 0.1.0"`. Derive from `pyproject.toml` via
  `importlib.metadata.version("orient")` at runtime.

---

## Deferred test concerns

- `test_session_note.py:TestNotesSweep.test_close_appends_flagged_items_to_notes_md` —
  Haiku-driven content; tested via StubHaikuClient. The `assert False` body must be
  replaced with a proper stub-based test during implementation. Not a blocker for other
  modules.

- `test_session_note.py:TestPreflightEdgeCases.test_ambiguous_mode` — ambiguous trigger
  is now defined (`multiple-today`); fixture can manufacture it. Wire up during
  orient.preflight implementation.

- `test_session_note.py:TestPreflightEdgeCases.test_unrecognised_preflight_output` —
  no injection mechanism. Documents invariant; acceptable.

- `test_brief.py:TestCliOutput.test_stdout_shows_prose_not_frontmatter` — assertion is
  loose. Tighten during orient.cli implementation.

## Pre-implementation decisions

None. All gaps resolved above.

## Tracer bullet recommendation

Not warranted. Every module seam is explicitly typed and covered by tests. The one
non-deterministic seam (Python → Haiku → morning-brief.md and session notes) is validated
structurally via `BriefFrontmatter` assertions and the injectable client pattern —
the right mitigation without requiring end-to-end Haiku calls in CI.

Note for implementation-writer: AI agents have a strong pull toward horizontal layering
(completing one module fully before touching the next). The DAG above has genuine
parallelism at steps 6/7 and 9/10 — resist the urge to treat them sequentially.
