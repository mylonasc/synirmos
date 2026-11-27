"""Basic joint entity-and-relation extraction (JERE) provider.

A bounded LangChain agent that extracts entities and their relations in
one joint proposal. The agent's only window into already known state is
the injected :class:`ParsingContext`: a read-only, horizon-filtered,
bounded handle over other entities, relations, and (in future
graph-backed implementations) the already parsed graph.

The loop is deliberately small and dependency-free (``langchain-core``
only, no agent-framework extra): the model either calls one of the four
context tools or returns the final :class:`JereProposal` as a single JSON
object. Every invocation is budgeted, cached, and provenance-recorded, and
ungrounded identifiers are retried, then abstained — never invented into
the graph.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ...core.analysis import AnalysisResult, DecisionStatus, Provenance
from ...core.budgets import BudgetExceeded, BudgetLedger
from ...core.ids import IdFactory
from ...core.models import EvidenceRef, LLMSettings, ensure_utc
from .common import (
    AgentCache,
    AgentModelError,
    cache_key,
    check_model,
    estimate_tokens,
    parse_json_object,
    require_consent,
)
from .jere_models import (
    JERE_METHOD,
    JERE_METHOD_VERSION,
    JERE_SCHEMA_VERSION,
    JereProposal,
    link_relation_for,
)
from .parsing_context import ParsingContext

__all__ = [
    "JERE_CACHE_NAMESPACE",
    "JERE_MAX_CONTEXT_CHARS",
    "JERE_MAX_ENTITIES",
    "JERE_MAX_OBSERVATION_CHARS",
    "JERE_MAX_RELATIONS",
    "BasicJereProvider",
]

JERE_CACHE_NAMESPACE = "jere-v1"
JERE_MAX_CONTEXT_CHARS = 4000
JERE_MAX_OBSERVATION_CHARS = 2000
JERE_MAX_ENTITIES = 32
JERE_MAX_RELATIONS = 64

_TOOL_NAMES = ("search_entities", "get_entity", "list_relations", "neighbors")


class BasicJereProvider:
    """Run budgeted, cached, validated JERE proposals over a ParsingContext."""

    name = "jere-basic"
    version = "1"

    def __init__(
        self,
        model: BaseChatModel,
        settings: LLMSettings,
        *,
        ledger: BudgetLedger,
        cache: AgentCache,
        run_id: str,
        ids: IdFactory,
        max_tool_steps: int = 3,
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
        self._ids = ids
        self._max_tool_steps = max(0, max_tool_steps)

    @property
    def invocations(self) -> int:
        return getattr(self, "_invocations", 0)

    # -- public entry points -------------------------------------------
    def extract(
        self,
        *,
        context: ParsingContext,
        evidence: Sequence[EvidenceRef] = (),
    ) -> AnalysisResult:
        """Extract entities and relations for ``context.subject_id``."""

        horizon = ensure_utc(context.info_horizon)
        subject_id = context.subject_id
        subject_text = context.subject_text[:JERE_MAX_CONTEXT_CHARS]
        context_hash = hashlib.sha256(
            f"{subject_text}\x00{context.snapshot_digest()}".encode()
        ).hexdigest()
        key = cache_key(
            namespace=JERE_CACHE_NAMESPACE,
            model_id=self.model_id,
            prompt_version=self._settings.prompt_version,
            schema_version=JERE_SCHEMA_VERSION,
            method="extract",
            context_hash=context_hash,
        )

        cached = self._cache.lookup(key)
        if cached is not None:
            return self._envelope(
                subject_id,
                JereProposal.model_validate(cached["proposal"]),
                DecisionStatus(cached["status"]),
                tuple(evidence),
                horizon,
                cached=True,
                context_hash=context_hash,
                tool_steps=int(cached.get("tool_steps", 0)),
                reason=cached.get("reason"),
                estimated=cached.get("estimated_tokens", {}),
                actual=cached.get("actual_tokens", {}),
            )

        if not subject_text.strip():
            return self._envelope(
                subject_id,
                JereProposal(abstained=True, rationale="Empty subject text."),
                DecisionStatus.ABSTAINED,
                tuple(evidence),
                horizon,
                cached=False,
                context_hash=context_hash,
                tool_steps=0,
                reason="empty subject text; no LLM call was made",
            )

        try:
            proposal, status, reason, tool_steps, estimated, actual = self._run_agent(
                subject_id, subject_text, context
            )
        except BudgetExceeded as exc:
            estimated_blank = {"input": 0, "output": 0}
            return self._envelope(
                subject_id,
                None,
                DecisionStatus.BUDGET_EXHAUSTED,
                tuple(evidence),
                horizon,
                cached=False,
                context_hash=context_hash,
                tool_steps=0,
                reason=f"LLM budget exhausted: {exc}",
                estimated=estimated_blank,
                actual={},
            )

        if proposal is None:
            # Mid-loop failures never produced a proposal: report without caching.
            return self._envelope(
                subject_id,
                None,
                status,
                tuple(evidence),
                horizon,
                cached=False,
                context_hash=context_hash,
                tool_steps=tool_steps,
                reason=reason,
                estimated=estimated,
                actual=actual,
            )
        record = {
            "proposal": proposal.model_dump(mode="json"),
            "status": status.value,
            "reason": reason,
            "tool_steps": tool_steps,
            "estimated_tokens": estimated,
            "actual_tokens": actual,
        }
        # A decided proposal (including a deliberate abstention) is stable
        # for this context: cache it.
        self._cache.store(key, record)
        return self._envelope(
            subject_id,
            proposal,
            status,
            tuple(evidence),
            horizon,
            cached=False,
            context_hash=context_hash,
            tool_steps=tool_steps,
            reason=reason,
            estimated=estimated,
            actual=actual,
        )

    def label(self, *, text: str, context: Any) -> Sequence[AnalysisResult]:
        """Implement the :class:`Labeler` protocol via :meth:`extract`."""

        parsing_context = _require_parsing_context(context)
        _ = text  # subject text travels inside the parsing context
        return (self.extract(context=parsing_context, evidence=tuple(context.get("evidence", ()))),)

    def resolve(
        self, *, subject: Any, candidates: Sequence[Any], context: Any
    ) -> Sequence[AnalysisResult]:
        """Implement the :class:`RelationshipResolver` protocol via :meth:`extract`."""

        parsing_context = _require_parsing_context(context)
        _ = (subject, candidates)  # candidates travel inside the parsing context
        return (self.extract(context=parsing_context, evidence=tuple(context.get("evidence", ()))),)

    # -- agent loop ------------------------------------------------------
    def _run_agent(
        self, subject_id: str, subject_text: str, context: ParsingContext
    ) -> tuple[JereProposal | None, DecisionStatus, str | None, int, dict, dict]:
        last_error = "no attempts made"
        estimated = {"input": 0, "output": 0}
        actual = {"input": 0, "output": 0}
        tool_steps = 0
        for _ in range(max(1, self._settings.max_attempts)):
            history: list = [_system_message(), _initial_human(subject_id, subject_text, context)]
            for _ in range(self._max_tool_steps + 1):
                prompt_text = "\n".join(str(getattr(message, "content", "")) for message in history)
                estimated_input = estimate_tokens(prompt_text)
                estimated_output = estimate_tokens(subject_text) + 100
                self._ledger.reserve_llm(
                    input_tokens=estimated_input,
                    output_tokens=estimated_output,
                    estimated_input_tokens=estimated_input,
                    estimated_output_tokens=estimated_output,
                )
                estimated["input"] += estimated_input
                estimated["output"] += estimated_output
                response = self._invoke(history)
                usage = dict(getattr(response, "usage_metadata", None) or {})
                actual["input"] += int(usage.get("input_tokens", 0))
                actual["output"] += int(usage.get("output_tokens", 0))
                payload = parse_json_object(response.content)
                if payload is None:
                    last_error = "model output was not a JSON object"
                    history.append(_feedback(f"Invalid reply: {last_error}."))
                    continue
                if "tool_call" in payload:
                    if tool_steps >= self._max_tool_steps:
                        last_error = "tool step budget exhausted without a final proposal"
                        break
                    try:
                        observation = self._dispatch_tool(payload["tool_call"], context)
                    except ValueError as exc:
                        last_error = str(exc)
                        history.append(_feedback(f"Invalid tool call: {exc}."))
                        continue
                    tool_steps += 1
                    history.append(_feedback(f"Observation:\n{observation}"))
                    continue
                try:
                    proposal = JereProposal.model_validate(payload)
                    self._check_grounding(proposal, context)
                except ValueError as exc:
                    last_error = str(exc)
                    history.append(_feedback(f"Invalid proposal: {exc}."))
                    continue
                if proposal.abstained:
                    return proposal, DecisionStatus.ABSTAINED, None, tool_steps, estimated, actual
                return proposal, DecisionStatus.ACCEPTED, None, tool_steps, estimated, actual
        return (
            None,
            DecisionStatus.ABSTAINED,
            f"model output failed validation after retries: {last_error}",
            tool_steps,
            estimated,
            actual,
        )

    def _invoke(self, messages: list) -> AIMessage:
        self._invocations = self.invocations + 1
        try:
            response = self._model.invoke(messages)
        except Exception as exc:
            raise AgentModelError(f"Chat model invocation failed: {exc}") from exc
        if not isinstance(response, AIMessage):
            raise AgentModelError(
                f"Chat model returned {type(response).__name__}, not an AIMessage"
            )
        return response

    def _dispatch_tool(self, call: Any, context: ParsingContext) -> str:
        if not isinstance(call, dict):
            raise ValueError("tool_call must be an object with name and args")
        name = call.get("name")
        args = call.get("args", {})
        if not isinstance(name, str) or not isinstance(args, dict):
            raise ValueError("tool_call must be an object with name and args")
        try:
            if name == "search_entities":
                query = str(args.get("query", ""))[:500]
                found = context.search_entities(
                    query, limit=_clamp_int(args.get("limit", 20), 1, 50)
                )
                return _render_entities(found)
            if name == "get_entity":
                entity_id = str(args.get("entity_id", ""))
                found_one = context.get_entity(entity_id)
                return _render_entities((found_one,) if found_one is not None else ())
            if name == "list_relations":
                raw = args.get("entity_id")
                entity_id = str(raw) if raw is not None else None
                relations = context.list_relations(
                    entity_id, limit=_clamp_int(args.get("limit", 50), 1, 50)
                )
                return _render_relations(relations)
            if name == "neighbors":
                entity_id = str(args.get("entity_id", ""))
                raw_relation = args.get("relation")
                relation = str(raw_relation) if raw_relation is not None else None
                return _render_neighbors(context.neighbors(entity_id, relation))
        except ValueError:
            raise
        except Exception as exc:
            return f"tool {name} failed: {exc}"[:JERE_MAX_OBSERVATION_CHARS]
        return f"unknown tool {name!r}; available: {', '.join(_TOOL_NAMES)}"

    def _check_grounding(self, proposal: JereProposal, context: ParsingContext) -> None:
        if len(proposal.entities) > JERE_MAX_ENTITIES:
            raise ValueError(f"proposal has {len(proposal.entities)} entities; at most 32 allowed")
        if len(proposal.relations) > JERE_MAX_RELATIONS:
            raise ValueError(
                f"proposal has {len(proposal.relations)} relations; at most 64 allowed"
            )
        known = {entity.entity_id for entity in context.list_entities(limit=1000)}
        known.add(context.subject_id)
        keys = {entity.key for entity in proposal.entities}
        for relation in proposal.relations:
            for endpoint in (relation.source, relation.target):
                if endpoint not in keys and endpoint not in known:
                    raise ValueError(
                        f"relation endpoint {endpoint!r} is neither a declared "
                        "entity key nor an observed entity ID"
                    )

    # -- result envelope -------------------------------------------------
    def _envelope(
        self,
        subject_id: str,
        proposal: JereProposal | None,
        status: DecisionStatus,
        evidence: Sequence[EvidenceRef],
        horizon: datetime,
        *,
        cached: bool,
        context_hash: str,
        tool_steps: int,
        reason: str | None = None,
        estimated: dict | None = None,
        actual: dict | None = None,
    ) -> AnalysisResult:
        estimated = estimated or {}
        actual = actual or {}
        value: dict[str, Any] = {
            "method": "extract",
            "model": self.model_id,
            "prompt_version": self._settings.prompt_version,
            "schema_version": JERE_SCHEMA_VERSION,
            "context_hash": context_hash,
            "cached": cached,
            "tool_steps": tool_steps,
            "proposal": self._resolved_value(proposal) if proposal is not None else None,
            "status_detail": status.value,
        }
        if reason is not None:
            value["reason"] = reason
        return AnalysisResult.create(
            subject_id=subject_id,
            kind="jere",
            status=status,
            value=value,
            provenance=Provenance(
                method=JERE_METHOD,
                method_version=JERE_METHOD_VERSION,
                run_id=self._run_id,
                info_horizon=horizon,
                model=self.model_id,
                prompt_version=self._settings.prompt_version,
                schema_version=JERE_SCHEMA_VERSION,
                estimated_input_tokens=estimated.get("input", 0),
                estimated_output_tokens=estimated.get("output", 0),
                actual_input_tokens=actual.get("input", 0),
                actual_output_tokens=actual.get("output", 0),
            ),
            evidence=tuple(evidence),
            error=reason if status is DecisionStatus.BUDGET_EXHAUSTED else None,
        )

    def _resolved_value(self, proposal: JereProposal) -> dict[str, Any]:
        key_to_id = {
            entity.key: self._ids.evidence(
                "jere-entity", entity.kind.value, entity.name.strip().lower()
            )
            for entity in proposal.entities
        }
        return {
            "entities": [
                {
                    "entity_id": key_to_id[entity.key],
                    "key": entity.key,
                    "kind": entity.kind.value,
                    "name": entity.name,
                    "confidence": entity.confidence,
                    "rationale": entity.rationale,
                    "evidence_quotes": list(entity.evidence_quotes),
                }
                for entity in proposal.entities
            ],
            "relations": [
                {
                    "source_id": key_to_id.get(relation.source, relation.source),
                    "target_id": key_to_id.get(relation.target, relation.target),
                    "relation": relation.relation.value,
                    "link_relation": link_relation_for(relation.relation),
                    "confidence": relation.confidence,
                    "rationale": relation.rationale,
                }
                for relation in proposal.relations
            ],
            "abstained": proposal.abstained,
            "rationale": proposal.rationale,
        }


# ---------------------------------------------------------------------------
# Prompt and rendering helpers (pure; no I/O, no model calls)
# ---------------------------------------------------------------------------


def _system_message() -> SystemMessage:
    return SystemMessage(
        content=(
            "You are a joint entity-and-relation extractor for repository-history indexing. "
            "Use ONLY the subject text and the observations returned by the context tools. "
            "Reply with exactly one JSON object per turn: either a tool call "
            '{"tool_call": {"name": ..., "args": {...}}} or the final extraction '
            '{"entities": [...], "relations": [...], "abstained": false, "rationale": "..."}. '
            "New entities use temporary keys "
            '{"key": "e1", "kind": "CONCEPT", "name": ..., "confidence": ..., '
            '"rationale": ..., "evidence_quotes": [...]} with kind in '
            "FILE, SYMBOL, SECTION, TOPIC, CONCEPT, WORK_ITEM, COMMIT. "
            "FILE, SYMBOL, SECTION, TOPIC, CONCEPT, WORK_ITEM, COMMIT. "
            "Relations use "
            '{"source": ..., "target": ..., "relation": ..., "confidence": ..., "rationale": ...} '
            "with relation in MENTIONS, RELATED_TO, INTENDS_TO_RESOLVE, DEFINES, PART_OF; "
            "endpoints must be declared keys or previously observed entity IDs. "
            "If the evidence is insufficient, return the abstain object "
            '{"entities": [], "relations": [], "abstained": true, "rationale": "..."}. '
            "Never invent identifiers. Available tools: "
            "search_entities(query, limit), get_entity(entity_id), "
            "list_relations(entity_id?, limit), neighbors(entity_id, relation?)."
        )
    )


def _initial_human(subject_id: str, subject_text: str, context: ParsingContext) -> HumanMessage:
    snapshot = _render_entities(context.list_entities(limit=20))
    relations = _render_relations(context.list_relations(limit=20))
    return HumanMessage(
        content=(
            f"Subject: {subject_id}\nSubject text:\n{subject_text}\n\n"
            f"Known entities (read-only, reference by ID):\n{snapshot}\n\n"
            f"Known relations:\n{relations}\n\n"
            "Required schema (final JSON object, no other text):\n"
            f"{json.dumps(JereProposal.model_json_schema(), indent=1)}"
        )
    )


def _feedback(text: str) -> HumanMessage:
    return HumanMessage(content=f"{text} Reply with corrected JSON or abstain.")


def _render_entities(entities: Sequence[Any]) -> str:
    lines = []
    for entity in entities:
        description = str(getattr(entity, "description", "") or "")[:160]
        lines.append(
            f"- {entity.entity_id} [{entity.kind}] {entity.name}"
            + (f" :: {description}" if description else "")
        )
    return _truncate("\n".join(lines) if lines else "(no entities)")


def _render_relations(relations: Sequence[Any]) -> str:
    lines = [f"- {item.source_id} --{item.relation}--> {item.target_id}" for item in relations]
    return _truncate("\n".join(lines) if lines else "(no relations)")


def _render_neighbors(neighbors: Sequence[str]) -> str:
    return _truncate("\n".join(f"- {entity_id}" for entity_id in neighbors) or "(no neighbors)")


def _truncate(text: str) -> str:
    if len(text) > JERE_MAX_OBSERVATION_CHARS:
        return text[:JERE_MAX_OBSERVATION_CHARS]
    return text


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def _require_parsing_context(context: Any) -> ParsingContext:
    if not isinstance(context, dict):
        raise ValueError("label/resolve context must provide a parsing_context entry")
    parsing_context = context.get("parsing_context")
    if not isinstance(parsing_context, ParsingContext):
        raise ValueError("label/resolve context must provide a parsing_context entry")
    return parsing_context
