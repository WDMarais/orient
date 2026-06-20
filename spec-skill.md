# orient skill — behavioral spec

Part of [orient behavioral spec](spec.md).

A local skill harness. orient owns a registry of skill prompts and **emits** them
assembled with the mechanical context its lifecycle commands already produce. It does
not depend on Claude Code's Skills feature or MCP — those become optional fast-paths,
not load-bearing infrastructure. When the retention boundary of the host feature is
untrusted (a zero-data-retention workplace), orient falls back to its own harness,
which is provably local: in emit mode it makes zero Anthropic calls and only prints
text.

This inverts the original dependency. agent-skills' generalizable skills move *into*
orient as natives; project-specific skills stay on disk and register against orient.

**Skill = SKILL.md verbatim.** A skill is a file with YAML frontmatter (`name`,
`description`, optional `kind`/`extends`) and a markdown body. The format is identical
to existing on-disk SKILL.md files, so external skills drop in unchanged and natives
are authored the same way. No bespoke format.

## Two kinds

- **native** — ships inside orient as package data at `orient/skills/<name>/SKILL.md`,
  resolved relative to the installed package (`Path(__file__).parent / "skills"`), not
  `ORIENT_ROOT` (which is user config/notes). Intrinsic; never registered; versions with
  orient's source.
- **external** — lives in a project's own filesystem. Registered via `workspace.toml`
  (search paths + per-skill overrides). Optionally sets `extends: <native>` to layer
  project-specific steps onto a native base; an external skill with no `extends` is
  standalone.

"external-addition" is not a third kind — it is an external skill with `extends` set.

## Native set

Lifted from agent-skills by the genericization audit. Two families:

**Dev-pipeline** (no project coupling — owm references in those files are illustrative
examples only): `case-interviewer`, `harness-writer`, `architecture-proposer`,
`implementation-writer`.

**Lifecycle** — the judgment half of orient's existing lifecycle commands, recognized
as the same skill viewed from a project rather than newly extracted:

| native skill | paired command | genericized from |
|---|---|---|
| `day-starter` | `orient day start` | owm hub-starter |
| `day-closer` | `orient day close` | owm hub-closer |
| `session-closer` | `orient session close` | owm session-closer |
| `topic-briefer` | `orient session start` | owm instance-briefer |

## Command ↔ skill pairing

Each native lifecycle skill is the **judgment half** of a command whose **mechanical
half** already exists. The command produces a context token (preflight routing,
rolled-forward Pending/Deferred, ranked topics, skeleton path); the skill is the
prompt that directs the in-session LLM to act on it.

`orient skill show <native>` for a lifecycle skill therefore emits **the skill body +
the context token its paired command produces** — not the prompt alone. The harness
consumes lifecycle command tokens; it is not bolted alongside them. This is the
lookup-vs-judgment layer made literal: Python does the lookup, the emitted skill
directs the judgment.

Dev-pipeline and standalone external skills have no paired command; they emit body
plus any explicitly requested context only.

## Commands

```
orient skill list
  → native skills, then external (with source path + extends target)
  → one per line; marks each native | external | external→<base>

orient skill show <name>
  → resolve <name>, print the assembled prompt to stdout:
      [context token from paired command, if lifecycle native]
      [native base body, if <name> is an external with extends]
      [skill body]
  → emit-only; never calls the API. This is the ZDR-safe path.
```

`show` is the primary verb — orient is a registry and emitter, not an executor of
judgment skills. Execution is always the interactive session's job (or, for the few
mechanical-LLM steps, the lifecycle command's own `claude -p`).

## Resolution

`<name>` resolves native-first, then external. An external skill may not shadow a
native of the same name (collision → error naming both sources). An external with
`extends: <base>` requires `<base>` to resolve to a native; emitting it prints the
native base body followed by the external overlay body, so the overlay reads as
"...and additionally:" on top of the generic skill.

## workspace.toml registration

External skills only. Search paths auto-discover any `SKILL.md` beneath them;
per-skill overrides declare `kind`/`extends` or pin flags that can't be inferred.

```toml
[skills]
paths = ["~/work/skills", "~/coding-projects/agent-skills/owm"]

[[skills.override]]
name = "owm-session-close"
extends = "session-closer"        # overlay onto native base

[[skills.override]]
name = "blind-reviewer"
kind = "external"                 # standalone; no generic core
```

Discovery reads each found SKILL.md's frontmatter for `name`/`kind`/`extends`;
overrides win over frontmatter. Native skills need no entry.

## ZDR / emit-only invariant

Two independent guarantees:

- **`--zdr` / `ORIENT_NO_API=1`**: orient makes zero Anthropic calls for the whole
  process. Every step that would shell to `claude -p` (brief prose, day-close
  synthesis) degrades to emit-prompt; `orient skill show` is unaffected because it is
  already emit-only. The work venue is provably API-silent.
- **External skills are always emit-only**, in any mode. They are never piped to an
  autonomous `claude -p` path — orient prints them for the interactive (ZDR-compliant)
  session to follow. This covers the PR-review pipeline (`pr-fetcher`,
  `blind-reviewer`, `context-reviewer`): registered as standalone external skills so
  orient can emit them under ZDR at work — exactly the case where the host Skills
  feature can't be trusted and the need is highest.

native lifecycle skills retain the option of their paired command's `claude -p` step
outside ZDR mode (e.g. day-start prose), but the judgment skill body itself is always
emit-only.

## Out of scope

- Executing judgment skills autonomously. orient emits; the session acts.
- An MCP-tool registry. The same native/external + emit pattern is intended to extend
  to MCP-shaped tools later, but tools are not specced here.
- Migrating the owm overlays' content. This spec defines the harness and the native
  set; the genericized native bodies and the thin owm overlays are authored against
  it, not enumerated here.
