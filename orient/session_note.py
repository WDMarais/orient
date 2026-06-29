"""Session note write logic - parse_note, run_session_note."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from orient.lib.note_parser import (
    parse_sections,
    parse_bullets,
    parse_kv_bullets,
    find_latest_note,
)
from orient.paths import topic_dir
from orient.preflight import run_preflight
from orient.state import mark_active_topic


@dataclass
class SessionSection:
    reason: str
    phase: str = ""
    recommended_next_phase: Optional[str] = None
    cost: Optional[str] = None
    duration: Optional[str] = None
    model: str = "sonnet"


@dataclass
class ParsedNote:
    date: str
    topic: str
    goal: Optional[str] = None
    shipped: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    session: Optional[SessionSection] = None
    checkpoint_count: int = 0


def parse_note(path: Path) -> ParsedNote:
    """Parse a session note file using orient.lib.note_parser."""
    text = path.read_text()
    sections = parse_sections(text)

    note_date = ""
    topic = ""
    for line in text.splitlines():
        if line.startswith("# "):
            parts = line[2:].split(" - ", 1)
            if parts:
                note_date = parts[0].strip()
            if len(parts) > 1:
                topic = parts[1].strip()
            break

    goal = sections.get("Goal") or None
    shipped = parse_bullets(sections.get("Shipped", ""))
    pending = parse_bullets(sections.get("Pending", ""))
    deferred = parse_bullets(sections.get("Deferred", ""))
    calls = parse_bullets(sections.get("Calls", ""))

    session_text = sections.get("Session")
    session = None
    if session_text:
        kv = parse_kv_bullets(session_text)
        session = SessionSection(
            reason=kv.get("reason", "natural-end"),
            phase=kv.get("phase", ""),
            recommended_next_phase=kv.get("recommended_next_phase"),
            cost=kv.get("cost"),
            duration=kv.get("duration"),
            model=kv.get("model", "sonnet"),
        )

    checkpoint_count = sum(
        1 for line in text.splitlines()
        if line.startswith("### Checkpoint")
    )

    return ParsedNote(
        date=note_date,
        topic=topic,
        goal=goal,
        shipped=shipped,
        pending=pending,
        deferred=deferred,
        calls=calls,
        session=session,
        checkpoint_count=checkpoint_count,
    )


def _load_prev(prev_path: Optional[str]) -> Optional[ParsedNote]:
    if not prev_path:
        return None
    try:
        return parse_note(Path(prev_path))
    except Exception:
        return None


def _write_skeleton(
    note_path: Path,
    project: str,
    topic: str,
    today: str,
    reason: Optional[str],
    prev_parsed: Optional[ParsedNote],
) -> None:
    """Write a skeleton note with rolled-forward pending/deferred. No Haiku."""
    pending_block = "\n".join(f"- {p}" for p in (prev_parsed.pending if prev_parsed else [])) or "(none)"
    deferred_block = "\n".join(f"- {d}" for d in (prev_parsed.deferred if prev_parsed else [])) or "(none)"
    content = (
        f"# {today} - {project}/{topic}\n\n"
        f"## Goal\n\n"
        f"## Shipped\n\n"
        f"## Pending\n{pending_block}\n\n"
        f"## Deferred\n{deferred_block}\n"
    )
    if reason is not None:
        content += f"\n## Session\n- reason: {reason}\n- phase: \n- model: sonnet\n"
    note_path.write_text(content)


def _section_block(text: str, heading: str) -> Optional[str]:
    """Return the full block for a '## heading' (the heading line plus its body up to
    the next '## ' heading or EOF), or None if the heading is absent."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end]).rstrip()


