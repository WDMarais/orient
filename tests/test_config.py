"""Tests for orient config behavioral contract.

Spec: spec-config.md
Config commands validate, display, and scaffold workspace.toml — never act as a
key-value setter. Human edits TOML directly; orient config is a guardrail layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json

import pytest

from conftest import run, make_workspace


# ---------------------------------------------------------------------------
# Sketched data model
# TODO: fixture pattern — replace with real types from orient.config
# ---------------------------------------------------------------------------

# TODO: fixture pattern — replace with real ValidationResult from orient.config
@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# TODO: fixture pattern — replace with real ProjectEntry from orient.config
@dataclass
class ProjectEntry:
    name: str
    path: str
    push: bool = False
    pinned: bool = False
    unit_type: str = "git"


# TODO: fixture pattern — replace with real DefaultsConfig from orient.config
@dataclass
class DefaultsConfig:
    note_root: str
    push: bool = False
    active_days: int = 14
    activity_model: str = "recency"


# TODO: fixture pattern — replace with real EffectiveConfig from orient.config
@dataclass
class EffectiveConfig:
    orient_root: str
    config_path: str
    defaults: DefaultsConfig
    projects: list[ProjectEntry]


# ---------------------------------------------------------------------------
# Wired imports
# ---------------------------------------------------------------------------

from orient.config import (
    validate_workspace,
    load_effective_config,
    add_project_entry,
    config_path,
)


# ---------------------------------------------------------------------------
# orient config (no subcommand) — CLI level
# ---------------------------------------------------------------------------

@pytest.mark.config
class TestNoSubcommand:
    def test_lists_all_subcommands(self, orient_root):
        result = run("config", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0
        assert "validate" in result.output
        assert "show" in result.output
        assert "add-project" in result.output
        assert "path" in result.output

    def test_shows_config_file_path(self, orient_root):
        result = run("config", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert str(orient_root) in result.output

    def test_includes_usage_examples(self, orient_root):
        result = run("config", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "orient config validate" in result.output
        assert "orient config add-project" in result.output


# ---------------------------------------------------------------------------
# orient config validate
# ---------------------------------------------------------------------------

@pytest.mark.config
class TestValidate:
    def test_valid_config_all_paths_exist_returns_ok(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()
        make_workspace(orient_root, [{"name": "re-owm", "path": str(repo)}])

        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert result.ok is True
        assert result.errors == []

    def test_valid_config_reports_project_count(self, orient_root, tmp_path):
        repos = []
        for i in range(4):
            r = tmp_path / f"repo{i}"
            r.mkdir()
            repos.append(r)
        make_workspace(orient_root, [{"name": f"repo{i}", "path": str(r)} for i, r in enumerate(repos)])

        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert result.ok is True
        # CLI rendering: "OK — 4 projects, all paths valid"

    def test_duplicate_project_name_is_error(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()
        make_workspace(orient_root, [
            {"name": "re-owm", "path": str(repo)},
            {"name": "re-owm", "path": str(repo)},
        ])

        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert result.ok is False
        assert any("re-owm" in e and "duplicate" in e.lower() for e in result.errors)

    def test_project_path_not_found_is_warning_not_error(self, orient_root, tmp_path):
        make_workspace(orient_root, [{"name": "re-owm", "path": str(tmp_path / "missing")}])

        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert result.ok is True    # warnings don't make ok=False
        assert any("re-owm" in w and "path not found" in w for w in result.warnings)

    def test_unknown_key_in_project_entry_is_warning(self, orient_root):
        toml = '[defaults]\npush = false\nactive_days = 14\nactivity_model = "recency"\n\n[[projects]]\nname = "re-owm"\npath = "/tmp/re-owm"\ntypo_key = "oops"\n'
        (orient_root / "workspace.toml").write_text(toml)

        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert any("typo_key" in w and "re-owm" in w for w in result.warnings)

    def test_invalid_activity_model_is_error(self, orient_root):
        toml = '[defaults]\npush = false\nactive_days = 14\nactivity_model = "weekly"\n'
        (orient_root / "workspace.toml").write_text(toml)

        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert result.ok is False
        assert any("weekly" in e and "activity_model" in e for e in result.errors)

    def test_toml_syntax_error_is_error(self, orient_root):
        (orient_root / "workspace.toml").write_text("[defaults]\npush = \n")  # invalid TOML

        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert result.ok is False
        assert any("TOML" in e or "parse" in e.lower() for e in result.errors)

    def test_workspace_toml_not_found_is_error(self, orient_root):
        result = validate_workspace(orient_root / "workspace.toml")  # TODO: wire up
        assert result.ok is False
        assert any("not found" in e or "config not found" in e for e in result.errors)

    def test_json_flag_valid_config(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()
        make_workspace(orient_root, [{"name": "re-owm", "path": str(repo)}])

        result = run("config", "validate", "--json", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["errors"] == []
        assert payload["warnings"] == []

    def test_json_flag_invalid_config_exits_nonzero(self, orient_root, tmp_path):
        make_workspace(orient_root, [
            {"name": "re-owm", "path": str(tmp_path / "a")},
            {"name": "re-owm", "path": str(tmp_path / "b")},
        ])

        result = run("config", "validate", "--json", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert len(payload["errors"]) > 0


# ---------------------------------------------------------------------------
# orient config show
# ---------------------------------------------------------------------------

@pytest.mark.config
class TestShow:
    def test_show_includes_orient_root(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        config = load_effective_config(orient_root)  # TODO: wire up
        assert str(orient_root) in config.orient_root

    def test_show_resolves_defaults(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        config = load_effective_config(orient_root)  # TODO: wire up
        assert config.defaults.push is False
        assert config.defaults.active_days == 14
        assert config.defaults.activity_model == "recency"

    def test_show_lists_all_projects(self, orient_root, tmp_path):
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        repo_a.mkdir()
        repo_b.mkdir()
        make_workspace(orient_root, [
            {"name": "re-owm", "path": str(repo_a)},
            {"name": "agent-skills", "path": str(repo_b), "push": True},
        ])

        config = load_effective_config(orient_root)  # TODO: wire up
        names = [p.name for p in config.projects]
        assert "re-owm" in names
        assert "agent-skills" in names

    def test_show_project_push_flag_resolved(self, orient_root, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        make_workspace(orient_root, [{"name": "agent-skills", "path": str(repo), "push": True}])

        config = load_effective_config(orient_root)  # TODO: wire up
        project = next(p for p in config.projects if p.name == "agent-skills")
        assert project.push is True

    def test_show_json_flag_renders_cli(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        result = run("config", "show", "--json", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "projects" in payload
        assert "defaults" in payload


# ---------------------------------------------------------------------------
# orient config add-project
# ---------------------------------------------------------------------------

@pytest.mark.config
class TestAddProject:
    def test_adds_basic_entry_to_workspace_toml(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()
        make_workspace(orient_root, [])

        add_project_entry(orient_root / "workspace.toml", "re-owm", str(repo))  # TODO: wire up

        config = load_effective_config(orient_root)  # TODO: wire up
        assert any(p.name == "re-owm" for p in config.projects)

    def test_adds_entry_with_push_and_pinned_flags(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()
        make_workspace(orient_root, [])

        add_project_entry(orient_root / "workspace.toml", "re-owm", str(repo), push=True, pinned=True)  # TODO: wire up

        config = load_effective_config(orient_root)  # TODO: wire up
        project = next(p for p in config.projects if p.name == "re-owm")
        assert project.push is True
        assert project.pinned is True

    def test_duplicate_name_raises_error(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()
        make_workspace(orient_root, [{"name": "re-owm", "path": str(repo)}])

        result = run("config", "add-project", "re-owm", str(repo), env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert '"re-owm" already exists' in result.output
        assert "edit workspace.toml directly" in result.output

    def test_nonexistent_path_raises_error(self, orient_root, tmp_path):
        missing = str(tmp_path / "nonexistent")
        make_workspace(orient_root, [])

        result = run("config", "add-project", "re-owm", missing, env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert "path not found" in result.output
        assert missing in result.output

    def test_creates_workspace_toml_if_absent(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()
        workspace = orient_root / "workspace.toml"
        assert not workspace.exists()

        add_project_entry(workspace, "re-owm", str(repo))  # TODO: wire up

        assert workspace.exists()
        config = load_effective_config(orient_root)  # TODO: wire up
        assert any(p.name == "re-owm" for p in config.projects)

    def test_created_workspace_toml_includes_defaults_block(self, orient_root, tmp_path):
        repo = tmp_path / "re-owm"
        repo.mkdir()

        add_project_entry(orient_root / "workspace.toml", "re-owm", str(repo))  # TODO: wire up

        content = (orient_root / "workspace.toml").read_text()
        assert "[defaults]" in content


# ---------------------------------------------------------------------------
# orient config path
# ---------------------------------------------------------------------------

@pytest.mark.config
class TestConfigPath:
    def test_returns_workspace_toml_under_orient_root(self, orient_root):
        path = config_path(orient_root)  # TODO: wire up
        assert path == orient_root / "workspace.toml"

    def test_cli_prints_config_path(self, orient_root):
        result = run("config", "path", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0
        assert "workspace.toml" in result.output
        assert str(orient_root) in result.output

    def test_not_yet_created_notes_absence(self, orient_root):
        result = run("config", "path", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0
        assert "not yet created" in result.output

    def test_existing_file_does_not_show_not_yet_created(self, orient_root):
        make_workspace(orient_root, [])

        result = run("config", "path", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "not yet created" not in result.output


# === SPEC GAPS ===
# TestValidate.test_valid_config_reports_project_count: ValidationResult doesn't include
#   a project_count field — count is only surfaced in CLI rendering ("OK — 4 projects");
#   test asserts ok=True and leaves count to the rendering smoke test
# TestAddProject: spec says add-project validates path exists on disk — unclear whether
#   this check uses the literal path string or expands ~ first; test uses absolute paths
#   to avoid ambiguity; architecture must decide tilde expansion behaviour
# TestShow.test_show_json_flag_renders_cli: --json schema for "show" is described as
#   "machine-readable effective config" but field names are not specified; test only
#   checks top-level keys "projects" and "defaults" are present
