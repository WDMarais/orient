"""Local SKILL.md registry: parse, discover, resolve, and **emit** skill prompts.

orient owns a registry of skill prompts and emits them assembled with the mechanical
context its lifecycle commands already produce. It never executes a skill — `show`
prints assembled text to stdout and is emit-only (zero API calls, ZDR-safe).

See spec-skill.md and the `### orient.skill` section of ARCHITECTURE.md.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from orient.brief import PreflightToken, build_preflight_token
from orient.config import EffectiveConfig
from orient.preflight import PreflightResult, run_preflight
from orient.session_note import build_cold_brief, parse_note


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
            skills.append(skill)

    return skills


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


def _render_preflight_result(result: PreflightResult) -> str:
    lines = ["# orient session close — preflight context", f"mode: {result.mode}"]
    if result.prev_path:
        lines.append(f"previous note: {result.prev_path}")
    lines.append(f"pending carried: {result.pending_count}")
    lines.append(f"deferred carried: {result.deferred_count}")
    return "\n".join(lines)


def _day_starter_token(orient_root: Path, project: Optional[str], topic: Optional[str]) -> str:
    return _render_preflight_token(build_preflight_token(orient_root))


def _session_closer_token(orient_root: Path, project: Optional[str], topic: Optional[str]) -> str:
    assert project is not None and topic is not None  # gated by _NEEDS_PROJECT_TOPIC
    today = date.today().isoformat()
    notes_md = orient_root / "notes" / project / "NOTES.md"
    lines = [
        _render_preflight_result(run_preflight(project, topic, "close", orient_root)),
        "",
        "## NOTES.md sweep target (mechanically resolved)",
        f"date: {today}",
        f"project tag: [{project}]",
        f"file: {notes_md}",
        f"append flagged items as: {today} HH:MM [{project}] <text>",
    ]
    return "\n".join(lines)


def _topic_briefer_token(orient_root: Path, project: Optional[str], topic: Optional[str]) -> str:
    assert project is not None and topic is not None  # gated by _NEEDS_PROJECT_TOPIC
    result = run_preflight(project, topic, "start", orient_root)
    prev = parse_note(Path(result.prev_path)) if result.prev_path else None
    return build_cold_brief(project, topic, prev)


# Lifecycle native → context-token provider. Uniform (orient_root, project, topic).
_LIFECYCLE_TOKENS: dict[str, Callable[[Path, Optional[str], Optional[str]], str]] = {
    "day-starter": _day_starter_token,
    "session-closer": _session_closer_token,
    "topic-briefer": _topic_briefer_token,
    # "day-closer": pending — day close unbuilt; emits body alone for now.
}

# Lifecycle skills whose token needs an explicit project/topic to build.
_NEEDS_PROJECT_TOPIC = {"session-closer", "topic-briefer"}


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
) -> None:
    """Resolve <name> and emit the assembled prompt. Emit-only — never calls the API."""
    skills = discover_skills(config)
    try:
        skill = resolve_skill(name, skills)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

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
