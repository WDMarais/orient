"""Note parsing utilities - fork of agent-skills/lib/note_parser.py.

Changes from upstream: ticket→topic; parse_sections/extract_section take text not path;
added parse_bullets, parse_kv_bullets; find_latest_note takes explicit note_root.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def parse_sections(text: str) -> dict[str, str]:
    """Split markdown into {section_name: content} for each ## heading."""
    sections: dict[str, str] = {}
    current_heading: Optional[str] = None
    current_lines: list[str] = []

    for line in text.splitlines():
        m = re.match(r"^#{1,3} (.+)", line)
        if m:
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = m.group(1).strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def extract_section(text: str, section: str) -> Optional[str]:
    """Return content of a single named ## section; None if absent."""
    sections = parse_sections(text)
    section_lower = section.lower()
    for key, body in sections.items():
        if section_lower in key.lower():
            return body
    return None


def count_bullets(section_text: str) -> int:
    """Count '- item' lines in a section body."""
    return sum(1 for line in section_text.splitlines() if re.match(r"^\s*[-*•]\s+\S", line))


def parse_bullets(section_text: str) -> list[str]:
    """Return each '- item' stripped of the leading '- '."""
    result = []
    for line in section_text.splitlines():
        m = re.match(r"^\s*[-*•]\s+(.+)", line)
        if m:
            result.append(m.group(1).strip())
    return result


def parse_kv_bullets(section_text: str) -> dict[str, str]:
    """Parse '- key: value' lines → {'key': 'value'}."""
    result = {}
    for line in section_text.splitlines():
        m = re.match(r"^\s*[-*•]\s+([^:]+):\s*(.+)", line)
        if m:
            result[m.group(1).strip()] = m.group(2).strip()
    return result


def find_latest_note(note_root: Path, project: str, topic: str) -> Optional[Path]:
    """Return most recent YYYY-MM-DD.md under note_root/project/topic/, or None."""
    topic_dir = note_root / project / topic
    if not topic_dir.is_dir():
        return None
    notes = sorted(p for p in topic_dir.glob("????-??-??.md"))
    return notes[-1] if notes else None
