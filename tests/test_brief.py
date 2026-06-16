"""Tests for orient brief behavioral contract.

Spec: spec-brief.md
Brief has two layers:
  1. Python preflight - deterministic; reads notes, builds structured token for Haiku
  2. Haiku invocation - writes morning-brief.md; non-deterministic prose, deterministic frontmatter

Tests focus on the preflight layer and the frontmatter contract. Prose content is not
asserted beyond structural presence of required sections.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pytest

from conftest import run, make_workspace


# ---------------------------------------------------------------------------
# Sketched data model
# TODO: fixture pattern - replace with real types from orient.brief / orient.note
# ---------------------------------------------------------------------------

# TODO: fixture pattern - replace with real TopicPreflight from orient.brief
@dataclass
class TopicPreflight:
    topic: str          # "project/topic" e.g. "re-owm/mcp"
    note_path: str
    phase: str          # e.g. "harness-writer-complete", "case-interviewer-in-progress"
    pending: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)


# TODO: fixture pattern - replace with real PreflightToken from orient.brief
@dataclass
class PreflightToken:
    last_brief: str                 # YYYY-MM-DD
    active_topics: int
    topics: list[TopicPreflight]
    notes_since_last_brief: list[str] = field(default_factory=list)  # raw note lines


# TODO: fixture pattern - replace with real TopicAction from orient.brief
@dataclass
class TopicAction:
    topic: str
    phase: str
    skill: str
    invocation: str
    priority: int


# TODO: fixture pattern - replace with real BriefFrontmatter from orient.brief
@dataclass
class BriefFrontmatter:
    date: str
    last_brief: str
    active_topics: int
    next_actions: list[TopicAction]
    notes_unreviewed: int


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

# TODO: from orient.brief import build_preflight_token, get_next_action, parse_brief_frontmatter, run_brief
def build_preflight_token(
    orient_root: Path,
    last_brief_date: Optional[str] = None,
    active_days: int = 14,
) -> PreflightToken:
    raise NotImplementedError("orient.brief not yet implemented")  # TODO: wire up


def get_next_action(phase: str, project: str, topic: str) -> TopicAction:
    """Phase → next_action lookup. Mechanical - not reasoning."""
    raise NotImplementedError("orient.brief not yet implemented")  # TODO: wire up


def parse_brief_frontmatter(brief_path: Path) -> BriefFrontmatter:
    raise NotImplementedError("orient.brief not yet implemented")  # TODO: wire up


# ---------------------------------------------------------------------------
# Note file helpers
# ---------------------------------------------------------------------------

def _write_note(
    orient_root: Path,
    project: str,
    topic: str,
    note_date: str,
    phase_line: str = "natural-end",
    pending: list[str] | None = None,
    deferred: list[str] | None = None,
    close_reason: str = "natural-end",
) -> Path:
    """Write a minimal session note file in the correct location."""
    note_dir = orient_root / "notes" / project / topic
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / f"{note_date}.md"

    pending_block = "\n".join(f"- {p}" for p in (pending or [])) or "(none)"
    deferred_block = "\n".join(f"- {d}" for d in (deferred or [])) or "(none)"

    note_path.write_text(
        f"# {note_date} - {project}/{topic}\n\n"
        f"## Goal\nTest session\n\n"
        f"## Shipped\n- did things\n\n"
        f"## Pending\n{pending_block}\n\n"
        f"## Deferred\n{deferred_block}\n\n"
        f"## Session\n"
        f"- reason: {close_reason}\n"
        f"- phase: {phase_line}\n"
        f"- model: haiku\n"
    )
    return note_path


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# Phase → next_action lookup (mechanical table)
# ---------------------------------------------------------------------------

@pytest.mark.brief
class TestPhaseNextActionLookup:
    @pytest.mark.parametrize("phase,expected_skill,expected_invocation_fragment", [
        ("case-interviewer-in-progress",  "case-interviewer",    "continue /case-interviewer"),
        ("case-interviewer-complete",     "harness-writer",      "/harness-writer"),
        ("harness-writer-complete",       "architecture-proposer", "/architecture-proposer"),
        ("architecture-proposer-complete","implementation-writer", "/implementation-writer"),
        ("implementation-writer-in-progress", "implementation-writer", "continue /implementation-writer"),
        ("implementation-writer-complete","verify",              "/verify"),
    ])
    def test_phase_maps_to_correct_skill_and_invocation(self, phase, expected_skill, expected_invocation_fragment):
        action = get_next_action(phase, "re-owm", "mcp")  # TODO: wire up
        assert action.skill == expected_skill
        assert expected_invocation_fragment in action.invocation

    def test_unknown_phase_maps_to_open_note_action(self):
        action = get_next_action("unknown", "re-owm", "mcp")  # TODO: wire up
        assert "open" in action.invocation or action.skill == "unknown"  # TODO: tighten once spec gap resolved

    def test_invocation_includes_project_and_topic_for_skill_commands(self):
        action = get_next_action("harness-writer-complete", "re-owm", "mcp")  # TODO: wire up
        assert "re-owm" in action.invocation
        assert "mcp" in action.invocation


# ---------------------------------------------------------------------------
# Preflight token - structural pass
# ---------------------------------------------------------------------------

@pytest.mark.brief
class TestPreflightToken:
    def test_active_topic_within_active_days_included(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(3), phase_line="harness-writer-complete")

        token = build_preflight_token(orient_root, active_days=14)  # TODO: wire up
        topics = [t.topic for t in token.topics]
        assert "re-owm/mcp" in topics

    def test_topic_beyond_active_days_excluded_when_not_pinned(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "old-topic", _days_ago(30), phase_line="natural-end")

        token = build_preflight_token(orient_root, active_days=14)  # TODO: wire up
        topics = [t.topic for t in token.topics]
        assert "re-owm/old-topic" not in topics

    def test_pinned_project_always_included_regardless_of_activity(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm", "pinned": True}])
        _write_note(orient_root, "re-owm", "dormant", _days_ago(30), phase_line="natural-end")

        token = build_preflight_token(orient_root, active_days=14)  # TODO: wire up
        topics = [t.topic for t in token.topics]
        assert "re-owm/dormant" in topics

    def test_active_topics_count_matches_included_topics(self, orient_root):
        make_workspace(orient_root, [
            {"name": "re-owm", "path": "/tmp/re-owm"},
            {"name": "orient", "path": "/tmp/orient"},
        ])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(3))
        _write_note(orient_root, "orient", "cli", _days_ago(1))

        token = build_preflight_token(orient_root, active_days=14)  # TODO: wire up
        assert token.active_topics == len(token.topics) == 2

    def test_pending_items_extracted_from_note(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(2),
                    pending=["run /architecture-proposer"])

        token = build_preflight_token(orient_root, active_days=14)  # TODO: wire up
        topic = next(t for t in token.topics if t.topic == "re-owm/mcp")
        assert "run /architecture-proposer" in topic.pending

    def test_deferred_items_extracted_from_note(self, orient_root):
        make_workspace(orient_root, [{"name": "orient", "path": "/tmp/orient"}])
        _write_note(orient_root, "orient", "cli", _days_ago(1),
                    deferred=["hub-marker equivalent → dropped"])

        token = build_preflight_token(orient_root, active_days=14)  # TODO: wire up
        topic = next(t for t in token.topics if t.topic == "orient/cli")
        assert any("hub-marker" in d for d in topic.deferred)

    def test_notes_since_last_brief_included(self, orient_root):
        make_workspace(orient_root, [])
        notes_path = orient_root / "NOTES.md"
        notes_path.write_text(
            f"{_today()} 14:30  [orient]  preflight exits 0 even when note dir is unwritable\n"
            f"{_today()} 14:31  [untagged]  sync stalled on unreachable remote\n"
        )

        token = build_preflight_token(orient_root, last_brief_date=_days_ago(1))  # TODO: wire up
        assert len(token.notes_since_last_brief) == 2

    def test_notes_before_last_brief_not_included(self, orient_root):
        make_workspace(orient_root, [])
        notes_path = orient_root / "NOTES.md"
        old_date = _days_ago(5)
        notes_path.write_text(f"{old_date} 10:00  [orient]  old note\n")

        token = build_preflight_token(orient_root, last_brief_date=_days_ago(2))  # TODO: wire up
        assert len(token.notes_since_last_brief) == 0

    def test_absent_notes_md_gives_zero_unreviewed(self, orient_root):
        make_workspace(orient_root, [])

        token = build_preflight_token(orient_root, last_brief_date=_days_ago(1))  # TODO: wire up
        assert len(token.notes_since_last_brief) == 0


# ---------------------------------------------------------------------------
# Brief frontmatter - output contract
# ---------------------------------------------------------------------------

@pytest.mark.brief
class TestBriefFrontmatter:
    def test_frontmatter_has_required_top_level_fields(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1), phase_line="harness-writer-complete")

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        assert fm.date == _today()
        assert fm.active_topics >= 1
        assert isinstance(fm.next_actions, list)
        assert isinstance(fm.notes_unreviewed, int)

    def test_frontmatter_priority_order_phase_transition_first(self, orient_root):
        make_workspace(orient_root, [
            {"name": "re-owm", "path": "/tmp/re-owm"},
            {"name": "orient", "path": "/tmp/orient"},
        ])
        # harness-writer-complete → priority 1 (phase transition)
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1), phase_line="harness-writer-complete",
                    pending=["run /architecture-proposer"])
        # case-interviewer-in-progress → priority 2
        _write_note(orient_root, "orient", "cli", _days_ago(1), phase_line="case-interviewer-in-progress",
                    pending=["finish sync cases"])

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        priorities = [a.priority for a in fm.next_actions]
        assert priorities == sorted(priorities)   # ascending priority order

    def test_frontmatter_phase_transition_has_priority_1(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1), phase_line="harness-writer-complete")

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        mcp_action = next(a for a in fm.next_actions if "mcp" in a.topic)
        assert mcp_action.priority == 1

    def test_notes_unreviewed_count_matches_notes_since_last_brief(self, orient_root):
        make_workspace(orient_root, [])
        (orient_root / "NOTES.md").write_text(
            f"{_today()} 10:00  [orient]  note one\n"
            f"{_today()} 10:01  [untagged]  note two\n"
        )

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        assert fm.notes_unreviewed == 2

    def test_absent_notes_md_gives_zero_notes_unreviewed_and_omits_section(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1))

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        assert fm.notes_unreviewed == 0

    def test_run_twice_same_day_overwrites_not_appends(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1))
        brief_path = orient_root / "morning-brief.md"

        run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        mtime_first = brief_path.stat().st_mtime if brief_path.exists() else None

        run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        mtime_second = brief_path.stat().st_mtime if brief_path.exists() else None

        # File should be overwritten, not appended; content should not duplicate
        content = brief_path.read_text()
        assert content.count("date:") == 1    # not doubled


# ---------------------------------------------------------------------------
# Topic inclusion edge cases
# ---------------------------------------------------------------------------

@pytest.mark.brief
class TestTopicInclusion:
    def test_unknown_phase_surfaced_with_open_note_suggestion(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1), phase_line="unrecognised-phase")

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        mcp_action = next((a for a in fm.next_actions if "mcp" in a.topic), None)
        assert mcp_action is not None
        assert mcp_action.phase == "unknown"

    def test_no_active_topics_empty_do_first_section(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        # Note is beyond active_days and project is not pinned
        _write_note(orient_root, "re-owm", "mcp", _days_ago(30))

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        assert fm.next_actions == []

    def test_no_active_topics_cli_suggests_pinning(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(30))

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "orient config add-project" in result.output
        assert "--pinned" in result.output

    def test_pinned_topic_with_no_notes_surfaces_in_brief(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm", "pinned": True}])
        # No notes written for this topic

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        fm = parse_brief_frontmatter(orient_root / "morning-brief.md")  # TODO: wire up
        assert any("re-owm" in a.topic for a in fm.next_actions)

    def test_no_notes_anywhere_first_run_message(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "no session notes found" in result.output or "session" in result.output
        assert "session-note close" in result.output


# ---------------------------------------------------------------------------
# Previous close reason surfaced in brief
# ---------------------------------------------------------------------------

@pytest.mark.brief
class TestCloseReasonSurfacing:
    def test_budget_hit_close_reason_surfaced(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1), close_reason="budget-hit")

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "budget" in result.output
        assert "re-owm/mcp" in result.output

    def test_context_limit_close_reason_surfaced(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1), close_reason="context-limit")

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "context limit" in result.output
        assert "compact" in result.output


# ---------------------------------------------------------------------------
# CLI output - prose section only; frontmatter not shown on stdout
# ---------------------------------------------------------------------------

@pytest.mark.brief
class TestCliOutput:
    def test_stdout_shows_prose_not_frontmatter(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1), phase_line="harness-writer-complete")

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code == 0
        # Frontmatter delimiters should not appear in stdout
        assert "---" not in result.output or result.output.count("---") == 0  # TODO: tighten - spec says frontmatter not shown on stdout

    def test_morning_brief_md_written_to_orient_root(self, orient_root):
        make_workspace(orient_root, [{"name": "re-owm", "path": "/tmp/re-owm"}])
        _write_note(orient_root, "re-owm", "mcp", _days_ago(1))

        run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert (orient_root / "morning-brief.md").exists()


# ---------------------------------------------------------------------------
# Error cases (CLI level)
# ---------------------------------------------------------------------------

@pytest.mark.brief
class TestErrorCases:
    def test_no_workspace_toml_shows_first_run_guidance(self, orient_root):
        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert "orient is not configured yet" in result.output

    def test_note_root_unwritable_errors(self, orient_root):
        make_workspace(orient_root, [])
        note_root = orient_root / "notes"
        note_root.mkdir()
        note_root.chmod(0o555)

        result = run("brief", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert "cannot write" in result.output
        assert "note_root" in result.output or "notes" in result.output

        note_root.chmod(0o755)


# === SPEC GAPS ===
# TestPhaseNextActionLookup.test_unknown_phase: spec says "open <note-path> to orient,
#   then choose next stage" but doesn't specify what skill/invocation fields contain for
#   unknown phase; test uses loose assertion pending spec clarification
# TestCliOutput.test_stdout_shows_prose_not_frontmatter: spec says "terminal shows prose
#   only" but doesn't specify whether the "---" separator lines appear; assertion is loose
# TestTopicInclusion.test_no_notes_anywhere_first_run_message: spec gives two slightly
#   different messages ("orient is configured but no session notes found" vs the first-run
#   message); test checks for key strings rather than exact message
# _write_note phase_line: the spec shows phase as part of the ## Session block but the
#   exact field name ("phase:") is not shown in the spec note format - inferred from
#   the preflight token structure; architecture must confirm phase is stored in the note
