"""state.toml management - atomic read/write; single-backup MVP."""
from __future__ import annotations

import shutil
import tomllib
import tomli_w
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectState:
    last_synced_hash: str
    last_synced_at: str   # ISO-8601


def _state_path(orient_root: Path) -> Path:
    return orient_root / "state.toml"


def load_state(orient_root: Path) -> dict[str, ProjectState]:
    """Read state.toml; return {} if absent. Falls back to .bak if primary is corrupt."""
    path = _state_path(orient_root)
    bak = path.with_suffix(".toml.bak")

    def _parse(p: Path) -> dict[str, ProjectState] | None:
        try:
            data = tomllib.loads(p.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return None
        result: dict[str, ProjectState] = {}
        for name, entry in data.get("project", {}).items():
            result[name] = ProjectState(
                last_synced_hash=entry.get("last_synced_hash", ""),
                last_synced_at=entry.get("last_synced_at", ""),
            )
        return result

    if not path.exists():
        return {}

    states = _parse(path)
    if states is not None:
        return states

    if bak.exists():
        states = _parse(bak)
        if states is not None:
            return states

    return {}


def save_state(
    orient_root: Path,
    states: dict[str, ProjectState],
    active_topics: list[str] | None = None,
    last_day_close: str | None = None,
    skill_modes: dict[str, str] | None = None,
) -> None:
    """Write atomically: tmp → rename. Keep .bak as single backup.

    active_topics is preserved across writes: pass an explicit list to replace it,
    or None to carry forward whatever is on disk — so sync and other state writers
    do not clobber the active-topics registry. last_day_close (the day-close frontier
    date) and skill_modes (per-skill active mode) follow the same carry-forward rule.
    """
    path = _state_path(orient_root)
    tmp = path.with_suffix(".toml.tmp")

    if active_topics is None:
        active_topics = load_active_topics(orient_root)
    if last_day_close is None:
        last_day_close = load_last_day_close(orient_root)
    if skill_modes is None:
        skill_modes = load_skill_modes(orient_root)

    data: dict = {}
    if active_topics:
        data["active_topics"] = active_topics
    if last_day_close:
        data["last_day_close"] = last_day_close
    if skill_modes:
        data["skill_modes"] = skill_modes
    data["project"] = {}
    for name, state in states.items():
        data["project"][name] = {
            "last_synced_hash": state.last_synced_hash,
            "last_synced_at": state.last_synced_at,
        }

    tmp.write_bytes(tomli_w.dumps(data).encode())

    if path.exists():
        shutil.copy2(path, path.with_suffix(".toml.bak"))

    tmp.rename(path)


def update_project_state(orient_root: Path, project_name: str, state: ProjectState) -> None:
    """Load → patch one entry → save."""
    states = load_state(orient_root)
    states[project_name] = state
    save_state(orient_root, states)


# ---------------------------------------------------------------------------
# Active-topics registry — explicit "I'm working on this" set, project/topic keys.
# ---------------------------------------------------------------------------

def load_active_topics(orient_root: Path) -> list[str]:
    """Read the active_topics list ("project/topic" strings); [] if absent/corrupt."""
    path = _state_path(orient_root)
    bak = path.with_suffix(".toml.bak")

    def _parse(p: Path) -> list[str] | None:
        try:
            data = tomllib.loads(p.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return None
        return [t for t in data.get("active_topics", []) if isinstance(t, str)]

    if not path.exists():
        return []
    topics = _parse(path)
    if topics is not None:
        return topics
    if bak.exists():
        topics = _parse(bak)
        if topics is not None:
            return topics
    return []


def mark_active_topic(orient_root: Path, project: str, topic: str) -> bool:
    """Add project/topic to the active set. Returns False if already present."""
    key = f"{project}/{topic}"
    topics = load_active_topics(orient_root)
    if key in topics:
        return False
    topics.append(key)
    save_state(orient_root, load_state(orient_root), active_topics=topics)
    return True


def drop_active_topic(orient_root: Path, project: str, topic: str) -> bool:
    """Remove project/topic from the active set. Returns False if not present."""
    key = f"{project}/{topic}"
    topics = load_active_topics(orient_root)
    if key not in topics:
        return False
    save_state(orient_root, load_state(orient_root), active_topics=[t for t in topics if t != key])
    return True


# ---------------------------------------------------------------------------
# Day-close frontier — the date of the most recent promoted day marker. day close
# advances it; backfilling behind it never regresses it (spec-day-close.md).
# ---------------------------------------------------------------------------

def load_last_day_close(orient_root: Path) -> str | None:
    """Read the last_day_close date string; None if absent/corrupt."""
    path = _state_path(orient_root)
    bak = path.with_suffix(".toml.bak")

    def _parse(p: Path) -> str | None:
        try:
            data = tomllib.loads(p.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return None
        value = data.get("last_day_close")
        return value if isinstance(value, str) else None

    if not path.exists():
        return None
    value = _parse(path)
    if value is not None:
        return value
    if bak.exists():
        return _parse(bak)
    return None


def save_last_day_close(orient_root: Path, day_close_date: str) -> None:
    """Advance the day-close frontier pointer, preserving project state + active topics."""
    save_state(orient_root, load_state(orient_root), last_day_close=day_close_date)


# ---------------------------------------------------------------------------
# Per-skill active mode — {skill_name: level}. `orient skill mode <name> <level>`
# sets it; `orient skill show <name>` filters the body to it (spec-skill.md).
# ---------------------------------------------------------------------------

def load_skill_modes(orient_root: Path) -> dict[str, str]:
    """Read the skill_modes table ({skill: level}); {} if absent/corrupt."""
    path = _state_path(orient_root)
    bak = path.with_suffix(".toml.bak")

    def _parse(p: Path) -> dict[str, str] | None:
        try:
            data = tomllib.loads(p.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return None
        raw = data.get("skill_modes", {})
        if not isinstance(raw, dict):
            return {}
        return {k: v for k, v in raw.items() if isinstance(v, str)}

    if not path.exists():
        return {}
    modes = _parse(path)
    if modes is not None:
        return modes
    if bak.exists():
        modes = _parse(bak)
        if modes is not None:
            return modes
    return {}


def set_skill_mode(orient_root: Path, skill: str, level: str) -> None:
    """Set a skill's active mode, preserving all other state."""
    modes = load_skill_modes(orient_root)
    modes[skill] = level
    save_state(orient_root, load_state(orient_root), skill_modes=modes)


def clear_skill_mode(orient_root: Path, skill: str) -> bool:
    """Clear a skill's active mode. Returns False if none was set."""
    modes = load_skill_modes(orient_root)
    if skill not in modes:
        return False
    del modes[skill]
    save_state(orient_root, load_state(orient_root), skill_modes=modes)
    return True
