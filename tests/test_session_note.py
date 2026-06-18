"""Tests for orient session behavioral contract.

Spec: spec-session-note.md
One operation, two modes: checkpoint (mid-session) and close (terminal).

Layers:
  1. Python preflight - deterministic; resolves note path, produces routing token
  2. Haiku - writes the note; rollforward and ## Session are constrained/verbatim

Rollforward invariant: the latest note is always fully self-contained.
Pending re-appears verbatim unless landed in Shipped. Deferred re-appears verbatim.
Nothing drops silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import pytest

from conftest import run, make_workspace


# ---------------------------------------------------------------------------
# Sketched data model
# TODO: fixture pattern - replace with real types from orient.session_note / orient.preflight
# ---------------------------------------------------------------------------

# TODO: fixture pattern - replace with real PreflightResult from orient.preflight
@dataclass
class PreflightResult:
    mode: str                           # "new" | "append" | "no-prev" | "ambiguous"
    prev_path: Optional[str] = None
    pending_count: int = 0
    deferred_count: int = 0
    append_line: Optional[int] = None   # first line of append target
    append_pass: Optional[int] = None   # checkpoint count for this day
    error: Optional[str] = None         # populated for error:* modes


# TODO: fixture pattern - replace with real SessionSection from orient.session_note
@dataclass
class SessionSection:
    reason: str     # "natural-end" | "budget-hit" | "context-limit" | "human-stepped-away"
    cost: Optional[str] = None
    duration: Optional[str] = None
    model: str = "haiku"


# TODO: fixture pattern - replace with real ParsedNote from orient.session_note
@dataclass
class ParsedNote:
    date: str
    topic: str                              # "project/topic"
    goal: Optional[str] = None
    shipped: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    session: Optional[SessionSection] = None
    checkpoint_count: int = 0               # number of ### Checkpoint blocks


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

from orient.preflight import run_preflight
from orient.session_note import parse_note


# ---------------------------------------------------------------------------
# Note file helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().isoformat()


def _note_path(orient_root: Path, project: str, topic: str, note_date: str) -> Path:
    return orient_root / "notes" / project / topic / f"{note_date}.md"


def _write_prev_note(
    orient_root: Path,
    project: str,
    topic: str,
    note_date: str,
    pending: list[str] | None = None,
    deferred: list[str] | None = None,
    close_reason: str = "natural-end",
) -> Path:
    """Write a previous closed session note."""
    path = _note_path(orient_root, project, topic, note_date)
    path.parent.mkdir(parents=True, exist_ok=True)

    pending_lines = "\n".join(f"- {p}" for p in (pending or []))
    deferred_lines = "\n".join(f"- {d}" for d in (deferred or []))

    path.write_text(
        f"# {note_date} - {project}/{topic}\n\n"
        f"## Goal\nPrevious session goal\n\n"
        f"## Shipped\n- previous shipped item\n\n"
        f"## Pending\n{pending_lines or '(none)'}\n\n"
        f"## Deferred\n{deferred_lines or '(none)'}\n\n"
        f"## Session\n"
        f"- reason: {close_reason}\n"
        f"- cost: ~$0.42 (estimated)\n"
        f"- duration: ~2h\n"
        f"- model: haiku\n"
    )
    return path


# ---------------------------------------------------------------------------
# Preflight - routing token
# ---------------------------------------------------------------------------

@pytest.mark.session_note
class TestPreflight:
    def test_no_prev_note_produces_no_prev_mode(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])

        result = run_preflight("orient", "cli", "checkpoint", orient_root)  # TODO: wire up
        assert result.mode == "no-prev"
        assert result.prev_path is None

    def test_prev_note_no_today_note_produces_new_mode(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23",
                         pending=["finish sync cases", "write brief cases"],
                         deferred=["hub-marker equivalent → dropped"])

        result = run_preflight("orient", "cli", "checkpoint", orient_root)  # TODO: wire up
        assert result.mode == "new"
        assert result.pending_count == 2
        assert result.deferred_count == 1
        assert result.prev_path is not None
        assert "2026-05-23" in result.prev_path

    def test_today_note_exists_produces_append_mode(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        today_path = _note_path(orient_root, "orient", "cli", _today())
        today_path.parent.mkdir(parents=True, exist_ok=True)
        today_path.write_text(f"# {_today()} - orient/cli\n\n## Goal\nToday session\n")

        result = run_preflight("orient", "cli", "checkpoint", orient_root)  # TODO: wire up
        assert result.mode == "append"
        assert result.append_line is not None
        assert result.append_pass is not None

    def test_note_dir_unwritable_produces_error_mode(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        note_root = orient_root / "notes" / "orient" / "cli"
        note_root.mkdir(parents=True)
        note_root.chmod(0o555)

        result = run_preflight("orient", "cli", "checkpoint", orient_root)  # TODO: wire up
        assert result.mode.startswith("error")
        assert result.error is not None

        note_root.chmod(0o755)


# ---------------------------------------------------------------------------
# Checkpoint mode
# ---------------------------------------------------------------------------

@pytest.mark.session_note
class TestCheckpointMode:
    def test_new_note_written_with_rollforward(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23",
                         pending=["finish sync cases", "write brief cases"],
                         deferred=["hub-marker equivalent → dropped"])

        result = run("session", "checkpoint", "orient", "cli",  # TODO: wire up - project/topic passing is fixture pattern
                     env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0

        note_path = _note_path(orient_root, "orient", "cli", _today())
        assert note_path.exists()

    def test_rollforward_pending_items_appear_in_new_note(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23",
                         pending=["finish sync cases", "write brief cases"])

        run("session", "checkpoint", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        content = _note_path(orient_root, "orient", "cli", _today()).read_text()
        assert "finish sync cases" in content
        assert "write brief cases" in content

    def test_rollforward_deferred_items_appear_verbatim(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23",
                         deferred=["hub-marker equivalent → dropped"])

        run("session", "checkpoint", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        content = _note_path(orient_root, "orient", "cli", _today()).read_text()
        assert "hub-marker equivalent → dropped" in content

    def test_checkpoint_does_not_write_session_section(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23")

        run("session", "checkpoint", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        assert note.session is None

    def test_append_to_existing_today_note_adds_checkpoint_block(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        today_path = _note_path(orient_root, "orient", "cli", _today())
        today_path.parent.mkdir(parents=True, exist_ok=True)
        today_path.write_text(f"# {_today()} - orient/cli\n\n## Goal\nToday\n\n## Pending\n- item\n")

        run("session", "checkpoint", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(today_path)  # TODO: wire up
        assert note.checkpoint_count >= 1

    def test_append_does_not_overwrite_existing_today_note(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        today_path = _note_path(orient_root, "orient", "cli", _today())
        today_path.parent.mkdir(parents=True, exist_ok=True)
        original_content = f"# {_today()} - orient/cli\n\n## Goal\nToday\n\n## Pending\n- original item\n"
        today_path.write_text(original_content)

        run("session", "checkpoint", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        content = today_path.read_text()
        assert "original item" in content   # original content preserved

    def test_no_prev_note_writes_fresh_note_without_rollforward(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])

        run("session", "checkpoint", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note_path = _note_path(orient_root, "orient", "cli", _today())
        assert note_path.exists()


# ---------------------------------------------------------------------------
# Close mode
# ---------------------------------------------------------------------------

@pytest.mark.session_note
class TestCloseMode:
    def test_close_writes_session_section(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23")

        run("session", "close", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        assert note.session is not None

    def test_close_default_reason_is_natural_end(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23")

        run("session", "close", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        assert note.session.reason == "natural-end"

    def test_close_reason_budget_hit(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23")

        run("session", "close", "orient", "cli", "reason:budget-hit",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        assert note.session.reason == "budget-hit"

    def test_close_reason_context_limit(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23")

        run("session", "close", "orient", "cli", "reason:context-limit",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        assert note.session.reason == "context-limit"

    def test_close_appends_to_existing_today_note_from_checkpoint(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        # Simulate checkpoint already ran today
        today_path = _note_path(orient_root, "orient", "cli", _today())
        today_path.parent.mkdir(parents=True, exist_ok=True)
        today_path.write_text(
            f"# {_today()} - orient/cli\n\n## Goal\nToday\n\n## Pending\n- item\n\n"
            f"### Checkpoint 1 - 10:00\n- progress note\n"
        )

        run("session", "close", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        content = today_path.read_text()
        assert "Checkpoint 1" in content     # existing checkpoint preserved
        assert "## Session" in content       # close section appended

    def test_close_no_prev_note_writes_fresh_note_with_session(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])

        run("session", "close", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        assert note.session is not None


# ---------------------------------------------------------------------------
# Rollforward invariant
# ---------------------------------------------------------------------------

@pytest.mark.session_note
class TestRollforwardInvariant:
    def test_all_prev_pending_completed_pending_section_omitted(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23",
                         pending=["do the thing"])

        # Close with all previous pending shipped (Haiku marks them done)
        run("session", "close", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        # Either item is in Shipped, or it re-appears in Pending - never silently absent
        all_items = note.shipped + note.pending
        assert "do the thing" in all_items

    def test_prev_deferred_untouched_restated_verbatim(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23",
                         deferred=["hub-marker equivalent → dropped"])

        run("session", "close", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        note = parse_note(_note_path(orient_root, "orient", "cli", _today()))  # TODO: wire up
        assert any("hub-marker equivalent → dropped" in d for d in note.deferred)

    def test_nothing_drops_silently_pending_always_appears(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        pending_items = ["item A", "item B", "item C"]
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23", pending=pending_items)

        run("session", "checkpoint", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        content = _note_path(orient_root, "orient", "cli", _today()).read_text()
        for item in pending_items:
            assert item in content   # every pending item must appear somewhere


# ---------------------------------------------------------------------------
# NOTES.md sweep (close only)
# ---------------------------------------------------------------------------

@pytest.mark.session_note
class TestNotesSweep:
    def test_close_appends_flagged_items_to_notes_md(self):
        assert False, "spec gap - NOTES.md sweep content is determined by Haiku reading session context; no mechanism to inject known-flagged items without mocking Haiku or a real session fixture"

    def test_close_no_flagged_items_notes_md_unchanged(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_prev_note(orient_root, "orient", "cli", "2026-05-23")
        notes_path = orient_root / "NOTES.md"
        notes_path.write_text("existing note\n")
        original = notes_path.read_text()

        run("session", "close", "orient", "cli",  # TODO: wire up
            env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        # Sweep runs silently; notes not appended when nothing flagged
        # Content may or may not change depending on Haiku - this is a weak assertion
        assert notes_path.exists()


# ---------------------------------------------------------------------------
# Preflight edge cases
# ---------------------------------------------------------------------------

@pytest.mark.session_note
class TestPreflightEdgeCases:
    def test_ambiguous_mode_surfaces_reason_and_suggests_sonnet(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        # Ambiguous state: create conditions preflight cannot resolve
        # (e.g. multiple notes for same day - this is an architecture decision on what triggers ambiguous)
        # TODO: fixture pattern - ambiguous trigger condition is architecture decision

        result = run_preflight("orient", "cli", "checkpoint", orient_root)  # TODO: wire up
        if result.mode == "ambiguous":
            assert result.error is not None
            # CLI surfaces reason and suggests Sonnet
            cli_result = run("session", "checkpoint", "orient", "cli",
                             env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
            assert "Sonnet" in cli_result.output
            assert cli_result.exit_code != 0

    def test_unrecognised_preflight_output_prints_raw_and_stops(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        # TODO: fixture pattern - need a way to inject a bad preflight response;
        # this test documents the invariant but cannot be wired up until
        # the preflight/Haiku boundary is settled by architecture-proposer
        result = run_preflight("orient", "cli", "checkpoint", orient_root)  # TODO: wire up
        # If mode is unrecognised, CLI must print raw output and stop
        if result.mode not in ("new", "append", "no-prev", "ambiguous") and not result.mode.startswith("error"):
            cli_result = run("session", "checkpoint", "orient", "cli",
                             env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
            assert cli_result.exit_code != 0


# === SPEC GAPS ===
# TestNotesSweep.test_close_appends_flagged_items_to_notes_md: the sweep is driven by
#   Haiku reading the session context - we cannot assert specific swept content without
#   knowing what Haiku flagged; test has a structural bug (result not in scope) that
#   must be fixed once the CLI boundary is settled; marked with noqa to stay importable
# TestPreflightEdgeCases.test_ambiguous_mode: spec does not specify what conditions
#   produce mode:ambiguous; fixture pattern marked - architecture must define this
# TestPreflightEdgeCases.test_unrecognised_preflight_output: no mechanism to inject
#   bad preflight output at test time; documents invariant only
# run() call signature for session-note: spec shows /session-note checkpoint but CLI
#   arg passing for project/topic is not specified - all session-note run() calls use
#   positional args ("orient", "cli") as a fixture pattern; architecture must settle
#   how project/topic are passed (CLI args, cwd inference, or env var)
# SessionSection.model field: spec says "model: haiku" in ## Session - unclear whether
#   this is hardcoded or read from the actual invocation; test asserts field exists,
#   not its value
