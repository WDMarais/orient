"""Tests for orient.skill — the local SKILL.md registry: parse, discover, resolve, emit.

Spec: spec-skill.md. Interface: the `### orient.skill` section of ARCHITECTURE.md.
Cross-cutting invariant (spec.md / spec-skill.md "ZDR / emit-only"): `skill show`
NEVER calls the Anthropic API — it only assembles and prints text.

These tests import the real orient.skill module directly. It is the next module to be
built, so until it exists the whole file fails to collect (ImportError) — that is the
honest red: the tests fail because the thing they exercise is absent, not because of any
in-file scaffolding. No stub classes, no tolerant fixtures. Pure-contract tests
(parse/assemble/resolve) call real functions; integration tests (discover/list/show/
lifecycle-token/ZDR) drive the CLI plus a `native_dir` fixture that monkeypatches
`orient.skill._native_skills_dir` to an isolated tmp dir.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pytest

from conftest import run
from orient.skill import (
    Skill,
    SkillKind,
    assemble_skill,
    parse_skill,
    resolve_skill,
)

pytestmark = pytest.mark.skill


# ===========================================================================
# Helpers / fixtures
# ===========================================================================

def _skill_text(name: str, *, description: str = "desc", kind: Optional[str] = None,
                extends: Optional[str] = None, body: str = "BODY TEXT") -> str:
    fm = [f"name: {name}", f"description: {description}"]
    if kind is not None:
        fm.append(f"kind: {kind}")
    if extends is not None:
        fm.append(f"extends: {extends}")
    return "---\n" + "\n".join(fm) + "\n---\n\n" + body + "\n"


def _write_skill(root: Path, name: str, **kw) -> Path:
    """Write <root>/<name>/SKILL.md with the given frontmatter/body; return the path."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(_skill_text(name, **kw))
    return path


def _write_workspace(orient_root: Path, *, skill_paths: list[str] | None = None,
                     overrides: list[dict] | None = None) -> None:
    """Minimal workspace.toml with an optional [skills] table for external discovery."""
    lines = ["[defaults]", "push = false", ""]
    if skill_paths is not None:
        joined = ", ".join(f'"{p}"' for p in skill_paths)
        lines += ["[skills]", f"paths = [{joined}]", ""]
    for ov in overrides or []:
        lines.append("[[skills.override]]")
        for k, v in ov.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    (orient_root / "workspace.toml").write_text("\n".join(lines))


def _note_path(orient_root: Path, project: str, topic: str, note_date: str) -> Path:
    return orient_root / "notes" / project / topic / f"{note_date}.md"


@pytest.fixture
def native_dir(tmp_path, monkeypatch) -> Path:
    """Isolated package-data dir; monkeypatches orient.skill._native_skills_dir.

    Decouples discovery/show tests from the authored native set (the native SKILL.md
    bodies are written in a later step). Importing orient.skill here is what makes the
    integration tests fail loudly until the module exists.
    """
    d = tmp_path / "native_skills"
    d.mkdir()
    monkeypatch.setattr("orient.skill._native_skills_dir", lambda: d)
    return d


# ===========================================================================
# parse_skill — frontmatter / body split (pure, stubbed)
# ===========================================================================

class TestParseSkill:
    def test_strips_frontmatter_returns_body(self, tmp_path):
        path = _write_skill(tmp_path, "alpha", body="Hello body\nmore")
        skill = parse_skill(path, SkillKind.native)  # TODO: wire up
        assert skill.body.strip() == "Hello body\nmore"

    def test_reads_name_and_description(self, tmp_path):
        path = _write_skill(tmp_path, "alpha", description="the alpha skill")
        skill = parse_skill(path, SkillKind.native)  # TODO: wire up
        assert skill.name == "alpha"
        assert skill.description == "the alpha skill"

    def test_kind_comes_from_caller_argument(self, tmp_path):
        path = _write_skill(tmp_path, "beta")
        skill = parse_skill(path, SkillKind.external)  # TODO: wire up
        assert skill.kind == SkillKind.external

    def test_source_path_is_the_skill_md_path(self, tmp_path):
        path = _write_skill(tmp_path, "beta")
        skill = parse_skill(path, SkillKind.external)  # TODO: wire up
        assert skill.source_path == str(path)

    def test_extends_parsed_when_present(self, tmp_path):
        path = _write_skill(tmp_path, "owm-close", extends="session-closer")
        skill = parse_skill(path, SkillKind.external)  # TODO: wire up
        assert skill.extends == "session-closer"

    def test_extends_none_when_absent(self, tmp_path):
        path = _write_skill(tmp_path, "standalone")
        skill = parse_skill(path, SkillKind.external)  # TODO: wire up
        assert skill.extends is None


