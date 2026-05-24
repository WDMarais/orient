"""Tests for orient sync behavioral contract.

Spec: spec-sync.md
Each test encodes one spec case at the logic level (SyncResult fields) rather than
the rendering level (terminal string). A thin TestRendering class covers coarse CLI output.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import pytest

from conftest import (
    run,
    make_workspace,
    make_state,
    make_git_repo,
    make_remote_pair,
    add_remote_commits,
    head_sha,
    _git,
    _configure_git_identity,
)


# ---------------------------------------------------------------------------
# Sketched data model
# TODO: fixture pattern throughout — replace with real types once orient.* exists
# ---------------------------------------------------------------------------

# TODO: fixture pattern — replace with real ProjectConfig from orient.config
@dataclass
class ProjectConfig:
    name: str
    path: str
    push: bool = False
    pinned: bool = False
    unit_type: str = "git"        # "git" | "vault"
    auto_commit: bool = False
    side_branch: bool = False
    suggest_backup: bool = True


# TODO: fixture pattern — replace with real SyncResult from orient.sync
@dataclass
class SyncResult:
    name: str
    branch: str = "main"
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    dirty_count: int = 0
    pushed: bool = False
    diverged: bool = False
    error: Optional[str] = None
    suppressed: bool = False
    # vault-specific
    modified: bool = False
    backup_recent: bool = False
    # opt-in facilitation
    auto_commit_message: Optional[str] = None   # TODO: fixture pattern
    side_branch_name: Optional[str] = None       # TODO: fixture pattern
    # feature branch
    ahead_of_base: int = 0                       # TODO: fixture pattern — feat↔base delta
    behind_of_base: int = 0                      # TODO: fixture pattern


# TODO: fixture pattern — replace with real ProjectState from orient.state
@dataclass
class ProjectState:
    last_synced_hash: str
    last_synced_at: str  # ISO-8601


# ---------------------------------------------------------------------------
# Stubs — swap for real imports when orient.sync exists
# ---------------------------------------------------------------------------

# TODO: from orient.sync import sync_project, sync_all
def sync_project(
    config: ProjectConfig,
    prior_state: Optional[ProjectState] = None,
    push_override: bool = False,       # TODO: fixture pattern — may be expressed as RunConfig
) -> SyncResult:
    raise NotImplementedError("orient.sync not yet implemented")  # TODO: wire up


def sync_all(
    configs: list[ProjectConfig],
    prior_states: dict[str, ProjectState],
    push_override: bool = False,
) -> list[SyncResult]:
    raise NotImplementedError("orient.sync not yet implemented")  # TODO: wire up


# ---------------------------------------------------------------------------
# First-run / missing config (CLI level)
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestFirstRun:
    def test_no_workspace_toml_shows_first_run_guidance(self, orient_root):
        result = run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert "orient is not configured yet" in result.output
        assert "orient config add-project" in result.output

    def test_empty_projects_list_shows_add_project_hint(self, empty_workspace):
        result = run("sync", env={"ORIENT_ROOT": str(empty_workspace)})  # TODO: wire up
        assert result.exit_code != 0
        assert "no projects configured" in result.output
        assert "orient config add-project" in result.output


# ---------------------------------------------------------------------------
# Suppression logic
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestSuppression:
    def test_clean_up_to_date_repo_is_suppressed(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        prior = ProjectState(last_synced_hash=head_sha(local), last_synced_at="2026-05-24T10:00:00")

        result = sync_project(ProjectConfig("repo", str(local)), prior)  # TODO: wire up
        assert result.suppressed is True

    def test_second_sync_after_successful_pull_is_suppressed(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 2)
        config = ProjectConfig("repo", str(local))

        first = sync_project(config)  # TODO: wire up
        assert first.suppressed is False

        second_prior = ProjectState(last_synced_hash=head_sha(local), last_synced_at="2026-05-24T10:01:00")
        second = sync_project(config, second_prior)  # TODO: wire up
        assert second.suppressed is True

    def test_vault_untouched_is_suppressed(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        prior = ProjectState(last_synced_hash="mtime:stable", last_synced_at="2026-05-24T10:00:00")  # TODO: fixture pattern — mtime hash format is architecture decision
        config = ProjectConfig("working-notes", str(vault), unit_type="vault")

        result = sync_project(config, prior)  # TODO: wire up
        assert result.suppressed is True

    def test_vault_recently_backed_up_is_suppressed(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "note.md").write_text("modified content")
        prior = ProjectState(last_synced_hash="mtime:old", last_synced_at="2026-05-24T10:00:00")  # TODO: fixture pattern
        config = ProjectConfig("working-notes", str(vault), unit_type="vault")

        result = sync_project(config, prior)  # TODO: wire up
        assert result.backup_recent is True
        assert result.suppressed is True


# ---------------------------------------------------------------------------
# Git repo sync results
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestGitRepoDelta:
    def test_behind_3_commits_clean(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 3)

        result = sync_project(ProjectConfig("repo-a", str(local)))  # TODO: wire up
        assert result.behind == 3
        assert result.ahead == 0
        assert result.dirty is False
        assert result.suppressed is False

    def test_ahead_1_push_enabled_pushes(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        (local / "new.txt").write_text("change")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "local commit")

        result = sync_project(ProjectConfig("repo-b", str(local), push=True))  # TODO: wire up
        assert result.ahead == 1
        assert result.pushed is True
        assert result.dirty is False

    def test_ahead_1_push_disabled_not_pushed(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        (local / "new.txt").write_text("change")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "local commit")

        result = sync_project(ProjectConfig("repo-c", str(local), push=False))  # TODO: wire up
        assert result.ahead == 1
        assert result.pushed is False

    def test_dirty_up_to_date_reports_dirty_count(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        for i in range(3):
            (local / f"dirty_{i}.txt").write_text("uncommitted")

        result = sync_project(ProjectConfig("repo-d", str(local)))  # TODO: wire up
        assert result.dirty is True
        assert result.dirty_count == 3
        assert result.behind == 0

    def test_dirty_and_behind_pull_is_not_attempted(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 2)
        (local / "dirty.txt").write_text("uncommitted")

        result = sync_project(ProjectConfig("repo-e", str(local)))  # TODO: wire up
        assert result.dirty is True
        assert result.behind == 2
        assert result.pushed is False

    def test_diverged_both_ahead_and_behind(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 1)
        (local / "local.txt").write_text("diverging")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "diverging commit")
        _git(local, "fetch")

        result = sync_project(ProjectConfig("repo-g", str(local)))  # TODO: wire up
        assert result.diverged is True
        assert result.ahead >= 1
        assert result.behind >= 1


# ---------------------------------------------------------------------------
# Feature branch
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestFeatureBranch:
    def test_feat_branch_in_sync_with_upstream_feat_shows_base_delta(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        _git(local, "checkout", "-b", "feat/cli")
        for i in range(5):
            (local / f"feat_{i}.txt").write_text("feature")
            _git(local, "add", ".")
            _git(local, "commit", "-m", f"feat {i}")
        _git(local, "push", "--set-upstream", "origin", "feat/cli")

        result = sync_project(ProjectConfig("repo-f", str(local)))  # TODO: wire up
        assert result.branch == "feat/cli"
        assert result.ahead == 0        # in sync with upstream/feat
        assert result.behind == 0
        assert result.ahead_of_base >= 5  # TODO: fixture pattern — ahead_of_base field is architecture decision

    def test_feat_branch_behind_upstream_feat_not_in_sync(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        _git(local, "checkout", "-b", "feat/cli")
        _git(local, "push", "--set-upstream", "origin", "feat/cli")
        pusher = tmp_path / "pusher"
        subprocess.run(["git", "clone", str(remote), str(pusher)], check=True, capture_output=True)
        _configure_git_identity(pusher)
        _git(pusher, "checkout", "feat/cli")
        for i in range(2):
            _git(pusher, "commit", "-m", f"upstream feat {i}", "--allow-empty")
        _git(pusher, "push")

        result = sync_project(ProjectConfig("repo-f", str(local)))  # TODO: wire up
        assert result.branch == "feat/cli"
        assert result.behind == 2


# ---------------------------------------------------------------------------
# Error states
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestErrorStates:
    def test_remote_unreachable_sets_error_field(self, tmp_path):
        local = make_git_repo(tmp_path / "repo-h")
        _git(local, "remote", "add", "origin", "https://192.0.2.1/unreachable.git")

        result = sync_project(ProjectConfig("repo-h", str(local)))  # TODO: wire up
        assert result.error is not None
        assert "remote unreachable" in result.error

    def test_path_not_found_sets_error_field(self, tmp_path):
        result = sync_project(ProjectConfig("repo-h", str(tmp_path / "missing")))  # TODO: wire up
        assert result.error is not None
        assert "path not found" in result.error

    def test_error_in_one_project_does_not_cancel_others(self, tmp_path):
        good, remote = make_remote_pair(tmp_path, "good")
        add_remote_commits(remote, tmp_path, 1)

        results = sync_all(
            [ProjectConfig("good", str(good)), ProjectConfig("bad", str(tmp_path / "missing"))],
            {},
        )  # TODO: wire up
        by_name = {r.name: r for r in results}
        assert by_name["bad"].error is not None
        assert by_name["good"].behind == 1


# ---------------------------------------------------------------------------
# Non-git units (vaults)
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestVaultUnits:
    def test_vault_modified_no_backup_surfaces_with_modified_flag(self, tmp_path):
        vault = tmp_path / "working-notes"
        vault.mkdir()
        (vault / "note.md").write_text("recent note")

        result = sync_project(ProjectConfig("working-notes", str(vault), unit_type="vault"))  # TODO: wire up
        assert result.modified is True
        assert result.backup_recent is False
        assert result.suppressed is False

    def test_vault_modified_suggest_backup_false_still_surfaces(self, tmp_path):
        vault = tmp_path / "working-notes"
        vault.mkdir()
        (vault / "note.md").write_text("recent note")
        config = ProjectConfig("working-notes", str(vault), unit_type="vault", suggest_backup=False)

        result = sync_project(config)  # TODO: wire up
        assert result.modified is True
        assert result.suppressed is False


# ---------------------------------------------------------------------------
# --push flag per-run override
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestPushFlag:
    def test_push_override_promotes_feature_branch_when_config_push_false(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        _git(local, "checkout", "-b", "feat/cli")
        (local / "feat.txt").write_text("feature")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "feat commit")
        _git(local, "push", "--set-upstream", "origin", "feat/cli")
        (local / "feat2.txt").write_text("more")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "ahead on feat")

        result = sync_project(ProjectConfig("repo-f", str(local), push=False), push_override=True)  # TODO: wire up
        assert result.pushed is True

    def test_push_override_does_not_push_default_branch_when_config_push_false(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        (local / "local.txt").write_text("change")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "commit on main")

        result = sync_project(ProjectConfig("repo-c", str(local), push=False), push_override=True)  # TODO: wire up
        assert result.pushed is False


# ---------------------------------------------------------------------------
# Opt-in facilitation (dirty + behind)
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestOptInFacilitation:
    def test_auto_commit_commits_dirty_state_then_pulls(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 2)
        (local / "wip.txt").write_text("in progress")

        result = sync_project(ProjectConfig("repo-e", str(local), auto_commit=True))  # TODO: wire up
        assert result.dirty is False
        assert result.behind == 0
        assert result.auto_commit_message is not None  # TODO: fixture pattern
        assert "IN-PROGRESS" in result.auto_commit_message

    def test_side_branch_preserves_dirty_tree_and_names_branch(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 2)
        (local / "wip.txt").write_text("in progress")

        result = sync_project(ProjectConfig("repo-e", str(local), side_branch=True))  # TODO: wire up
        assert result.dirty is True
        assert result.side_branch_name is not None  # TODO: fixture pattern
        assert result.side_branch_name.startswith("upstream-sync-")


# ---------------------------------------------------------------------------
# Project targeting (CLI level)
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestProjectTargeting:
    def test_unknown_project_name_errors(self, orient_root, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        make_workspace(orient_root, [{"name": "re-owm", "path": str(local)}])

        result = run("sync", "unknown-project", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert 'project "unknown-project" not found' in result.output

    def test_explicit_target_always_surfaces_even_when_suppressed(self, orient_root, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        make_workspace(orient_root, [{"name": "re-owm", "path": str(local)}])
        make_state(orient_root, {"re-owm": {"last_synced_hash": head_sha(local), "last_synced_at": "2026-05-24T10:00:00"}})  # TODO: fixture pattern

        result = run("sync", "re-owm", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "re-owm" in result.output


# ---------------------------------------------------------------------------
# Rendering (thin CLI-level smoke assertions)
# ---------------------------------------------------------------------------

@pytest.mark.sync
class TestRendering:
    def test_behind_renders_plus_notation(self, orient_root, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 3)
        make_workspace(orient_root, [{"name": "repo-a", "path": str(local)}])

        result = run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "+3" in result.output

    def test_pushed_renders_up_arrow_notation(self, orient_root, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        (local / "new.txt").write_text("change")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "commit")
        make_workspace(orient_root, [{"name": "repo-b", "path": str(local), "push": True}])

        result = run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "↑" in result.output
        assert "pushed" in result.output

    def test_all_suppressed_renders_summary_and_brief_pointer(self, orient_root, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        make_workspace(orient_root, [{"name": "repo", "path": str(local)}])
        make_state(orient_root, {"repo": {"last_synced_hash": head_sha(local), "last_synced_at": "2026-05-24T10:00:00"}})  # TODO: fixture pattern

        result = run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "all up-to-date" in result.output
        assert "morning-brief.md" in result.output

    def test_vault_modified_no_backup_renders_consider_backup(self, orient_root, tmp_path):
        vault = tmp_path / "working-notes"
        vault.mkdir()
        (vault / "note.md").write_text("recent note")
        make_workspace(orient_root, [{"name": "working-notes", "path": str(vault), "type": "vault"}])

        result = run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "consider backup" in result.output

    def test_vault_suggest_backup_false_omits_consider_backup(self, orient_root, tmp_path):
        vault = tmp_path / "working-notes"
        vault.mkdir()
        (vault / "note.md").write_text("recent note")
        make_workspace(orient_root, [{"name": "working-notes", "path": str(vault), "type": "vault", "suggest_backup": False}])

        result = run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "working-notes" in result.output
        assert "consider backup" not in result.output


# === SPEC GAPS ===
# TestFeatureBranch: ahead_of_base / behind_of_base field names are invented — architecture
#   must settle how the feat↔base delta is represented in SyncResult
# TestOptInFacilitation: auto_commit_message and side_branch_name are invented fields —
#   architecture may express these differently (e.g. a separate FacilitationResult)
# TestPushFlag: push_override parameter name is invented — may become part of a RunConfig
#   or be expressed as a second argument to sync_project
# TestSuppression.test_vault_*: mtime hash representation ("mtime:stable", "mtime:old")
#   is a placeholder — actual format is an architecture decision
# TestVaultUnits: no spec case specifies what "modified" means precisely (mtime delta
#   threshold, content hash change) — test asserts result.modified is True without
#   prescribing the detection mechanism
