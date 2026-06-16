"""Shared fixtures and CLI stub for the orient test harness."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
from typer.testing import CliRunner

from orient.cli import app

_runner = CliRunner()


@dataclass
class InvokeResult:
    exit_code: int
    output: str


def run(*args: str, env: Optional[dict[str, str]] = None, input: Optional[str] = None) -> InvokeResult:
    result = _runner.invoke(app, list(args), env=env, input=input)
    return InvokeResult(result.exit_code, result.output)


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def make_workspace(orient_root: Path, projects: list[dict]) -> None:
    """Write workspace.toml with given [[projects]] entries into orient_root."""
    lines = [
        '[defaults]',
        'push = false',
        'active_days = 14',
        'activity_model = "recency"',
        "",
    ]
    for p in projects:
        lines.append("[[projects]]")
        for k, v in p.items():
            if isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, bool):
                lines.append(f'{k} = {"true" if v else "false"}')
            else:
                lines.append(f"{k} = {v}")
        lines.append("")
    (orient_root / "workspace.toml").write_text("\n".join(lines))


def make_state(orient_root: Path, entries: dict[str, dict]) -> None:
    """Write state.toml with per-project sync state into orient_root.

    entries: {project_name: {"last_synced_hash": str, "last_synced_at": ISO8601 str}}

    TODO: fixture pattern — exact state.toml TOML schema is an architecture decision.
    Replace with the real schema once architecture-proposer has settled it.
    """
    lines: list[str] = []
    for name, data in entries.items():
        lines.append(f"[project.{name}]")
        for k, v in data.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    (orient_root / "state.toml").write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _configure_git_identity(repo: Path) -> None:
    _git(repo, "config", "user.email", "test@orient.test")
    _git(repo, "config", "user.name", "Orient Test")


def make_git_repo(path: Path) -> Path:
    """Init a git repo at `path` with one commit on main, no remote."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _configure_git_identity(path)
    (path / "README.md").write_text("# test")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")
    return path


def make_remote_pair(tmp_path: Path, name: str = "repo") -> tuple[Path, Path]:
    """Return (local_clone, bare_remote) with one commit pushed to remote.

    Caller can add further commits to local or push from a second clone to
    simulate ahead/behind states.
    """
    remote = tmp_path / f"{name}.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)],
        check=True, capture_output=True,
    )
    seed = tmp_path / f"{name}_seed"
    seed.mkdir()
    subprocess.run(["git", "clone", str(remote), str(seed)], check=True, capture_output=True)
    _configure_git_identity(seed)
    (seed / "README.md").write_text("# test")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial")
    _git(seed, "push", "origin", "main")

    local = tmp_path / name
    subprocess.run(["git", "clone", str(remote), str(local)], check=True, capture_output=True)
    _configure_git_identity(local)
    return local, remote


def add_remote_commits(remote: Path, tmp_path: Path, n: int, name: str = "pusher") -> None:
    """Add `n` commits to `remote` via a temporary clone (simulates upstream advance)."""
    pusher = tmp_path / name
    subprocess.run(["git", "clone", str(remote), str(pusher)], check=True, capture_output=True)
    _configure_git_identity(pusher)
    for i in range(n):
        (pusher / f"upstream_{i}.txt").write_text(f"upstream commit {i}")
        _git(pusher, "add", ".")
        _git(pusher, "commit", "-m", f"upstream commit {i}")
    _git(pusher, "push", "origin", "main")


def head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orient_root(tmp_path: Path) -> Path:
    root = tmp_path / "orient_root"
    root.mkdir()
    return root


@pytest.fixture
def empty_workspace(orient_root: Path) -> Path:
    """workspace.toml present but zero [[projects]] entries."""
    make_workspace(orient_root, [])
    return orient_root