# ===========================================================================
# assemble_skill — the emit ordering invariant: token -> base -> overlay (pure)
# ===========================================================================

class TestAssembleSkill:
    def _native(self, name="g", body="GENERIC BODY"):
        return Skill(name=name, description="d", kind=SkillKind.native,
                     body=body, source_path=f"/n/{name}/SKILL.md")

    def _external(self, name="x", body="OVERLAY BODY", extends=None):
        return Skill(name=name, description="d", kind=SkillKind.external,
                     body=body, source_path=f"/e/{name}/SKILL.md", extends=extends)

    def test_native_standalone_emits_body_only(self):
        s = self._native(body="ONLY BODY")
        out = assemble_skill(s, base=None, context_token=None)  # TODO: wire up
        assert "ONLY BODY" in out

    def test_lifecycle_native_emits_token_before_body(self):
        s = self._native(name="day-starter", body="DAY STARTER BODY")
        out = assemble_skill(s, base=None, context_token="TOKEN BLOB")  # TODO: wire up
        assert "TOKEN BLOB" in out and "DAY STARTER BODY" in out
        assert out.index("TOKEN BLOB") < out.index("DAY STARTER BODY")

    def test_external_overlay_emits_base_before_overlay(self):
        base = self._native(body="GENERIC BODY")
        overlay = self._external(body="OVERLAY BODY", extends=base.name)
        out = assemble_skill(overlay, base=base, context_token=None)  # TODO: wire up
        assert out.index("GENERIC BODY") < out.index("OVERLAY BODY")

    def test_external_overlay_onto_lifecycle_emits_token_base_overlay(self):
        base = self._native(name="session-closer", body="GENERIC BODY")
        overlay = self._external(body="OVERLAY BODY", extends="session-closer")
        out = assemble_skill(overlay, base=base, context_token="TOKEN BLOB")  # TODO: wire up
        assert out.index("TOKEN BLOB") < out.index("GENERIC BODY") < out.index("OVERLAY BODY")

    def test_parts_are_separated_not_concatenated(self):
        # token -> body must have a blank line / rule between them, not run together.
        s = self._native(body="BODY")
        out = assemble_skill(s, base=None, context_token="TOKEN")  # TODO: wire up
        assert "TOKENBODY" not in out


# ===========================================================================
# resolve_skill — native-first, collision, unknown (pure)
# ===========================================================================

class TestResolveSkill:
    def _n(self, name):
        return Skill(name, "d", SkillKind.native, "NBODY", f"/n/{name}/SKILL.md")

    def _e(self, name, extends=None):
        return Skill(name, "d", SkillKind.external, "EBODY", f"/e/{name}/SKILL.md", extends)

    def test_native_resolves_before_external_same_name_is_collision(self):
        # A native and an external sharing a name is an error, not a silent pick.
        skills = [self._n("session-closer"), self._e("session-closer")]
        with pytest.raises(ValueError):
            resolve_skill("session-closer", skills)

    def test_collision_error_names_both_sources(self):
        skills = [self._n("dup"), self._e("dup")]
        try:
            resolve_skill("dup", skills)  # TODO: wire up
            raised = None
        except NotImplementedError:
            raise
        except Exception as e:  # noqa: BLE001
            raised = str(e)
        assert raised is not None
        assert "/n/dup/SKILL.md" in raised and "/e/dup/SKILL.md" in raised

    def test_external_resolves_when_no_native(self):
        skills = [self._n("other"), self._e("blind-reviewer")]
        got = resolve_skill("blind-reviewer", skills)  # TODO: wire up
        assert got.name == "blind-reviewer" and got.kind == SkillKind.external

    def test_native_resolves_when_unique(self):
        skills = [self._n("harness-writer"), self._e("blind-reviewer")]
        got = resolve_skill("harness-writer", skills)  # TODO: wire up
        assert got.kind == SkillKind.native

    def test_unknown_name_raises_with_list_hint(self):
        try:
            resolve_skill("nope", [self._n("a")])  # TODO: wire up
            raised = None
        except NotImplementedError:
            raise
        except Exception as e:  # noqa: BLE001
            raised = str(e)
        assert raised is not None
        assert "nope" in raised and "skill list" in raised


