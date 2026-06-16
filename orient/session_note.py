"""Session note write logic - parse_note, run_session_note."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import anthropic

_TEMPLATE_DIR = Path(__file__).parent / "templates"

from orient.lib.note_parser import (
    parse_sections,
    parse_bullets,
    parse_kv_bullets,
    count_bullets,
    find_latest_note,
)
from orient.preflight import run_preflight


@dataclass
class SessionSection:
    reason: str
    phase: str = ""
    recommended_next_phase: Optional[str] = None
    cost: Optional[str] = None
    duration: Optional[str] = None
    model: str = "haiku"


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

    # Title line: "# YYYY-MM-DD - project/topic"
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
            model=kv.get("model", "haiku"),
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


def _build_checkpoint_prompt(
    preflight_mode: str,
    prev_path: Optional[str],
    pending_count: int,
    deferred_count: int,
    today: str,
    project: str,
    topic: str,
) -> str:
    prev_content = ""
    if prev_path and prev_path != "None":
        try:
            prev_content = Path(prev_path).read_text()
        except OSError:
            pass

    template = (_TEMPLATE_DIR / "checkpoint_prompt.md").read_text()
    return template.format(
        project=project,
        topic=topic,
        today=today,
        preflight_mode=preflight_mode,
        pending_count=pending_count,
        deferred_count=deferred_count,
        prev_content=prev_content or "(none)",
    )


def _build_close_prompt(
    preflight_mode: str,
    prev_path: Optional[str],
    pending_count: int,
    deferred_count: int,
    today: str,
    project: str,
    topic: str,
    reason: str,
    existing_content: Optional[str] = None,
) -> str:
    prev_content = ""
    if prev_path and prev_path != "None":
        try:
            prev_content = Path(prev_path).read_text()
        except OSError:
            pass

    existing = f"\nExisting today note to append to:\n{existing_content}\n" if existing_content else ""

    template = (_TEMPLATE_DIR / "close_prompt.md").read_text()
    return template.format(
        project=project,
        topic=topic,
        today=today,
        preflight_mode=preflight_mode,
        reason=reason,
        pending_count=pending_count,
        deferred_count=deferred_count,
        prev_content=prev_content or "(none)",
        existing=existing,
    )


def _write_template_note(
    note_path: Path,
    project: str,
    topic: str,
    today: str,
    mode: str,
    reason: str,
    prev_parsed: Optional["ParsedNote"] = None,
) -> None:
    """Write a deterministic rollforward note without Haiku."""
    pending_block = "\n".join(f"- {p}" for p in (prev_parsed.pending if prev_parsed else [])) or "(none)"
    deferred_block = "\n".join(f"- {d}" for d in (prev_parsed.deferred if prev_parsed else [])) or "(none)"
    content = (
        f"# {today} - {project}/{topic}\n\n"
        f"## Goal\n(carry forward from previous)\n\n"
        f"## Shipped\n(nothing yet)\n\n"
        f"## Pending\n{pending_block}\n\n"
        f"## Deferred\n{deferred_block}\n"
    )
    if mode == "close":
        content += f"\n## Session\n- reason: {reason}\n- model: haiku\n"
    note_path.write_text(content)


def run_session_note(
    project: str,
    topic: str,
    mode: str,
    orient_root: Path,
    reason: str = "natural-end",
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    """Run preflight, build prompt, write note (via Haiku or template fallback)."""
    use_haiku = client is not None or bool(os.getenv("ANTHROPIC_API_KEY"))
    if use_haiku and client is None:
        client = anthropic.Anthropic()

    preflight = run_preflight(project, topic, mode, orient_root)

    if preflight.mode.startswith("error") or preflight.mode == "ambiguous":
        print(f"orient session-note: {preflight.error or preflight.mode}", file=sys.stderr)
        sys.exit(1)

    today = date.today().isoformat()
    note_root = orient_root / "notes"
    note_path = Path(preflight.note_path) if preflight.note_path else (
        note_root / project / topic / f"{today}.md"
    )
    note_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "checkpoint":
        if preflight.mode == "append":
            checkpoint_n = preflight.append_pass or 1
            checkpoint_block = f"\n### Checkpoint {checkpoint_n} - {preflight.called_at or ''}\n"
            with note_path.open("a") as f:
                f.write(checkpoint_block)
            return

        # new or no-prev
        if not use_haiku:
            prev_parsed = None
            if preflight.prev_path:
                try:
                    prev_parsed = parse_note(Path(preflight.prev_path))
                except Exception:
                    pass
            _write_template_note(note_path, project, topic, today, mode, reason, prev_parsed)
            return

        prompt = _build_checkpoint_prompt(
            preflight.mode,
            preflight.prev_path,
            preflight.pending_count,
            preflight.deferred_count,
            today,
            project,
            topic,
        )
        response = client.messages.create(  # type: ignore[union-attr]
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        note_path.write_text(response.content[0].text)

    else:  # close
        if preflight.mode == "append" and note_path.exists():
            # Append session section only — no Haiku needed
            session_section = f"\n## Session\n- reason: {reason}\n- model: haiku\n"
            with note_path.open("a") as f:
                f.write(session_section)
            return

        # new or no-prev
        if not use_haiku:
            prev_parsed = None
            if preflight.prev_path:
                try:
                    prev_parsed = parse_note(Path(preflight.prev_path))
                except Exception:
                    pass
            _write_template_note(note_path, project, topic, today, mode, reason, prev_parsed)
            return

        existing_content = None
        if preflight.mode == "append" and note_path.exists():
            existing_content = note_path.read_text()

        prompt = _build_close_prompt(
            preflight.mode,
            preflight.prev_path,
            preflight.pending_count,
            preflight.deferred_count,
            today,
            project,
            topic,
            reason,
            existing_content,
        )
        response = client.messages.create(  # type: ignore[union-attr]
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        note_path.write_text(response.content[0].text)
