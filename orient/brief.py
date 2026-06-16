"""build_preflight_token, get_next_action, parse_brief_frontmatter, run_brief."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import anthropic

from orient.config import load_effective_config
from orient.lib.note_parser import find_latest_note
from orient.note import parse_notes_md
from orient.session_note import parse_note


@dataclass
class TopicPreflight:
    topic: str
    note_path: str
    phase: str
    recommended_next_phase: Optional[str] = None
    close_reason: Optional[str] = None
    pending: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)


@dataclass
class PreflightToken:
    last_brief: str
    active_topics: int
    topics: list[TopicPreflight]
    notes_since_last_brief: list[str] = field(default_factory=list)


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


# (skill, invocation_template, priority): 1=phase-transition, 2=in-progress, 3=unknown
_PHASE_TABLE: dict[str, tuple[str, str, int]] = {
    "case-interviewer-in-progress":      ("case-interviewer",     "continue /case-interviewer",               2),
    "case-interviewer-complete":         ("harness-writer",        "/harness-writer {project} {topic}",        1),
    "harness-writer-complete":           ("architecture-proposer", "/architecture-proposer {project} {topic}", 1),
    "architecture-proposer-complete":    ("implementation-writer", "/implementation-writer {project} {topic}", 1),
    "implementation-writer-in-progress": ("implementation-writer", "continue /implementation-writer",          2),
    "implementation-writer-complete":    ("verify",                "/verify → /session-closer",                1),
}


def get_next_action(
    phase: str,
    project: str,
    topic: str,
    recommended_next_phase: Optional[str] = None,
) -> TopicAction:
    lookup = recommended_next_phase if (recommended_next_phase and recommended_next_phase in _PHASE_TABLE) else phase

    if lookup not in _PHASE_TABLE:
        return TopicAction(
            topic=f"{project}/{topic}",
            phase="unknown",
            skill="unknown",
            invocation="open <note-path> to orient, then choose next stage",
            priority=3,
        )

    skill, tpl, priority = _PHASE_TABLE[lookup]
    return TopicAction(
        topic=f"{project}/{topic}",
        phase=lookup,
        skill=skill,
        invocation=tpl.format(project=project, topic=topic),
        priority=priority,
    )


def build_preflight_token(
    orient_root: Path,
    last_brief_date: Optional[str] = None,
    active_days: int = 14,
) -> PreflightToken:
    try:
        cfg = load_effective_config(orient_root)
        projects = cfg.projects
    except Exception:
        projects = []

    note_root = orient_root / "notes"
    cutoff = (date.today() - timedelta(days=active_days)).isoformat()

    topics: list[TopicPreflight] = []

    for project in projects:
        project_note_dir = note_root / project.name
        if not project_note_dir.exists() or not project_note_dir.is_dir():
            if project.pinned:
                topics.append(TopicPreflight(
                    topic=f"{project.name}/(no topic)",
                    note_path="",
                    phase="no-notes",
                ))
            continue

        for topic_dir in sorted(project_note_dir.iterdir()):
            if not topic_dir.is_dir():
                continue
            topic_name = topic_dir.name
            topic_str = f"{project.name}/{topic_name}"

            latest = find_latest_note(note_root, project.name, topic_name)
            if latest is None:
                if project.pinned:
                    topics.append(TopicPreflight(
                        topic=topic_str, note_path="", phase="no-notes",
                    ))
                continue

            is_active = latest.stem >= cutoff
            if not is_active and not project.pinned:
                continue

            try:
                parsed = parse_note(latest)
            except Exception:
                continue

            phase = parsed.session.phase if parsed.session else "no-notes"
            recommended = parsed.session.recommended_next_phase if parsed.session else None
            close_reason = parsed.session.reason if parsed.session else None

            topics.append(TopicPreflight(
                topic=topic_str,
                note_path=str(latest),
                phase=phase,
                recommended_next_phase=recommended,
                close_reason=close_reason,
                pending=parsed.pending,
                deferred=parsed.deferred,
            ))

    notes_since: list[str] = []
    notes_md = orient_root / "NOTES.md"
    if notes_md.exists():
        for entry in parse_notes_md(notes_md):
            if last_brief_date is None or entry.date > last_brief_date:
                notes_since.append(f"{entry.date} {entry.time}  [{entry.tag}]  {entry.text}")

    return PreflightToken(
        last_brief=last_brief_date or date.today().isoformat(),
        active_topics=len(topics),
        topics=topics,
        notes_since_last_brief=notes_since,
    )


def _serialize_frontmatter(fm: BriefFrontmatter) -> str:
    lines = [
        "---",
        f"date: {fm.date}",
        f"last_brief: {fm.last_brief}",
        f"active_topics: {fm.active_topics}",
        f"notes_unreviewed: {fm.notes_unreviewed}",
        "next_actions:",
    ]
    for action in fm.next_actions:
        lines.append(f"  - topic: {action.topic}")
        lines.append(f"    phase: {action.phase}")
        lines.append(f"    skill: {action.skill}")
        lines.append(f"    invocation: {action.invocation}")
        lines.append(f"    priority: {action.priority}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _coerce(v: str) -> object:
    try:
        return int(v)
    except ValueError:
        return v


def _parse_simple_yaml(text: str) -> dict:
    """Parse the restricted YAML produced by _serialize_frontmatter."""
    lines = text.strip().splitlines()
    result: dict = {}
    current_list_key: Optional[str] = None
    current_item: Optional[dict] = None

    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 0:
            if current_item is not None and current_list_key is not None:
                result[current_list_key].append(current_item)
                current_item = None
            current_list_key = None

            if ": " in stripped:
                k, v = stripped.split(": ", 1)
                result[k.strip()] = _coerce(v.strip())
            elif stripped.endswith(":"):
                k = stripped[:-1].strip()
                result[k] = []
                current_list_key = k

        elif stripped.startswith("- "):
            if current_item is not None and current_list_key is not None:
                result[current_list_key].append(current_item)
            current_item = {}
            rest = stripped[2:]
            if ": " in rest:
                k, v = rest.split(": ", 1)
                current_item[k.strip()] = _coerce(v.strip())

        elif current_item is not None and ": " in stripped:
            k, v = stripped.split(": ", 1)
            current_item[k.strip()] = _coerce(v.strip())

    if current_item is not None and current_list_key is not None:
        result[current_list_key].append(current_item)

    return result


def parse_brief_frontmatter(brief_path: Path) -> BriefFrontmatter:
    text = brief_path.read_text()
    parts = text.split("---\n", 2)
    fm_text = parts[1] if len(parts) >= 3 else (parts[1] if len(parts) >= 2 else "")
    data = _parse_simple_yaml(fm_text)

    next_actions = [
        TopicAction(
            topic=str(a.get("topic", "")),
            phase=str(a.get("phase", "")),
            skill=str(a.get("skill", "")),
            invocation=str(a.get("invocation", "")),
            priority=int(a.get("priority", 3)),
        )
        for a in data.get("next_actions", [])
    ]

    return BriefFrontmatter(
        date=str(data.get("date", "")),
        last_brief=str(data.get("last_brief", "")),
        active_topics=int(data.get("active_topics", 0)),
        next_actions=next_actions,
        notes_unreviewed=int(data.get("notes_unreviewed", 0)),
    )


def run_brief(
    orient_root: Path,
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    if client is None and os.getenv("ANTHROPIC_API_KEY"):
        client = anthropic.Anthropic()
    today = date.today().isoformat()
    brief_path = orient_root / "morning-brief.md"

    # Archive: move previous brief if from a different day
    last_brief_date: Optional[str] = None
    if brief_path.exists():
        try:
            existing_fm = parse_brief_frontmatter(brief_path)
            if existing_fm.date and existing_fm.date != today:
                archive_dir = orient_root / "morning-briefs"
                archive_dir.mkdir(exist_ok=True)
                brief_path.rename(archive_dir / f"{existing_fm.date}.md")
                last_brief_date = existing_fm.date
            # same-day: overwrite in-place, keep last_brief as today
        except Exception:
            try:
                mtime_date = date.fromtimestamp(brief_path.stat().st_mtime).isoformat()
                if mtime_date != today:
                    archive_dir = orient_root / "morning-briefs"
                    archive_dir.mkdir(exist_ok=True)
                    brief_path.rename(archive_dir / f"{mtime_date}.md")
            except Exception:
                pass

    note_root = orient_root / "notes"
    if note_root.exists() and not note_root.is_dir():
        print("cannot write to note_root: not a directory", file=sys.stderr)
        sys.exit(1)

    token = build_preflight_token(orient_root, last_brief_date=last_brief_date)

    # Build actions and sort by priority
    actions: list[TopicAction] = []
    for t in token.topics:
        if "/" in t.topic:
            proj, top = t.topic.split("/", 1)
        else:
            proj, top = t.topic, ""
        actions.append(get_next_action(t.phase, proj, top, t.recommended_next_phase))
    actions.sort(key=lambda a: a.priority)

    fm = BriefFrontmatter(
        date=today,
        last_brief=last_brief_date or today,
        active_topics=token.active_topics,
        next_actions=actions,
        notes_unreviewed=len(token.notes_since_last_brief),
    )

    # Prose section: call Haiku if client available; placeholder otherwise
    if client is not None and token.topics:
        topic_lines = "\n".join(
            f"- {a.topic} ({a.phase} → {a.invocation})" for a in actions
        )
        prompt = (
            f"Write a brief morning context note for {today}.\n"
            f"Active topics:\n{topic_lines}\n\n"
            "2-4 concise sentences summarising priorities. No YAML or frontmatter."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        prose = response.content[0].text.strip()
    elif not token.topics:
        prose = (
            "No active topics. Use `orient session-note close` to record a session,\n"
            "or `orient config add-project --pinned` to pin a project that's always active."
        )
    else:
        topic_map = {t.topic: t for t in token.topics}
        lines = []
        for a in actions:
            t = topic_map.get(a.topic)
            reason_note = ""
            if t and t.close_reason and t.close_reason not in ("natural-end", ""):
                if t.close_reason == "budget-hit":
                    reason_note = f" [previous session hit budget limit]"
                elif t.close_reason == "context-limit":
                    reason_note = f" [previous session hit context limit — consider /compact]"
                else:
                    reason_note = f" [previous close: {t.close_reason}]"
            lines.append(f"- {a.topic}: {a.invocation}{reason_note}")
        prose = "\n".join(lines)

    brief_path.write_text(_serialize_frontmatter(fm) + "\n" + prose + "\n")
    print(prose)
