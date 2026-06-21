"""Provider-agnostic LLM client: a Protocol, concrete adapters, and a factory.

orient's prose steps (day-start brief, day-close synthesis) call an LLM only for
optional flourish; every caller degrades to a deterministic fallback when the factory
returns None. The Protocol keeps brief.py provider-agnostic: adding a provider
(Gemini, Codex, …) is one adapter class plus one branch in get_llm_client — the
Strategy pattern, with no core change.

ZDR: get_llm_client returns None whenever --zdr / ORIENT_NO_API is set, so a
zero-data-retention venue is provably API-silent — no client is even constructed.
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional, Protocol, runtime_checkable

import anthropic

from orient.config import LLMConfig


@runtime_checkable
class LLMClient(Protocol):
    """A single-shot completion. Implementations must not retain prompt data beyond
    the call (the CommandClient/AnthropicClient honor whatever the endpoint does)."""

    def complete(
        self, prompt: str, *, max_tokens: int = 512, model: Optional[str] = None
    ) -> str: ...


class AnthropicClient:
    """Direct Anthropic SDK adapter. Holds a default model; `complete(model=...)`
    overrides per call."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = anthropic.Anthropic()
        self._model = model

    def complete(
        self, prompt: str, *, max_tokens: int = 512, model: Optional[str] = None
    ) -> str:
        response = self._client.messages.create(
            model=model or self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


class CommandClient:
    """Shell-command adapter (e.g. ["claude", "-p"]). Prompt on stdin, completion on
    stdout. The ZDR-friendly path at work: routes through a locally-governed CLI
    rather than the SDK. `model` is advisory — passed only if the command's contract
    uses it; the default impl ignores it and trusts the command's own config."""

    def __init__(self, argv: list[str], timeout: int = 120) -> None:
        if not argv:
            raise ValueError("llm command is empty: set [llm] command in workspace.toml")
        self._argv = argv
        self._timeout = timeout

    def complete(
        self, prompt: str, *, max_tokens: int = 512, model: Optional[str] = None
    ) -> str:
        proc = subprocess.run(
            self._argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"llm command {self._argv!r} failed (rc={proc.returncode}): "
                f"{proc.stderr.strip()}"
            )
        return proc.stdout.strip()


def get_llm_client(config: LLMConfig, *, zdr: bool = False) -> Optional[LLMClient]:
    """Construct the configured client, or None to force the deterministic fallback.

    None is returned (no client constructed, no API reachable) when:
      - zdr is True, or ORIENT_NO_API is set in the environment;
      - provider is "none";
      - provider resolves to anthropic but ANTHROPIC_API_KEY is absent.

    provider "auto" (the default) preserves orient's historical behavior: Anthropic
    SDK if a key is present, deterministic fallback otherwise.
    """
    if zdr or os.getenv("ORIENT_NO_API"):
        return None

    provider = config.provider
    if provider == "none":
        return None
    if provider == "command":
        return CommandClient(config.command, timeout=config.timeout)
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        return AnthropicClient(model=config.model)

    # "auto" (and any unrecognized value, defensively): key-gated Anthropic.
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicClient(model=config.model)
    return None
