"""NOTES.md append/parse."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from orient.config import ProjectEntry, load_effective_config


@dataclass
class NoteEntry:
    date: str   # YYYY-MM-DD
    time: str   # HH:MM
    tag: str    # project name or "untagged"
    text: str


def infer_tag(cwd: Path, configs: list[ProjectEntry]) -> str:
    """Return project name if cwd is at or under a configured project path; else 'untagged'."""
    cwd_resolved = cwd.resolve()
    for project in configs:
        project_path = Path(project.path).resolve()
        try:
            cwd_resolved.relative_to(project_path)
            return project.name
        except ValueError:
            continue
    return "untagged"


def _format_entry(entry: NoteEntry) -> str:
    return f"{entry.date} {entry.time}  [{entry.tag}]  {entry.text}\n"


def append_note(text: str, cwd: Path, orient_root: Path) -> NoteEntry:
    """Infer tag, format entry, append to NOTES.md (creates if absent)."""
    if not text:
        raise ValueError("note text cannot be empty")

    try:
        cfg = load_effective_config(orient_root)
        configs = cfg.projects
    except Exception:
        configs = []

    tag = infer_tag(cwd, configs)
    now = datetime.now()
    entry = NoteEntry(
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        tag=tag,
        text=text,
    )

    notes_path = orient_root / "NOTES.md"
    try:
        with notes_path.open("a") as f:
            f.write(_format_entry(entry))
    except OSError:
        raise OSError(f"cannot write to {notes_path} - check permissions")

    return entry


def parse_notes_md(path: Path) -> list[NoteEntry]:
    """Parse NOTES.md line-by-line. Each line: 'YYYY-MM-DD HH:MM  [tag]  text'."""
    if not path.exists():
        return []

    entries: list[NoteEntry] = []
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})  \[(.+?)\]  (.+)$")
    for line in path.read_text().splitlines():
        m = pattern.match(line.rstrip())
        if m:
            entries.append(NoteEntry(
                date=m.group(1),
                time=m.group(2),
                tag=m.group(3),
                text=m.group(4),
            ))
    return entries
