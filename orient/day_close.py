"""day close — aggregate a day's session notes into the day marker + pre-plan.

The EOD keystone: what makes `day start` non-empty. Mirrors brief.py's current-file +
archive pattern (day-marker.md + day-markers/<date>.md) and its injectable-client
fallback. See spec-day-close.md.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from orient.llm import LLMClient
from orient.note import parse_notes_md
from orient.session_note import parse_note
from orient.state import load_last_day_close, save_last_day_close

# Close reasons that warrant a Flags line when the day is aggregated.
_ALARM_REASONS = {
    "budget-hit": "review cost before resuming",
    "context-limit": "compact before resuming",
}


@dataclass
class DayMarker:
    date: str
    shipped: list[str] = field(default_factory=list)        # "project/topic: synthesis"
    open_threads: list[str] = field(default_factory=list)   # "project/topic: live items"
    cross_topic: list[str] = field(default_factory=list)    # ## Calls + NOTES.md sweep
    pre_plan: list[str] = field(default_factory=list)        # ordered next actions
    flags: list[str] = field(default_factory=list)           # worked-not-closed / alarms


def _iter_day_notes(note_root: Path, target_date: str):
    """Yield (project, topic, ParsedNote) for every <target_date>.md under note_root.

    Walks the filesystem directly so it catches every project with notes, whether or
    not it is in workspace.toml (spec: "across every project").
    """
    if not note_root.is_dir():
        return
    for project_dir in sorted(note_root.iterdir()):
        if not project_dir.is_dir():
            continue
        for topic_dir in sorted(project_dir.iterdir()):
            if not topic_dir.is_dir():
                continue
            note_path = topic_dir / f"{target_date}.md"
            if not note_path.exists():
                continue
            try:
                parsed = parse_note(note_path)
            except Exception:
                continue
            yield project_dir.name, topic_dir.name, parsed


def _notes_md_sweep(orient_root: Path, target_date: str) -> list[str]:
    """Cross-topic observations captured via `orient note` on the target date."""
    note_root = orient_root / "notes"
    swept: list[str] = []
    candidates = [orient_root / "NOTES.md"]
    if note_root.is_dir():
        for project_dir in sorted(note_root.iterdir()):
            if project_dir.is_dir():
                candidates.append(project_dir / "NOTES.md")
    for notes_md in candidates:
        if not notes_md.exists():
            continue
        for entry in parse_notes_md(notes_md):
            if entry.date == target_date:
                swept.append(f"[{entry.tag}] {entry.text}")
    return swept


def aggregate_day(orient_root: Path, target_date: str) -> DayMarker:
    """Read every session note dated target_date and synthesise a DayMarker.

    Deterministic and API-free — the structured marker is the source of truth. An
    optional Haiku pass (run_day_close) only enriches Cross-topic prose on top.
    """
    note_root = orient_root / "notes"
    marker = DayMarker(date=target_date)

    pending_actions: list[str] = []   # "project/topic → item"  (pre-plan tier 1)
    deferred_actions: list[str] = []  # "project/topic → item"  (pre-plan tier 2)

    for project, topic, parsed in _iter_day_notes(note_root, target_date):
        topic_str = f"{project}/{topic}"

        if parsed.shipped:
            marker.shipped.append(f"{topic_str}: {'; '.join(parsed.shipped)}")

        live = parsed.pending + parsed.deferred
        if live:
            marker.open_threads.append(f"{topic_str}: {'; '.join(live)}")

        for call in parsed.calls:
            marker.cross_topic.append(f"{topic_str}: {call}")

        for item in parsed.pending:
            pending_actions.append(f"{topic_str} → {item}")
        for item in parsed.deferred:
            deferred_actions.append(f"{topic_str} → {item}")

        if parsed.session is None:
            marker.flags.append(f"{topic_str}: worked but not closed (no close note for {target_date})")
        elif parsed.session.reason in _ALARM_REASONS:
            marker.flags.append(
                f"{topic_str}: last session {parsed.session.reason} — {_ALARM_REASONS[parsed.session.reason]}"
            )

    marker.cross_topic.extend(_notes_md_sweep(orient_root, target_date))

    # Pre-plan heuristic: pending-first (unblock imminent work), then active deferred.
    marker.pre_plan = pending_actions + deferred_actions

    return marker


def serialize_marker(marker: DayMarker) -> str:
    """Render a DayMarker to the marker file format. Empty sections are omitted;
    a fully empty day still writes an explicit line — never a silent no-op."""
    head = ["---", f"date: {marker.date}", "---", ""]
    body: list[str] = []

    def section(title: str, items: list[str], numbered: bool = False) -> None:
        if not items:
            return
        body.append(f"## {title}")
        if numbered:
            body.extend(f"{i}. {item}" for i, item in enumerate(items, 1))
        else:
            body.extend(f"- {item}" for item in items)
        body.append("")

    section("Shipped today", marker.shipped)
    section("Open threads", marker.open_threads)
    section("Cross-topic", marker.cross_topic)
    section("Pre-plan (tomorrow)", marker.pre_plan, numbered=True)
    section("Flags", marker.flags)

    if not body:
        body = ["_nothing closed today_"]

    return "\n".join(head + body).rstrip() + "\n"


def _read_marker_date(path: Path) -> Optional[str]:
    """Read the `date:` value from a marker's frontmatter.

    Returns None only when the file is readable but carries no parseable `date:`
    (caller falls back to file mtime, as brief.py does). An OSError propagates — we
    are about to archive/overwrite this file, so an unreadable marker must surface
    rather than be silently clobbered.
    """
    seen_open_fence = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("date:"):
            return stripped[len("date:"):].strip()
        if stripped == "---":
            if seen_open_fence:
                break          # closing fence — frontmatter ended, no date found
            seen_open_fence = True
    return None


def _enrich_cross_topic(marker: DayMarker, client: LLMClient) -> None:
    """Single Haiku pass: synthesise one cross-topic insight line. Best-effort —
    any failure leaves the deterministic marker untouched (cf. brief.py prose)."""
    shipped = "\n".join(f"- {s}" for s in marker.shipped)
    threads = "\n".join(f"- {t}" for t in marker.open_threads)
    prompt = (
        f"Day summary for {marker.date}.\n"
        f"Shipped:\n{shipped or '(none)'}\n\n"
        f"Open threads:\n{threads or '(none)'}\n\n"
        "In ONE sentence, name the most important cross-topic connection or risk for "
        "tomorrow. No preamble, no list."
    )
    try:
        insight = client.complete(prompt, max_tokens=128).strip()
    except Exception:
        return
    if insight:
        marker.cross_topic.append(f"(synthesis) {insight}")


def run_day_close(
    orient_root: Path,
    target_date: Optional[str] = None,
    client: Optional[LLMClient] = None,
) -> None:
    """Aggregate target_date's notes into the day marker; archive + advance frontier.

    target_date defaults to today. A future date is rejected. The frontier
    (state.last_day_close) never moves backward: backdating behind it writes straight
    to the archive, leaving the current marker and frontier untouched.
    """
    today = date.today().isoformat()
    if target_date is None:
        target_date = today
    if target_date > today:
        print(f"error:future-date given:{target_date} today:{today}", file=sys.stderr)
        sys.exit(1)

    note_root = orient_root / "notes"
    if note_root.exists() and not note_root.is_dir():
        print(f"cannot read note_root: not a directory: {note_root}", file=sys.stderr)
        sys.exit(1)

    marker = aggregate_day(orient_root, target_date)
    if client is not None and (marker.shipped or marker.open_threads):
        _enrich_cross_topic(marker, client)

    content = serialize_marker(marker)

    current_path = orient_root / "day-marker.md"
    archive_dir = orient_root / "day-markers"

    # Effective frontier: the later of the recorded pointer and the current marker's
    # own date — so a fresher current marker is never clobbered by a stale pointer.
    frontier = load_last_day_close(orient_root)
    existing_date: Optional[str] = None
    if current_path.exists():
        existing_date = _read_marker_date(current_path)
    candidates = [d for d in (frontier, existing_date) if d]
    effective_frontier = max(candidates) if candidates else None

    promote = effective_frontier is None or target_date >= effective_frontier

    if promote:
        # Archive a stale current marker before overwriting (same-day re-run overwrites
        # in place, mirroring brief.py).
        if current_path.exists() and existing_date != target_date:
            archive_dir.mkdir(exist_ok=True)
            archive_name = existing_date or date.fromtimestamp(current_path.stat().st_mtime).isoformat()
            current_path.rename(archive_dir / f"{archive_name}.md")
        current_path.write_text(content)
        save_last_day_close(orient_root, target_date)
        written = current_path
    else:
        # Backfill behind the frontier: write straight to the archive; current marker
        # and frontier pointer unchanged (backdating does not regress state).
        archive_dir.mkdir(exist_ok=True)
        written = archive_dir / f"{target_date}.md"
        written.write_text(content)

    print(f"day marker: {written}")
    print()
    print(content)

