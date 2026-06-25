# Architecture

## Module layout

```
orient/
├── __init__.py
├── cli.py               # Typer app — all subcommands; terminal node (entry point: `orient` console script)
├── paths.py             # canonical ORIENT_ROOT layout: notes_root, topic_dir
├── config.py            # workspace.toml management; ProjectEntry, EffectiveConfig, ValidationResult
├── state.py             # state.toml management; ProjectState
├── note.py              # NOTES.md append/parse; NoteEntry, infer_tag
├── status.py            # compute_status, should_fetch, StatusResult
├── sync.py              # sync_project, sync_all, SyncResult
├── preflight.py         # run_preflight, PreflightResult
├── session_note.py      # parse_note, run_session_note, ParsedNote, SessionSection
├── brief.py             # build_preflight_token, get_next_action, run_brief, BriefFrontmatter
├── day_close.py         # aggregate_day, serialize_marker, run_day_close, DayMarker
├── llm.py               # LLMClient Protocol, AnthropicClient, CommandClient, get_llm_client
├── skill.py             # parse_skill, discover_skills, resolve_skill, assemble_skill, run_skill_show, Skill
├── skills/              # native SKILL.md bodies (package data): day-starter, session-closer, dev-pipeline, ...
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
├── test_day_close.py
├── test_session_note.py
├── test_llm.py
└── test_skill.py
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
| `LLMClient` | `orient.llm` | brief, cli (Protocol; type of the injected client) |
| `LLMConfig` | `orient.config` | llm, cli |
| `Skill` | `orient.skill` | cli |
| `SkillKind` | `orient.skill` | (internal to skill) |
| `SkillsConfig` | `orient.config` | skill, cli |
| `SkillOverride` | `orient.config` | skill, cli |

## Implementation order (DAG)

1. `orient.lib.note_parser` — leaf; fork, ~5 line changes; unblocks brief + session_note
2. `orient.lib.preflight` — leaf; fork, ~3 line changes; unblocks orient.preflight
3. `orient.config` — leaf (tomllib + Pydantic only); unblocks everything else
4. `orient.state` — depends on (3); unblocks status, sync, preflight
5. `orient.note` — depends on (3); unblocks sync, brief
6. `orient.status` — depends on (3), (4); parallel with (7)
7. `orient.sync` — depends on (3), (4), (5); parallel with (6)
8. `orient.preflight` — depends on (2), (3), (4)
9. `orient.llm` — depends on (3) [config: `LLMConfig`]; leaf otherwise; unblocks brief
10. `orient.session_note` — depends on (1), (8); parallel with (11)
11. `orient.brief` — depends on (1), (3), (4), (5), (9); parallel with (10)
12. `orient.skill` — depends on (3) [config: `[skills]` section], (11) brief, and
    `day_close`; imports their token builders for day-tier lifecycle context. No longer
    depends on preflight/session_note (session-tier context comes from the paired command)
13. `orient.cli` — terminal; depends on all

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

class SkillOverride(BaseModel):
    name: str
    kind: Optional[str] = None       # "native"|"external"; inferred from location if absent
    extends: Optional[str] = None    # native base name, for an overlay skill

class SkillsConfig(BaseModel):
    paths: list[str] = []            # search roots for external SKILL.md (tilde-expanded)
    overrides: list[SkillOverride] = []

class EffectiveConfig(BaseModel):
    orient_root: str
    config_path: str
    defaults: DefaultsConfig
    projects: list[ProjectEntry]
    skills: SkillsConfig = SkillsConfig()   # parsed from [skills] table; empty if absent

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
    # Parses [skills] table (paths + [[skills.override]]) into SkillsConfig; tilde-expands paths.
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

### orient.llm

```python
@runtime_checkable
class LLMClient(Protocol):
    def complete(self, prompt: str, *, max_tokens: int = 512,
                 model: Optional[str] = None) -> str: ...

class AnthropicClient:        # wraps anthropic.Anthropic().messages.create
    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None
    def complete(self, prompt, *, max_tokens=512, model=None) -> str

class CommandClient:          # shells argv (e.g. ["claude","-p"]); prompt→stdin, stdout→return
    def __init__(self, argv: list[str], timeout: int = 120) -> None  # empty argv → ValueError
    def complete(self, prompt, *, max_tokens=512, model=None) -> str  # rc!=0 → RuntimeError

def get_llm_client(config: LLMConfig, *, zdr: bool = False) -> Optional[LLMClient]
    # None (no client constructed, API unreachable) when:
    #   - zdr is True, or ORIENT_NO_API is set;
    #   - provider == "none";
    #   - provider resolves to anthropic but ANTHROPIC_API_KEY is absent.
    # provider "auto" (default): AnthropicClient if key else None (preserves legacy behavior).
    # provider "command": CommandClient(config.command, config.timeout).