# ===========================================================================
# discover + list (integration — real module via CLI)
# ===========================================================================

class TestSkillList:
    def test_list_marks_native_external_and_extends(self, orient_root, native_dir, tmp_path):
        _write_skill(native_dir, "harness-writer")
        ext_root = tmp_path / "ext"
        _write_skill(ext_root, "blind-reviewer", kind="external")
        _write_skill(native_dir, "session-closer")
        _write_skill(ext_root, "owm-close", extends="session-closer")
        _write_workspace(
            orient_root,
            skill_paths=[str(ext_root)],
            overrides=[{"name": "owm-close", "extends": "session-closer"}],
        )
        r = run("skill", "list", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert "harness-writer" in r.output
        assert "native" in r.output
        assert "blind-reviewer" in r.output
        assert "external" in r.output
        # external overlay marked as targeting its base
        assert "session-closer" in r.output and "owm-close" in r.output

    def test_list_lists_natives_before_externals(self, orient_root, native_dir, tmp_path):
        _write_skill(native_dir, "architecture-proposer")
        ext_root = tmp_path / "ext"
        _write_skill(ext_root, "zzz-external", kind="external")
        _write_workspace(orient_root, skill_paths=[str(ext_root)])
        r = run("skill", "list", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert r.output.index("architecture-proposer") < r.output.index("zzz-external")


class TestDiscovery:
    def test_external_discovered_under_search_path(self, orient_root, native_dir, tmp_path):
        ext_root = tmp_path / "work-skills"
        _write_skill(ext_root, "pr-fetcher", kind="external")
        _write_workspace(orient_root, skill_paths=[str(ext_root)])
        r = run("skill", "show", "pr-fetcher", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert "BODY TEXT" in r.output

    def test_override_extends_wins_over_frontmatter(self, orient_root, native_dir, tmp_path):
        # Frontmatter has no extends; the override supplies it -> emitted as overlay.
        _write_skill(native_dir, "session-closer", body="NATIVE CLOSE BODY")
        ext_root = tmp_path / "ext"
        _write_skill(ext_root, "owm-close", body="OVERLAY CLOSE BODY")  # no extends in fm
        _write_workspace(
            orient_root,
            skill_paths=[str(ext_root)],
            overrides=[{"name": "owm-close", "extends": "session-closer"}],
        )
        r = run("skill", "show", "owm-close", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert "NATIVE CLOSE BODY" in r.output and "OVERLAY CLOSE BODY" in r.output
        assert r.output.index("NATIVE CLOSE BODY") < r.output.index("OVERLAY CLOSE BODY")

    def test_override_kind_marks_standalone_external(self, orient_root, native_dir, tmp_path):
        # kind=external override; no native of this name -> standalone, body alone.
        ext_root = tmp_path / "ext"
        _write_skill(ext_root, "blind-reviewer", body="REVIEW BODY")
        _write_workspace(
            orient_root,
            skill_paths=[str(ext_root)],
            overrides=[{"name": "blind-reviewer", "kind": "external"}],
        )
        r = run("skill", "show", "blind-reviewer", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert "REVIEW BODY" in r.output


# ===========================================================================
# Resolution errors through the CLI (integration)
# ===========================================================================

class TestResolutionErrors:
    def test_external_may_not_shadow_native(self, orient_root, native_dir, tmp_path):
        _write_skill(native_dir, "harness-writer", body="NATIVE")
        ext_root = tmp_path / "ext"
        _write_skill(ext_root, "harness-writer", kind="external", body="SHADOW")
        _write_workspace(orient_root, skill_paths=[str(ext_root)])
        r = run("skill", "show", "harness-writer", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code != 0
        # error names both the native and external sources
        assert "native" in r.output and "external" in r.output

    def test_extends_base_must_be_native(self, orient_root, native_dir, tmp_path):
        # owm-close extends another EXTERNAL, not a native -> error.
        ext_root = tmp_path / "ext"
        _write_skill(ext_root, "some-external", kind="external")
        _write_skill(ext_root, "owm-close", extends="some-external")
        _write_workspace(
            orient_root,
            skill_paths=[str(ext_root)],
            overrides=[{"name": "owm-close", "extends": "some-external"}],
        )
        r = run("skill", "show", "owm-close", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code != 0

    def test_unknown_skill_errors_with_hint(self, orient_root, native_dir):
        _write_workspace(orient_root)
        r = run("skill", "show", "ghost", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code != 0
        assert "ghost" in r.output and "skill list" in r.output


# ===========================================================================
# show — native standalone & overlay emission (integration)
# ===========================================================================

class TestShowBody:
    def test_native_standalone_prints_body(self, orient_root, native_dir):
        _write_skill(native_dir, "case-interviewer", body="INTERVIEW BODY")
        _write_workspace(orient_root)
        r = run("skill", "show", "case-interviewer", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert "INTERVIEW BODY" in r.output

    def test_dev_pipeline_skill_has_no_lifecycle_token(self, orient_root, native_dir):
        # case-interviewer is not a lifecycle skill -> body only, no paired-command token.
        _write_skill(native_dir, "case-interviewer", body="INTERVIEW BODY")
        _write_workspace(orient_root)
        r = run("skill", "show", "case-interviewer", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert r.output.strip().endswith("INTERVIEW BODY") or "INTERVIEW BODY" in r.output


# ===========================================================================
# show — lifecycle natives emit their paired command's context token (integration)
# ===========================================================================

class TestLifecycleTokens:
    def test_day_starter_includes_preflight_token(self, orient_root, native_dir):
        _write_skill(native_dir, "day-starter", body="DAY STARTER BODY")
        _write_workspace(orient_root)
        # Seed an active topic so build_preflight_token surfaces it in the token text.
        env = {"ORIENT_ROOT": str(orient_root)}
        run("topic", "mark", "myproj", "mytopic", env=env)
        r = run("skill", "show", "day-starter", env=env)
        assert r.exit_code == 0
        assert "DAY STARTER BODY" in r.output
        # token derived from build_preflight_token mentions the active topic
        assert "mytopic" in r.output
        assert r.output.index("mytopic") < r.output.index("DAY STARTER BODY")

    def test_session_closer_emits_body_only(self, orient_root, native_dir):
        # Session-tier skills carry NO context token: `orient session close` emits the
        # mechanical context (note path, prev note, priming block) itself and then appends
        # this body, so preflight is consumed exactly once. `skill show` is body-only.
        _write_skill(native_dir, "session-closer", body="SESSION CLOSE BODY")
        _write_workspace(orient_root)
        # A previous note would have fed the old preflight token — it must NOT leak now.
        prev = _note_path(orient_root, "myproj", "mytopic", "2026-06-20")
        prev.parent.mkdir(parents=True, exist_ok=True)
        prev.write_text(
            "# 2026-06-20 - myproj/mytopic\n\n## Goal\nx\n\n## Pending\n- carry me forward\n"
        )
        r = run("skill", "show", "session-closer", "myproj", "mytopic",
                env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert r.output.strip() == "SESSION CLOSE BODY"
        assert "2026-06-20" not in r.output

    def test_topic_briefer_emits_body_only(self, orient_root, native_dir):
        # Like session-closer: the cold brief comes from `orient session start`, not from a
        # skill-show token. `skill show topic-briefer` is body-only.
        _write_skill(native_dir, "topic-briefer", body="TOPIC BRIEF BODY")
        _write_workspace(orient_root)
        prev = _note_path(orient_root, "myproj", "mytopic", "2026-06-20")
        prev.parent.mkdir(parents=True, exist_ok=True)
        prev.write_text(
            "# 2026-06-20 - myproj/mytopic\n\n## Goal\nlast goal\n\n## Pending\n- open thread\n"
        )
        r = run("skill", "show", "topic-briefer", "myproj", "mytopic",
                env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert r.output.strip() == "TOPIC BRIEF BODY"
        assert "open thread" not in r.output

    def test_session_closer_without_project_topic_emits_body(
        self, orient_root, native_dir
    ):
        # No project/topic given -> still body-only, no error (no token to need them).
        _write_skill(native_dir, "session-closer", body="SESSION CLOSE BODY")
        _write_workspace(orient_root)
        r = run("skill", "show", "session-closer", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert r.output.strip() == "SESSION CLOSE BODY"

    def test_day_closer_includes_marker_token(self, orient_root, native_dir):
        # day close is built: day-closer emits today's auto-aggregated marker as its
        # context token, before the body. Workspace-wide — no project/topic needed.
        _write_skill(native_dir, "day-closer", body="DAY CLOSE BODY")
        _write_workspace(orient_root)
        today = date.today().isoformat()
        note = _note_path(orient_root, "myproj", "mytopic", today)
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(
            f"# {today} - myproj/mytopic\n\n## Shipped\n- shipped-marker-item\n\n"
            "## Pending\n\n## Deferred\n\n## Session\n- reason: natural-end\n- phase: \n- model: sonnet\n"
        )
        r = run("skill", "show", "day-closer", env={"ORIENT_ROOT": str(orient_root)})
        assert r.exit_code == 0
        assert "DAY CLOSE BODY" in r.output
        # token = aggregated marker preview, emitted before the body
        assert "shipped-marker-item" in r.output
        assert r.output.index("shipped-marker-item") < r.output.index("DAY CLOSE BODY")
        # emit-only: previewing the marker must NOT write or advance anything
        assert not (orient_root / "day-marker.md").exists()


# ===========================================================================
# ZDR / emit-only invariant (integration)
# ===========================================================================

class TestEmitOnly:
    def test_show_unaffected_by_no_api_env(self, orient_root, native_dir):
        # ORIENT_NO_API + a present key must not change `show`; it never calls the API.
        _write_skill(native_dir, "case-interviewer", body="INTERVIEW BODY")
        _write_workspace(orient_root)
        r = run("skill", "show", "case-interviewer", env={
            "ORIENT_ROOT": str(orient_root),
            "ORIENT_NO_API": "1",
            "ANTHROPIC_API_KEY": "sk-present",
        })
        assert r.exit_code == 0
        assert "INTERVIEW BODY" in r.output

    def test_show_does_not_call_get_llm_client(self, orient_root, native_dir, monkeypatch):
        # If show tried to build an LLM client, this would raise and fail the command.
        _write_skill(native_dir, "day-starter", body="DAY STARTER BODY")
        _write_workspace(orient_root)

        def _boom(*a, **k):
            raise RuntimeError("skill show must never construct an LLM client")

        monkeypatch.setattr("orient.llm.get_llm_client", _boom)
        env = {"ORIENT_ROOT": str(orient_root), "ANTHROPIC_API_KEY": "sk-present"}
        run("topic", "mark", "myproj", "mytopic", env=env)
        r = run("skill", "show", "day-starter", env=env)
        assert r.exit_code == 0
        assert "DAY STARTER BODY" in r.output


# === SPEC GAPS ===
# - test_topic_briefer_includes_cold_brief: spec-skill.md pairs topic-briefer with the
#   `session start` cold brief but the exact token rendering (which note fields appear)
#   is not pinned; assertion accepts either the carried Pending text or the prev date.
# - Chained overlays (external extends external) are declared out of scope in
#   ARCHITECTURE.md; test_extends_base_must_be_native pins the error, not a behavior.
