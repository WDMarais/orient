"""Local SKILL.md registry: parse, discover, resolve, and **emit** skill prompts.

orient owns a registry of skill prompts and emits them assembled with the mechanical
context its lifecycle commands already produce. It never executes a skill — `show`
prints assembled text to stdout and is emit-only (zero API calls, ZDR-safe).

See spec-skill.md and the `### orient.skill` section of ARCHITECTURE.md.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from orient.brief import PreflightToken, build_preflight_token
from orient.config import EffectiveConfig
from orient.day_close import aggregate_day, serialize_marker
from orient.state import load_skill_modes


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
    modes: list[str] = field(default_factory=list)  # mode vocabulary (from override)


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def parse_skill(path: Path, kind: SkillKind) -> Skill:
    """Split leading --- frontmatter from body. Scalar `key: value` only (same
    hand-rolled approach as brief.parse_brief_frontmatter — no PyYAML). `kind` comes
    from the caller; frontmatter may supply `extends`."""
    text = path.read_text()
    parts = text.split("---\n", 2)
    if len(parts) >= 3:
        fm_text, body = parts[1], parts[2]
    else:
        fm_text, body = "", text

    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fm[key.strip()] = value.strip()

    return Skill(
        name=fm.get("name", path.parent.name),
        description=fm.get("description", ""),
        kind=kind,
        body=body.strip(),
        source_path=str(path),
        extends=fm.get("extends") or None,
    )


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

def resolve_skill(name: str, skills: list[Skill]) -> Skill:
    """Native-first. An external may not shadow a native of the same name (collision →
    error naming both sources). Unknown name → error pointing at `orient skill list`."""
    natives = [s for s in skills if s.name == name and s.kind == SkillKind.native]
    externals = [s for s in skills if s.name == name and s.kind == SkillKind.external]

    if natives and externals:
        raise ValueError(
            f"skill '{name}' is both native ({natives[0].source_path}) "
            f"and external ({externals[0].source_path})"
        )
    if natives:
        return natives[0]
    if externals:
        return externals[0]
    raise ValueError(f"no skill named '{name}' — orient skill list")


# ---------------------------------------------------------------------------
# Assemble (pure — no I/O)
# ---------------------------------------------------------------------------

_SEPARATOR = "\n\n---\n\n"


def assemble_skill(
    skill: Skill,
    base: Optional[Skill],
    context_token: Optional[str],
) -> str:
    """Concatenate, rule-separated, in order: context_token (lifecycle), base.body
    (native base of an external overlay), skill.body. base/context_token are None when
    not applicable."""
    parts: list[str] = []
    if context_token:
        parts.append(context_token.strip())
    if base is not None:
        parts.append(base.body.strip())
    parts.append(skill.body.strip())
    return _SEPARATOR.join(parts)


# ---------------------------------------------------------------------------
# Discover
# ---------------------------------------------------------------------------

def _native_skills_dir() -> Path:
    """Package data, NOT ORIENT_ROOT — natives version with orient's source."""
    return Path(__file__).parent / "skills"


def discover_skills(config: EffectiveConfig) -> list[Skill]:
    """Native skills first (package data), then external (config.skills.paths).
    Per-skill overrides (kind/extends) win over discovered frontmatter."""
    skills: list[Skill] = []

    native_dir = _native_skills_dir()
    if native_dir.is_dir():
        for sub in sorted(native_dir.iterdir()):
            skill_md = sub / "SKILL.md"
            if skill_md.is_file():
                skills.append(parse_skill(skill_md, SkillKind.native))

    overrides = {o.name: o for o in config.skills.override}
    for raw_root in config.skills.paths:
        root = Path(raw_root).expanduser()
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("**/SKILL.md")):
            skill = parse_skill(skill_md, SkillKind.external)
            override = overrides.get(skill.name)
            if override and override.extends is not None:
                skill.extends = override.extends
            if override and override.modes:
                skill.modes = override.modes
            skills.append(skill)

    return skills


def filter_body_by_mode(body: str, mode: str, modes: list[str]) -> str:
    """Keep only the active mode's rows in a mode-keyed body.

    A line whose leading label — a bold table cell `| **X** |` or a bullet `- X:` —
    matches one of the skill's declared `modes` is kept only when X is the active
    mode; lines not labeled with any declared mode are kept verbatim. Generic over
    any mode-keyed SKILL.md (mirrors ponytail's filterSkillBodyForMode). Case-folded.
    """
    declared = {m.lower() for m in modes}
    active = mode.lower()
    kept: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|", line) or re.match(r"^-\s*([^:]+):", line)
        if m:
            label = m.group(1).strip().lower()
            if label in declared and label != active:
                continue
        kept.append(line)
    return "\n".join(kept).strip()


