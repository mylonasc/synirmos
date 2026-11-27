"""Ontology registry: versioned classes, properties, releases, validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from synirmos.processing.ontology import (
    OntologyClass,
    OntologyProperty,
    OntologyRegistry,
    OntologyStatus,
    class_id_for,
    property_id_for,
    seed_document_ontology,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def registry(*, at: datetime = NOW) -> OntologyRegistry:
    return OntologyRegistry(version=0, updated_at=at)


def test_ids_are_derived_and_validated():
    assert class_id_for("Board Agreement") == "onto:board_agreement"
    assert property_id_for("governedBy") == "onto:governedby"
    with pytest.raises(ValueError):
        class_id_for("   ")
    with pytest.raises(ValueError):
        OntologyClass(class_id="bad id", name="Bad")
    with pytest.raises(ValueError):
        OntologyClass(class_id="onto:ok", name="  ")


def test_register_class_rejects_collisions_and_unknown_parents():
    reg = registry()
    reg, _ = reg.register_class(
        OntologyClass(class_id="onto:organization", name="Organization"), at=NOW
    )
    assert reg.version == 1
    with pytest.raises(ValueError, match="already exists"):
        reg.register_class(OntologyClass(class_id="onto:organization", name="Other"), at=NOW)
    with pytest.raises(ValueError, match="already exists"):
        reg.register_class(OntologyClass(class_id="onto:other", name="Organization"), at=NOW)
    with pytest.raises(ValueError, match="Unknown parent"):
        reg.register_class(
            OntologyClass(class_id="onto:child", name="Child", parent_ids=("onto:missing",)),
            at=NOW,
        )


def test_register_property_requires_known_domain_range_and_parents():
    reg = registry()
    reg, _ = reg.register_class(
        OntologyClass(class_id="onto:organization", name="Organization"), at=NOW
    )
    with pytest.raises(ValueError, match="Unknown domain/range"):
        reg.register_property(
            OntologyProperty(
                property_id="onto:governed_by",
                name="GOVERNED_BY",
                domains=("onto:organization",),
                ranges=("onto:missing",),
            ),
            at=NOW,
        )
    with pytest.raises(ValueError, match="Unknown parent property"):
        reg.register_property(
            OntologyProperty(
                property_id="onto:governed_by",
                name="GOVERNED_BY",
                domains=("onto:organization",),
                ranges=("onto:organization",),
                parent_ids=("onto:missing",),
            ),
            at=NOW,
        )
    reg, prop = reg.register_property(
        OntologyProperty(
            property_id="onto:governed_by",
            name="GOVERNED_BY",
            domains=("onto:organization",),
            ranges=("onto:organization",),
        ),
        at=NOW,
    )
    assert prop.property_id == "onto:governed_by"
    assert reg.version == 2


def test_aliases_attach_without_rewriting_history():
    reg = registry()
    reg, _ = reg.register_class(
        OntologyClass(class_id="onto:organization", name="Organization"), at=NOW
    )
    reg, updated = reg.add_class_alias("onto:organization", "Company", at=NOW)
    assert updated.aliases == ("Company",)
    assert reg.lookup_class("company") is not None
    reg, same = reg.add_class_alias("onto:organization", "Company", at=NOW)
    assert same.aliases == ("Company",)  # re-adding own alias is idempotent
    reg, _ = reg.register_class(OntologyClass(class_id="onto:bank", name="Bank"), at=NOW)
    with pytest.raises(ValueError, match="already belongs"):
        reg.add_class_alias("onto:bank", "company", at=NOW)
    with pytest.raises(ValueError, match="Unknown ontology element"):
        reg.add_class_alias("onto:missing", "Whatever", at=NOW)


def test_contextualizing_tags_toggle_retrieval_without_code_changes():
    reg = registry()
    reg, _ = reg.register_class(
        OntologyClass(class_id="onto:organization", name="Organization"), at=NOW
    )
    reg, _ = reg.register_property(
        OntologyProperty(
            property_id="onto:governed_by",
            name="GOVERNED_BY",
            domains=("onto:organization",),
            ranges=("onto:organization",),
        ),
        at=NOW,
    )
    reg, tagged = reg.set_contextualizing("onto:governed_by", True, at=NOW)
    assert tagged.contextualizing is True
    reg, _ = reg.set_contextualizing("onto:governed_by", False, at=NOW)
    assert reg.lookup_property("onto:governed_by").contextualizing is False
    with pytest.raises(ValueError, match="Unknown property"):
        reg.set_contextualizing("onto:missing", True, at=NOW)


def test_deprecation_keeps_history_resolvable_but_inactive():
    reg = registry()
    reg, _ = reg.register_class(
        OntologyClass(class_id="onto:organization", name="Organization"), at=NOW
    )
    reg, deprecated = reg.deprecate_class("onto:organization", at=NOW)
    assert deprecated.status is OntologyStatus.DEPRECATED
    assert reg.active_classes() == ()
    assert reg.lookup_class("onto:organization") is not None
    with pytest.raises(ValueError, match="Unknown ontology element"):
        reg.deprecate_class("onto:missing", at=NOW)


def test_validate_triple_respects_hierarchy_and_openness():
    reg = registry()
    for name, parents in (("Organization", ()), ("StockCorporation", ("onto:organization",))):
        reg, _ = reg.register_class(
            OntologyClass(
                class_id=f"onto:{name.lower()}",
                name=name,
                parent_ids=parents,
            ),
            at=NOW,
        )
    reg, _ = reg.register_property(
        OntologyProperty(
            property_id="onto:subsidiary_of",
            name="SUBSIDIARY_OF",
            domains=("onto:organization",),
            ranges=("onto:organization",),
        ),
        at=NOW,
    )
    reg, _ = reg.register_property(
        OntologyProperty(property_id="onto:related_to", name="RELATED_TO"), at=NOW
    )
    assert reg.validate_triple("onto:stockcorporation", "onto:subsidiary_of", "onto:organization")
    assert not reg.validate_triple(
        "onto:organization", "onto:subsidiary_of", "onto:stockcorporationX"
    )
    assert reg.validate_triple("onto:organization", "onto:related_to", "onto:stockcorporation")
    assert not reg.validate_triple("onto:organization", "onto:missing", "onto:organization")


def test_compile_schema_emits_closed_vocabulary():
    reg = seed_document_ontology(at=NOW)
    schema = reg.compile_schema()
    class_ids = {c["class_id"] for c in schema["classes"]}
    assert {"onto:document", "onto:chunk", "onto:person"} <= class_ids
    mentions = next(p for p in schema["properties"] if p["property_id"] == "onto:mentions")
    assert "onto:person" in mentions["ranges"]
    assert mentions["contextualizing"] is False
    defines = next(p for p in schema["properties"] if p["property_id"] == "onto:defines")
    assert defines["contextualizing"] is True


def test_release_is_immutable_and_fingerprinted():
    reg = seed_document_ontology(at=NOW)
    first = reg.release("v1", at=NOW, created_by="slice-0")
    second = reg.release("v1", at=NOW, created_by="slice-0")
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    reg, _ = reg.register_class(
        OntologyClass(class_id="onto:regulation", name="Regulation"), at=NOW
    )
    third = reg.release("v2", at=NOW, created_by="slice-0", supersedes="v1")
    assert third.fingerprint != first.fingerprint
    assert third.supersedes == "v1"
    assert third.created_at == NOW


def test_seed_ontology_is_self_consistent():
    reg = seed_document_ontology(at=NOW)
    assert len(reg.active_classes()) == 7
    assert len(reg.active_properties()) == 8
    assert reg.validate_triple("onto:chunk", "onto:mentions", "onto:person")
    assert reg.validate_triple("onto:document", "onto:has_section", "onto:section")
    assert not reg.validate_triple("onto:person", "onto:has_section", "onto:section")
    assert not reg.validate_triple("onto:chunk", "onto:mentions", "onto:chunk")
