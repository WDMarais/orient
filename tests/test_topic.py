"""Tests for the active-topics registry and the orient topic command group.

Spec: spec.md (active-topics registry), spec-brief.md (day start consumes it).
The registry is an explicit "I'm working on this" set, persisted in state.toml as
project/topic keys, independent of note recency and day-close markers.
"""
from __future__ import annotations

from orient.state import (
    ProjectState,
    drop_active_topic,
    load_active_topics,
    load_state,
    mark_active_topic,
    save_state,
)

from conftest import run, make_workspace


# ---------------------------------------------------------------------------
# Registry (state layer)
# ---------------------------------------------------------------------------

def test_load_empty_when_absent(orient_root):
    assert load_active_topics(orient_root) == []


def test_mark_adds_topic(orient_root):
    assert mark_active_topic(orient_root, "orient", "day-close") is True
    assert load_active_topics(orient_root) == ["orient/day-close"]


def test_mark_idempotent(orient_root):
    assert mark_active_topic(orient_root, "orient", "cli") is True
    assert mark_active_topic(orient_root, "orient", "cli") is False
    assert load_active_topics(orient_root) == ["orient/cli"]


def test_drop_removes_topic(orient_root):
    mark_active_topic(orient_root, "orient", "cli")
    assert drop_active_topic(orient_root, "orient", "cli") is True
    assert load_active_topics(orient_root) == []


def test_drop_absent_returns_false(orient_root):
    assert drop_active_topic(orient_root, "orient", "nope") is False


def test_save_state_preserves_active_topics(orient_root):
    """A sync-style state write must not clobber the active-topics registry."""
    mark_active_topic(orient_root, "orient", "day-close")
    save_state(orient_root, {
        "owm": ProjectState(last_synced_hash="abc123", last_synced_at="2026-06-18T00:00:00"),
    })
    assert "orient/day-close" in load_active_topics(orient_root)
    assert "owm" in load_state(orient_root)


# ---------------------------------------------------------------------------
# CLI: orient topic mark / list / drop
# ---------------------------------------------------------------------------

def test_topic_cli_mark_list_drop(orient_root):
    env = {"ORIENT_ROOT": str(orient_root)}

    r = run("topic", "mark", "orient", "day-close", env=env)
    assert r.exit_code == 0
    assert "marked active" in r.output

    r = run("topic", "list", env=env)
    assert "orient/day-close" in r.output

    r = run("topic", "drop", "orient", "day-close", env=env)
    assert "dropped" in r.output

    r = run("topic", "list", env=env)
    assert "no active topics" in r.output


def test_topic_mark_already_active(orient_root):
    env = {"ORIENT_ROOT": str(orient_root)}
    run("topic", "mark", "orient", "cli", env=env)
    r = run("topic", "mark", "orient", "cli", env=env)
    assert "already active" in r.output


# ---------------------------------------------------------------------------
# session start auto-marks the topic active
# ---------------------------------------------------------------------------

def test_session_start_marks_topic_active(orient_root):
    make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
    run("session", "start", "orient", "cli", env={"ORIENT_ROOT": str(orient_root)})
    assert "orient/cli" in load_active_topics(orient_root)
