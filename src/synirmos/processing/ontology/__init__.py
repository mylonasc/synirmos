"""Versioned ontology registry: the shared contract for ONTO-KG."""

from .models import (
    OntologyClass,
    OntologyProperty,
    OntologyRelease,
    OntologyStatus,
    class_id_for,
    property_id_for,
)
from .registry import OntologyRegistry
from .seed import seed_document_ontology

__all__ = [
    "OntologyClass",
    "OntologyProperty",
    "OntologyRegistry",
    "OntologyRelease",
    "OntologyStatus",
    "class_id_for",
    "property_id_for",
    "seed_document_ontology",
]
