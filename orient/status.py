"""compute_status, should_fetch, StatusResult — read-only; no state writes."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from orient.config import ProjectEntry, UnitType
from orient.state import ProjectState


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
    fetched: bool = False
    ahead_of_base: int = 0
    behind_of_base: int = 0
    modified: bool = False
    backup_recent: bool = False


def should_fetch(
    prior_state: Optional[ProjectState],
    current_head: str,
    freshness_window_minutes: int = 60,
) -> bool:
    """True if: no prior state, outside freshness window, or HEAD diverged from stored hash."""
    if prior_state is None:
        return True
    if prior_state.last_synced_hash != current_head:
        return True
    try:
        last = datetime.fromisoformat(prior_state.last_synced_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - last).total_seconds() / 60
        return age_minutes >= freshness_window_minutes
    except Exception:
        return True


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def _git_check(repo: Path, *args: str) -> tuple[str, str, int]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _default_branch(repo: Path) -> str:
    """Best-effort detection of default branch (main or master)."""
    out = _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD")
    if out:
        return out.split("/")[-1]
    for candidate in ("main", "master"):
        rc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"origin/{candidate}"],
            capture_output=True,
        ).returncode
        if rc == 0:
            return candidate
    return "main"


def compute_status(
    config: ProjectEntry,
    prior_state: Optional[ProjectState] = None,
    local_only: bool = False,
    freshness_window_minutes: int = 60,
) -> StatusResult:
    """Compute status of a project. Read-only — does not write state."""
    project_path = Path(config.path)

    if not project_path.exists():
        return StatusResult(name=config.name, error="path not found")

    unit_type = config.unit_type if hasattr(config, "unit_type") else "git"
    if str(unit_type) == "vault":
        return _vault_status(config, prior_state)

    return _git_status(config, prior_state, local_only, freshness_window_minutes)


def _vault_status(
    config: ProjectEntry,
    prior_state: Optional[ProjectState],
) -> StatusResult:
    vault_path = Path(config.path)
    result = StatusResult(name=config.name)

    has_files = vault_path.is_dir() and any(True for _ in vault_path.iterdir())

    if prior_state is not None:
        # Previously synced — vault is backed up; files present means backup was recent
        result.backup_recent = has_files
        result.suppressed = True
        return result

    # No prior state: report modification if vault has content
    result.modified = has_files
    result.suppressed = not has_files
    return result


def _vault_mtime(vault_path: Path) -> str:
    try:
        mtime = vault_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return ""


def _git_status(
    config: ProjectEntry,
    prior_state: Optional[ProjectState],
    local_only: bool,
    freshness_window_minutes: int,
) -> StatusResult:
    repo = Path(config.path)
    result = StatusResult(name=config.name)

    # Current HEAD
    head_out, _, head_rc = _git_check(repo, "rev-parse", "HEAD")
    if head_rc != 0:
        result.error = "not a git repository"
        return result
    current_head = head_out

    # Branch name
    branch_out = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    result.branch = branch_out or "main"

    # Fetch if needed
    has_remote = bool(_git(repo, "remote"))
    fetched = False
    if not local_only and has_remote:
        if should_fetch(prior_state, current_head, freshness_window_minutes):
            fetch_out, fetch_err, fetch_rc = _git_check(repo, "fetch", "--quiet")
            if fetch_rc != 0:
                result.error = "remote unreachable"
                return result
            fetched = True
    result.fetched = fetched

    # Dirty check
    status_out = _git(repo, "status", "--porcelain")
    dirty_lines = [l for l in status_out.splitlines() if l.strip()]
    result.dirty = bool(dirty_lines)
    result.dirty_count = len(dirty_lines)

    # Ahead/behind vs tracking branch
    if has_remote:
        tracking = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if tracking:
            rev_list_out = _git(repo, "rev-list", "--left-right", "--count", f"HEAD...{tracking}")
            if rev_list_out:
                parts = rev_list_out.split()
                if len(parts) == 2:
                    result.ahead = int(parts[0])
                    result.behind = int(parts[1])

            if result.ahead > 0 and result.behind > 0:
                result.diverged = True

    # Feature branch: ahead/behind vs default branch
    if result.branch not in ("main", "master") and has_remote:
        default = _default_branch(repo)
        base_ref = f"origin/{default}"
        base_out = _git(repo, "rev-list", "--left-right", "--count", f"HEAD...{base_ref}")
        if base_out:
            parts = base_out.split()
            if len(parts) == 2:
                result.ahead_of_base = int(parts[0])
                result.behind_of_base = int(parts[1])

    # Suppression
    if (not result.dirty and result.ahead == 0 and result.behind == 0
            and not result.diverged and not result.modified and result.error is None):
        result.suppressed = True

    return result
