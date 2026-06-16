"""Session close preflight — fork of agent-skills/lib/session_close_preflight.py.

Changes from upstream: ticket→topic; note_root passed explicitly (no NOTE_ROOT env var);
adapted from CLI script to callable route() returning a dict (no stdout token output).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from orient.lib.note_parser import find_latest_note, parse_sections, count_bullets


def route(
    project: str,
    topic: str,
    mode: str,       # "checkpoint" | "close"
    note_root: Path,
) -> dict[str, Any]:
    """Return routing dict consumed by orient.preflight.

    Keys: mode, prev_path, pending_count, deferred_count,
          append_line, append_pass, error, note_path, called_at.
    """
    today = date.today().strftime("%Y-%m-%d")
    called_at = datetime.now().strftime("%H:%M")
    topic_dir = note_root / project / topic
    today_path = topic_dir / f"{today}.md"

    try:
        topic_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return {
            "mode": f"error:no-note-dir",
            "error": f"no-note-dir path:{topic_dir}",
            "note_path": str(today_path),
            "called_at": called_at,
            "prev_path": None,
            "pending_count": 0,
            "deferred_count": 0,
            "append_line": None,
            "append_pass": None,
        }

    # Append mode: today's note already exists
    if today_path.exists():
        try:
            text = today_path.read_text()
            lines = text.splitlines()
            append_line = len(lines) + 2
            append_pass = sum(1 for l in lines if l.startswith("### Checkpoint")) + 2
        except OSError:
            return {
                "mode": "ambiguous",
                "error": f"unexpectedly-empty",
                "note_path": str(today_path),
                "called_at": called_at,
                "prev_path": None,
                "pending_count": 0,
                "deferred_count": 0,
                "append_line": None,
                "append_pass": None,
            }
        prev = find_latest_note(note_root, project, topic)
        # find_latest_note returns any note including today's; we want prev excl today
        prev_excl = _find_latest_excl(note_root, project, topic, today)
        return {
            "mode": "append",
            "note_path": str(today_path),
            "called_at": called_at,
            "prev_path": str(prev_excl) if prev_excl else None,
            "pending_count": 0,
            "deferred_count": 0,
            "append_line": append_line,
            "append_pass": append_pass,
            "error": None,
        }

    # No today note — check for previous
    prev = _find_latest_excl(note_root, project, topic, today)
    if prev is None:
        return {
            "mode": "no-prev",
            "note_path": str(today_path),
            "called_at": called_at,
            "prev_path": None,
            "pending_count": 0,
            "deferred_count": 0,
            "append_line": None,
            "append_pass": None,
            "error": None,
        }

    # New note with rollforward
    try:
        text = prev.read_text()
        sections = parse_sections(text)
    except Exception:
        return {
            "mode": "ambiguous",
            "error": "unrecognised",
            "note_path": str(today_path),
            "called_at": called_at,
            "prev_path": str(prev),
            "pending_count": 0,
            "deferred_count": 0,
            "append_line": None,
            "append_pass": None,
        }

    pending = count_bullets(sections.get("Pending", ""))
    deferred = count_bullets(
        sections.get("Deferred", "") or sections.get("Deferred / punted", "")
    )
    return {
        "mode": "new",
        "note_path": str(today_path),
        "called_at": called_at,
        "prev_path": str(prev),
        "pending_count": pending,
        "deferred_count": deferred,
        "append_line": None,
        "append_pass": None,
        "error": None,
    }


def _find_latest_excl(note_root: Path, project: str, topic: str, exclude_date: str) -> Path | None:
    """Return most recent note excluding a specific date."""
    topic_dir = note_root / project / topic
    if not topic_dir.is_dir():
        return None
    notes = sorted(
        p for p in topic_dir.glob("????-??-??.md")
        if p.stem != exclude_date
    )
    return notes[-1] if notes else None