```

Design decisions:
- `Protocol` + concrete adapters = the Strategy pattern. A new provider (Gemini,
  Codex, …) is one adapter class + one branch in `get_llm_client`; no caller changes.
  Not pre-built — YAGNI until a second provider is actually needed.
- The factory is the only place that reads env/ZDR state, so callers stay pure: they
  receive a client or None and branch on that alone. This is the ZDR seam made literal
  — in `--zdr`/`ORIENT_NO_API` mode no client is even constructed, so the process is
  provably API-silent (cf. spec-skill.md ZDR invariant).
- `LLMConfig` lives in `orient.config` (the `[llm]` table); `orient.llm` imports it,
  keeping config the single Pydantic schema owner.

Spec gaps: none. (Parked, separate design pass: promoting the provider-agnostic
artifact boundary to a first-class emitted datastructure for external orchestration —
see project memory.)

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
) -> None
    # 1. Calls run_preflight() to get routing token.
    # 2. On ambiguous/error: surfaces message to stdout, exits non-zero; does not proceed.
    # 3. Scaffolds a skeleton note (rolled-forward Pending/Deferred) and prints the
    #    path + context for the in-conversation LLM to fill. Mechanical — NO Haiku.
    # 4. Close mode only: appends ## Session block skeleton; the NOTES.md sweep is the
    #    in-conversation session's job (it has the context), not a here-and-now API call.
    # 5. Close mode only: _sync_open_threads() mirrors pr-context.md's ## Open threads
    #    into context.md (touch-only that section; idempotent; no-op if absent).
    # Note: paths.topic_dir(orient_root, project, topic) / YYYY-MM-DD.md is the note path.

def _sync_open_threads(topic_dir: Path) -> None
    # Deterministic, filesystem-only. Copies the ## Open threads block from
    # topic_dir/pr-context.md into topic_dir/context.md via _section_block /
    # _replace_or_append_section. Creates context.md if absent; preserves its other
    # sections. Silent no-op when pr-context.md is absent or has no such section.
```

Design decisions:
- `run_session_note` is fully mechanical and client-free: session edges scaffold and
  emit context for the live (already-running, ZDR-compliant) session to act on, rather
  than making their own API call. Only the day edges (`run_brief`, day-close) take an
  optional `LLMClient` for prose. This keeps the session tier provably API-silent.
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
    client: Optional[LLMClient] = None,  # injected by cli via llm.get_llm_client; None → fallback
) -> None
    # 1. Archive check: if morning-brief.md exists and its date: frontmatter is not today,
    #    move it to morning-briefs/<date-from-frontmatter>.md (create morning-briefs/ if absent).
    #    Frontmatter date unreadable: fall back to file mtime, warn inline, proceed.
    #    Same-day re-run: skip archive, overwrite in-place.
    # 2. Calls build_preflight_token().
    # 3. Builds prose prompt with token.
    # 4. If client is not None: client.complete(prompt) for prose; else deterministic
    #    fallback prose (no API). Writes morning-brief.md either way.
    # 5. Prints prose section to stdout (content after closing ---).
    # 6. Updates state: last_brief date in state.toml after successful write.
```

Design decisions:
- Priority ordering in `next_actions`: phase-transition topics first (priority 1+),
  in-progress topics second, deferred-heavy third. `get_next_action` assigns priority
  based on phase category; `run_brief` sorts by priority before writing frontmatter.
- `run_brief` accepts an injectable `LLMClient` for test isolation and provider
  agnosticism; cli constructs it via `llm.get_llm_client(config.llm, zdr=...)`. None
  (the test default, and the `--zdr`/no-key case) takes the deterministic fallback.
- `recommended_next_phase` is surfaced to Haiku in the preflight token; `get_next_action`
  uses it to override the mechanical lookup table. Haiku does not reason about it — the
  override is communicated verbatim.

Spec gaps:
- `test_stdout_shows_prose_not_frontmatter`: assertion is loose (`"---" not in output`).
  Tighten during CLI implementation by asserting output starts after the closing `---\n`.

---

### orient.day_close

EOD keystone: aggregates the day's session notes into the day marker + pre-plan that
`day start` consumes next morning. Mirrors `brief.py`'s current-file + archive pattern
(`day-marker.md` + `day-markers/<date>.md`) and its injectable-client fallback. See
[spec-day-close.md](spec-day-close.md).

```python
@dataclass
class DayMarker:
    date: str
    shipped: list[str]       # "project/topic: synthesis from ## Shipped"
    open_threads: list[str]  # "project/topic: Pending/Deferred still live"
    cross_topic: list[str]   # ## Calls + NOTES.md sweep (+ optional synthesis line)
    pre_plan: list[str]      # ordered next actions (pending-first, then deferred)
    flags: list[str]         # worked-not-closed / alarm-reason flags

