"""Scoped context values and exact exposure receipts, independent of agents/storage."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    SHA256,
    ArtifactSpec,
    ContractModel,
    NonBlank,
    canonical_json,
    json_fingerprint,
)
from .documents import SourceSpan
from .graph import EntityRecord, GraphScope, Properties, RelationshipRecord, Visibility
from .limits import ReadUsage
from .models import CoverageGap


class KnowledgeQuery(ContractModel):
    """Bounded scope browsing is allowed; None/empty filters mean all granted/none."""

    text: str = ""
    entity_ids: tuple[NonBlank, ...] | None = None
    predicate_ids: tuple[NonBlank, ...] | None = None
    direction: Literal["out", "in", "any"] = "any"

    @field_validator("entity_ids", "predicate_ids")
    @classmethod
    def canonical_filters(cls, values: tuple[str, ...] | None) -> tuple[str, ...] | None:
        return None if values is None else tuple(sorted(set(values)))


class ContextRequest(ContractModel):
    subject_id: NonBlank
    scope: GraphScope
    query: KnowledgeQuery = Field(default_factory=KnowledgeQuery)
    continuation: NonBlank | None = None

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(self.model_dump(mode="json"))


class EvidenceRecord(ContractModel):
    evidence_id: NonBlank
    version_id: NonBlank
    visibility: Visibility
    properties: Properties = Field(default_factory=lambda: Properties({}))
    span: SourceSpan | None = None


def _payload_bytes(entities, relationships, evidence) -> int:
    if not (entities or relationships or evidence):
        return 0
    return len(
        canonical_json(
            {
                "entities": [item.model_dump(mode="json") for item in entities],
                "relationships": [item.model_dump(mode="json") for item in relationships],
                "evidence": [item.model_dump(mode="json") for item in evidence],
            }
        ).encode("utf-8")
    )


class ResultStatus(StrEnum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    UNSUPPORTED = "unsupported"
    DENIED = "denied"
    FAILED = "failed"


class RecordReference(ContractModel):
    record_id: NonBlank
    version_id: NonBlank
    payload_fingerprint: SHA256


class ContextExposure(ContractModel):
    """Trusted host's receipt of exact delivered values, not a model-supplied claim."""

    scope_fingerprint: SHA256
    context_fingerprint: SHA256
    entity_versions: tuple[RecordReference, ...] = ()
    relationship_versions: tuple[RecordReference, ...] = ()
    evidence_versions: tuple[RecordReference, ...] = ()
    usage: ReadUsage

    @model_validator(mode="after")
    def complete_references(self) -> Self:
        groups = (self.entity_versions, self.relationship_versions, self.evidence_versions)
        if self.usage.results != sum(len(group) for group in groups):
            raise ValueError("exposure count must match delivered references")
        for group in groups:
            if len({ref.record_id for ref in group}) != len(group):
                raise ValueError("exposure contains duplicate record identities")
        return self