def _replace_or_append_section(text: str, heading: str, block: str) -> str:
    """Return text with the '## heading' section replaced by block, or block appended
    if the heading is absent. Every other section is left untouched."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        base = text.rstrip()
        return (base + "\n\n" + block + "\n") if base else block + "\n"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    merged = lines[:start] + block.splitlines() + lines[end:]
    return "\n".join(merged).rstrip() + "\n"


def _sync_open_threads(topic_dir_path: Path) -> None:
    """Mirror the '## Open threads' section from pr-context.md into context.md.

    Deterministic and filesystem-only — the mechanical half, not the skill's judgment.
    Touches only that one section; the rest of context.md is preserved. Silent no-op if
    pr-context.md is absent or carries no such section. Idempotent.
    """
    pr_context = topic_dir_path / "pr-context.md"
    if not pr_context.exists():
        return
    try:
        block = _section_block(pr_context.read_text(), "## Open threads")
    except OSError:
        return
    if block is None:
        return
    context_md = topic_dir_path / "context.md"
    existing = context_md.read_text() if context_md.exists() else ""
    updated = _replace_or_append_section(existing, "## Open threads", block)
    if updated != existing:
        context_md.write_text(updated)


def _session_close_priming(
    orient_root: Path,
    project: str,
    topic: str,
    today: str,
    topic_dir_path: Path,
) -> str:
    """The mechanical context the judgment half needs to finish a close: the project-local
    NOTES.md sweep target (with the fixed entry prefix) and any per-topic context artifacts.

    Printed on stdout after the scaffold; the note path, date, and previous-note contents
    are already surfaced by the caller. Filesystem-only — no preflight re-run, no Haiku.
    """
    notes_md = orient_root / "notes" / project / "NOTES.md"
    lines = [
        "--- session close priming ---",
        f"NOTES.md sweep target: {notes_md}",
        f"  append each flagged item as: {today} <HH:MM>  [{project}]  <text>",
    ]
    artifacts = [
        topic_dir_path / name
        for name in ("pr-context.md", "context.md")
        if (topic_dir_path / name).exists()
    ]
    if artifacts:
        lines.append("topic context artifacts:")
        lines.extend(f"  - {a}" for a in artifacts)
    lines.append("---")
    return "\n".join(lines)


def run_session_note(
    project: str,
    topic: str,
    mode: str,
    orient_root: Path,
    reason: str = "natural-end",
    target_date: Optional[str] = None,
) -> None:
    """Run preflight, scaffold note, print path + context for in-conversation LLM.

    target_date (YYYY-MM-DD) backdates the note: it sets the written date (filename +
    header) and resolves rollforward from the note before that date. Intra-note
    timestamps stay real; a future date is rejected.
    """
    today = date.today().isoformat()
    if target_date is None:
        target_date = today
    if target_date > today:
        print(f"orient session: error:future-date given:{target_date} today:{today}", file=sys.stderr)
        sys.exit(1)

    preflight = run_preflight(project, topic, mode, orient_root, target_date=target_date)

    if preflight.mode.startswith("error") or preflight.mode == "ambiguous":
        print(f"orient session: {preflight.error or preflight.mode}", file=sys.stderr)
        sys.exit(1)

    note_date = target_date
    note_path = Path(preflight.note_path) if preflight.note_path else (
        topic_dir(orient_root, project, topic) / f"{note_date}.md"
    )
    note_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "checkpoint":
        if preflight.mode == "append":
            checkpoint_n = preflight.append_pass or 1
            checkpoint_block = f"\n### Checkpoint {checkpoint_n} - {preflight.called_at or ''}\n"
            with note_path.open("a") as f:
                f.write(checkpoint_block)
            print(f"note: {note_path}")
            return

        prev_parsed = _load_prev(preflight.prev_path)
        _write_skeleton(note_path, project, topic, note_date, reason=None, prev_parsed=prev_parsed)
        print(f"note: {note_path}")
        if prev_parsed and preflight.prev_path:
            print("\n--- previous note ---")
            print(Path(preflight.prev_path).read_text())
            print("---")

    else:  # close
        _sync_open_threads(note_path.parent)
        if preflight.mode == "append" and note_path.exists():
            session_section = f"\n## Session\n- reason: {reason}\n- phase: \n- model: sonnet\n"
            with note_path.open("a") as f:
                f.write(session_section)
            print(f"note: {note_path}")
            print(note_path.read_text())
        else:
            prev_parsed = _load_prev(preflight.prev_path)
            _write_skeleton(note_path, project, topic, note_date, reason=reason, prev_parsed=prev_parsed)
            print(f"note: {note_path}")
            if prev_parsed and preflight.prev_path:
                print("\n--- previous note ---")
                print(Path(preflight.prev_path).read_text())
                print("---")

        print("\n" + _session_close_priming(orient_root, project, topic, note_date, note_path.parent))


# Close reasons that warrant a flag when resuming a topic.
_ALARM_REASONS = {
    "budget-hit": "review before resuming",
    "context-limit": "compact before resuming",
}


def build_cold_brief(project: str, topic: str, prev: Optional[ParsedNote]) -> str:
    """Render where a topic left off: prev Goal/Pending/Deferred + any alarm reason.

    Returned as a string (no leading newline) so it can be embedded — e.g. as the
    topic-briefer skill's context token (orient.skill) — as well as printed."""
    if prev is None:
        return f"fresh start - no prior notes for {project}/{topic}"
    lines = [f"--- resuming {project}/{topic} (last note {prev.date}) ---"]
    if prev.goal:
        lines.append(f"Goal: {prev.goal}")
    if prev.pending:
        lines.append(f"Pending ({len(prev.pending)}):")
        lines.extend(f"- {item}" for item in prev.pending)
    if prev.deferred:
        lines.append(f"Deferred ({len(prev.deferred)}):")
        lines.extend(f"- {item}" for item in prev.deferred)
    if prev.session and prev.session.reason in _ALARM_REASONS:
        lines.append(f"[!] last session: {prev.session.reason} - {_ALARM_REASONS[prev.session.reason]}")
    lines.append("---")
    return "\n".join(lines)


def _print_cold_brief(project: str, topic: str, prev: Optional[ParsedNote]) -> None:
    """Surface where a topic left off: prev Goal/Pending/Deferred + any alarm reason."""
    print("\n" + build_cold_brief(project, topic, prev))


def run_session_start(project: str, topic: str, orient_root: Path) -> None:
    """Scaffold today's note and surface a cold brief of where the topic left off.

    Mechanical - no Haiku. Idempotent: if today's note already exists, re-surface
    context without adding a checkpoint marker or overwriting.
    """
    preflight = run_preflight(project, topic, "start", orient_root)

    if preflight.mode.startswith("error") or preflight.mode == "ambiguous":
        print(f"orient session: {preflight.error or preflight.mode}", file=sys.stderr)
        sys.exit(1)

    today = date.today().isoformat()
    note_path = Path(preflight.note_path) if preflight.note_path else (
        topic_dir(orient_root, project, topic) / f"{today}.md"
    )
    note_path.parent.mkdir(parents=True, exist_ok=True)

    prev_parsed = _load_prev(preflight.prev_path)

    # Starting a session marks the topic active for day start, regardless of mode.
    mark_active_topic(orient_root, project, topic)

    if preflight.mode == "append":
        # Already started today: idempotent re-surface, no checkpoint marker.
        print(f"session already started today: {note_path}")
        _print_cold_brief(project, topic, prev_parsed)
        return

    _write_skeleton(note_path, project, topic, today, reason=None, prev_parsed=prev_parsed)
    print(f"note: {note_path}")
    _print_cold_brief(project, topic, prev_parsed)