def aggregate_day(orient_root: Path, target_date: str) -> DayMarker
    # Deterministic, API-free. Walks notes/<project>/<topic>/<target_date>.md across
    # every project (filesystem, not workspace.toml) + NOTES.md date-filtered sweep.
    # The structured marker is the source of truth.

def serialize_marker(marker: DayMarker) -> str
    # Renders the marker file (date: frontmatter + sections). Empty sections omitted;
    # a fully empty day still writes "_nothing closed today_" — never a silent no-op.

def run_day_close(
    orient_root: Path,
    target_date: Optional[str] = None,   # defaults to today; future dates rejected
    client: Optional[LLMClient] = None,  # None → deterministic no-Haiku branch
) -> None
    # 1. Reject future target_date (error:future-date on stderr, exit 1).
    # 2. Reject note_root that exists but is not a directory (exit 1).
    # 3. aggregate_day(); optional single _enrich_cross_topic Haiku pass when a client
    #    is present and there is shipped/open-thread content.
    # 4. Frontier placement (state.last_day_close, never regresses):
    #    - promote (target >= effective frontier): write current day-marker.md, archive
    #      a stale current marker, advance the frontier. Same-day re-run overwrites in
    #      place (no archive).
    #    - backfill (target < frontier): write straight to day-markers/<date>.md; current
    #      marker and frontier untouched.
```

Design decisions:
- Effective frontier = `max(state.last_day_close, current marker's own date:)` — a fresher
  current marker is never clobbered by a stale pointer.
- `run_day_close` takes the injectable `LLMClient` (None in tests / `--zdr` / no-key →
  deterministic). The Haiku pass only appends one cross-topic synthesis line on top of the
  already-complete deterministic marker; any failure leaves the marker untouched.

Spec gaps:
- Touched-but-unclosed detection only covers topics with a `<date>.md` note lacking a
  `## Session` block. The spec also wants git-commits-since-midnight / note-dir-mtime
  detection for topics with **no note at all** — deferred, documented gap.

---

### orient.skill

Local SKILL.md registry. Parses, discovers, resolves, and **emits** skill prompts —
never executes. `show` prints assembled text to stdout. See [spec-skill.md](spec-skill.md).

```python
class SkillKind(str, Enum):
    native = "native"
    external = "external"

@dataclass
class Skill:
    name: str
    description: str
    kind: SkillKind
    body: str                       # markdown body, frontmatter stripped
    source_path: str                # absolute path to the SKILL.md
    extends: Optional[str] = None   # native base name, for external overlays

def parse_skill(path: Path, kind: SkillKind) -> Skill
    # Splits leading --- frontmatter from body. Frontmatter keys: name, description,
    # kind, extends (scalar "key: value" only — same hand-rolled approach as
    # brief.parse_brief_frontmatter; no PyYAML). kind from caller; frontmatter/override
    # may refine extends.

def _native_skills_dir() -> Path
    # Path(__file__).parent / "skills" — package data, NOT ORIENT_ROOT.

def discover_skills(config: EffectiveConfig) -> list[Skill]
    # Native: parse every <pkg>/skills/*/SKILL.md (kind=native).
    # External: for each config.skills.paths root, glob **/SKILL.md (kind=external);
    #   apply matching SkillOverride by name (kind/extends override frontmatter).
    # Native first, then external; each in discovery order.

def resolve_skill(name: str, skills: list[Skill]) -> Skill
    # Native-first. External may not shadow a native of the same name →
    #   raises "skill '<name>' is both native (<path>) and external (<path>)".
    # Unknown → raises "no skill named '<name>' — orient skill list".

def assemble_skill(
    skill: Skill,
    base: Optional[Skill],
    context_token: Optional[str],
) -> str
    # Pure (no I/O). Concatenates, blank-line + rule separated, in order:
    #   1. context_token  — if a lifecycle native produced one
    #   2. base.body      — if `skill` is an external overlay (base = its native)
    #   3. skill.body
    # base is None for native/standalone skills; context_token is None for non-lifecycle.

# Lifecycle native → context-token provider. Uniform signature; unused args ignored.
# DAY-TIER ONLY: their context is workspace-wide and re-derivable, so `skill show` builds
# it from scratch. Session-tier natives (session-closer, topic-briefer) have NO token —
# their paired command (`orient session close` / `start`) emits the mechanical context and
# appends the body itself, so the stateful preflight is consumed exactly once. See cli
# `_emit_judgment_skill` and session_note `_session_close_priming`.
_LIFECYCLE_TOKENS: dict[str, Callable[[Path, Optional[str], Optional[str]], str]] = {
    "day-starter": ...,   # wraps brief.build_preflight_token (orient_root only)
    "day-closer":  ...,   # wraps day_close.aggregate_day marker preview (orient_root only)
}
_NEEDS_PROJECT_TOPIC: set[str] = set()   # no token needs project/topic today

def run_skill_list(config: EffectiveConfig) -> None
    # One line per skill: "<name>  [native | external | external→<base>]  <source_path>".

def run_skill_show(
    name: str,
    orient_root: Path,
    config: EffectiveConfig,
    project: Optional[str] = None,
    topic: Optional[str] = None,
) -> None
    # 1. discover_skills + resolve_skill(name). Collision/unknown → stderr, exit non-zero.
    # 2. External overlay: resolve its `extends` base (must be native, else error).
    # 3. Lifecycle base = self if native lifecycle, else the extends base. If in
    #    _LIFECYCLE_TOKENS, build its context token. (Day-tier only today; the
    #    _NEEDS_PROJECT_TOPIC guard exists but is empty, so session-tier natives just emit
    #    body — their command supplies context out-of-band.)
    # 4. print(assemble_skill(skill, base, context_token)). Emit-only — no API call ever.
```

Design decisions:
- Native skills are **package data** via `Path(__file__).parent / "skills"`, not
  `ORIENT_ROOT`; they version with orient's source. (Corrects the spec's earlier
  "ORIENT_ROOT-relative" wording, since fixed.)
