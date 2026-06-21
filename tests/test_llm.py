"""Tests for orient.llm — the provider-agnostic client factory and adapters.

Spec: spec.md (provider-agnostic artifact boundary), spec-skill.md (ZDR invariant).

The factory is the load-bearing contract: it decides whether a client exists at all,
and ZDR / missing-key must resolve to None (the deterministic fallback). Adapters are
tested for their dispatch shape, not for real network/subprocess behavior.
"""
from __future__ import annotations

import pytest

from orient.config import LLMConfig
from orient.llm import (
    AnthropicClient,
    CommandClient,
    LLMClient,
    get_llm_client,
)

pytestmark = pytest.mark.llm


# ---------------------------------------------------------------------------
# get_llm_client — provider resolution
# ---------------------------------------------------------------------------

class TestFactoryZDR:
    def test_zdr_flag_forces_none_even_with_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-present")
        assert get_llm_client(LLMConfig(provider="anthropic"), zdr=True) is None

    def test_orient_no_api_env_forces_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-present")
        monkeypatch.setenv("ORIENT_NO_API", "1")
        assert get_llm_client(LLMConfig(provider="anthropic")) is None

    def test_zdr_forces_none_for_command_provider(self, monkeypatch):
        # command would otherwise construct unconditionally; zdr still wins.
        assert get_llm_client(LLMConfig(provider="command"), zdr=True) is None


class TestFactoryProviders:
    def test_provider_none_returns_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-present")
        assert get_llm_client(LLMConfig(provider="none")) is None

    def test_anthropic_without_key_returns_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        assert get_llm_client(LLMConfig(provider="anthropic")) is None

    def test_anthropic_with_key_returns_anthropic_client(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-present")
        client = get_llm_client(LLMConfig(provider="anthropic"))
        assert isinstance(client, AnthropicClient)

    def test_command_provider_returns_command_client(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        client = get_llm_client(LLMConfig(provider="command", command=["claude", "-p"]))
        assert isinstance(client, CommandClient)

    def test_auto_with_key_returns_anthropic(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-present")
        client = get_llm_client(LLMConfig(provider="auto"))
        assert isinstance(client, AnthropicClient)

    def test_auto_without_key_returns_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        assert get_llm_client(LLMConfig(provider="auto")) is None

    def test_unrecognized_provider_defaults_to_auto_behavior(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        assert get_llm_client(LLMConfig(provider="banana")) is None


# ---------------------------------------------------------------------------
# Adapters — dispatch shape (no real network / subprocess)
# ---------------------------------------------------------------------------

class TestCommandClient:
    def test_empty_argv_is_rejected(self):
        with pytest.raises(ValueError):
            CommandClient([])

    def test_complete_pipes_prompt_and_returns_stdout(self, monkeypatch):
        captured = {}

        class _Proc:
            returncode = 0
            stdout = "  prose out  "
            stderr = ""

        def _fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["input"] = kwargs.get("input")
            return _Proc()

        monkeypatch.setattr("orient.llm.subprocess.run", _fake_run)
        client = CommandClient(["claude", "-p"])
        out = client.complete("hello prompt")

        assert out == "prose out"
        assert captured["argv"] == ["claude", "-p"]
        assert captured["input"] == "hello prompt"

    def test_nonzero_exit_raises(self, monkeypatch):
        class _Proc:
            returncode = 2
            stdout = ""
            stderr = "boom"

        monkeypatch.setattr("orient.llm.subprocess.run", lambda argv, **kw: _Proc())
        client = CommandClient(["claude", "-p"])
        with pytest.raises(RuntimeError):
            client.complete("x")


class TestProtocol:
    def test_adapters_satisfy_protocol(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-present")
        assert isinstance(AnthropicClient(), LLMClient)
        assert isinstance(CommandClient(["claude", "-p"]), LLMClient)
