"""Ontology metamodel: versioned classes, properties, and releases.

The ontology is the single semantic contract for extraction and
retrieval. This module defines the internal representation (plain
``FrozenModel``s, no OWL/SHACL engine): human-readable stable IDs of the
form ``onto:snake_name``, subclass/subproperty hierarchies, domain/range
constraints, aliases, lifecycle status, and retrieval tags
(``contextualizing``) that later drive graph traversal without code
changes.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from ...core.models import FrozenModel

__all__ = [
    "ONTOLOGY_ID_PATTERN",
    "OntologyClass",
    "OntologyProperty",
    "OntologyRelease",
    "OntologyStatus",
    "class_id_for",
    "property_id_for",
]

ONTOLOGY_ID_PATTERN = re.compile(r"^onto:[a-z][a-z0-9_]*$")


class OntologyStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


def class_id_for(name: str) -> str:
    """Derive a stable, human-readable class ID from a display name."""

    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    if not slug:
        raise ValueError("Ontology class names must contain alphanumeric characters")
    return f"onto:{slug}"


def property_id_for(name: str) -> str:
    """Derive a stable, human-readable property ID from a display name."""

    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    if not slug:
        raise ValueError("Ontology property names must contain alphanumeric characters")
    return f"onto:{slug}"


class OntologyClass(FrozenModel):
    class_id: str
    name: str
    definition: str = ""
    parent_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    status: OntologyStatus = OntologyStatus.ACTIVE
    introduced_in: str = "v1"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if not ONTOLOGY_ID_PATTERN.match(self.class_id):
            raise ValueError(f"Invalid ontology class ID: {self.class_id!r}")
        if not self.name.strip():
            raise ValueError("Ontology class names must not be blank")


class OntologyProperty(FrozenModel):
    property_id: str
    name: str
    definition: str = ""
    domains: tuple[str, ...] = ()
    ranges: tuple[str, ...] = ()
    parent_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    contextualizing: bool = False
    status: OntologyStatus = OntologyStatus.ACTIVE
    introduced_in: str = "v1"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if not ONTOLOGY_ID_PATTERN.match(self.property_id):
            raise ValueError(f"Invalid ontology property ID: {self.property_id!r}")
        if not self.name.strip():
            raise ValueError("Ontology property names must not be blank")


class OntologyRelease(FrozenModel):
    version: str
    fingerprint: str
    classes: tuple[OntologyClass, ...] = ()
    properties: tuple[OntologyProperty, ...] = ()
    created_at: datetime
    created_by: str = ""
    supersedes: str | None = None