- `skill.py` imports `brief.build_preflight_token` and `day_close` aggregation at module
  top (no inline imports) — hence its DAG position after both. It no longer imports
  `preflight`/`session_note`: the session-tier judgment halves get their context from the
  paired command (cli `_emit_judgment_skill` → `run_skill_show` for body, after
  `run_session_*` has printed the mechanical context), not from a token here.
  `_LIFECYCLE_TOKENS` keeps the per-skill wiring in a single table.
- `assemble_skill` is pure so the ordering invariant (token → base → overlay) is
  unit-testable with no filesystem or lifecycle-command involvement.
- ZDR: `run_skill_show` never calls the API in any mode, so it needs no special-casing.
  The `--zdr`/`ORIENT_NO_API` gate lives in cli for the *other* (claude -p) commands.

Spec gaps:
- Chained overlays (an external whose `extends` base is itself external): out of scope.
  `resolve_skill`/`run_skill_show` require the base to be native. Documented, unsupported
  at MVP.

---

### orient.cli

Typer app. All user-facing error messages and rendering live here. Modules return typed
result objects; cli.py converts them to Rich output.

```python
app: typer.Typer   # root app

# Subcommands registered on app:
# sync, status, note, brief, session-note
# config is a Typer sub-app with: validate, show, add-project, path
# skill is a Typer sub-app with: list, show

# CLI arg shape for session-note:
# orient session-note <mode> <project> <topic> [reason:<reason>]
# mode: "checkpoint" | "close"

# CLI arg shape for skill:
# orient skill show <name> [project] [topic]
#   project/topic optional; used only by day-tier lifecycle tokens that want them (none
#   today). session-tier natives emit body-only here. orient skill list takes no args.

# session start / close append their paired judgment skill after the mechanical output:
def _emit_judgment_skill(name: str, project: str, topic: str) -> None
    # Best-effort: skip silently if no workspace.toml (the mechanical scaffold is the
    # contract; the skill body is a convenience). Loads config, prints a
    # "--- /<name> ---" header, then run_skill_show(name, ...). Swallows SystemExit so a
    # skill-resolution failure never aborts the already-completed close/start.
    # close → "session-closer"; start → "topic-briefer". checkpoint emits nothing.
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
- LLM client construction is delegated to `llm.get_llm_client(config.llm, zdr=...)`,
  not done inline. `day start` passes its `--zdr` flag through; the factory also honors
  `ORIENT_NO_API`. Missing key under provider "auto"/"anthropic" yields None (silent
  deterministic fallback), not an error — running brief without a key is valid.
- `--zdr` flag / `ORIENT_NO_API=1` env: when set, `get_llm_client` returns None so no
  client is constructed for brief/day-close — those degrade to emit-prompt. Session
  edges are already client-free. `orient skill show` is unaffected (already emit-only);
  external skills are never routed to a `claude -p` path in any mode.

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

Note for implementation-writer: implement the DAG serially. Where a module depends on
one not yet written, proceed speculatively — implement against the interface declared
above, making reasonable assumptions about what the dependency will look like. If the
dependency's actual implementation diverges from those assumptions, fix up at wire-up
time. This is cheaper than true parallelism and avoids the coordination cost of
splitting work across concurrent agents.
