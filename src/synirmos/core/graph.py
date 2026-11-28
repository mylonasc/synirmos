"""Neutral graph values and scope specifications, not a backend or authorizer."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    ConfigDict,
    Field,
    JsonValue,
    RootModel,
    StrictInt,
    WithJsonSchema,
    field_validator,
    model_serializer,
    model_validator,
)

from .contracts import (
    SHA256,
    ArtifactSpec,
    ContractModel,
    NonBlank,
    canonical_json,
    json_fingerprint,
)
from .limits import ReadLimits
from .temporal import ReadPoint, RevisionTiming

_PropertyJSON = Annotated[str, WithJsonSchema({"type": "object", "additionalProperties": True})]


class Properties(RootModel[_PropertyJSON]):
    """Deeply immutable JSON object, serialized as an object rather than a string.

    Store detached canonical JSON internally; returning a mapping always decodes
    a fresh copy. A shallow frozen dict would allow nested mutation of evidence,
    cache keys or write payloads after validation.
    """

    model_config = ConfigDict(frozen=True)

    @field_validator("root", mode="before")
    @classmethod
    def object_json(cls, value: object) -> str:
        if not isinstance(value, dict):
            raise ValueError("properties must be a JSON object")
        return canonical_json(value)

    @model_serializer
    def to_dict(self) -> dict[str, JsonValue]:
        return json.loads(self.root)


class ApprovalStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETRACTED = "retracted"


class SnapshotPin(ContractModel):
    """Exact adapter-issued identity; opaque IDs alone do not authenticate a view."""

    database_id: NonBlank
    snapshot_id: NonBlank
    provenance_fingerprint: SHA256
    point: ReadPoint
    commit_horizon: StrictInt | None = Field(default=None, ge=0)
    ontology_release: NonBlank | None = None
    graph_profile_fingerprint: SHA256


class ScopeRequest(ContractModel):
    """None selects all *granted* IDs; an empty tuple selects none."""

    point: ReadPoint
    collection_ids: tuple[NonBlank, ...] | None = None
    source_instances: tuple[NonBlank, ...] | None = None
    approvals: tuple[ApprovalStatus, ...] = (ApprovalStatus.APPROVED,)
    limits: ReadLimits = Field(default_factory=ReadLimits)

    @field_validator("collection_ids", "source_instances", "approvals")
    @classmethod
    def canonical_selection(cls, values: tuple | None) -> tuple | None:
        return None if values is None else tuple(sorted(set(values)))


class ScopeGrant(ContractModel):
    """Trusted application's finite grant. Never accept this value from an agent.

    Runtime authenticates the principal/policy and selects the pin before making
    this value. Constructing/deserializing it is not authentication. Every scope
    dimension is explicit; no implicit global collection/source wildcard exists.
    """

    principal_id: NonBlank
    authorization_fingerprint: SHA256
    snapshot: SnapshotPin
    collection_ids: tuple[NonBlank, ...]
    source_instances: tuple[NonBlank, ...]
    approvals: tuple[ApprovalStatus, ...] = (ApprovalStatus.APPROVED,)
    limits: ReadLimits = Field(default_factory=ReadLimits)

    @field_validator("collection_ids", "source_instances", "approvals")
    @classmethod
    def canonical_selection(cls, values: tuple) -> tuple:
        return tuple(sorted(set(values)))

    def restrict(self, request: ScopeRequest) -> GraphScope:
        if request.point != self.snapshot.point:
            raise ValueError("request point must match the trusted snapshot pin")
        return GraphScope(
            principal_id=self.principal_id,
            authorization_fingerprint=self.authorization_fingerprint,
            snapshot=self.snapshot,
            collection_ids=tuple(
                value
                for value in self.collection_ids
                if request.collection_ids is None or value in request.collection_ids
            ),
            source_instances=tuple(
                value
                for value in self.source_instances
                if request.source_instances is None or value in request.source_instances
            ),
            approvals=tuple(value for value in self.approvals if value in request.approvals),
            limits=self.limits.intersect(request.limits),
        )


class Visibility(ContractModel):
    """Membership/evidence metadata for one payload version, not merged fields."""

    source_instance: NonBlank
    collection_ids: tuple[NonBlank, ...]
    approval: ApprovalStatus = ApprovalStatus.PROPOSED
    timing: RevisionTiming

    @field_validator("collection_ids")
    @classmethod
    def canonical_membership(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))


class GraphScope(ScopeGrant):
    """Effective read-only specification; adapters enforce it before candidate ranking."""

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(self.model_dump(mode="json"))

    @property
    def is_empty(self) -> bool:
        return not (self.collection_ids and self.source_instances and self.approvals)

    def includes(self, visibility: Visibility) -> bool:
        return (
            visibility.source_instance in self.source_instances
            and bool(set(visibility.collection_ids).intersection(self.collection_ids))
            and visibility.approval in self.approvals
            and self.snapshot.point.includes(visibility.timing)
        )


class EntityValue(ContractModel):
    entity_id: NonBlank
    labels: tuple[NonBlank, ...] = ()
    properties: Properties = Field(default_factory=lambda: Properties({}))
    visibility: Visibility
    evidence_ids: tuple[NonBlank, ...] = ()

    @field_validator("labels", "evidence_ids")
    @classmethod
    def canonical_sets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))


class RelationshipValue(ContractModel):
    relationship_id: NonBlank
    predicate_id: NonBlank
    source_id: NonBlank
    target_id: NonBlank
    properties: Properties = Field(default_factory=lambda: Properties({}))
    visibility: Visibility
    evidence_ids: tuple[NonBlank, ...] = ()

    @field_validator("evidence_ids")
    @classmethod
    def canonical_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))


class EntityRecord(EntityValue):
    version_id: NonBlank


class RelationshipRecord(RelationshipValue):
    version_id: NonBlank


class WriteOperation(StrEnum):
    ASSERT = "assert"
    CORRECT = "correct"
    RETRACT = "retract"


class VersionIntent(ContractModel):
    """Mapper-issued retry key, independent of incidental run IDs."""

    version_key: NonBlank
    operation: WriteOperation = WriteOperation.ASSERT
    supersedes_version_id: NonBlank | None = None

    @model_validator(mode="after")
    def correction_target(self) -> Self:
        if (self.operation == WriteOperation.CORRECT) != (self.supersedes_version_id is not None):
            raise ValueError("only corrections require a supersedes_version_id")
        return self


class EntityWrite(EntityValue):
    intent: VersionIntent


class RelationshipWrite(RelationshipValue):
    intent: VersionIntent


class IndexRequirement(ContractModel):
    entity_kind: str = Field(pattern=r"^(node|edge)$")
    property_name: NonBlank


class GraphProfile(ContractModel):
    """Pure descriptor. Composition/migrations belong to D1, never callable config."""

    profile_id: NonBlank
    version: NonBlank
    mapping: ArtifactSpec
    identity_version: NonBlank
    labels: tuple[NonBlank, ...] = ()
    predicates: tuple[NonBlank, ...] = ()
    required_properties: tuple[NonBlank, ...] = ()
    reserved_properties: tuple[NonBlank, ...] = ()
    indexes: tuple[IndexRequirement, ...] = ()
    required_capabilities: tuple[NonBlank, ...] = ()

    @field_validator(
        "labels",
        "predicates",
        "required_properties",
        "reserved_properties",
        "required_capabilities",
    )
    @classmethod
    def canonical_sets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @field_validator("indexes")
    @classmethod
    def canonical_indexes(
        cls, values: tuple[IndexRequirement, ...]
    ) -> tuple[IndexRequirement, ...]:
        return tuple(sorted(set(values), key=lambda item: (item.entity_kind, item.property_name)))

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(self.model_dump(mode="json"))


class WriteContext(ContractModel):
    """No read grant/write authorization implied. Per-record origins/times are explicit."""

    operation_id: NonBlank
    run_id: NonBlank
    profile_fingerprint: SHA256
    mapping: ArtifactSpec
    ontology_release: NonBlank | None = None


class WriteLimits(ContractModel):
    max_records: StrictInt = Field(default=256, ge=1)
    max_payload_bytes: StrictInt = Field(default=1024 * 1024, ge=1)


class GraphWriteBatch(ContractModel):
    """One bounded intent batch, not a journal/DB atomicity promise.

    The writer checks policy/profile, reserved keys and idempotence conflicts;
    native correction/retraction existence and transaction semantics stay native.
    Retractions retain an explicit last payload for audit, not a current assertion.
    """

    context: WriteContext
    entities: tuple[EntityWrite, ...] = ()
    relationships: tuple[RelationshipWrite, ...] = ()
    limits: WriteLimits = Field(default_factory=WriteLimits)

    @model_validator(mode="after")
    def bounded_unique_intents(self) -> Self:
        writes = (*self.entities, *self.relationships)
        if len(writes) > self.limits.max_records:
            raise ValueError("write batch exceeds max_records")
        keys = [write.intent.version_key for write in writes]
        if len(set(keys)) != len(keys):
            raise ValueError("write batch contains duplicate version keys")
        if len(self.model_dump_json().encode("utf-8")) > self.limits.max_payload_bytes:
            raise ValueError("write batch exceeds max_payload_bytes")
        return self
