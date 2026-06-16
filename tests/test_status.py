"""Tests for orient status behavioral contract.

Spec: spec-status.md
Status is read-only: no pull, no push. Same suppress rules and output format as sync,
but no transient delta indicators and with a freshness fast path on fetches.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

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
)


# ---------------------------------------------------------------------------
# Sketched data model
# TODO: fixture pattern — replace with real types from orient.status / orient.config
# ---------------------------------------------------------------------------

# TODO: fixture pattern — replace with real ProjectConfig from orient.config
@dataclass
class ProjectConfig:
    name: str
    path: str
    push: bool = False
    unit_type: str = "git"      # "git" | "vault"


# TODO: fixture pattern — replace with real ProjectState from orient.state
@dataclass
class ProjectState:
    last_synced_hash: str
    last_synced_at: str         # ISO-8601


# TODO: fixture pattern — replace with real StatusResult from orient.status
# Note: no pushed / auto_commit_message / side_branch_name — status is read-only
@dataclass
class StatusResult:
    name: str
    branch: str = "main"
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    dirty_count: int = 0
    diverged: bool = False
    error: Optional[str] = None
    suppressed: bool = False
    fetched: bool = False           # whether a network fetch was performed this run
    ahead_of_base: int = 0          # TODO: fixture pattern — feat↔base delta
    behind_of_base: int = 0
    modified: bool = False          # vault-specific
    backup_recent: bool = False


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

from orient.status import compute_status, should_fetch


def _ts(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


# ---------------------------------------------------------------------------
# Freshness fast path — should_fetch predicate
# ---------------------------------------------------------------------------

@pytest.mark.status
class TestFreshnessFastPath:
    def test_within_window_and_head_matches_no_fetch(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        sha = head_sha(local)
        prior = ProjectState(last_synced_hash=sha, last_synced_at=_ts(20))

        assert should_fetch(prior, sha, freshness_window_minutes=60) is False  # TODO: wire up

    def test_outside_window_fetches_regardless_of_head(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        sha = head_sha(local)
        prior = ProjectState(last_synced_hash=sha, last_synced_at=_ts(90))

        assert should_fetch(prior, sha, freshness_window_minutes=60) is True  # TODO: wire up

    def test_within_window_but_head_diverged_fetches(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        sha = head_sha(local)
        prior = ProjectState(last_synced_hash="deadbeef00000000", last_synced_at=_ts(20))

        assert should_fetch(prior, sha, freshness_window_minutes=60) is True  # TODO: wire up

    def test_no_prior_state_always_fetches(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)

        assert should_fetch(None, head_sha(local)) is True  # TODO: wire up

    def test_compute_status_records_whether_fetch_occurred(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        sha = head_sha(local)
        prior_fresh = ProjectState(last_synced_hash=sha, last_synced_at=_ts(20))
        prior_stale = ProjectState(last_synced_hash=sha, last_synced_at=_ts(90))

        fast = compute_status(ProjectConfig("repo", str(local)), prior_fresh)  # TODO: wire up
        slow = compute_status(ProjectConfig("repo", str(local)), prior_stale)  # TODO: wire up
        assert fast.fetched is False
        assert slow.fetched is True


# ---------------------------------------------------------------------------
# --local flag
# ---------------------------------------------------------------------------

@pytest.mark.status
class TestLocalFlag:
    def test_local_flag_skips_fetch_for_all_projects(self, orient_root, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        make_workspace(orient_root, [{"name": "repo", "path": str(local)}])

        result = run("status", "--local", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0
        # footer must be present on every --local run
        assert "local remote-tracking refs" in result.output
        assert "orient status" in result.output     # reminder to run full status

    def test_local_flag_compute_status_does_not_fetch(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        result = compute_status(
            ProjectConfig("repo", str(local)),
            local_only=True,
        )  # TODO: wire up
        assert result.fetched is False


# ---------------------------------------------------------------------------
# Status results
# ---------------------------------------------------------------------------

@pytest.mark.status
class TestStatusResults:
    def test_all_clean_up_to_date_suppressed(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        prior = ProjectState(last_synced_hash=head_sha(local), last_synced_at=_ts(20))

        result = compute_status(ProjectConfig("repo", str(local)), prior)  # TODO: wire up
        assert result.suppressed is True

    def test_dirty_3_files_not_suppressed(self, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        for i in range(3):
            (local / f"dirty_{i}.txt").write_text("uncommitted")

        result = compute_status(ProjectConfig("repo-a", str(local)))  # TODO: wire up
        assert result.dirty is True
        assert result.dirty_count == 3
        assert result.suppressed is False

    def test_behind_2_not_suppressed(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        add_remote_commits(remote, tmp_path, 2)

        result = compute_status(ProjectConfig("repo-b", str(local)))  # TODO: wire up
        assert result.behind == 2
        assert result.suppressed is False

    def test_ahead_1_push_false_not_suppressed(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        (local / "new.txt").write_text("local change")
        _git(local, "add", ".")
        _git(local, "commit", "-m", "local commit")

        result = compute_status(ProjectConfig("repo-c", str(local), push=False))  # TODO: wire up
        assert result.ahead == 1
        assert result.suppressed is False

    def test_feature_branch_in_sync_shows_base_delta(self, tmp_path):
        local, remote = make_remote_pair(tmp_path)
        _git(local, "checkout", "-b", "feat/cli")
        for i in range(5):
            (local / f"feat_{i}.txt").write_text("feature")
            _git(local, "add", ".")
            _git(local, "commit", "-m", f"feat {i}")
        _git(local, "push", "--set-upstream", "origin", "feat/cli")

        result = compute_status(ProjectConfig("repo-d", str(local)))  # TODO: wire up
        assert result.branch == "feat/cli"
        assert result.ahead == 0
        assert result.ahead_of_base >= 5    # TODO: fixture pattern — field name is architecture decision

    def test_path_not_found_sets_error(self, tmp_path):
        result = compute_status(ProjectConfig("repo-e", str(tmp_path / "missing")))  # TODO: wire up
        assert result.error is not None
        assert "path not found" in result.error


# ---------------------------------------------------------------------------
# Non-git vaults
# ---------------------------------------------------------------------------

@pytest.mark.status
class TestVaultStatus:
    def test_vault_modified_no_backup_not_suppressed(self, tmp_path):
        vault = tmp_path / "working-notes"
        vault.mkdir()
        (vault / "note.md").write_text("recent content")

        result = compute_status(ProjectConfig("working-notes", str(vault), unit_type="vault"))  # TODO: wire up
        assert result.modified is True
        assert result.backup_recent is False
        assert result.suppressed is False

    def test_vault_not_recently_modified_suppressed(self, tmp_path):
        vault = tmp_path / "working-notes"
        vault.mkdir()
        prior = ProjectState(last_synced_hash="mtime:stable", last_synced_at=_ts(20))  # TODO: fixture pattern

        result = compute_status(ProjectConfig("working-notes", str(vault), unit_type="vault"), prior)  # TODO: wire up
        assert result.suppressed is True


# ---------------------------------------------------------------------------
# Project targeting (CLI level)
# ---------------------------------------------------------------------------

@pytest.mark.status
class TestProjectTargeting:
    def test_explicit_target_always_surfaces_even_when_suppressed(self, orient_root, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        make_workspace(orient_root, [{"name": "re-owm", "path": str(local)}])
        make_state(orient_root, {"re-owm": {"last_synced_hash": head_sha(local), "last_synced_at": _ts(20)}})  # TODO: fixture pattern

        result = run("status", "re-owm", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "re-owm" in result.output

    def test_unknown_project_name_errors(self, orient_root, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        make_workspace(orient_root, [{"name": "re-owm", "path": str(local)}])

        result = run("status", "unknown-project", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert 'project "unknown-project" not found' in result.output


# ---------------------------------------------------------------------------
# First-run / missing config (CLI level)
# ---------------------------------------------------------------------------

@pytest.mark.status
class TestFirstRun:
    def test_no_workspace_toml_shows_first_run_guidance(self, orient_root):
        result = run("status", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert "orient is not configured yet" in result.output
        assert "orient config add-project" in result.output


# ---------------------------------------------------------------------------
# Rendering (thin CLI-level smoke assertions)
# ---------------------------------------------------------------------------

@pytest.mark.status
class TestRendering:
    def test_all_suppressed_shows_summary(self, orient_root, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        make_workspace(orient_root, [{"name": "repo", "path": str(local)}])
        make_state(orient_root, {"repo": {"last_synced_hash": head_sha(local), "last_synced_at": _ts(20)}})  # TODO: fixture pattern

        result = run("status", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "all up-to-date" in result.output

    def test_dirty_renders_file_count(self, orient_root, tmp_path):
        local, _ = make_remote_pair(tmp_path)
        for i in range(3):
            (local / f"dirty_{i}.txt").write_text("uncommitted")
        make_workspace(orient_root, [{"name": "repo-a", "path": str(local)}])

        result = run("status", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "dirty (3 files)" in result.output

    def test_vault_modified_renders_consider_backup(self, orient_root, tmp_path):
        vault = tmp_path / "working-notes"
        vault.mkdir()
        (vault / "note.md").write_text("recent content")
        make_workspace(orient_root, [{"name": "working-notes", "path": str(vault), "type": "vault"}])

        result = run("status", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "consider backup" in result.output


# === SPEC GAPS ===
# TestFreshnessFastPath: freshness_window_minutes default is 60 per spec, but spec doesn't
#   say whether this is configurable in workspace.toml — test passes it explicitly as a
#   parameter; architecture must decide if it comes from config or is hardcoded
# TestStatusResults.test_feature_branch: ahead_of_base field name is invented —
#   same gap as test_sync.py; deduplication at architecture time will settle the name
# TestVaultStatus.test_vault_not_recently_modified_suppressed: "mtime:stable" placeholder —
#   mtime hash representation is an architecture decision shared with test_sync.py
