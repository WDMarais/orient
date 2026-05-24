"""Tests for orient note behavioral contract.

Spec: spec-note.md
Appends a timestamped observation to NOTES.md. Tag inferred from cwd;
falls back to [untagged]. Orient itself auto-appends soft observations during operations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from conftest import run, make_workspace


# ---------------------------------------------------------------------------
# Sketched data model
# TODO: fixture pattern — replace with real types from orient.note
# ---------------------------------------------------------------------------

# TODO: fixture pattern — replace with real NoteEntry from orient.note
@dataclass
class NoteEntry:
    date: str   # YYYY-MM-DD
    time: str   # HH:MM
    tag: str    # project name or "untagged"
    text: str


# TODO: fixture pattern — replace with real ProjectConfig from orient.config
@dataclass
class ProjectConfig:
    name: str
    path: str


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

# TODO: from orient.note import append_note, infer_tag, parse_notes_md
def append_note(text: str, cwd: Path, orient_root: Path) -> NoteEntry:
    """Append one observation to NOTES.md and return the parsed entry."""
    raise NotImplementedError("orient.note not yet implemented")  # TODO: wire up


def infer_tag(cwd: Path, configs: list[ProjectConfig]) -> str:
    """Return the project name if cwd is inside a configured project path, else 'untagged'."""
    raise NotImplementedError("orient.note not yet implemented")  # TODO: wire up


def parse_notes_md(path: Path) -> list[NoteEntry]:
    """Parse NOTES.md and return all entries in order."""
    raise NotImplementedError("orient.note not yet implemented")  # TODO: wire up


# ---------------------------------------------------------------------------
# Tag inference
# ---------------------------------------------------------------------------

@pytest.mark.note
class TestTagInference:
    def test_cwd_inside_configured_project_uses_project_name(self, tmp_path):
        project_root = tmp_path / "orient"
        project_root.mkdir()
        configs = [ProjectConfig("orient", str(project_root))]

        tag = infer_tag(project_root, configs)  # TODO: wire up
        assert tag == "orient"

    def test_cwd_in_subdir_of_project_uses_project_name(self, tmp_path):
        project_root = tmp_path / "orient"
        subdir = project_root / "src" / "cli"
        subdir.mkdir(parents=True)
        configs = [ProjectConfig("orient", str(project_root))]

        tag = infer_tag(subdir, configs)  # TODO: wire up
        assert tag == "orient"

    def test_cwd_outside_all_projects_uses_untagged(self, tmp_path):
        project_root = tmp_path / "orient"
        project_root.mkdir()
        configs = [ProjectConfig("orient", str(project_root))]
        unrelated = tmp_path / "some" / "other" / "path"
        unrelated.mkdir(parents=True)

        tag = infer_tag(unrelated, configs)  # TODO: wire up
        assert tag == "untagged"

    def test_no_configured_projects_uses_untagged(self, tmp_path):
        tag = infer_tag(tmp_path, [])  # TODO: wire up
        assert tag == "untagged"


# ---------------------------------------------------------------------------
# append_note — entry structure
# ---------------------------------------------------------------------------

@pytest.mark.note
class TestAppendNote:
    def test_appended_entry_has_correct_tag_for_project_cwd(self, orient_root, tmp_path):
        project_root = tmp_path / "orient"
        project_root.mkdir()
        make_workspace(orient_root, [{"name": "orient", "path": str(project_root)}])

        entry = append_note(
            "preflight exits 0 even when note dir is unwritable",
            cwd=project_root,
            orient_root=orient_root,
        )  # TODO: wire up
        assert entry.tag == "orient"
        assert entry.text == "preflight exits 0 even when note dir is unwritable"

    def test_appended_entry_has_untagged_for_unrelated_cwd(self, orient_root, tmp_path):
        make_workspace(orient_root, [{"name": "orient", "path": str(tmp_path / "orient")}])
        unrelated = tmp_path / "elsewhere"
        unrelated.mkdir()

        entry = append_note(
            "sync stalled on unreachable remote, no timeout shown",
            cwd=unrelated,
            orient_root=orient_root,
        )  # TODO: wire up
        assert entry.tag == "untagged"

    def test_entry_date_is_today(self, orient_root, tmp_path):
        from datetime import date
        make_workspace(orient_root, [])

        entry = append_note("some observation", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up
        assert entry.date == date.today().isoformat()

    def test_entry_time_is_hhmm_format(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        entry = append_note("some observation", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up
        assert re.match(r"^\d{2}:\d{2}$", entry.time)


# ---------------------------------------------------------------------------
# NOTES.md file content
# ---------------------------------------------------------------------------

@pytest.mark.note
class TestNotesFile:
    def test_entry_written_to_notes_md(self, orient_root, tmp_path):
        make_workspace(orient_root, [])
        notes_path = orient_root / "NOTES.md"

        append_note("some observation", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up

        assert notes_path.exists()
        content = notes_path.read_text()
        assert "some observation" in content

    def test_entry_line_format(self, orient_root, tmp_path):
        # Expected: YYYY-MM-DD HH:MM  [tag]  text
        make_workspace(orient_root, [])
        notes_path = orient_root / "NOTES.md"

        append_note("my note", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up

        line = notes_path.read_text().strip().splitlines()[-1]
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}  \[.+\]  .+$", line)

    def test_notes_md_created_if_absent(self, orient_root, tmp_path):
        make_workspace(orient_root, [])
        notes_path = orient_root / "NOTES.md"
        assert not notes_path.exists()

        append_note("creating notes file", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up

        assert notes_path.exists()

    def test_second_note_appended_not_overwritten(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        append_note("first note", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up
        append_note("second note", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up

        content = (orient_root / "NOTES.md").read_text()
        assert "first note" in content
        assert "second note" in content

    def test_parse_notes_md_returns_entries_in_order(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        append_note("first note", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up
        append_note("second note", cwd=tmp_path, orient_root=orient_root)  # TODO: wire up

        entries = parse_notes_md(orient_root / "NOTES.md")  # TODO: wire up
        assert len(entries) == 2
        assert entries[0].text == "first note"
        assert entries[1].text == "second note"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.note
class TestEdgeCases:
    def test_empty_text_errors(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        result = run("note", "", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert "note text cannot be empty" in result.output

    def test_orient_root_not_writable_errors(self, orient_root, tmp_path):
        make_workspace(orient_root, [])
        # Make NOTES.md unwritable by making orient_root read-only
        orient_root.chmod(0o555)

        result = run("note", "some text", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert result.exit_code != 0
        assert "cannot write" in result.output
        assert "NOTES.md" in result.output

        orient_root.chmod(0o755)  # restore for cleanup


# ---------------------------------------------------------------------------
# Auto-append (orient-generated observations)
# ---------------------------------------------------------------------------

@pytest.mark.note
class TestAutoAppend:
    def test_sync_no_upstream_appends_observation_to_notes(self, orient_root, tmp_path):
        # orient sync, when it detects no upstream configured, auto-appends to NOTES.md
        from conftest import make_git_repo
        repo = make_git_repo(tmp_path / "re-owm")
        make_workspace(orient_root, [{"name": "re-owm", "path": str(repo)}])

        run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up

        notes = orient_root / "NOTES.md"
        assert notes.exists()
        content = notes.read_text()
        assert "re-owm" in content
        assert "no upstream configured" in content

    def test_sync_auto_append_also_shows_inline_observation_logged(self, orient_root, tmp_path):
        from conftest import make_git_repo
        repo = make_git_repo(tmp_path / "re-owm")
        make_workspace(orient_root, [{"name": "re-owm", "path": str(repo)}])

        result = run("sync", env={"ORIENT_ROOT": str(orient_root)})  # TODO: wire up
        assert "observation logged" in result.output
        assert "NOTES.md" in result.output


# ---------------------------------------------------------------------------
# Rendering / CLI (thin smoke assertions)
# ---------------------------------------------------------------------------

@pytest.mark.note
class TestRendering:
    def test_cli_note_appends_and_exits_zero(self, orient_root, tmp_path):
        make_workspace(orient_root, [])

        result = run(
            "note", "sync stalled on unreachable remote",
            env={"ORIENT_ROOT": str(orient_root)},
        )  # TODO: wire up
        assert result.exit_code == 0


# === SPEC GAPS ===
# TestEdgeCases.test_orient_root_not_writable_errors: spec says "cannot write to
#   ~/.orient/NOTES.md — check permissions" but does not specify exit code; test
#   asserts exit_code != 0 and key strings; exact message may need tightening
# TestAutoAppend: spec shows auto-append triggered by "no upstream configured" during sync;
#   no exhaustive list of other auto-append triggers is given — only this one case is tested
# TestNotesFile.test_entry_line_format: two-space separators between fields are from the
#   spec example; exact whitespace normalisation (tabs vs spaces) is not specified
