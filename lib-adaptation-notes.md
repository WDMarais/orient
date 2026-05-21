# lib/ adaptation notes

How agent-skills/lib/ maps to orient's equivalent. Most of the core logic is
already generic — adaptations are mostly env var renaming and semantic parameter
naming.

---

## note_parser.py

**Reuse as-is:** `parse_sections`, `count_bullets`, `extract_section`, CLI
subcommands (`find`, `sections`, `bullets`). No changes needed.

**Adapt:**
- `_default_note_root()`: currently reads `NOTE_ROOT` env var directly. In orient,
  note root lives under `ORIENT_ROOT` (e.g. `$ORIENT_ROOT/notes`). Either read
  `NOTE_ROOT` as an override with `ORIENT_ROOT/notes` as default, or derive from
  `ORIENT_ROOT` only.
- `find_latest_note(project, ticket, ...)`: rename `ticket` param to `topic` for
  semantic clarity. Logic is identical — `<note_root>/<project>/<topic>/YYYY-MM-DD.md`
  is the same path shape.

**Net change:** ~5 lines.

---

## session_close_preflight.py

**Reuse as-is:** routing token output format, note dir creation, append-mode
detection, pass counting, all routing logic.

**Adapt:**
- CLI args: `<ticket> <project>` → `<topic> <project>` (semantic rename only).
- `NOTE_ROOT` resolution: same env var pattern, just sourced from `ORIENT_ROOT`.
- No `OWM_WORKSPACE` dependency in the current script — already clean.

**Net change:** ~3 lines (arg names + env var default).

---

## marker_detect.py

**Not needed for MVP.** No running instances, no `instance-state.json`, no
`odoo.log` mtime signals.

**Future adaptation** (deferred): a lightweight "detect projects with git activity
today" variant would use the `git-commits` signal only — strip the `instance-ran`
and `mtime` branches entirely. Simpler and faster.

---

## Tests (lib/tests/)

The fixture-based smoke tests (`smoke.py`) are reusable with minor path updates.
The fixtures (`myproject/feat-123/`, `myproject/hub/`) already use the generic
project/topic path shape — no structural changes needed.

---

## Recommended approach

Start orient's lib as a thin fork of agent-skills/lib/ — copy, rename params,
update env var resolution. Don't rewrite. The algorithms are correct and tested.
Divergence will happen naturally as orient's note format evolves (e.g. `## Calls`
section) and as adapt-specific needs emerge.

Keep the two libs in sync manually for now; if they converge on identical logic,
extract a shared package later. Don't extract prematurely.