class ContextResult(ContractModel):
    """Whole visible records; the host creates receipts only after actual delivery.

    Counts/bytes cover all dependency records, not just primary hits. Bytes are
    canonical JSON record payload (zero for no records), not a model-token count
    or the entire envelope/formatted tool response. Those have separate caps.
    """

    request: ContextRequest
    provider: ArtifactSpec
    entities: tuple[EntityRecord, ...] = ()
    relationships: tuple[RelationshipRecord, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    status: ResultStatus = ResultStatus.COMPLETE
    continuation: NonBlank | None = None
    gaps: tuple[CoverageGap, ...] = ()
    usage: ReadUsage

    @property
    def payload_bytes(self) -> int:
        return _payload_bytes(self.entities, self.relationships, self.evidence)

    @model_validator(mode="after")
    def explicit_outcome(self) -> Self:
        records = (*self.entities, *self.relationships, *self.evidence)
        if self.status == ResultStatus.COMPLETE and self.continuation is not None:
            raise ValueError("complete results cannot have continuation")
        if self.status == ResultStatus.TRUNCATED and not (self.continuation or self.gaps):
            raise ValueError("truncated results require continuation or an explicit gap")
        if self.status in {ResultStatus.UNSUPPORTED, ResultStatus.DENIED, ResultStatus.FAILED}:
            if records or self.continuation is not None or not self.gaps:
                raise ValueError(
                    "failed/denied/unsupported results require gaps and no records/cursor"
                )
        return self

    @model_validator(mode="after")
    def exact_bounded_usage(self) -> Self:
        records = (*self.entities, *self.relationships, *self.evidence)
        if self.usage.results != len(records) or self.usage.output_bytes != self.payload_bytes:
            raise ValueError("usage must match the exact delivered record count and payload bytes")
        self.usage.check(self.request.scope.limits)
        return self

    @model_validator(mode="after")
    def visible_dependencies(self) -> Self:
        records = (*self.entities, *self.relationships, *self.evidence)
        for items, field in (
            (self.entities, "entity_id"),
            (self.relationships, "relationship_id"),
            (self.evidence, "evidence_id"),
        ):
            ids = [getattr(item, field) for item in items]
            if len(set(ids)) != len(ids):
                raise ValueError(f"context contains duplicate {field} values")
        if any(not self.request.scope.includes(item.visibility) for item in records):
            raise ValueError("context contains a record outside the effective scope")
        entity_ids = {item.entity_id for item in self.entities}
        if any(
            edge.source_id not in entity_ids or edge.target_id not in entity_ids
            for edge in self.relationships
        ):
            raise ValueError("relationship endpoints must be visible and delivered")
        evidence_ids = {item.evidence_id for item in self.evidence}
        if any(
            not set(item.evidence_ids) <= evidence_ids
            for item in (*self.entities, *self.relationships)
        ):
            raise ValueError("referenced evidence must be visible and delivered")
        return self

    @classmethod
    def from_records(
        cls,
        *,
        request: ContextRequest,
        provider: ArtifactSpec,
        entities: tuple[EntityRecord, ...] = (),
        relationships: tuple[RelationshipRecord, ...] = (),
        evidence: tuple[EvidenceRecord, ...] = (),
        status: ResultStatus = ResultStatus.COMPLETE,
        continuation: str | None = None,
        gaps: tuple[CoverageGap, ...] = (),
        candidates: int | None = None,
        read_bytes: int | None = None,
    ) -> Self:
        # Calculate the same wire payload without constructing an unvalidated model.
        records = (*entities, *relationships, *evidence)
        return cls(
            request=request,
            provider=provider,
            entities=entities,
            relationships=relationships,
            evidence=evidence,
            status=status,
            continuation=continuation,
            gaps=gaps,
            usage=ReadUsage(
                results=len(records),
                output_bytes=_payload_bytes(entities, relationships, evidence),
                candidates=candidates,
                read_bytes=read_bytes,
            ),
        )

    @property
    def fingerprint(self) -> str:
        # Physical telemetry is persisted, but warm/cold read costs cannot turn
        # the same delivered knowledge into a new extraction operation.
        return json_fingerprint(self.model_dump(mode="json", exclude={"usage"}))

    def exposure(self) -> ContextExposure:
        def references(items, id_field):
            return tuple(
                RecordReference(
                    record_id=getattr(item, id_field),
                    version_id=item.version_id,
                    payload_fingerprint=json_fingerprint(item.model_dump(mode="json")),
                )
                for item in items
            )

        return ContextExposure(
            scope_fingerprint=self.request.scope.fingerprint,
            context_fingerprint=self.fingerprint,
            entity_versions=references(self.entities, "entity_id"),
            relationship_versions=references(self.relationships, "relationship_id"),
            evidence_versions=references(self.evidence, "evidence_id"),
            usage=self.usage,
        )


class ExposureSet(ContractModel):
    """Ordered delivered tool-result receipts. Duplicate calls still spend budget.

    Only the trusted host may create receipts, after whole-record delivery. The
    receipt model itself is neither an authentication token nor proof of truth.
    """

    scope: GraphScope
    contexts: tuple[ContextExposure, ...] = ()

    @model_validator(mode="after")
    def compatible_contexts(self) -> Self:
        scope_id = self.scope.fingerprint
        for context in self.contexts:
            if context.scope_fingerprint != scope_id:
                raise ValueError("cannot combine exposure from different scopes/pins")
        for field in ("entity_versions", "relationship_versions", "evidence_versions"):
            seen = {}
            for context in self.contexts:
                for ref in getattr(context, field):
                    if ref.record_id in seen and seen[ref.record_id] != ref:
                        raise ValueError("conflicting exposed versions or payloads")
                    seen[ref.record_id] = ref
        self.usage.check(self.scope.limits)
        return self

    @property
    def usage(self) -> ReadUsage:
        total = ReadUsage(candidates=0, read_bytes=0)
        for context in self.contexts:
            total = total.add(context.usage)
        return total

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({ref.record_id for item in self.contexts for ref in item.entity_versions})
        )

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(
            self.model_dump(mode="json", exclude={"contexts": {"__all__": {"usage"}}})
        )
