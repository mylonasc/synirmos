"""Neutral proposal/provenance contracts. Agents cannot publish canonical facts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, StrictInt, field_validator, model_validator

from .context import ExposureSet
from .contracts import SHA256, ArtifactSpec, ContractModel, NonBlank, contract_id, json_fingerprint
from .documents import ContentMismatchError, DocumentRevision, SourceSpan
from .graph import ApprovalStatus, Visibility
from .models import ensure_utc
from .temporal import RevisionTiming


class EvidenceSpan(ContractModel):
    """Claimed exact original quote. Verify bytes/access again at trust boundaries."""

    span: SourceSpan
    quote: NonBlank
    encoding: NonBlank = "utf-8"

    @model_validator(mode="after")
    def nonempty_span(self) -> Self:
        if self.span.start == self.span.end:
            raise ValueError("supporting evidence cannot be an empty span")
        return self

    def verify(self, original: bytes) -> None:
        if self.span.extract(original).decode(self.encoding) != self.quote:
            raise ContentMismatchError("evidence quote differs from original bytes")


class ExtractionSubject(ContractModel):
    """One contiguous original-text input; transforms need explicit parser source maps."""

    revision: DocumentRevision
    span: SourceSpan
    text: str
    visibility: Visibility
    chunk_occurrence_id: NonBlank | None = None

    @model_validator(mode="after")
    def consistent_source(self) -> Self:
        if (
            self.span.revision_id != self.revision.revision_id
            or self.span.content != self.revision.content
        ):
            raise ValueError("subject span must bind the exact captured revision/content")
        if (
            self.visibility.source_instance != self.revision.document.key.source_instance
            or self.visibility.timing != self.revision.timing
        ):
            raise ValueError("subject visibility source/timing must match its revision")
        return self

    def verify(self, original: bytes) -> None:
        if self.span.extract(original).decode(self.revision.encoding) != self.text:
            raise ContentMismatchError("subject text differs from original bytes")

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(self.model_dump(mode="json"))

    @property
    def subject_id(self) -> str:
        return contract_id("subject", self.fingerprint)


class ExtractionLimits(ContractModel):
    max_entities: StrictInt = Field(default=128, ge=0)
    max_relations: StrictInt = Field(default=256, ge=0)
    max_evidence_spans: StrictInt = Field(default=512, ge=0)
    max_model_calls: StrictInt = Field(default=4, ge=0)
    max_input_tokens: StrictInt = Field(default=16_000, ge=0)
    max_output_tokens: StrictInt = Field(default=4_000, ge=0)


class ExtractionProfile(ContractModel):
    """Exact versioned task/model/prompt/tools/schema identity, not a live model."""

    task: ArtifactSpec
    model: ArtifactSpec
    prompt: ArtifactSpec
    tools: ArtifactSpec
    schema_fingerprint: SHA256
    ontology_release: NonBlank | None = None
    limits: ExtractionLimits = Field(default_factory=ExtractionLimits)

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(self.model_dump(mode="json"))


class ExtractionOperation(ContractModel):
    """Intent identity survives retries. Run lineage and physical telemetry do not define it."""

    subject: ExtractionSubject
    profile: ExtractionProfile
    exposure: ExposureSet
    analysis_version: NonBlank = "1"

    @model_validator(mode="after")
    def pinned_inputs(self) -> Self:
        scope = self.exposure.scope
        if not scope.includes(self.subject.visibility):
            raise ValueError("extraction subject is outside the effective scope")
        if self.profile.ontology_release != scope.snapshot.ontology_release:
            raise ValueError("extraction profile must match the pinned ontology release")
        return self

    @property
    def operation_id(self) -> str:
        return contract_id(
            "extraction",
            self.subject.fingerprint,
            self.profile.fingerprint,
            self.exposure.fingerprint,
            self.analysis_version,
        )


class EntityCandidate(ContractModel):
    operation_id: NonBlank
    local_key: NonBlank
    name: NonBlank
    class_id: NonBlank
    evidence: tuple[EvidenceSpan, ...] = Field(min_length=1)
    reuse_entity_id: NonBlank | None = None

    @property
    def candidate_id(self) -> str:
        return contract_id("entity-candidate", self.operation_id, self.local_key)

    @property
    def mention_ids(self) -> tuple[str, ...]:
        return tuple(
            contract_id(
                "mention", self.candidate_id, json_fingerprint(item.model_dump(mode="json"))
            )
            for item in self.evidence
        )


class ClaimPolarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class RelationCandidate(ContractModel):
    operation_id: NonBlank
    local_key: NonBlank
    subject_key: NonBlank
    predicate_id: NonBlank
    object_key: NonBlank
    evidence: tuple[EvidenceSpan, ...] = Field(min_length=1)
    polarity: ClaimPolarity = ClaimPolarity.POSITIVE

    @property
    def candidate_id(self) -> str:
        return contract_id("relation-candidate", self.operation_id, self.local_key)


class ExtractionCandidates(ContractModel):
    """Unapproved proposals only. Truth/schema admissibility remain external policy."""

    operation: ExtractionOperation
    run_id: NonBlank
    entities: tuple[EntityCandidate, ...] = ()
    relations: tuple[RelationCandidate, ...] = ()
    status: Literal[ApprovalStatus.PROPOSED] = ApprovalStatus.PROPOSED

    @model_validator(mode="after")
    def bounded_candidates(self) -> Self:
        limits = self.operation.profile.limits
        candidates = (*self.entities, *self.relations)
        if len(self.entities) > limits.max_entities or len(self.relations) > limits.max_relations:
            raise ValueError("candidate count exceeds extraction limits")
        if sum(len(item.evidence) for item in candidates) > limits.max_evidence_spans:
            raise ValueError("evidence count exceeds extraction limits")
        for group in (self.entities, self.relations):
            if len({item.local_key for item in group}) != len(group):
                raise ValueError("candidate local keys must be unique within their kind")
        return self

    @model_validator(mode="after")
    def grounded_references(self) -> Self:
        candidates = (*self.entities, *self.relations)
        operation_id = self.operation.operation_id
        if any(item.operation_id != operation_id for item in candidates):
            raise ValueError("candidate operation identity mismatch")
        local_keys = {item.local_key for item in self.entities}
        if any(
            item.subject_key not in local_keys or item.object_key not in local_keys
            for item in self.relations
        ):
            raise ValueError("relation endpoints must reference declared candidate local keys")
        exposed = set(self.operation.exposure.entity_ids)
        if any(
            item.reuse_entity_id is not None and item.reuse_entity_id not in exposed
            for item in self.entities
        ):
            raise ValueError("reused canonical entities must actually have been exposed")
        return self

    @model_validator(mode="after")
    def subject_evidence(self) -> Self:
        subject = self.operation.subject
        for item in (*self.entities, *self.relations):
            for evidence in item.evidence:
                if (
                    evidence.span.revision_id != subject.span.revision_id
                    or evidence.span.content != subject.span.content
                    or evidence.span.start < subject.span.start
                    or evidence.span.end > subject.span.end
                    or evidence.encoding != subject.revision.encoding
                ):
                    raise ValueError("candidate evidence must map within the extraction subject")
        return self


class ReviewDecision(ContractModel):
    """Trusted application's recorded decision, never approval from a model reply."""

    decision_id: NonBlank
    actor_id: NonBlank
    decided_at: datetime
    status: Literal[ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.RETRACTED]
    rationale: NonBlank

    @field_validator("decided_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class AssertionSupport(ContractModel):
    """One support for a canonical statement. Resolution/review/publication are external."""

    operation_id: NonBlank
    profile_fingerprint: SHA256
    subject_id: NonBlank
    predicate_id: NonBlank
    object_id: NonBlank
    polarity: ClaimPolarity = ClaimPolarity.POSITIVE
    evidence: tuple[EvidenceSpan, ...] = Field(min_length=1)
    timing: RevisionTiming
    run_ids: tuple[NonBlank, ...] = ()
    supersedes_assertion_id: NonBlank | None = None
    review: ReviewDecision | None = None

    @field_validator("evidence")
    @classmethod
    def canonical_evidence(cls, values: tuple[EvidenceSpan, ...]) -> tuple[EvidenceSpan, ...]:
        return tuple(sorted(set(values), key=lambda item: item.model_dump_json()))

    @field_validator("run_ids")
    @classmethod
    def canonical_runs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def no_backdated_review(self) -> Self:
        if self.review is not None and self.review.decided_at > self.timing.info_horizon:
            raise ValueError("reviewed support cannot be known before its decision")
        return self

    @property
    def status(self) -> ApprovalStatus:
        return ApprovalStatus.PROPOSED if self.review is None else self.review.status

    @property
    def statement_id(self) -> str:
        return contract_id(
            "statement", self.subject_id, self.predicate_id, self.object_id, self.polarity
        )

    @property
    def assertion_id(self) -> str:
        return contract_id(
            "assertion",
            self.statement_id,
            self.operation_id,
            self.profile_fingerprint,
            json_fingerprint([item.model_dump(mode="json") for item in self.evidence]),
            json_fingerprint(self.timing.valid.model_dump(mode="json")),
            self.supersedes_assertion_id or "no-supersession",
        )
