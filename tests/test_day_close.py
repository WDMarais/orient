"""Tests for orient.day_close — EOD aggregation into the day marker + pre-plan.

Spec: spec-day-close.md. These import the real orient.day_close module directly; no
stubs. The suite runs with a blanked ANTHROPIC_API_KEY (conftest autouse fixture), so
run_day_close takes the deterministic no-Haiku branch — the structured marker is the
asserted contract.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from conftest import make_workspace, run
from orient.day_close import (
    DayMarker,
    aggregate_day,
    run_day_close,
    serialize_marker,
)
from orient.state import load_last_day_close, save_last_day_close

pytestmark = pytest.mark.day_close


def _note(orient_root: Path, project: str, topic: str, note_date: str, body: str) -> Path:
    p = orient_root / "notes" / project / topic / f"{note_date}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _closed(project: str, topic: str, note_date: str, *, shipped="", pending="",
            deferred="", calls="", reason="natural-end") -> str:
    def block(name: str, value: str) -> str:
        return f"## {name}\n{value}\n\n"
    return (
        f"# {note_date} - {project}/{topic}\n\n"
        + block("Shipped", "\n".join(f"- {s}" for s in shipped.split("|") if s))
        + block("Pending", "\n".join(f"- {p}" for p in pending.split("|") if p))
        + block("Deferred", "\n".join(f"- {d}" for d in deferred.split("|") if d))
        + block("Calls", "\n".join(f"- {c}" for c in calls.split("|") if c))
        + f"## Session\n- reason: {reason}\n- phase: \n- model: sonnet\n"
    )


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _days_ahead(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _write_marker(orient_root: Path, marker_date: str,
                  body: str = "## Shipped today\n- stale/topic: old work\n") -> Path:
    """Plant a current day-marker.md dated marker_date (frontmatter + body)."""
    p = orient_root / "day-marker.md"
    p.write_text(f"---\ndate: {marker_date}\n---\n\n{body}")
    return p


# ===========================================================================
# aggregate_day — reads every <date>.md across projects
# ===========================================================================

class TestAggregate:
    def test_collects_shipped_open_threads_and_calls(self, orient_root):
        _note(orient_root, "orient", "day-close", "2026-06-22",
              _closed("orient", "day-close", "2026-06-22",
                      shipped="built run_day_close|added frontier",
                      pending="write tests", deferred="git detection",
                      calls="marker mirrors brief.py"))
        m = aggregate_day(orient_root, "2026-06-22")
        assert m.date == "2026-06-22"
        assert m.shipped == ["orient/day-close: built run_day_close; added frontier"]
        assert m.open_threads == ["orient/day-close: write tests; git detection"]
        assert "orient/day-close: marker mirrors brief.py" in m.cross_topic

    def test_only_target_date_notes_included(self, orient_root):
        _note(orient_root, "p", "t", "2026-06-22",
              _closed("p", "t", "2026-06-22", shipped="today"))
        _note(orient_root, "p", "t", "2026-06-21",
              _closed("p", "t", "2026-06-21", shipped="yesterday"))
        m = aggregate_day(orient_root, "2026-06-22")
        assert m.shipped == ["p/t: today"]

    def test_pre_plan_is_pending_first_then_deferred(self, orient_root):
        _note(orient_root, "p", "t", "2026-06-22",
              _closed("p", "t", "2026-06-22", pending="do A", deferred="someday B"))
        m = aggregate_day(orient_root, "2026-06-22")
        assert m.pre_plan == ["p/t → do A", "p/t → someday B"]

    def test_worked_but_not_closed_is_flagged(self, orient_root):
        # A note with no ## Session block = started/checkpointed but not closed.
        _note(orient_root, "p", "t", "2026-06-22",
              "# 2026-06-22 - p/t\n\n## Goal\n\n## Shipped\n- wip\n\n## Pending\n\n## Deferred\n")
        m = aggregate_day(orient_root, "2026-06-22")
        assert any("worked but not closed" in f for f in m.flags)

    def test_alarm_reason_is_flagged(self, orient_root):
        _note(orient_root, "p", "t", "2026-06-22",
              _closed("p", "t", "2026-06-22", shipped="x", reason="budget-hit"))
        m = aggregate_day(orient_root, "2026-06-22")
        assert any("budget-hit" in f for f in m.flags)

    def test_notes_md_sweep_is_date_filtered(self, orient_root):
        (orient_root / "NOTES.md").write_text(
            "2026-06-22 14:30  [orient]  keep me\n"
            "2026-06-21 09:00  [orient]  drop me\n"
        )
        m = aggregate_day(orient_root, "2026-06-22")
        assert "[orient] keep me" in m.cross_topic
        assert all("drop me" not in c for c in m.cross_topic)


# ===========================================================================
# serialize_marker — marker file format
# ===========================================================================

class TestSerialize:
    def test_empty_sections_omitted(self, orient_root):
        m = DayMarker(date="2026-06-22", shipped=["p/t: x"])
        out = serialize_marker(m)
        assert "## Shipped today" in out
        assert "## Open threads" not in out
        assert "## Flags" not in out

    def test_fully_empty_day_is_explicit_not_silent(self, orient_root):
        out = serialize_marker(DayMarker(date="2026-06-22"))
        assert "date: 2026-06-22" in out
        assert "nothing closed today" in out

    def test_pre_plan_is_numbered(self, orient_root):
        m = DayMarker(date="2026-06-22", pre_plan=["a", "b"])
        out = serialize_marker(m)
        assert "1. a" in out
        assert "2. b" in out


# ===========================================================================
# run_day_close — frontier placement, archive, advance (direct, no CLI)
# ===========================================================================

class TestRunDayClose:
    def test_promote_advances_frontier_and_archives_stale_current(self, orient_root):
        # A stale current marker behind the frontier; closing today promotes it.
        _write_marker(orient_root, _days_ago(2))
        save_last_day_close(orient_root, _days_ago(2))
        _note(orient_root, "p", "t", _today(),
              _closed("p", "t", _today(), shipped="todays work"))

        run_day_close(orient_root, target_date=_today())

        current = orient_root / "day-marker.md"
        assert f"date: {_today()}" in current.read_text()
        assert "p/t: todays work" in current.read_text()
        # stale marker rolled to the archive under its own date
        archived = orient_root / "day-markers" / f"{_days_ago(2)}.md"
        assert archived.exists()
        assert f"date: {_days_ago(2)}" in archived.read_text()
        # frontier advanced
        assert load_last_day_close(orient_root) == _today()

    def test_backfill_behind_frontier_leaves_current_and_frontier_untouched(self, orient_root):
        # Frontier already at today; backdating writes straight to the archive.
        _write_marker(orient_root, _today())
        save_last_day_close(orient_root, _today())
        _note(orient_root, "p", "t", _days_ago(3),
              _closed("p", "t", _days_ago(3), shipped="old day work"))

        run_day_close(orient_root, target_date=_days_ago(3))

        backfilled = orient_root / "day-markers" / f"{_days_ago(3)}.md"
        assert backfilled.exists()
        assert "p/t: old day work" in backfilled.read_text()
        # current marker untouched (still today, still the stale body)
        current = (orient_root / "day-marker.md").read_text()
        assert f"date: {_today()}" in current
        assert "stale/topic: old work" in current
        # frontier did not regress
        assert load_last_day_close(orient_root) == _today()

    def test_same_day_rerun_overwrites_in_place_without_archiving(self, orient_root):
        _write_marker(orient_root, _today())
        save_last_day_close(orient_root, _today())
        _note(orient_root, "p", "t", _today(),
              _closed("p", "t", _today(), shipped="fresh content"))

        run_day_close(orient_root, target_date=_today())

        current = (orient_root / "day-marker.md").read_text()
        assert "p/t: fresh content" in current
        assert "stale/topic: old work" not in current   # overwritten, not appended
        # no archive copy made for a same-day re-run
        assert not (orient_root / "day-markers" / f"{_today()}.md").exists()
        assert load_last_day_close(orient_root) == _today()

    def test_future_date_is_rejected_before_writing(self, orient_root, capsys):
        with pytest.raises(SystemExit) as exc:
            run_day_close(orient_root, target_date=_days_ahead(1))
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "error:future-date" in err
        assert f"given:{_days_ahead(1)}" in err
        assert not (orient_root / "day-marker.md").exists()

    def test_no_notes_today_writes_explicit_marker_not_silent_noop(self, orient_root):
        run_day_close(orient_root, target_date=_today())
        current = orient_root / "day-marker.md"
        assert current.exists()
        text = current.read_text()
        assert f"date: {_today()}" in text
        assert "nothing closed today" in text

    def test_note_root_not_a_directory_errors_without_proceeding(self, orient_root, capsys):
        (orient_root / "notes").write_text("not a directory")
        with pytest.raises(SystemExit) as exc:
            run_day_close(orient_root, target_date=_today())
        assert exc.value.code == 1
        assert "not a directory" in capsys.readouterr().err
        assert not (orient_root / "day-marker.md").exists()


# ===========================================================================
# day close — CLI integration (conftest.run)
# ===========================================================================

class TestDayCloseCLI:
    def test_backdate_via_date_option(self, orient_root):
        make_workspace(orient_root, [])
        _note(orient_root, "p", "t", _days_ago(1),
              _closed("p", "t", _days_ago(1), shipped="yesterday work"))

        result = run("day", "close", "--date", _days_ago(1),
                     env={"ORIENT_ROOT": str(orient_root)})
        assert result.exit_code == 0
        # no later marker existed, so the backdated close promotes to current
        current = (orient_root / "day-marker.md").read_text()
        assert f"date: {_days_ago(1)}" in current
        assert "p/t: yesterday work" in current
        assert load_last_day_close(orient_root) == _days_ago(1)

    def test_zdr_flag_makes_no_api_call_and_still_writes(self, orient_root):
        make_workspace(orient_root, [])
        _note(orient_root, "p", "t", _today(),
              _closed("p", "t", _today(), shipped="todays work"))

        result = run("day", "close", "--zdr", env={"ORIENT_ROOT": str(orient_root)})
        assert result.exit_code == 0
        assert "p/t: todays work" in (orient_root / "day-marker.md").read_text()

    def test_future_date_via_cli_exits_nonzero(self, orient_root):
        make_workspace(orient_root, [])
        result = run("day", "close", "--date", _days_ahead(1),
                     env={"ORIENT_ROOT": str(orient_root)})
        assert result.exit_code == 1
        assert not (orient_root / "day-marker.md").exists()

    def test_help_documents_date_backdating(self, orient_root):
        result = run("day", "close", "--help", env={"ORIENT_ROOT": str(orient_root)})
        assert result.exit_code == 0
        assert "--date" in result.output
        assert "Backdate" in result.output
