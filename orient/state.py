"""state.toml management — atomic read/write; single-backup MVP."""
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


def save_state(orient_root: Path, states: dict[str, ProjectState]) -> None:
    """Write atomically: tmp → rename. Keep .bak as single backup."""
    path = _state_path(orient_root)
    tmp = path.with_suffix(".toml.tmp")

    data: dict = {"project": {}}
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
