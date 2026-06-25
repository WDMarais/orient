# orient skill — behavioral spec

Part of [orient behavioral spec](spec.md).

A local skill harness. orient owns a registry of skill prompts and **emits** them
assembled with the mechanical context its lifecycle commands already produce. It does
not depend on Claude Code's Skills feature or MCP — those become optional fast-paths,
not load-bearing infrastructure. When the retention boundary of the host feature is
untrusted (a zero-data-retention workplace), orient falls back to its own harness,
which is provably local: in emit mode it makes zero Anthropic calls and only prints
text.

orient owns as **natives** only the judgment halves of its own lifecycle commands.
Every other skill — whether broadly reusable or project-specific — stays on disk in its
own repo and registers against orient as **external**. The native/external line is
"orient's own vs guest", not "generalizable vs project-specific".

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

The natives are exactly the **judgment halves of orient's own lifecycle commands** —
nothing else ships as package data. Each is the same skill viewed from a project rather
than newly invented:

| native skill | paired command |
|---|---|
| `day-starter` | `orient day start` |
| `day-closer` | `orient day close` |
| `session-closer` | `orient session close` |
| `topic-briefer` | `orient session start` |

A skill with no paired orient command is not a native; it registers as external. Only
intrinsic-to-orient is native — reusability is not the test.

## Command ↔ skill pairing

Each native lifecycle skill is the **judgment half** of a command whose **mechanical
half** already exists. The mechanical half produces context — preflight routing,
rolled-forward Pending/Deferred, ranked topics, skeleton path; the skill is the prompt
that directs the in-session LLM to act on it. How the two halves meet differs by tier:

- **Day-tier** (`day-starter`, `day-closer`): the mechanical context is workspace-wide
  and re-derivable on demand, so `orient skill show <native>` emits **the skill body +
  a context token** the skill computes from scratch (preflight preview, marker preview).
  Showing the skill is self-sufficient; no paired command need have run.
- **Session-tier** (`session-closer`, `topic-briefer`): the mechanical half is a
  **stateful, single-consumption** preflight that writes a dated note. Re-running it from
  `skill show` after the command already ran would double-consume preflight and report
  stale counts. So these skills carry **no token**: their paired command
  (`orient session close` / `orient session start`) emits the mechanical context itself
  — scaffold path, previous note, close priming / cold brief — and then appends the skill
  body. `orient skill show <session-tier>` is therefore **body-only**.

Either way it is the lookup-vs-judgment layer made literal: Python does the lookup once,
the emitted skill directs the judgment. Standalone external skills have no paired command;
they emit body plus any explicitly requested context only.

## Commands

```
orient skill list
  → native skills, then external (with source path + extends target)
  → one per line; marks each native | external | external→<base>

orient skill show <name>
  → resolve <name>, print the assembled prompt to stdout:
      [context token, if <name> is a day-tier lifecycle native]
      [native base body, if <name> is an external with extends]
      [skill body]
  → session-tier natives (session-closer, topic-briefer) emit body-only — their paired
    command emits the mechanical context and appends the body itself.
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
paths = ["~/work/skills", "~/projects/my-skills"]

[[skills.override]]
name = "my-session-close"
extends = "session-closer"        # overlay onto native base

[[skills.override]]
name = "pr-reviewer"
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
  session to follow. This covers, for example, a project's PR-review pipeline
  registered as standalone external skills, so orient can emit them under ZDR at work —
  exactly the case where the host Skills feature can't be trusted and the need is
  highest.

native lifecycle skills retain the option of their paired command's `claude -p` step
outside ZDR mode (e.g. day-start prose), but the judgment skill body itself is always
emit-only.

## Out of scope

- Executing judgment skills autonomously. orient emits; the session acts.
- An MCP-tool registry. The same native/external + emit pattern is intended to extend
  to MCP-shaped tools later, but tools are not specced here.
- Migrating external overlays' content. This spec defines the harness and the native
  set; the native bodies and any thin external overlays are authored against it, not
  enumerated here.