# ---------------------------------------------------------------------------
# Lifecycle context tokens — the mechanical half each lifecycle command produces
# ---------------------------------------------------------------------------

def _render_preflight_token(token: PreflightToken) -> str:
    lines = [
        "# orient day start — preflight context",
        f"last brief: {token.last_brief}",
        f"active topics: {token.active_topics}",
    ]
    for topic in token.topics:
        lines.append(f"- {topic.topic}  [{topic.phase}]")
        for item in topic.pending:
            lines.append(f"    pending: {item}")
    if token.notes_since_last_brief:
        lines.append(f"notes since last brief: {len(token.notes_since_last_brief)}")
        for note in token.notes_since_last_brief:
            lines.append(f"  - {note}")
    return "\n".join(lines)


def _day_starter_token(orient_root: Path, project: Optional[str], topic: Optional[str]) -> str:
    return _render_preflight_token(build_preflight_token(orient_root))


def _day_closer_token(orient_root: Path, project: Optional[str], topic: Optional[str]) -> str:
    # Workspace-wide, like day-starter. Emit-only: aggregate today's notes into a marker
    # preview WITHOUT writing it or advancing the frontier — running the command does that.
    today = date.today().isoformat()
    return serialize_marker(aggregate_day(orient_root, today))


# Lifecycle native → context-token provider. Uniform (orient_root, project, topic).
# The session-tier skills (session-closer, topic-briefer) deliberately have no token:
# their paired commands (`orient session close` / `orient session start`) emit the
# mechanical context themselves and then append the skill body, so preflight is consumed
# exactly once. Only the day-tier markers carry a token here.
_LIFECYCLE_TOKENS: dict[str, Callable[[Path, Optional[str], Optional[str]], str]] = {
    "day-starter": _day_starter_token,
    "day-closer": _day_closer_token,
}

# Lifecycle skills whose token needs an explicit project/topic to build. (None today —
# the day-tier tokens are workspace-wide.)
_NEEDS_PROJECT_TOPIC: set[str] = set()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def run_skill_list(config: EffectiveConfig) -> None:
    for skill in discover_skills(config):
        if skill.kind == SkillKind.native:
            tag = "native"
        elif skill.extends:
            tag = f"external→{skill.extends}"
        else:
            tag = "external"
        print(f"{skill.name}  [{tag}]  {skill.source_path}")


def run_skill_show(
    name: str,
    orient_root: Path,
    config: EffectiveConfig,
    project: Optional[str] = None,
    topic: Optional[str] = None,
    mode: Optional[str] = None,
) -> None:
    """Resolve <name> and emit the assembled prompt. Emit-only — never calls the API.

    Mode filtering: an explicit `mode` ("off" disables filtering) wins; otherwise the
    skill's persisted mode (state.skill_modes) applies. When an effective mode and the
    skill's declared modes are both present, the body is sliced to that mode's rows.
    """
    skills = discover_skills(config)
    try:
        skill = resolve_skill(name, skills)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

    if mode == "off":
        effective_mode: Optional[str] = None
    elif mode is not None:
        effective_mode = mode
    else:
        effective_mode = load_skill_modes(orient_root).get(skill.name)
    if effective_mode and skill.modes:
        skill.body = filter_body_by_mode(skill.body, effective_mode, skill.modes)

    base: Optional[Skill] = None
    lifecycle_name: Optional[str] = None
    if skill.kind == SkillKind.external and skill.extends:
        base_matches = [
            s for s in skills if s.name == skill.extends and s.kind == SkillKind.native
        ]
        if not base_matches:
            print(
                f"skill '{name}' extends '{skill.extends}', which is not a native skill",
                file=sys.stderr,
            )
            raise SystemExit(1)
        base = base_matches[0]
        lifecycle_name = base.name
    elif skill.kind == SkillKind.native:
        lifecycle_name = skill.name

    context_token: Optional[str] = None
    if lifecycle_name in _LIFECYCLE_TOKENS:
        if lifecycle_name in _NEEDS_PROJECT_TOPIC and not (project and topic):
            print(
                f"note: {lifecycle_name} context token needs <project> <topic>; "
                "emitting skill body only",
                file=sys.stderr,
            )
        else:
            context_token = _LIFECYCLE_TOKENS[lifecycle_name](orient_root, project, topic)

    print(assemble_skill(skill, base, context_token))
