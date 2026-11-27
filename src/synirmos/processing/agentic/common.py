"""Shared agent plumbing owned by ``processing.agentic``.

LangChain-backed analyzers used to scatter this logic across modules
(consent gates, model capability checks, token estimates, file-backed
proposal caches, JSON fence stripping). It now lives here;
``processing.enrichment`` re-exports the same names so existing imports
keep working while new agents import from this package directly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from ...core.models import LLMSettings

__all__ = [
    "AgentCache",
    "AgentConsentError",
    "AgentError",
    "AgentModelError",
    "cache_key",
    "check_model",
    "estimate_tokens",
    "parse_json_object",
    "require_consent",
    "strip_fences",
]


class AgentError(RuntimeError):
    """Base class for agent failures that never fabricate output."""


class AgentConsentError(AgentError):
    def __init__(self) -> None:
        super().__init__("LLM enrichment requires enabled=true and explicit privacy_consent=true")


class AgentModelError(AgentError):
    """The injected model is missing, unsuitable, or unreachable."""


def require_consent(settings: LLMSettings) -> None:
    if not settings.enabled or not settings.privacy_consent:
        raise AgentConsentError()


def check_model(model: Any) -> str:
    """Fail closed unless ``model`` is an invokable LangChain chat model."""

    if not isinstance(model, BaseChatModel):
        raise AgentModelError(f"Expected a LangChain BaseChatModel, got {type(model).__name__}")
    if not callable(getattr(model, "invoke", None)):
        raise AgentModelError("Chat model has no invokable interface")
    name = getattr(model, "model_name", None) or getattr(model, "model", None)
    return str(name or type(model).__name__)


def estimate_tokens(text: str) -> int:
    """Deterministic, dependency-free token estimate for budget bounds."""

    return max(1, len(text) // 4)


def cache_key(
    *,
    namespace: str,
    model_id: str,
    prompt_version: str,
    schema_version: str,
    method: str,
    context_hash: str,
) -> str:
    """Hash the full cache identity: model, prompt, schema, method, context."""

    material = "|".join([namespace, model_id, prompt_version, schema_version, method, context_hash])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            closing = len(lines) if lines[-1].strip() != "```" else -1
            return "\n".join(lines[1:closing]).strip()
    return text


def parse_json_object(content: Any) -> dict[str, Any] | None:
    """Return ``content`` as a JSON object, tolerating code fences."""

    if not isinstance(content, str):
        return None
    text = content.strip()
    for candidate in (text, strip_fences(text)):
        try:
            payload = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


class AgentCache:
    """File-backed proposal cache keyed by model, prompt, schema, and context."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._records: dict[str, dict[str, Any]] = {}
        if self._path.is_file():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self._records = payload
            except (OSError, ValueError):
                self._records = {}

    @property
    def path(self) -> Path:
        return self._path

    def lookup(self, key: str) -> dict[str, Any] | None:
        return self._records.get(key)

    def store(self, key: str, record: dict[str, Any]) -> None:
        self._records[key] = record
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._records, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self._path)
