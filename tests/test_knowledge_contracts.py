"""D0 scope/exposure/extraction conformance with pure values and explicit test doubles."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from synirmos.core.context import (
    ContextExposure,
    ContextRequest,
    ContextResult,
    EvidenceRecord,
    ExposureSet,
    KnowledgeQuery,
    ResultStatus,
)
from synirmos.core.contracts import ArtifactSpec, SourceKey, json_fingerprint
from synirmos.core.documents import (
    ContentMismatchError,
    ContentReference,
    DocumentRevision,
    SourceSpan,
    TextDocument,
)
from synirmos.core.extraction import (
    AssertionSupport,
    ClaimPolarity,
    EntityCandidate,
    EvidenceSpan,
    ExtractionCandidates,
    ExtractionLimits,
    ExtractionOperation,
    ExtractionProfile,
    ExtractionSubject,
    RelationCandidate,
    ReviewDecision,
)
from synirmos.core.graph import (
    ApprovalStatus,
    EntityRecord,
    Properties,
    RelationshipRecord,
    ScopeGrant,
    ScopeRequest,
    SnapshotPin,
    Visibility,
)
from synirmos.core.limits import ReadCapabilities, ReadLimitError, ReadLimits, ReadUsage
from synirmos.core.models import CoverageGap, CoverageStatus
from synirmos.core.ports.extraction import Extractor
from synirmos.core.ports.knowledge import (
    ContextProvider,
    KnowledgeReader,
    ReadSession,
    ReadSessionClosedError,
    ReadSessionFactory,
)
from synirmos.core.temporal import ReadPoint, RevisionTiming, ValidInterval

NOW = datetime(2026, 11, 28, tzinfo=UTC)
BODY = b"Ada works at Acme."
HASH = json_fingerprint({})


def changed(value, **updates):
    return type(value).model_validate(value.model_dump() | updates)


def spec(name="fake"):
    return ArtifactSpec(
        implementation=f"test:{name}", implementation_version="1", config_fingerprint=HASH
    )


@pytest.fixture
def world():
    timing = RevisionTiming(valid=ValidInterval(start=NOW), observed_at=NOW, info_horizon=NOW)
    visible = Visibility(
        source_instance="source:docs",
        collection_ids=("collection:one",),
        approval=ApprovalStatus.APPROVED,
        timing=timing,
    )
    revision = DocumentRevision(
        document=TextDocument(key=SourceKey(source_instance="source:docs", native_key="one")),
        content=ContentReference.from_bytes(BODY),
        timing=timing,
    )
    span = SourceSpan(
        revision_id=revision.revision_id, content=revision.content, start=0, end=len(BODY)
    )
    subject = ExtractionSubject(
        revision=revision, span=span, text=BODY.decode(), visibility=visible
    )
    snapshot = SnapshotPin(
        database_id="memory:test",
        snapshot_id="snapshot:one",
        provenance_fingerprint=HASH,
        graph_profile_fingerprint=HASH,
        point=ReadPoint(valid_time=NOW, info_horizon=NOW),
        ontology_release="release:one",
    )
    grant = ScopeGrant(
        principal_id="user:one",
        authorization_fingerprint=HASH,
        snapshot=snapshot,
        collection_ids=("collection:one",),
        source_instances=("source:docs",),
    )
    scope = grant.restrict(ScopeRequest(point=snapshot.point))
    request = ContextRequest(subject_id=subject.subject_id, scope=scope)
    ada, acme = (
        EntityRecord(
            entity_id=f"entity:{name}",
            version_id=f"version:{name}",
            visibility=visible,
            labels=(kind,),
            properties=Properties({"name": name, "description": kind}),
            evidence_ids=("e:one",),
        )
        for name, kind in (
            ("ada", "https://example/Person"),
            ("acme", "https://example/Organization"),
        )
    )
    edge = RelationshipRecord(
        relationship_id="relationship:one",
        version_id="version:edge",
        source_id=ada.entity_id,
        target_id=acme.entity_id,
        predicate_id="https://example/worksFor",
        visibility=visible,
        evidence_ids=("e:one",),
    )
    evidence = EvidenceRecord(
        evidence_id="e:one",
        version_id="version:evidence",
        visibility=visible,
        properties=Properties({"quote": BODY.decode()}),
        span=span,
    )
    profile = ExtractionProfile(
        task=spec("task"),
        model=spec("model"),
        prompt=spec("prompt"),
        tools=spec("tools"),
        schema_fingerprint=HASH,
        ontology_release=snapshot.ontology_release,
    )
    return SimpleNamespace(
        timing=timing,
        visible=visible,
        revision=revision,
        span=span,
        subject=subject,
        grant=grant,
        scope=scope,
        request=request,
        ada=ada,
        acme=acme,
        edge=edge,
        evidence=evidence,
        profile=profile,
    )


def result(world, **updates):
    values = dict(
        request=world.request,
        provider=spec("provider"),
        entities=(world.ada, world.acme),
        relationships=(world.edge,),
        evidence=(world.evidence,),
        candidates=8,
        read_bytes=200,
    )
    return ContextResult.from_records(**(values | updates))


def operation(world, **updates):
    exposure = ExposureSet(scope=world.scope, contexts=(result(world).exposure(),))
    return ExtractionOperation(
        **(dict(subject=world.subject, profile=world.profile, exposure=exposure) | updates)
    )


def proposals(world, **updates):
    op = operation(world)
    evidence = (EvidenceSpan(span=world.span, quote=BODY.decode()),)
    ada = EntityCandidate(
        operation_id=op.operation_id,
        local_key="ada",
        name="Ada",
        class_id="https://example/Person",
        evidence=evidence,
        reuse_entity_id=world.ada.entity_id,
    )
    acme = EntityCandidate(
        operation_id=op.operation_id,
        local_key="acme",
        name="Acme",
        class_id="https://example/Organization",
        evidence=evidence,
    )
    edge = RelationCandidate(
        operation_id=op.operation_id,
        local_key="works",
        subject_key="ada",
        object_key="acme",
        predicate_id="https://example/worksFor",
        evidence=evidence,
    )
    return ExtractionCandidates(
        **(dict(operation=op, run_id="run:one", entities=(ada, acme), relations=(edge,)) | updates)
    )


def test_results_are_exact_complete_records_with_detached_properties_and_json_roundtrip(world):
    value = result(world)
    assert value.usage.results == 4
    assert value.usage.output_bytes == value.payload_bytes > 0
    assert value.usage.candidates == 8
    assert ContextResult.model_validate_json(value.model_dump_json()) == value
    receipt = value.exposure()
    assert receipt.entity_versions[0].record_id == world.ada.entity_id
    assert receipt.relationship_versions[0].record_id == world.edge.relationship_id
    assert receipt.evidence_versions[0].record_id == world.evidence.evidence_id
    assert ContextExposure.model_validate_json(receipt.model_dump_json()) == receipt
    assert ExposureSet(scope=world.scope, contexts=(receipt,)).entity_ids == (
        world.acme.entity_id,
        world.ada.entity_id,
    )


@pytest.mark.parametrize(
    "change,message",
    [
        ({"entities": ()}, "endpoints"),
        ({"evidence": ()}, "evidence must be visible"),
    ],
)
def test_context_requires_visible_endpoint_and_evidence_dependencies(world, change, message):
    with pytest.raises(ValidationError, match=message):
        result(world, **change)


@pytest.mark.parametrize("kind", ["entities", "relationships", "evidence"])
def test_duplicate_or_invisible_records_reject(world, kind):
    baseline = result(world)
    records = getattr(baseline, kind)
    with pytest.raises(ValidationError, match="duplicate"):
        result(world, **{kind: (*records, records[0])})
    hidden = changed(records[0], visibility=changed(world.visible, source_instance="secret"))
    with pytest.raises(ValidationError, match="outside the effective scope"):
        result(world, **{kind: (hidden, *records[1:])})


@pytest.mark.parametrize(
    "status", [ResultStatus.UNSUPPORTED, ResultStatus.DENIED, ResultStatus.FAILED]
)
def test_negative_outcomes_are_explicit_not_successful_empty_results(world, status):
    gap = CoverageGap(
        code="query-unavailable",
        status=CoverageStatus.UNAVAILABLE,
        message="not available",
        source="test",
    )
    empty = dict(entities=(), relationships=(), evidence=(), status=status)
    with pytest.raises(ValidationError, match="require gaps"):
        result(world, **empty)
    value = result(world, **empty, gaps=(gap,))
    assert value.status == status and value.usage.results == value.payload_bytes == 0
    with pytest.raises(ValidationError, match="no records/cursor"):
        result(world, status=status, gaps=(gap,))
    with pytest.raises(ValidationError, match="no records/cursor"):
        result(world, **empty, gaps=(gap,), continuation="next")


def test_truncation_is_distinct_from_empty_and_complete_cannot_hide_a_cursor(world):
    with pytest.raises(ValidationError, match="explicit gap"):
        result(world, status=ResultStatus.TRUNCATED)
    with pytest.raises(ValidationError, match="complete results"):
        result(world, continuation="next")
    truncated = result(world, status=ResultStatus.TRUNCATED, continuation="next")
    assert truncated.continuation == "next"
    gap = CoverageGap(
        code="query-cap", status=CoverageStatus.PARTIAL, message="limit reached", source="test"
    )
    assert (
        result(world, status=ResultStatus.TRUNCATED, gaps=(gap,)).status == ResultStatus.TRUNCATED
    )
    assert (
        ContextResult.from_records(request=world.request, provider=spec()).status
        == ResultStatus.COMPLETE
    )


def test_output_count_bytes_and_usage_cannot_be_forged_or_exceed_caps(world):
    baseline = result(world)
    with pytest.raises(ValidationError, match="exact delivered"):
        changed(baseline, usage=ReadUsage())
    for limits in (ReadLimits(max_results=1), ReadLimits(max_output_bytes=1)):
        request = changed(world.request, scope=changed(world.scope, limits=limits))
        with pytest.raises(ReadLimitError) as error:
            result(world, request=request)
        assert error.value.usage.results == 4
    zero = changed(
        world.request,
        scope=changed(world.scope, limits=ReadLimits(max_results=0, max_output_bytes=0)),
    )
    assert ContextResult.from_records(request=zero, provider=spec()).payload_bytes == 0


def test_actual_values_queries_policy_and_order_change_fingerprints_but_telemetry_does_not(world):
    base = result(world)
    renamed = changed(world.ada, properties=Properties({"name": "ada", "description": "changed"}))
    assert result(world, entities=(renamed, world.acme)).fingerprint != base.fingerprint
    assert result(world, entities=(world.acme, world.ada)).fingerprint != base.fingerprint
    query_result = result(
        world, request=changed(world.request, query=KnowledgeQuery(text="new query"))
    )
    assert query_result.fingerprint != base.fingerprint
    assert result(world, provider=spec("new-provider")).fingerprint != base.fingerprint
    cheaper = result(world, candidates=1, read_bytes=1)
    assert cheaper.fingerprint == base.fingerprint
    a = ExposureSet(scope=world.scope, contexts=(base.exposure(),))
    b = ExposureSet(scope=world.scope, contexts=(cheaper.exposure(),))
    assert a.fingerprint == b.fingerprint and a.usage != b.usage
    assert KnowledgeQuery(entity_ids=("b", "a", "a")).entity_ids == ("a", "b")
    assert KnowledgeQuery(predicate_ids=()).predicate_ids == ()
    assert changed(world.request, continuation="cursor").fingerprint != world.request.fingerprint


def test_exposure_sets_reject_mixed_scope_and_conflicting_payload_or_version(world):
    baseline = result(world).exposure()
    with pytest.raises(ValidationError, match="different scopes"):
        ExposureSet(scope=changed(world.scope, principal_id="other"), contexts=(baseline,))
    for ada in (
        changed(world.ada, version_id="another-version"),
        changed(world.ada, properties=Properties({"description": "changed in same version"})),
    ):
        conflict = result(world, entities=(ada, world.acme)).exposure()
        with pytest.raises(ValidationError, match="conflicting exposed"):
            ExposureSet(scope=world.scope, contexts=(baseline, conflict))
    with pytest.raises(ValidationError, match="exposure count"):
        changed(baseline, usage=ReadUsage())
    with pytest.raises(ValidationError, match="duplicate record"):
        changed(baseline, entity_versions=(baseline.entity_versions[0],) * 2, usage=baseline.usage)


def test_composed_tool_results_share_total_budget_and_preserve_call_order(world):
    limited = changed(world.scope, limits=ReadLimits(max_results=4))
    one = result(world, request=changed(world.request, scope=limited)).exposure()
    with pytest.raises(ReadLimitError, match="results exceeds"):
        ExposureSet(scope=limited, contexts=(one, one))
    baseline = result(world).exposure()
    other = result(
        world, request=changed(world.request, query=KnowledgeQuery(text="two"))
    ).exposure()
    a = ExposureSet(scope=world.scope, contexts=(baseline, other))
    b = ExposureSet(scope=world.scope, contexts=(other, baseline))
    assert a.fingerprint != b.fingerprint
    assert a.usage.results == 8 and a.usage.candidates == 16
    assert ExposureSet.model_validate_json(a.model_dump_json()) == a


def test_borrowed_reader_lifetime_is_explicit_and_reused_on_exception_exit(world):
    class Session:
        scope = world.scope

        def __init__(self):
            self.closed = False
            self.calls = 0
            self.reader = Reader(self)

        def __enter__(self):
            if self.closed:
                raise ReadSessionClosedError("closed")
            return self

        def __exit__(self, *_):
            self.close()

        def close(self):
            self.closed = True

    class Reader:
        capabilities = ReadCapabilities()

        def __init__(self, owner):
            self.owner = owner
            self.scope = owner.scope

        def read(self, request):
            if self.owner.closed:
                raise ReadSessionClosedError("closed")
            if request.scope != self.scope:
                raise ValueError("scope mismatch")
            self.capabilities.require(request.scope.limits)
            self.owner.calls += 1
            return ContextResult.from_records(request=request, provider=spec())

    class Factory:
        def open(self, scope):
            assert scope == world.scope
            return Session()

    class Provider:
        def select(self, request, *, reader=None):
            return (
                ContextResult.from_records(request=request, provider=spec())
                if reader is None
                else reader.read(request)
            )

    factory, provider = Factory(), Provider()
    assert isinstance(factory, ReadSessionFactory) and isinstance(provider, ContextProvider)
    assert provider.select(world.request).entities == ()
    owner = factory.open(world.scope)
    assert isinstance(owner, ReadSession) and isinstance(owner.reader, KnowledgeReader)
    borrowed = owner.reader
    with pytest.raises(RuntimeError, match="abort"):
        with owner as session:
            provider.select(world.request, reader=session.reader)
            provider.select(world.request, reader=session.reader)
            with pytest.raises(ValueError, match="scope mismatch"):
                borrowed.read(
                    changed(world.request, scope=changed(world.scope, principal_id="other"))
                )
            raise RuntimeError("abort")
    assert owner.closed and owner.calls == 2
    owner.close()
    with pytest.raises(ReadSessionClosedError):
        borrowed.read(world.request)
    with pytest.raises(ReadSessionClosedError):
        with owner:
            pass


def test_subject_and_evidence_verify_original_bytes_without_claiming_trust_from_ids(world):
    world.subject.verify(BODY)
    quote = EvidenceSpan(span=world.span, quote=BODY.decode())
    quote.verify(BODY)
    with pytest.raises(ContentMismatchError):
        changed(world.subject, text="invented").verify(BODY)
    with pytest.raises(ContentMismatchError):
        changed(quote, quote="invented").verify(BODY)
    with pytest.raises(ContentMismatchError):
        quote.verify(BODY[:-1])
    for updates in (
        {"span": changed(world.span, revision_id="different")},
        {"span": changed(world.span, content=ContentReference.from_bytes(BODY + b"extra"))},
        {"visibility": changed(world.visible, source_instance="different")},
        {
            "visibility": changed(
                world.visible,
                timing=changed(
                    world.timing,
                    observed_at=NOW + timedelta(seconds=1),
                    info_horizon=NOW + timedelta(seconds=1),
                ),
            )
        },
    ):
        with pytest.raises(ValidationError, match="subject"):
            changed(world.subject, **updates)
    with pytest.raises(ValidationError, match="empty span"):
        EvidenceSpan(span=changed(world.span, end=0), quote="not empty")


def test_operation_identity_binds_intent_and_exposure_not_run_or_work_counters(world):
    op = operation(world)
    cheaper = ExposureSet(
        scope=world.scope, contexts=(result(world, candidates=0, read_bytes=0).exposure(),)
    )
    assert operation(world, exposure=cheaper).operation_id == op.operation_id
    assert operation(world, analysis_version="intentional-rerun").operation_id != op.operation_id
    for field in ("task", "model", "prompt", "tools", "schema_fingerprint", "limits"):
        value = (
            json_fingerprint("new schema")
            if field == "schema_fingerprint"
            else ExtractionLimits(max_model_calls=1)
            if field == "limits"
            else spec("changed")
        )
        updated = operation(world, profile=changed(world.profile, **{field: value}))
        assert updated.operation_id != op.operation_id
    updated_subject = operation(
        world, subject=changed(world.subject, text="different visible text")
    )
    assert updated_subject.operation_id != op.operation_id
    with pytest.raises(ValidationError, match="outside the effective scope"):
        operation(world, exposure=ExposureSet(scope=changed(world.scope, source_instances=())))
    with pytest.raises(ValidationError, match="pinned ontology release"):
        operation(world, profile=changed(world.profile, ontology_release="release:other"))
    assert (
        ExtractionOperation.model_validate_json(op.model_dump_json()).operation_id
        == op.operation_id
    )


def test_candidates_are_local_proposals_with_full_domain_ids_and_retry_stable_mentions(world):
    value = proposals(world)
    retry = changed(value, run_id="run:retry")
    assert value.operation.operation_id == retry.operation.operation_id
    assert value.entities[0].candidate_id == retry.entities[0].candidate_id
    assert value.entities[0].mention_ids == retry.entities[0].mention_ids
    assert value.relations[0].candidate_id.startswith("relation-candidate:")
    assert value.relations[0].predicate_id == "https://example/worksFor"
    assert value.entities[1].reuse_entity_id is None
    assert value.status == ApprovalStatus.PROPOSED
    assert ExtractionCandidates.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        changed(value, status=ApprovalStatus.APPROVED)


def test_reuse_is_grounded_in_actual_delivered_ids_including_later_direct_lookup(world):
    value = proposals(world)
    hidden = changed(value.entities[0], reuse_entity_id="entity:hidden")
    with pytest.raises(ValidationError, match="actually have been exposed"):
        changed(value, entities=(hidden, value.entities[1]))
    direct_entity = changed(world.ada, entity_id="entity:hidden", evidence_ids=())
    direct = result(
        world,
        entities=(direct_entity,),
        relationships=(),
        evidence=(),
        request=changed(world.request, query=KnowledgeQuery(entity_ids=("entity:hidden",))),
    ).exposure()
    exposure = ExposureSet(scope=world.scope, contexts=(*value.operation.exposure.contexts, direct))
    op = changed(value.operation, exposure=exposure)
    entities = tuple(
        changed(item, operation_id=op.operation_id) for item in (hidden, value.entities[1])
    )
    relations = tuple(changed(item, operation_id=op.operation_id) for item in value.relations)
    grounded = changed(value, operation=op, entities=entities, relations=relations)
    assert grounded.entities[0].reuse_entity_id == "entity:hidden"


def test_candidate_structure_requires_operation_keys_endpoints_and_subject_evidence(world):
    value = proposals(world)
    for updates, message in (
        ({"entities": (value.entities[0], value.entities[0])}, "unique"),
        ({"relations": (value.relations[0], value.relations[0])}, "unique"),
        (
            {"entities": (changed(value.entities[0], operation_id="wrong"), value.entities[1])},
            "identity mismatch",
        ),
        ({"relations": (changed(value.relations[0], object_key="undeclared"),)}, "endpoints"),
        (
            {
                "entities": (
                    changed(
                        value.entities[0],
                        evidence=(changed(value.entities[0].evidence[0], encoding="utf-16"),),
                    ),
                    value.entities[1],
                )
            },
            "within the extraction subject",
        ),
    ):
        with pytest.raises(ValidationError, match=message):
            changed(value, **updates)
    for limit in ("max_entities", "max_relations", "max_evidence_spans"):
        op = changed(
            value.operation, profile=changed(world.profile, limits=ExtractionLimits(**{limit: 0}))
        )
        entities = tuple(changed(item, operation_id=op.operation_id) for item in value.entities)
        relations = tuple(changed(item, operation_id=op.operation_id) for item in value.relations)
        with pytest.raises(ValidationError, match="exceeds extraction limits"):
            changed(value, operation=op, entities=entities, relations=relations)
    with pytest.raises(ValidationError):
        changed(value.relations[0], evidence=())


def test_assertion_supports_preserve_contradictions_lineage_and_review_identity(world):
    values = dict(
        operation_id=operation(world).operation_id,
        profile_fingerprint=world.profile.fingerprint,
        subject_id=world.ada.entity_id,
        predicate_id=world.edge.predicate_id,
        object_id=world.acme.entity_id,
        evidence=(EvidenceSpan(span=world.span, quote=BODY.decode()),),
        timing=world.timing,
        run_ids=("run:one",),
    )
    support = AssertionSupport(**values)
    retry = changed(support, run_ids=("run:retry", "run:one", "run:one"))
    assert support.status == ApprovalStatus.PROPOSED
    assert support.assertion_id == retry.assertion_id
    assert retry.run_ids == ("run:one", "run:retry")
    negative = changed(support, polarity=ClaimPolarity.NEGATIVE)
    assert negative.statement_id != support.statement_id
    assert negative.assertion_id != support.assertion_id
    another = changed(support, operation_id="another-operation")
    assert another.statement_id == support.statement_id
    assert another.assertion_id != support.assertion_id
    reviewed = changed(
        support,
        review=ReviewDecision(
            decision_id="review:1",
            actor_id="reviewer:1",
            decided_at=NOW,
            status=ApprovalStatus.APPROVED,
            rationale="reviewed source",
        ),
    )
    assert reviewed.status == ApprovalStatus.APPROVED
    assert reviewed.assertion_id == support.assertion_id
    assert AssertionSupport.model_validate_json(reviewed.model_dump_json()) == reviewed
    with pytest.raises(ValidationError, match="known before its decision"):
        changed(reviewed, review=changed(reviewed.review, decided_at=NOW + timedelta(seconds=1)))
    with pytest.raises(ValidationError):
        changed(reviewed.review, decided_at=datetime(2026, 11, 28))
    shorter = EvidenceSpan(span=changed(world.span, end=3), quote="Ada")
    distinct = changed(support, evidence=(shorter,))
    assert distinct.statement_id == support.statement_id
    assert distinct.assertion_id != support.assertion_id
    deduplicated = changed(support, evidence=(*support.evidence, *support.evidence))
    assert deduplicated.assertion_id == support.assertion_id


def test_extractor_port_does_not_own_canonical_writes_or_approval(world):
    class FakeExtractor:
        def propose(self, operation, *, run_id):
            return ExtractionCandidates(operation=operation, run_id=run_id)

    extractor = FakeExtractor()
    assert isinstance(extractor, Extractor)
    assert extractor.propose(operation(world), run_id="test").entities == ()
