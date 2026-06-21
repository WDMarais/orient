"""Typer app — all orient subcommands."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer

from orient.brief import run_brief
from orient.config import (
    EffectiveConfig,
    add_project_entry,
    config_path,
    load_effective_config,
    validate_workspace,
)
from orient.llm import get_llm_client
from orient.note import append_note
from orient.session_note import run_session_note, run_session_start
from orient.skill import run_skill_list, run_skill_show
from orient.state import (
    ProjectState,
    drop_active_topic,
    load_active_topics,
    load_state,
    mark_active_topic,
    save_state,
)
from orient.status import compute_status
from orient.sync import sync_all

app = typer.Typer(name="orient", no_args_is_help=True, add_completion=False)
config_app = typer.Typer(name="config", invoke_without_command=True, no_args_is_help=False, add_completion=False)
app.add_typer(config_app, name="config")

day_app = typer.Typer(name="day", no_args_is_help=True, add_completion=False)
app.add_typer(day_app, name="day")
session_app = typer.Typer(name="session", no_args_is_help=True, add_completion=False)
app.add_typer(session_app, name="session")
topic_app = typer.Typer(name="topic", no_args_is_help=True, add_completion=False)
app.add_typer(topic_app, name="topic")
skill_app = typer.Typer(name="skill", no_args_is_help=True, add_completion=False)
app.add_typer(skill_app, name="skill")


def _orient_root() -> Path:
    return Path(os.environ.get("ORIENT_ROOT", "~/.orient")).expanduser()


def _require_config(orient_root: Path) -> None:
    if not (orient_root / "workspace.toml").exists():
        typer.echo("orient is not configured yet")
        typer.echo("  orient config add-project <name> <path>")
        raise typer.Exit(code=1)


def _load_config(orient_root: Path) -> EffectiveConfig:
    _require_config(orient_root)
    return load_effective_config(orient_root)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

@app.command()
def sync(
    projects: Annotated[Optional[list[str]], typer.Argument()] = None,
    push: bool = typer.Option(False, "--push"),
) -> None:
    orient_root = _orient_root()
    cfg = _load_config(orient_root)

    if not cfg.projects:
        typer.echo("no projects configured")
        typer.echo("  orient config add-project <name> <path>")
        raise typer.Exit(code=1)

    targeted: set[str] = set(projects) if projects else set()
    for name in targeted:
        if not any(p.name == name for p in cfg.projects):
            typer.echo(f'project "{name}" not found')
            raise typer.Exit(code=1)

    to_sync = [p for p in cfg.projects if not targeted or p.name in targeted]
    states = load_state(orient_root)
    results = sync_all(to_sync, states, push_override=push, orient_root=orient_root)

    # Persist state
    new_states = dict(states)
    for r, entry in zip(results, to_sync):
        if r.error:
            continue
        try:
            head = subprocess.run(
                ["git", "-C", entry.path, "rev-parse", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip()
            if head:
                new_states[r.name] = ProjectState(
                    last_synced_hash=head,
                    last_synced_at=datetime.now(timezone.utc).isoformat(),
                )
        except Exception:
            pass
    save_state(orient_root, new_states)

    all_suppressed = all(r.suppressed for r in results)

    for r in results:
        if r.suppressed and r.name not in targeted and not r.observation_logged:
            continue

        entry = next((p for p in cfg.projects if p.name == r.name), None)
        suggest_backup = getattr(entry, "suggest_backup", True) if entry else True

        parts = [r.name]
        if r.error:
            parts.append(f"error: {r.error}")
        elif r.diverged:
            parts.append("diverged — manual merge required")
            if r.dirty:
                parts.append(f"dirty ({r.dirty_count} files)")
        else:
            if r.behind > 0:
                parts.append(f"+{r.behind}")
            if r.ahead > 0:
                parts.append(f"↑{r.ahead} pushed" if r.pushed else f"↑{r.ahead} (push off)")
            if r.dirty:
                parts.append(f"dirty ({r.dirty_count} files)")
            if r.modified and suggest_backup:
                parts.append("consider backup")
            if r.auto_commit_message:
                parts.append("auto-committed")
            if r.side_branch_name:
                parts.append(f"sidecar: {r.side_branch_name}")
        if not r.suppressed or r.observation_logged or r.name in targeted:
            typer.echo("  ".join(parts))

        if r.observation_logged:
            typer.echo(f"  observation logged → {orient_root / 'NOTES.md'}")

    if all_suppressed and not targeted:
        n = len(results)
        typer.echo(f"{n} project{'s' if n != 1 else ''} · all up-to-date")
        typer.echo(f"  see morning-brief.md for context")


# ---------------------------------------------------------------------------
# session — checkpoint / close
# ---------------------------------------------------------------------------

def _run_session(project: str, topic: str, mode: str, reason: str) -> None:
    orient_root = _orient_root()
    try:
        run_session_note(project, topic, mode, orient_root, reason=reason)
    except SystemExit as exc:
        raise typer.Exit(code=int(exc.code) if exc.code else 1)


@session_app.command("start")
def session_start(project: str, topic: str) -> None:
    orient_root = _orient_root()
    try:
        run_session_start(project, topic, orient_root)
    except SystemExit as exc:
        raise typer.Exit(code=int(exc.code) if exc.code else 1)


@session_app.command("checkpoint")
def session_checkpoint(project: str, topic: str) -> None:
    _run_session(project, topic, "checkpoint", reason="natural-end")


@session_app.command("close")
def session_close(
    project: str,
    topic: str,
    reason_arg: Annotated[Optional[str], typer.Argument()] = None,
) -> None:
    reason = "natural-end"
    if reason_arg and reason_arg.startswith("reason:"):
        reason = reason_arg[len("reason:"):]
    _run_session(project, topic, "close", reason=reason)


# ---------------------------------------------------------------------------
# topic — active-topics registry
# ---------------------------------------------------------------------------

@topic_app.command("mark")
def topic_mark(project: str, topic: str) -> None:
    orient_root = _orient_root()
    if mark_active_topic(orient_root, project, topic):
        typer.echo(f"marked active: {project}/{topic}")
    else:
        typer.echo(f"already active: {project}/{topic}")


@topic_app.command("drop")
def topic_drop(project: str, topic: str) -> None:
    orient_root = _orient_root()
    if drop_active_topic(orient_root, project, topic):
        typer.echo(f"dropped: {project}/{topic}")
    else:
        typer.echo(f"not active: {project}/{topic}")


@topic_app.command("list")
def topic_list() -> None:
    orient_root = _orient_root()
    topics = load_active_topics(orient_root)
    if not topics:
        typer.echo("no active topics")
        typer.echo("  orient topic mark <project> <topic>")
        return
    for t in topics:
        typer.echo(t)


# ---------------------------------------------------------------------------
# skill — local SKILL.md registry (emit-only)
# ---------------------------------------------------------------------------

@skill_app.command("list")
def skill_list() -> None:
    orient_root = _orient_root()
    config = _load_config(orient_root)
    run_skill_list(config)


@skill_app.command("show")
def skill_show(
    name: str,
    project: Annotated[Optional[str], typer.Argument()] = None,
    topic: Annotated[Optional[str], typer.Argument()] = None,
) -> None:
    orient_root = _orient_root()
    config = _load_config(orient_root)
    try:
        run_skill_show(name, orient_root, config, project=project, topic=topic)
    except SystemExit as exc:
        raise typer.Exit(code=int(exc.code) if exc.code else 1)


# ---------------------------------------------------------------------------
# day — start (morning brief)
# ---------------------------------------------------------------------------

@day_app.command("start")
def day_start(
    zdr: Annotated[
        bool,
        typer.Option(
            "--zdr",
            help="Zero-data-retention: make no API calls; brief prose degrades to "
            "deterministic fallback. Also triggered by ORIENT_NO_API=1.",
        ),
    ] = False,
) -> None:
    orient_root = _orient_root()
    _require_config(orient_root)

    note_root = orient_root / "notes"
    if note_root.exists() and not os.access(note_root, os.W_OK):
        typer.echo(f"cannot write to note root: {note_root}")
        raise typer.Exit(code=1)

    config = load_effective_config(orient_root)
    client = get_llm_client(config.llm, zdr=zdr)

    try:
        run_brief(orient_root, client=client)
    except SystemExit as exc:
        raise typer.Exit(code=int(exc.code) if exc.code else 1)
    except OSError as exc:
        typer.echo(f"cannot write: {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# note
# ---------------------------------------------------------------------------

@app.command()
def note(text: str) -> None:
    orient_root = _orient_root()

    if not text.strip():
        typer.echo("note text cannot be empty")
        raise typer.Exit(code=1)

    try:
        entry = append_note(text, cwd=Path.cwd(), orient_root=orient_root)
        typer.echo(f"note: {entry.notes_path}")
    except OSError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(
    projects: Annotated[Optional[list[str]], typer.Argument()] = None,
    local: bool = typer.Option(False, "--local"),
) -> None:
    orient_root = _orient_root()
    cfg = _load_config(orient_root)

    if not cfg.projects:
        typer.echo("no projects configured")
        typer.echo("  orient config add-project <name> <path>")
        raise typer.Exit(code=1)

    targeted: set[str] = set(projects) if projects else set()
    for name in targeted:
        if not any(p.name == name for p in cfg.projects):
            typer.echo(f'project "{name}" not found')
            raise typer.Exit(code=1)

    to_check = [p for p in cfg.projects if not targeted or p.name in targeted]
    states = load_state(orient_root)

    results = [
        compute_status(p, states.get(p.name), local_only=local)
        for p in to_check
    ]

    all_suppressed = all(r.suppressed for r in results)

    for r in results:
        if r.suppressed and r.name not in targeted:
            continue

        entry = next((p for p in cfg.projects if p.name == r.name), None)
        suggest_backup = getattr(entry, "suggest_backup", True) if entry else True

        parts = [r.name]
        if r.error:
            parts.append(f"error: {r.error}")
        elif r.diverged:
            parts.append("diverged — manual merge required")
            if r.dirty:
                parts.append(f"dirty ({r.dirty_count} files)")
        else:
            if r.behind > 0:
                parts.append(f"+{r.behind}")
            if r.ahead > 0:
                parts.append(f"↑{r.ahead} (push off)")
            if r.dirty:
                parts.append(f"dirty ({r.dirty_count} files)")
            if r.modified and suggest_backup:
                parts.append("consider backup")
        typer.echo("  ".join(parts))

    if all_suppressed and not targeted:
        n = len(results)
        typer.echo(f"{n} project{'s' if n != 1 else ''} · all up-to-date")

    if local:
        typer.echo("")
        typer.echo("Note: showing local remote-tracking refs (no fetch performed)")
        typer.echo("  orient status  — for current upstream state")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@config_app.callback()
def config_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        orient_root = _orient_root()
        ws = config_path(orient_root)
        typer.echo(f"Config file: {ws}")
        if not ws.exists():
            typer.echo("  (not yet created)")
        typer.echo("")
        typer.echo("Subcommands:")
        typer.echo("  orient config validate   — check workspace.toml for errors")
        typer.echo("  orient config show       — display resolved configuration")
        typer.echo("  orient config add-project <name> <path>")
        typer.echo("  orient config path       — print config file path")
        typer.echo("")
        typer.echo("Examples:")
        typer.echo("  orient config validate")
        typer.echo("  orient config add-project my-repo ~/code/my-repo")


@config_app.command("validate")
def config_validate(json_out: bool = typer.Option(False, "--json")) -> None:
    orient_root = _orient_root()
    ws = config_path(orient_root)
    result = validate_workspace(ws)

    if json_out:
        payload = {"ok": result.ok, "errors": result.errors, "warnings": result.warnings}
        typer.echo(json.dumps(payload))
        raise typer.Exit(code=0 if result.ok else 1)

    if result.ok:
        typer.echo(f"OK — {ws}")
        for w in result.warnings:
            typer.echo(f"  warning: {w}")
    else:
        for e in result.errors:
            typer.echo(f"error: {e}")
        raise typer.Exit(code=1)


@config_app.command("show")
def config_show(json_out: bool = typer.Option(False, "--json")) -> None:
    orient_root = _orient_root()
    cfg = _load_config(orient_root)

    if json_out:
        payload = {
            "orient_root": cfg.orient_root,
            "config_path": cfg.config_path,
            "defaults": cfg.defaults.model_dump(),
            "projects": [p.model_dump() for p in cfg.projects],
        }
        typer.echo(json.dumps(payload))
        return

    typer.echo(f"orient_root: {cfg.orient_root}")
    typer.echo(f"config: {cfg.config_path}")
    typer.echo(f"projects ({len(cfg.projects)}):")
    for p in cfg.projects:
        flags = []
        if p.push:
            flags.append("push")
        if p.pinned:
            flags.append("pinned")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        typer.echo(f"  {p.name}{flag_str}  {p.path}")


@config_app.command("add-project")
def config_add_project(
    name: str,
    path: str,
    push: bool = typer.Option(False, "--push"),
    pinned: bool = typer.Option(False, "--pinned"),
) -> None:
    orient_root = _orient_root()
    ws = config_path(orient_root)

    expanded = Path(path).expanduser().resolve()
    if not expanded.exists():
        typer.echo(f"path not found: {path}")
        raise typer.Exit(code=1)

    if ws.exists():
        try:
            cfg = load_effective_config(orient_root)
            if any(p.name == name for p in cfg.projects):
                typer.echo(f'"{name}" already exists - edit workspace.toml directly')
                raise typer.Exit(code=1)
        except typer.Exit:
            raise
        except Exception:
            pass

    add_project_entry(ws, name, str(expanded), push=push, pinned=pinned)
    typer.echo(f"added {name}  ({expanded})")


@config_app.command("path")
def config_path_cmd() -> None:
    orient_root = _orient_root()
    ws = config_path(orient_root)
    if ws.exists():
        typer.echo(str(ws))
    else:
        typer.echo(f"{ws}  (not yet created)")
