"""Seed document-domain ontology: the starting contract for ONTO-KG slices.

Lexical classes model document structure; domain classes model the kind
of entities Slice 3+ extraction will produce. Property domains/ranges
are deliberately tight so validation has teeth, and traversal tags
(``contextualizing``) mark the relations retrieval may follow.
"""

from __future__ import annotations

from datetime import datetime

from .models import OntologyClass, OntologyProperty, OntologyStatus
from .registry import OntologyRegistry

__all__ = ["seed_document_ontology"]


def seed_document_ontology(*, at: datetime) -> OntologyRegistry:
    """Build the minimal working ontology for document indexing."""

    registry = OntologyRegistry(version=0, updated_at=at)
    for name, definition, parents in (
        ("Document", "A whole indexed document revision.", ()),
        ("Section", "A structural division of a document.", ()),
        ("Chunk", "An addressable span of document text.", ()),
        ("Person", "A human agent mentioned in or authoring a document.", ()),
        ("Organization", "A company, institution, or group.", ()),
        ("Concept", "An abstract idea or subject discussed in text.", ()),
        ("Topic", "A labeled theme grouping related concepts.", ()),
    ):
        registry, _ = registry.register_class(
            OntologyClass(
                class_id=f"onto:{name.lower()}",
                name=name,
                definition=definition,
                parent_ids=tuple(f"onto:{p.lower()}" for p in parents),
            ),
            at=at,
        )
    for name, definition, domains, ranges, contextualizing in (
        (
            "HAS_SECTION",
            "Links a document to one of its sections.",
            ("onto:document",),
            ("onto:section",),
            False,
        ),
        (
            "HAS_CHUNK",
            "Links a section to one of its text chunks.",
            ("onto:section",),
            ("onto:chunk",),
            False,
        ),
        (
            "NEXT_CHUNK",
            "Orders a chunk after its predecessor.",
            ("onto:chunk",),
            ("onto:chunk",),
            False,
        ),
        (
            "MENTIONS",
            "Links a chunk to an entity it names.",
            ("onto:chunk",),
            ("onto:person", "onto:organization", "onto:concept", "onto:topic"),
            False,
        ),
        (
            "AUTHORED_BY",
            "Links a document to its author.",
            ("onto:document",),
            ("onto:person", "onto:organization"),
            False,
        ),
        (
            "DEFINES",
            "Links a chunk to a concept it defines.",
            ("onto:chunk",),
            ("onto:concept", "onto:topic"),
            True,
        ),
        (
            "PART_OF",
            "Links an entity to the larger entity containing it.",
            ("onto:person", "onto:organization", "onto:concept", "onto:topic"),
            ("onto:organization", "onto:concept", "onto:topic"),
            True,
        ),
        (
            "RELATED_TO",
            "Weak topical association between domain entities.",
            ("onto:person", "onto:organization", "onto:concept", "onto:topic"),
            ("onto:person", "onto:organization", "onto:concept", "onto:topic"),
            True,
        ),
    ):
        registry, _ = registry.register_property(
            OntologyProperty(
                property_id=f"onto:{name.lower()}",
                name=name,
                definition=definition,
                domains=domains,
                ranges=ranges,
                contextualizing=contextualizing,
                status=OntologyStatus.ACTIVE,
                introduced_in="v1",
            ),
            at=at,
        )
    return registry
