"""workspace.toml management - Pydantic models, tomllib reads, tomli-w writes."""
from __future__ import annotations

import tomllib
import tomli_w
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel


class ActivityModel(str, Enum):
    recency = "recency"


class UnitType(str, Enum):
    git = "git"
    vault = "vault"


class ProjectEntry(BaseModel):
    name: str
    path: str
    push: bool = False
    pinned: bool = False
    unit_type: UnitType = UnitType.git
    auto_commit: bool = False
    side_branch: bool = False
    suggest_backup: bool = True


class DefaultsConfig(BaseModel):
    note_root: str = ""
    push: bool = False
    active_days: int = 14
    activity_model: ActivityModel = ActivityModel.recency
    freshness_window: int = 60


class LLMConfig(BaseModel):
    """[llm] table: which provider backs orient's optional prose steps. `provider`
    is auto | anthropic | command | none. See orient.llm.get_llm_client."""
    provider: str = "auto"
    model: str = "claude-haiku-4-5-20251001"
    command: list[str] = ["claude", "-p"]
    timeout: int = 120


class SkillOverride(BaseModel):
    """A [[skills.override]] entry: pins kind/extends that frontmatter can't carry or
    that should win over it. External skills only; natives need no entry."""
    name: str
    kind: Optional[str] = None
    extends: Optional[str] = None


class SkillsConfig(BaseModel):
    """[skills] table: external-skill search paths + per-skill overrides. Natives are
    package data and are never configured here. See orient.skill.discover_skills."""
    paths: list[str] = []
    override: list[SkillOverride] = []


class EffectiveConfig(BaseModel):
    orient_root: str
    config_path: str
    defaults: DefaultsConfig
    projects: list[ProjectEntry]
    llm: LLMConfig = LLMConfig()
    skills: SkillsConfig = SkillsConfig()


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_KNOWN_PROJECT_KEYS = {
    "name", "path", "push", "pinned", "unit_type", "auto_commit",
    "side_branch", "suggest_backup",
}

_VALID_ACTIVITY_MODELS = {"recency"}


def _expand_path(raw: str, base: Path) -> str:
    """Expand a project path: absolute/tilde paths expand as-is; relative paths resolve against base."""
    if not raw:
        return raw
    p = Path(raw)
    if raw.startswith("~") or p.is_absolute():
        return str(p.expanduser().resolve())
    return str((base / raw).expanduser().resolve())


def config_path(orient_root: Path) -> Path:
    """Returns orient_root / 'workspace.toml'. Pure computation - no I/O."""
    return orient_root / "workspace.toml"


def validate_workspace(workspace_path: Path) -> ValidationResult:
    """Validate workspace.toml. Errors: duplicate name, invalid activity_model, TOML syntax, file not found."""
    errors: list[str] = []
    warnings: list[str] = []

    if not workspace_path.exists():
        return ValidationResult(ok=False, errors=["config not found: workspace.toml not found"])

    try:
        data = tomllib.loads(workspace_path.read_text())
    except tomllib.TOMLDecodeError as e:
        return ValidationResult(ok=False, errors=[f"TOML parse error: {e}"])

    defaults = data.get("defaults", {})
    activity_model = defaults.get("activity_model", "recency")
    if activity_model not in _VALID_ACTIVITY_MODELS:
        errors.append(f"invalid activity_model '{activity_model}': must be one of {sorted(_VALID_ACTIVITY_MODELS)}")

    workspace = data.get("workspace", {})
    base = Path(workspace.get("base", "~")).expanduser()

    projects: list[dict[str, Any]] = workspace.get("projects", data.get("projects", []))
    seen_names: set[str] = set()
    for entry in projects:
        name = entry.get("name", "")
        if name in seen_names:
            errors.append(f"duplicate project name '{name}'")
        else:
            seen_names.add(name)

        raw_path = entry.get("path", "")
        if raw_path:
            expanded = Path(_expand_path(raw_path, base))
            if not expanded.exists():
                warnings.append(f"project '{name}': path not found: {raw_path}")

        for key in entry:
            if key not in _KNOWN_PROJECT_KEYS:
                warnings.append(f"project '{name}': unknown key '{key}'")

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def load_effective_config(orient_root: Path) -> EffectiveConfig:
    """Parse workspace.toml, apply defaults, expand tildes in all project paths."""
    ws_path = config_path(orient_root)
    if not ws_path.exists():
        raise FileNotFoundError(
            f"orient is not configured yet - run: orient config add-project <name> <path>"
        )

    try:
        data = tomllib.loads(ws_path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"TOML parse error in workspace.toml: {e}") from e

    raw_defaults = data.get("defaults", {})
    defaults = DefaultsConfig(
        note_root=raw_defaults.get("note_root", ""),
        push=raw_defaults.get("push", False),
        active_days=raw_defaults.get("active_days", 14),
        activity_model=raw_defaults.get("activity_model", "recency"),
        freshness_window=raw_defaults.get("freshness_window", 60),
    )

    raw_llm = data.get("llm", {})
    llm = LLMConfig(
        provider=raw_llm.get("provider", "auto"),
        model=raw_llm.get("model", "claude-haiku-4-5-20251001"),
        command=raw_llm.get("command", ["claude", "-p"]),
        timeout=raw_llm.get("timeout", 120),
    )

    raw_skills = data.get("skills", {})
    skills = SkillsConfig(
        paths=raw_skills.get("paths", []),
        override=[SkillOverride(**o) for o in raw_skills.get("override", [])],
    )

    workspace = data.get("workspace", {})
    base = Path(workspace.get("base", "~")).expanduser()

    projects: list[ProjectEntry] = []
    for entry in workspace.get("projects", data.get("projects", [])):
        raw_path = entry.get("path", "")
        expanded_path = _expand_path(raw_path, base)
        projects.append(ProjectEntry(
            name=entry.get("name", ""),
            path=expanded_path,
            push=entry.get("push", defaults.push),
            pinned=entry.get("pinned", False),
            unit_type=entry.get("unit_type", entry.get("type", "git")),
            auto_commit=entry.get("auto_commit", False),
            side_branch=entry.get("side_branch", False),
            suggest_backup=entry.get("suggest_backup", True),
        ))

    return EffectiveConfig(
        orient_root=str(orient_root),
        config_path=str(ws_path),
        defaults=defaults,
        projects=projects,
        llm=llm,
        skills=skills,
    )


def add_project_entry(
    workspace_path: Path,
    name: str,
    path: str,
    push: bool = False,
    pinned: bool = False,
) -> None:
    """Append [[projects]] entry. Creates workspace.toml with [defaults] block if absent."""
    expanded = Path(path).expanduser()
    if not expanded.exists():
        raise ValueError(f"path not found: {path}")

    if workspace_path.exists():
        data = tomllib.loads(workspace_path.read_text())
        existing_names = [p.get("name") for p in data.get("projects", [])]
        if name in existing_names:
            raise ValueError(f'"{name}" already exists - edit workspace.toml directly to modify')
    else:
        data = {
            "defaults": {
                "push": False,
                "active_days": 14,
                "activity_model": "recency",
                "freshness_window": 60,
            },
            "projects": [],
        }

    entry: dict[str, Any] = {"name": name, "path": path}
    if push:
        entry["push"] = True
    if pinned:
        entry["pinned"] = True

    data.setdefault("projects", []).append(entry)
    workspace_path.write_bytes(tomli_w.dumps(data).encode())
