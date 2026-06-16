"""sync_project, sync_all — git pull/push + vault detection."""
from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from orient.config import ProjectEntry
from orient.note import append_note
from orient.state import ProjectState
from orient.status import _git, _git_check, _default_branch


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
    modified: bool = False
    backup_recent: bool = False
    auto_commit_message: Optional[str] = None
    side_branch_name: Optional[str] = None
    ahead_of_base: int = 0
    behind_of_base: int = 0


def sync_project(
    config: ProjectEntry,
    prior_state: Optional[ProjectState] = None,
    push_override: bool = False,
    orient_root: Optional[Path] = None,
) -> SyncResult:
    project_path = Path(config.path)
    if not project_path.exists():
        return SyncResult(name=config.name, error="path not found")

    unit_type = str(config.unit_type) if hasattr(config, "unit_type") else "git"
    if unit_type == "vault":
        return _sync_vault(config, prior_state)

    return _sync_git(config, prior_state, push_override, orient_root)


def _sync_vault(
    config: ProjectEntry,
    prior_state: Optional[ProjectState],
) -> SyncResult:
    vault_path = Path(config.path)
    result = SyncResult(name=config.name)
    has_files = vault_path.is_dir() and any(True for _ in vault_path.iterdir())

    if prior_state is not None:
        result.backup_recent = has_files
        result.suppressed = True
        return result

    result.modified = has_files
    result.suppressed = not has_files
    return result


def _sync_git(
    config: ProjectEntry,
    prior_state: Optional[ProjectState],
    push_override: bool,
    orient_root: Optional[Path],
) -> SyncResult:
    repo = Path(config.path)
    result = SyncResult(name=config.name)

    branch_out = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    result.branch = branch_out or "main"

    status_out = _git(repo, "status", "--porcelain")
    dirty_lines = [l for l in status_out.splitlines() if l.strip()]
    result.dirty = bool(dirty_lines)
    result.dirty_count = len(dirty_lines)

    has_remote = bool(_git(repo, "remote"))

    if not has_remote:
        if orient_root is not None:
            try:
                append_note(
                    f"{config.name}: no upstream configured",
                    cwd=repo,
                    orient_root=orient_root,
                )
            except Exception:
                pass
        result.suppressed = not result.dirty
        return result

    auto_commit = getattr(config, "auto_commit", False)
    side_branch = getattr(config, "side_branch", False)

    # auto_commit facilitation: commit dirty files, then fetch+pull for post-op state
    if result.dirty and auto_commit:
        _git(repo, "add", "-A")
        msg = f"IN-PROGRESS auto-commit {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        _git(repo, "commit", "-m", msg)
        result.auto_commit_message = msg
        result.dirty = False
        result.dirty_count = 0

        _git_check(repo, "fetch", "--quiet")
        tracking = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if tracking:
            _git_check(repo, "pull", "--no-rebase", "--quiet")
        result.behind = 0
        result.ahead = 0
        return result

    # side_branch facilitation: stash dirty tree on a sidecar branch, then pull
    if result.dirty and side_branch:
        branch_name = f"upstream-sync-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        _git(repo, "checkout", "-b", branch_name)
        result.side_branch_name = branch_name
        return result

    # Fetch
    fetch_out, fetch_err, fetch_rc = _git_check(repo, "fetch", "--quiet")
    if fetch_rc != 0:
        result.error = "remote unreachable"
        return result

    # Detect ahead/behind vs tracking branch
    tracking = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    original_behind = 0
    if tracking:
        rev_list_out = _git(repo, "rev-list", "--left-right", "--count", f"HEAD...{tracking}")
        if rev_list_out:
            parts = rev_list_out.split()
            if len(parts) == 2:
                result.ahead = int(parts[0])
                original_behind = int(parts[1])
                result.behind = original_behind

        if result.ahead > 0 and original_behind > 0:
            result.diverged = True

    # Pull if behind and not dirty and not diverged
    pulled = False
    if original_behind > 0 and not result.dirty and not result.diverged:
        pull_out, pull_err, pull_rc = _git_check(repo, "pull", "--ff-only", "--quiet")
        if pull_rc == 0:
            pulled = True
            # result.behind stays as original count (transient delta indicator)

    # Feature branch: ahead_of_base vs default branch
    default_branch = _default_branch(repo)
    is_default = result.branch in ("main", "master") or result.branch == default_branch
    if not is_default:
        base_ref = f"origin/{default_branch}"
        base_out = _git(repo, "rev-list", "--left-right", "--count", f"HEAD...{base_ref}")
        if base_out:
            parts = base_out.split()
            if len(parts) == 2:
                result.ahead_of_base = int(parts[0])
                result.behind_of_base = int(parts[1])

    # Push
    push_config = getattr(config, "push", False)
    should_push = push_config or (push_override and not is_default)
    if should_push and result.ahead > 0 and not result.dirty:
        push_out, push_err, push_rc = _git_check(repo, "push", "--quiet")
        if push_rc == 0:
            result.pushed = True

    # Suppression: nothing to do and nothing was done
    if (result.behind == 0 and result.ahead == 0 and not result.dirty
            and not result.diverged and result.error is None
            and not result.pushed and not pulled):
        result.suppressed = True

    return result


def sync_all(
    configs: list[ProjectEntry],
    prior_states: dict[str, ProjectState],
    push_override: bool = False,
    orient_root: Optional[Path] = None,
) -> list[SyncResult]:
    """Sync all projects in parallel. Results in config order."""
    results: dict[str, SyncResult] = {}

    def _run(cfg: ProjectEntry) -> SyncResult:
        return sync_project(cfg, prior_states.get(cfg.name), push_override, orient_root)

    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(_run, cfg): cfg.name for cfg in configs}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = SyncResult(name=name, error=str(e))

    return [results[cfg.name] for cfg in configs]
