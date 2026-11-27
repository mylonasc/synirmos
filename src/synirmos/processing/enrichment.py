"""LangChain structured LLM enrichment with budgets, caching, and provenance.

An injected LangChain chat model proposes typed topics, summaries, and links
over grounded evidence.  Every call is opt-in (``enabled`` plus explicit
``privacy_consent``), budgeted (requests and tokens, across retries), cached
(model, prompt, schema, and context all participate in the cache key), and
recorded with complete provenance.  Invalid model output is retried and then
abstained — never invented into the graph.  Grounding is enforced structurally:
reused topics and link targets must come from the supplied candidates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import Field, field_validator

from ..core.analysis import AnalysisResult, DecisionStatus, Provenance
from ..core.budgets import BudgetExceeded, BudgetLedger
from ..core.models import CoverageGap, CoverageStatus, FrozenModel, LLMSettings, ensure_utc
from .agentic.common import (
    AgentCache,
    AgentConsentError,
    AgentError,
    AgentModelError,
    cache_key,
    check_model,
    estimate_tokens,
    parse_json_object,
    require_consent,
)

__all__ = [
    "ENRICHMENT_SCHEMA_VERSION",
    "Enricher",
    "EnrichmentCache",
    "EnrichmentConsentError",
    "EnrichmentError",
    "EnrichmentModelError",
    "LLMLinkProposal",
    "LLMSummaryProposal",
    "LLMTopicProposal",
    "LinkSuggestion",
    "build_chat_model",
    "check_model",
    "estimate_tokens",
    "require_consent",
]

ENRICHMENT_SCHEMA_VERSION = "1"
MAX_CONTEXT_CHARS = 4000
MAX_SUMMARY_CHARS = 2000


# Agent plumbing lives in processing.agentic.common; these aliases keep
# existing imports working while new agents import from there directly.
EnrichmentError = AgentError
EnrichmentConsentError = AgentConsentError
EnrichmentModelError = AgentModelError


class LLMTopicProposal(FrozenModel):
    action: Literal["reuse", "propose", "alias", "abstain"]
    topic_id: str | None = None
    proposed_name: str | None = None
    alias_of: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_quotes: tuple[str, ...] = ()


class LLMSummaryProposal(FrozenModel):
    summary: str = ""
    key_points: tuple[str, ...] = ()
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    abstained: bool = False

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        if len(value) > MAX_SUMMARY_CHARS:
            raise ValueError(f"summary exceeds {MAX_SUMMARY_CHARS} characters")
        return value


class LinkSuggestion(FrozenModel):
    target_id: str
    relation: Literal["MENTIONS", "INTENDS_TO_RESOLVE", "RELATED_TO"]
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class LLMLinkProposal(FrozenModel):
    links: tuple[LinkSuggestion, ...] = ()
    rationale: str = ""
    abstained: bool = False


# ---------------------------------------------------------------------------
# Capability checks and model construction
# ---------------------------------------------------------------------------


def build_chat_model(settings: LLMSettings) -> BaseChatModel:
    """Build the documented real provider model for ``settings``.

    Only ``openai`` is wired (via the ``openai`` extra,
    ``langchain-openai``); anything else must be injected directly so no
    unreviewed provider path can run quietly.
    """

    require_consent(settings)
    if settings.provider != "openai":
        raise EnrichmentModelError(
            f"Unsupported provider {settings.provider!r}; inject a BaseChatModel directly instead"
        )
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise EnrichmentModelError(
            "langchain-openai is not installed; install the synirmos "
            "'openai' extra to use the documented OpenAI configuration"
        ) from exc
    try:
        return ChatOpenAI(
            model=settings.model,
            temperature=settings.temperature,
            max_retries=0,  # retries are budgeted explicitly by the Enricher
        )
    except Exception as exc:
        raise EnrichmentModelError(f"Could not construct ChatOpenAI: {exc}") from exc


def _cache_key(
    model_id: str,
    prompt_version: str,
    method: str,
    context_hash: str,
) -> str:
    return cache_key(
        namespace="llm-v1",
        model_id=model_id,
        prompt_version=prompt_version,
        schema_version=ENRICHMENT_SCHEMA_VERSION,
        method=method,
        context_hash=context_hash,
    )


class EnrichmentCache(AgentCache):
    """Persisted proposals keyed by model, prompt, schema, and context."""


# ---------------------------------------------------------------------------
# Enricher
# ---------------------------------------------------------------------------


class Enricher:
    """Run budgeted, cached, validated LLM proposals over grounded evidence."""

    def __init__(
        self,
        model: BaseChatModel,
        settings: LLMSettings,
        *,
        ledger: BudgetLedger,
        cache: EnrichmentCache,
        run_id: str,
    ) -> None:
        require_consent(settings)
        self.model_id = (
            f"{settings.provider}:{check_model(model)}" if settings.provider else check_model(model)
        )
        self._model = model
        self._settings = settings
        self._ledger = ledger
        self._cache = cache
        self._run_id = run_id

    @property
    def invocations(self) -> int:
        return getattr(self, "_invocations", 0)

    def _invoke(self, messages: list) -> AIMessage:
        self._invocations = self.invocations + 1
        try:
            response = self._model.invoke(messages)
        except Exception as exc:
            raise EnrichmentModelError(f"Chat model invocation failed: {exc}") from exc
        if not isinstance(response, AIMessage):
            raise EnrichmentModelError(
                f"Chat model returned {type(response).__name__}, not an AIMessage"
            )
        return response

    # ------------------------------------------------------------------ internals
    def _attempt(
        self,
        method: str,
        subject_id: str,
        context_text: str,
        schema: type[FrozenModel],
        evidence: Sequence[Any],
        info_horizon: datetime,
        extra_instructions: str = "",
        context_label: str = "evidence",
        allowed_ids: frozenset[str] | None = None,
    ) -> AnalysisResult:
        horizon = ensure_utc(info_horizon)
        context_text = context_text[:MAX_CONTEXT_CHARS]
        context_hash = hashlib.sha256(context_text.encode("utf-8")).hexdigest()
        key = _cache_key(self.model_id, self._settings.prompt_version, method, context_hash)

        cached = self._cache.lookup(key)
        if cached is not None:
            proposal = schema.model_validate(cached["proposal"])
            return self._envelope(
                method,
                subject_id,
                proposal,
                evidence,
                horizon,
                cached=True,
                context_hash=context_hash,
                estimated=cached.get("estimated_tokens", {}),
                actual=cached.get("actual_tokens", {}),
            )

        system = (
            "You assist repository-history indexing. Use ONLY the evidence below. "
            "Reply with exactly one JSON object matching the required schema. "
            "If the evidence is insufficient, respond with the abstain object. "
            "Never invent identifiers, topics, or relationships."
        )
        human = (
            f"Method: {method}\nSchema version: {ENRICHMENT_SCHEMA_VERSION}\n"
            f"Subject: {subject_id}\n{context_label}:\n{context_text}\n"
            f"{extra_instructions}"
            "Required schema (JSON object, no other text):\n"
            f"{json.dumps(schema.model_json_schema(), indent=1)}"
        )
        messages = [SystemMessage(content=system), HumanMessage(content=human)]
        prompt_text = system + "\n" + human
        estimated_input = estimate_tokens(prompt_text)
        estimated_output = estimate_tokens(context_text) + 100

        last_error = "no attempts made"
        for _ in range(self._settings.max_attempts):
            try:
                self._ledger.reserve_llm(
                    input_tokens=estimated_input,
                    output_tokens=estimated_output,
                    estimated_input_tokens=estimated_input,
                    estimated_output_tokens=estimated_output,
                )
            except BudgetExceeded as exc:
                return self._envelope(
                    method,
                    subject_id,
                    None,
                    evidence,
                    horizon,
                    cached=False,
                    context_hash=context_hash,
                    status=DecisionStatus.BUDGET_EXHAUSTED,
                    error=f"LLM budget exhausted: {exc}",
                    estimated={"input": estimated_input, "output": estimated_output},
                    actual={},
                )
            response = self._invoke(messages)
            usage = dict(getattr(response, "usage_metadata", None) or {})
            payload = parse_json_object(response.content)
            if payload is None:
                last_error = "model output was not a JSON object"
                continue
            try:
                proposal = schema.model_validate(payload)
                self._check_grounding(method, proposal, allowed_ids)
            except ValueError as exc:
                last_error = str(exc)
                continue
            actual = {
                "input": int(usage.get("input_tokens", 0)),
                "output": int(usage.get("output_tokens", 0)),
            }
            if getattr(proposal, "abstained", False) or (
                isinstance(proposal, LLMTopicProposal) and proposal.action == "abstain"
            ):
                # A deliberate abstention is stable for this context: cache it.
                # Validation-failure abstentions below are not cached.
                record = {
                    "proposal": proposal.model_dump(mode="json"),
                    "estimated_tokens": {"input": estimated_input, "output": estimated_output},
                    "actual_tokens": actual,
                }
                self._cache.store(key, record)
                return self._envelope(
                    method,
                    subject_id,
                    proposal,
                    evidence,
                    horizon,
                    cached=False,
                    context_hash=context_hash,
                    status=DecisionStatus.ABSTAINED,
                    estimated={"input": estimated_input, "output": estimated_output},
                    actual=actual,
                )
            record = {
                "proposal": proposal.model_dump(mode="json"),
                "estimated_tokens": {"input": estimated_input, "output": estimated_output},
                "actual_tokens": actual,
            }
            self._cache.store(key, record)
            return self._envelope(
                method,
                subject_id,
                proposal,
                evidence,
                horizon,
                cached=False,
                context_hash=context_hash,
                estimated=record["estimated_tokens"],
                actual=actual,
            )
        return self._envelope(
            method,
            subject_id,
            None,
            evidence,
            horizon,
            cached=False,
            context_hash=context_hash,
            status=DecisionStatus.ABSTAINED,
            error=f"model output failed validation after retries: {last_error}",
            estimated={"input": estimated_input, "output": estimated_output},
            actual={},
        )

    def _check_grounding(
        self, method: str, proposal: FrozenModel, allowed_ids: frozenset[str] | None
    ) -> None:
        """Reject proposals that reference evidence never supplied.

        Allowed identifiers come from the caller-held candidate structures,
        not from re-parsing the prompt text, so a ``:`` inside an ID cannot
        confuse the check.
        """

        if isinstance(proposal, LLMTopicProposal):
            allowed = allowed_ids or frozenset()
            if proposal.action == "reuse" and proposal.topic_id not in allowed:
                raise ValueError(f"reused topic {proposal.topic_id!r} is not among candidates")
            if proposal.action == "alias" and proposal.alias_of not in allowed:
                raise ValueError(f"alias target {proposal.alias_of!r} is not among candidates")
        elif isinstance(proposal, LLMLinkProposal):
            if not proposal.abstained:
                allowed = allowed_ids or frozenset()
                for link in proposal.links:
                    if link.target_id not in allowed:
                        raise ValueError(f"link target {link.target_id!r} is not among candidates")

    def _envelope(
        self,
        method: str,
        subject_id: str,
        proposal: FrozenModel | None,
        evidence: Sequence[Any],
        horizon: datetime,
        *,
        cached: bool,
        context_hash: str,
        status: DecisionStatus = DecisionStatus.ACCEPTED,
        error: str | None = None,
        estimated: dict[str, int] | None = None,
        actual: dict[str, int] | None = None,
    ) -> AnalysisResult:
        estimated = estimated or {}
        actual = actual or {}
        value: dict[str, Any] = {
            "method": method,
            "model": self.model_id,
            "prompt_version": self._settings.prompt_version,
            "schema_version": ENRICHMENT_SCHEMA_VERSION,
            "context_hash": context_hash,
            "cached": cached,
            "proposal": proposal.model_dump(mode="json") if proposal is not None else None,
            "status_detail": status.value,
        }
        if error is not None:
            value["reason"] = error
        return AnalysisResult.create(
            subject_id=subject_id,
            kind=f"llm-{method}",
            status=status,
            value=value,
            provenance=Provenance(
                method=f"llm-{method}-proposal",
                method_version="1",
                run_id=self._run_id,
                info_horizon=horizon,
                model=self.model_id,
                prompt_version=self._settings.prompt_version,
                schema_version=ENRICHMENT_SCHEMA_VERSION,
                estimated_input_tokens=estimated.get("input", 0),
                estimated_output_tokens=estimated.get("output", 0),
                actual_input_tokens=actual.get("input", 0),
                actual_output_tokens=actual.get("output", 0),
            ),
            evidence=tuple(evidence),
            error=error if status is DecisionStatus.BUDGET_EXHAUSTED else None,
        )

    # -- typed entry points -------------------------------------------------
    def enrich_topic(
        self,
        *,
        subject_id: str,
        subject_text: str,
        candidates: Sequence[Mapping[str, str]],
        registry_version: int,
        info_horizon: datetime,
        evidence: Sequence[Any] = (),
    ) -> AnalysisResult:
        listing = "\n".join(f"- {item['topic_id']}: {item['name']}" for item in candidates)
        context = (
            f"Subject text:\n{subject_text}\n\n"
            f"Candidate topics (registry v{registry_version}):\n{listing or '(none)'}\n"
        )
        instructions = (
            "Set action to reuse (with topic_id), propose (with proposed_name), "
            "alias (with proposed_name and alias_of), or abstain. "
            "Reuse and alias targets MUST be chosen from the candidate list."
        )
        return self._attempt(
            "topic",
            subject_id,
            context,
            LLMTopicProposal,
            evidence,
            info_horizon,
            extra_instructions=instructions,
            allowed_ids=frozenset(item["topic_id"] for item in candidates),
        )

    def enrich_summary(
        self,
        *,
        subject_id: str,
        title: str,
        text: str,
        info_horizon: datetime,
        evidence: Sequence[Any] = (),
    ) -> AnalysisResult:
        context = f"Title: {title}\nBody:\n{text}"
        instructions = (
            "Summarize the subject in at most a few sentences plus key points. "
            "If the body is empty or unintelligible, abstain."
        )
        return self._attempt(
            "summary",
            subject_id,
            context,
            LLMSummaryProposal,
            evidence,
            info_horizon,
            extra_instructions=instructions,
        )

    def enrich_links(
        self,
        *,
        subject_id: str,
        subject_text: str,
        candidate_targets: Mapping[str, str],
        info_horizon: datetime,
        evidence: Sequence[Any] = (),
    ) -> AnalysisResult:
        listing = "\n".join(
            f"- {target_id}: {description}" for target_id, description in candidate_targets.items()
        )
        context = f"Subject text:\n{subject_text}\n\nLinkable targets:\n{listing or '(none)'}\n"
        instructions = (
            "Propose links only to the listed targets with one of the relations "
            "MENTIONS, INTENDS_TO_RESOLVE, or RELATED_TO. "
            "If no target is supported by the subject text, abstain."
        )
        return self._attempt(
            "link",
            subject_id,
            context,
            LLMLinkProposal,
            evidence,
            info_horizon,
            extra_instructions=instructions,
            allowed_ids=frozenset(candidate_targets),
        )


def gap_for_unavailable_history(subject: str, detail: str) -> CoverageGap:
    """Report unavailable source history instead of asking the model to guess."""

    return CoverageGap(
        code="llm-history-unavailable",
        status=CoverageStatus.UNAVAILABLE,
        message=f"No source history for {subject}; no LLM proposal was requested: {detail}",
        source="llm",
        source_ids=(subject,),
    )
