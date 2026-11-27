"""JERE (joint entity-and-relation extraction) schemas.

The agent proposes new entities under temporary ``key`` handles and links
them — to each other or to already known entity IDs observed through the
:class:`~synirmos.processing.agentic.parsing_context.ParsingContext` — in
one joint proposal. The provider resolves keys to stable IDs and rejects
endpoints that are neither declared keys nor observed IDs.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ...core.models import FrozenModel

__all__ = [
    "JERE_METHOD",
    "JERE_METHOD_VERSION",
    "JERE_SCHEMA_VERSION",
    "JereEntityKind",
    "JereEntityProposal",
    "JereProposal",
    "JereRelationKind",
    "JereRelationProposal",
    "link_relation_for",
]

JERE_SCHEMA_VERSION = "1"
JERE_METHOD = "jere-basic"
JERE_METHOD_VERSION = "1"


class JereEntityKind(StrEnum):
    FILE = "FILE"
    SYMBOL = "SYMBOL"
    SECTION = "SECTION"
    TOPIC = "TOPIC"
    CONCEPT = "CONCEPT"
    WORK_ITEM = "WORK_ITEM"
    COMMIT = "COMMIT"


class JereRelationKind(StrEnum):
    MENTIONS = "MENTIONS"
    RELATED_TO = "RELATED_TO"
    INTENDS_TO_RESOLVE = "INTENDS_TO_RESOLVE"
    DEFINES = "DEFINES"
    PART_OF = "PART_OF"


class JereEntityProposal(FrozenModel):
    key: str
    kind: JereEntityKind
    name: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_quotes: tuple[str, ...] = ()


class JereRelationProposal(FrozenModel):
    source: str
    target: str
    relation: JereRelationKind
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class JereProposal(FrozenModel):
    entities: tuple[JereEntityProposal, ...] = ()
    relations: tuple[JereRelationProposal, ...] = ()
    abstained: bool = False
    rationale: str = ""

    @model_validator(mode="after")
    def check_keys(self) -> Self:
        keys = [entity.key for entity in self.entities]
        if len(set(keys)) != len(keys):
            raise ValueError("entity keys must be unique")
        if not all(key.strip() for key in keys):
            raise ValueError("entity keys must not be blank")
        if self.abstained and (self.entities or self.relations):
            raise ValueError("abstained proposals must carry no entities or relations")
        return self


def link_relation_for(kind: JereRelationKind) -> str:
    """Map a JERE relation onto the shared link vocabulary.

    ``MENTIONS``, ``RELATED_TO``, and ``INTENDS_TO_RESOLVE`` already exist
    in :class:`synirmos.processing.linking.LinkRelation`; structural
    relations fold into ``RELATED_TO`` until the neutral vocabulary grows.
    """

    if kind in (
        JereRelationKind.MENTIONS,
        JereRelationKind.RELATED_TO,
        JereRelationKind.INTENDS_TO_RESOLVE,
    ):
        return kind.value
    return JereRelationKind.RELATED_TO.value
