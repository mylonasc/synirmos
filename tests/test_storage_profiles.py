"""D1 profile composition/validation/migration: pure descriptors, no storage handles."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synirmos.core.contracts import ArtifactSpec, json_fingerprint
from synirmos.core.graph import (
    EntityRecord,
    GraphProfile,
    IndexRequirement,
    Properties,
    RelationshipRecord,
    Visibility,
)
from synirmos.core.temporal import RevisionTiming, ValidInterval
from synirmos.storage.profiles import (
    RESERVED_PROVENANCE_KEYS,
    MigrationError,
    ProfileConflictError,
    ProfileViolationError,
    compose_profiles,
    missing_capabilities,
    plan_migration,
    require_capabilities,
    validate_record,
)

NOW = datetime(2026, 11, 28, tzinfo=UTC)
HASH = json_fingerprint({})

ROOT = Path(__file__).resolve().parents[1]


def mapping(name="mapper"):
    return ArtifactSpec(
        implementation=f"test:{name}", implementation_version="1", config_fingerprint=HASH
    )


def profile(name, **updates):
    values = dict(
        profile_id=f"profile:{name}",
        version="1",
        mapping=mapping(name),
        identity_version="contracts-v1",
        labels=("Document",),
        predicates=("https://example/mentions",),
    )
    return GraphProfile(**(values | updates))


def visibility():
    return Visibility(
        source_instance="source:docs",
        collection_ids=("collection:one",),
        timing=RevisionTiming(valid=ValidInterval(start=NOW), observed_at=NOW, info_horizon=NOW),
    )


def entity(**updates):
    values = dict(
        entity_id="entity:one",
        version_id="version:one",
        labels=("Document",),
        properties=Properties({"title": "Notes"}),
        visibility=visibility(),
    )
    return EntityRecord(**(values | updates))


def relationship(**updates):
    values = dict(
        relationship_id="relationship:one",
        version_id="version:one",
        predicate_id="https://example/mentions",
        source_id="entity:one",
        target_id="entity:two",
        properties=Properties({}),
        visibility=visibility(),
    )
    return RelationshipRecord(**(values | updates))


def composed(*profiles, **updates):
    values = dict(
        profile_id="profile:composed",
        version="1",
        mapping=mapping("composer"),
        identity_version="contracts-v1",
    )
    return compose_profiles(profiles, **(values | updates))


def test_composition_merges_deterministically_regardless_of_input_order():
    left = profile("doc", labels=("Document", "Section"), required_properties=("title",))
    right = profile(
        "lexical",
        labels=("Chunk",),
        predicates=("https://example/mentions", "https://example/partOf"),
        indexes=(IndexRequirement(entity_kind="node", property_name="title"),),
        required_capabilities=("transaction",),
    )
    first = composed(left, right)
    second = composed(right, left)
    assert first.fingerprint == second.fingerprint
    assert first.labels == ("Chunk", "Document", "Section")
    assert first.predicates == (
        "https://example/mentions",
        "https://example/partOf",
    )
    assert first.required_properties == ("title",)
    assert first.required_capabilities == ("transaction",)
    assert GraphProfile.model_validate_json(first.model_dump_json()) == first


def test_composition_rejects_conflicting_definitions():
    with pytest.raises(ProfileConflictError, match="at least one profile"):
        composed()
    with pytest.raises(ProfileConflictError, match="declares versions"):
        composed(profile("doc", version="1"), profile("doc", version="2"))
    changed = profile("doc", labels=("Document", "Changed"))
    with pytest.raises(ProfileConflictError, match="conflicting definitions"):
        composed(profile("doc"), changed)
    with pytest.raises(ProfileConflictError, match="identity"):
        composed(profile("doc"), profile("other", identity_version="contracts-v2"))
    with pytest.raises(ProfileConflictError, match="identity"):
        composed(
            profile("doc"),
            profile_id="profile:composed",
            version="1",
            mapping=mapping("composer"),
            identity_version="contracts-v2",
        )


def test_identical_duplicates_compose_cleanly():
    assert composed(profile("doc"), profile("doc")).labels == ("Document",)


def test_capability_requirements_fail_closed():
    full = profile("doc", required_capabilities=("transaction", "temporal"))
    assert missing_capabilities(full, ("transaction", "temporal", "index")) == ()
    assert missing_capabilities(full, ("transaction",)) == ("temporal",)
    require_capabilities(full, ("transaction", "temporal"))
    with pytest.raises(ProfileViolationError, match="temporal"):
        require_capabilities(full, ("transaction",))


def test_records_must_use_declared_vocabulary_and_required_properties():
    full = composed(
        profile("doc", required_properties=("title",), reserved_properties=("internal",))
    )
    validate_record(entity(), full)
    validate_record(relationship(properties=Properties({"title": "edge"})), full)
    with pytest.raises(ProfileViolationError, match="undeclared labels"):
        validate_record(entity(labels=("Secret",)), full)
    with pytest.raises(ProfileViolationError, match="undeclared predicate"):
        validate_record(relationship(predicate_id="https://example/unknown"), full)
    with pytest.raises(ProfileViolationError, match="required properties"):
        validate_record(entity(properties=Properties({})), full)


def test_reserved_keys_include_driver_provenance_and_profile_lists():
    full = composed(profile("doc", reserved_properties=("internal",)))
    for key in ("prov_run_id", "type", "internal"):
        with pytest.raises(ProfileViolationError, match="reserved"):
            validate_record(entity(properties=Properties({"title": "t", key: "x"})), full)
    assert "prov_run_id" in RESERVED_PROVENANCE_KEYS
    assert "type" in RESERVED_PROVENANCE_KEYS


def test_empty_vocabulary_authorizes_nothing():
    empty = GraphProfile(
        profile_id="profile:empty",
        version="1",
        mapping=mapping("empty"),
        identity_version="contracts-v1",
    )
    with pytest.raises(ProfileViolationError, match="undeclared labels"):
        validate_record(entity(), empty)
    with pytest.raises(ProfileViolationError, match="undeclared predicate"):
        validate_record(relationship(), empty)


def test_additive_migration_plans_without_approval_prompts():
    old = composed(profile("doc"))
    new = composed(profile("doc", labels=("Document", "Section")))
    plan = plan_migration(old, new)
    assert plan.from_fingerprint == old.fingerprint
    assert plan.to_fingerprint == new.fingerprint
    assert plan.added_labels == ("Section",)
    assert plan.removed_labels == ()
    assert plan.requires_approval is True
    assert type(plan).model_validate_json(plan.model_dump_json()) == plan


def test_drops_relabels_and_identity_rewrites_need_explicit_approval():
    old = composed(
        profile(
            "doc",
            labels=("Document", "Section"),
            predicates=("https://example/mentions", "https://example/old"),
            indexes=(IndexRequirement(entity_kind="node", property_name="title"),),
        )
    )
    slimmer = composed(profile("doc", labels=("Document",)))
    with pytest.raises(MigrationError, match="allow_drops"):
        plan_migration(old, slimmer)
    approved = plan_migration(old, slimmer, allow_drops=True)
    assert approved.removed_labels == ("Section",)
    assert approved.removed_predicates == ("https://example/old",)
    assert approved.removed_indexes == (
        IndexRequirement(entity_kind="node", property_name="title"),
    )
    rewritten = composed(profile("doc"), identity_version="contracts-v1")
    changed_scheme = GraphProfile.model_validate(
        rewritten.model_dump() | {"identity_version": "contracts-v2"}
    )
    with pytest.raises(MigrationError, match="allow_drops"):
        plan_migration(rewritten, changed_scheme)
    assert plan_migration(rewritten, changed_scheme, allow_drops=True).identity_version_changed


def test_generic_backend_module_has_no_source_or_storage_imports():
    source = (ROOT / "src/synirmos/storage/profiles.py").read_text()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("synirmos.sources"), module
            assert module != "synirmos.storage.graph", module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("synirmos.sources"), alias.name
