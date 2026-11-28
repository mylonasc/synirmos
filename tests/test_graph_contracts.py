"""Pure graph/scope/budget values do not grant backend or authorization authority."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from synirmos.core.contracts import ArtifactSpec, json_fingerprint
from synirmos.core.graph import (
    ApprovalStatus,
    EntityRecord,
    EntityWrite,
    GraphProfile,
    GraphScope,
    GraphWriteBatch,
    IndexRequirement,
    Properties,
    RelationshipRecord,
    RelationshipWrite,
    ScopeGrant,
    ScopeRequest,
    SnapshotPin,
    VersionIntent,
    Visibility,
    WriteContext,
    WriteLimits,
    WriteOperation,
)
from synirmos.core.limits import (
    ReadCapabilities,
    ReadLimitError,
    ReadLimits,
    ReadUsage,
    UnsupportedReadError,
)
from synirmos.core.ports.graph import GraphWriter, WriteReceipt
from synirmos.core.temporal import ReadPoint, RevisionTiming, ValidInterval

NOW = datetime(2026, 11, 28, tzinfo=UTC)
EARLIER = NOW - timedelta(days=1)
HASH = json_fingerprint({})


def spec():
    return ArtifactSpec(
        implementation="test:mapper", implementation_version="1", config_fingerprint=HASH
    )


def pin(**changes):
    values = dict(
        database_id="db:1",
        snapshot_id="snapshot:1",
        provenance_fingerprint=HASH,
        graph_profile_fingerprint=HASH,
        point=ReadPoint(valid_time=EARLIER, info_horizon=NOW),
        commit_horizon=7,
        ontology_release="release:1",
    )
    return SnapshotPin(**(values | changes))


def grant(**changes):
    values = dict(
        principal_id="user:1",
        authorization_fingerprint=HASH,
        snapshot=pin(),
        collection_ids=("c:2", "c:1", "c:1"),
        source_instances=("s:2", "s:1"),
        approvals=(ApprovalStatus.APPROVED,),
    )
    return ScopeGrant(**(values | changes))


def scope(**changes):
    trusted = grant(**changes)
    return trusted.restrict(ScopeRequest(point=trusted.snapshot.point))


def visibility(**changes):
    values = dict(
        source_instance="s:1",
        collection_ids=("c:1",),
        approval=ApprovalStatus.APPROVED,
        timing=RevisionTiming(
            valid=ValidInterval(start=EARLIER), observed_at=NOW, info_horizon=NOW
        ),
    )
    return Visibility(**(values | changes))


def entity(**changes):
    return EntityRecord(
        **(
            dict(
                entity_id="entity:a",
                version_id="version:a",
                labels=("Person", "Person"),
                properties=Properties({"description": "Alice", "embedding": [0.1, 0.2]}),
                visibility=visibility(),
                evidence_ids=("e:1", "e:1"),
            )
            | changes
        )
    )


def write_context():
    return WriteContext(
        operation_id="op:1", run_id="run:1", profile_fingerprint=HASH, mapping=spec()
    )


def test_properties_are_deeply_detached_and_serialize_as_json_objects():
    original = {"nested": {"items": [1, "two", True, None]}, "é": "title"}
    data = Properties(original)
    original["nested"]["items"].append("changed")
    assert data.to_dict()["nested"]["items"] == [1, "two", True, None]
    data.to_dict()["nested"]["items"].append("also changed")
    assert data.to_dict()["nested"]["items"] == [1, "two", True, None]
    assert Properties.model_validate_json(data.model_dump_json()) == data
    assert data.model_dump() == data.to_dict()
    assert Properties.model_json_schema()["type"] == "object"
    with pytest.raises(ValidationError, match="frozen"):
        data.root = "{}"


@pytest.mark.parametrize("value", [[], "{}", None, {1: "bad-key"}, {"n": float("inf")}])
def test_properties_reject_non_objects_and_non_json_data(value):
    with pytest.raises((ValidationError, ValueError)):
        Properties(value)


def test_request_intersection_cannot_expand_any_granted_dimension():
    trusted = grant(limits=ReadLimits(max_results=10, max_candidates=20))
    request = ScopeRequest(
        point=trusted.snapshot.point,
        collection_ids=("c:1", "c:secret", "c:1"),
        source_instances=("s:1", "s:secret"),
        approvals=(ApprovalStatus.APPROVED, ApprovalStatus.PROPOSED),
        limits=ReadLimits(max_results=1000, max_candidates=1000),
    )
    effective = trusted.restrict(request)
    assert effective.collection_ids == ("c:1",)
    assert effective.source_instances == ("s:1",)
    assert effective.approvals == (ApprovalStatus.APPROVED,)
    assert effective.limits.max_results == 10
    assert effective.limits.max_candidates == 20
    assert effective.snapshot == trusted.snapshot
    assert effective.principal_id == trusted.principal_id
    assert request.collection_ids == ("c:1", "c:secret")


def test_default_request_selects_granted_ids_but_not_staged_statuses():
    trusted = grant(approvals=(ApprovalStatus.APPROVED, ApprovalStatus.PROPOSED))
    effective = trusted.restrict(ScopeRequest(point=trusted.snapshot.point))
    assert effective.collection_ids == ("c:1", "c:2")
    assert effective.source_instances == ("s:1", "s:2")
    assert effective.approvals == (ApprovalStatus.APPROVED,)
    assert not effective.is_empty
    assert trusted.restrict(
        ScopeRequest(point=trusted.snapshot.point, approvals=(ApprovalStatus.PROPOSED,))
    ).approvals == (ApprovalStatus.PROPOSED,)


@pytest.mark.parametrize(
    "selection",
    [
        {"collection_ids": ()},
        {"source_instances": ()},
        {"approvals": ()},
        {"collection_ids": ("c:unknown",)},
    ],
)
def test_empty_or_disjoint_selection_is_deny_all_not_a_wildcard(selection):
    trusted = grant()
    effective = trusted.restrict(ScopeRequest(point=trusted.snapshot.point, **selection))
    assert effective.is_empty
    assert not effective.includes(visibility())


def test_agent_cannot_repin_the_time_selection():
    trusted = grant()
    with pytest.raises(ValueError, match="trusted snapshot"):
        trusted.restrict(ScopeRequest(point=ReadPoint(valid_time=NOW, info_horizon=NOW)))


def test_record_visibility_uses_membership_source_status_and_both_times_not_id_prefixes():
    effective = scope()
    assert effective.includes(visibility(collection_ids=("c:secret", "c:1")))
    for changes in (
        {"collection_ids": ("c:secret",)},
        {"source_instance": "s:secret"},
        {"approval": ApprovalStatus.PROPOSED},
        {
            "timing": RevisionTiming(
                valid=ValidInterval(start=NOW), observed_at=NOW, info_horizon=NOW
            )
        },
        {
            "timing": RevisionTiming(
                valid=ValidInterval(start=EARLIER),
                observed_at=NOW + timedelta(seconds=1),
                info_horizon=NOW + timedelta(seconds=1),
            )
        },
    ):
        assert not effective.includes(visibility(**changes))
    assert Visibility(
        source_instance="s:1", collection_ids=("c:2", "c:1", "c:1"), timing=visibility().timing
    ).collection_ids == ("c:1", "c:2")


def test_scope_fingerprint_binds_access_policy_pin_release_time_and_limits():
    baseline = scope()
    assert GraphScope.model_validate_json(baseline.model_dump_json()) == baseline
    for changes in (
        {"principal_id": "user:2"},
        {"authorization_fingerprint": json_fingerprint("policy:2")},
        {"snapshot": pin(snapshot_id="snapshot:2")},
        {"snapshot": pin(ontology_release="release:2")},
        {"snapshot": pin(commit_horizon=8)},
        {"snapshot": pin(database_id="db:2")},
        {"collection_ids": ("c:2",)},
        {"source_instances": ("s:2",)},
        {"limits": ReadLimits(max_results=1)},
    ):
        assert scope(**changes).fingerprint != baseline.fingerprint
    with pytest.raises(ValidationError):
        baseline.snapshot.snapshot_id = "mutated"


def test_record_payloads_are_neutral_immutable_and_allow_full_predicate_ids():
    node = entity()
    edge = RelationshipRecord(
        relationship_id="r:1",
        predicate_id="https://schema.example/memberOf",
        source_id=node.entity_id,
        target_id="entity:b",
        version_id="version:r",
        visibility=visibility(),
        evidence_ids=("e:2", "e:1", "e:2"),
    )
    assert node.labels == ("Person",)
    assert node.evidence_ids == ("e:1",)
    assert edge.evidence_ids == ("e:1", "e:2")
    assert edge.properties.to_dict() == {}
    for record in (node, edge):
        assert type(record).model_validate_json(record.model_dump_json()) == record
        with pytest.raises(ValidationError):
            record.version_id = "changed"


def test_profile_descriptor_canonicalizes_index_sets_and_fingerprints_every_policy_input():
    indexes = (
        IndexRequirement(entity_kind="edge", property_name="approved"),
        IndexRequirement(entity_kind="node", property_name="name"),
    )
    values = dict(
        profile_id="profile:document",
        version="1",
        mapping=spec(),
        identity_version="1",
        labels=("Person", "Document", "Person"),
        predicates=("https://example/mentions",),
        indexes=(*indexes, indexes[0]),
        required_properties=("name", "name"),
        reserved_properties=("prov_run",),
        required_capabilities=("transaction", "transaction"),
    )
    profile = GraphProfile(**values)
    reordered = GraphProfile(
        **(values | {"labels": ("Document", "Person"), "indexes": indexes[::-1]})
    )
    assert profile.fingerprint == reordered.fingerprint
    assert profile.required_properties == ("name",)
    assert profile.required_capabilities == ("transaction",)
    assert len(profile.indexes) == 2
    assert GraphProfile.model_validate_json(profile.model_dump_json()) == profile
    assert GraphProfile(**(values | {"version": "2"})).fingerprint != profile.fingerprint
    with pytest.raises(ValidationError):
        IndexRequirement(entity_kind="other", property_name="name")


@pytest.mark.parametrize(
    "operation,target,valid",
    [
        (WriteOperation.ASSERT, None, True),
        (WriteOperation.CORRECT, "version:old", True),
        (WriteOperation.RETRACT, None, True),
        (WriteOperation.CORRECT, None, False),
        (WriteOperation.ASSERT, "version:old", False),
        (WriteOperation.RETRACT, "version:old", False),
    ],
)
def test_version_intent_corrections_have_explicit_targets(operation, target, valid):
    values = dict(version_key="intent:1", operation=operation, supersedes_version_id=target)
    if valid:
        assert VersionIntent(**values).operation == operation
    else:
        with pytest.raises(ValidationError, match="corrections require"):
            VersionIntent(**values)


def test_write_batches_bound_count_bytes_and_keys_without_run_dependent_intent_identity():
    node = EntityWrite(
        **(
            entity().model_dump(exclude={"version_id"})
            | {"intent": VersionIntent(version_key="n:1")}
        )
    )
    edge = RelationshipWrite(
        relationship_id="r:1",
        predicate_id="memberOf",
        source_id="entity:a",
        target_id="entity:b",
        visibility=visibility(),
        intent=VersionIntent(version_key="r:1"),
    )
    batch = GraphWriteBatch(context=write_context(), entities=(node,), relationships=(edge,))
    assert GraphWriteBatch.model_validate_json(batch.model_dump_json()) == batch
    assert node.intent.version_key == "n:1"
    for values, message in (
        ({"limits": WriteLimits(max_records=1)}, "max_records"),
        ({"limits": WriteLimits(max_payload_bytes=1)}, "max_payload_bytes"),
        ({"entities": (node, node)}, "duplicate version keys"),
    ):
        with pytest.raises(ValidationError, match=message):
            GraphWriteBatch(**(batch.model_dump() | values))
    replay = GraphWriteBatch(
        **(
            batch.model_dump()
            | {"context": WriteContext(**(write_context().model_dump() | {"run_id": "run:retry"}))}
        )
    )
    assert replay.entities == batch.entities
    assert replay.context.operation_id == batch.context.operation_id
    assert GraphWriteBatch(context=write_context()).entities == ()


def test_graph_writer_protocol_exposes_only_borrowed_write_capability():
    class Writer:
        def write(self, batch):
            return WriteReceipt(operation_id=batch.context.operation_id, version_keys=())

    writer = Writer()
    assert isinstance(writer, GraphWriter)
    receipt = writer.write(GraphWriteBatch(context=write_context()))
    assert WriteReceipt.model_validate_json(receipt.model_dump_json()) == receipt


def test_limits_intersection_is_monotonic_and_preserves_explicit_zero():
    a = ReadLimits(max_results=8, max_candidates=10, deadline=NOW)
    b = ReadLimits(max_results=0, max_read_bytes=20, deadline=NOW + timedelta(seconds=1))
    both = a.intersect(b)
    assert both == b.intersect(a)
    assert both.max_results == 0 and both.max_candidates == 10 and both.max_read_bytes == 20
    assert both.deadline == NOW
    assert ReadLimits().intersect(ReadLimits()).max_candidates is None
    for values in (
        {"max_candidates": -1},
        {"max_results": True},
        {"deadline": datetime(2026, 1, 1)},
    ):
        with pytest.raises(ValidationError):
            ReadLimits(**values)


@pytest.mark.parametrize(
    "limit,capability,value",
    [
        ("max_candidates", "candidate_limit", 0),
        ("max_read_bytes", "read_byte_limit", 100),
        ("max_memory_bytes", "memory_limit", 100),
        ("deadline", "deadline", NOW),
    ],
)
def test_physical_guarantees_require_explicit_support(limit, capability, value):
    limits = ReadLimits(**{limit: value})
    with pytest.raises(UnsupportedReadError, match=limit):
        ReadCapabilities().require(limits)
    ReadCapabilities(**{capability: True}).require(limits)
    ReadCapabilities().require(ReadLimits(max_results=0, max_output_bytes=0))


def test_usage_is_aggregated_and_unknown_physical_work_remains_unknown():
    a = ReadUsage(results=1, output_bytes=10, candidates=2, read_bytes=20)
    b = ReadUsage(results=2, output_bytes=20, candidates=3, read_bytes=30)
    total = a.add(b)
    assert total == ReadUsage(results=3, output_bytes=30, candidates=5, read_bytes=50)
    total.check(ReadLimits(max_results=3, max_output_bytes=30, max_candidates=5, max_read_bytes=50))
    unknown = a.add(ReadUsage())
    assert unknown.candidates is unknown.read_bytes is None
    for limits in (ReadLimits(max_candidates=3), ReadLimits(max_read_bytes=3)):
        with pytest.raises(UnsupportedReadError, match="unknown"):
            unknown.check(limits)
    for limits in (
        ReadLimits(max_results=2),
        ReadLimits(max_output_bytes=20),
        ReadLimits(max_candidates=4),
        ReadLimits(max_read_bytes=40),
    ):
        with pytest.raises(ReadLimitError, match="exceeds") as error:
            total.check(limits)
        assert error.value.usage == total
    assert ReadLimitError("unspecified usage").usage is None
    assert ReadUsage.model_validate_json(total.model_dump_json()) == total
