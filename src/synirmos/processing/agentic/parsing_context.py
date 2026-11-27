"""Read-only parsing handle for agentic extraction.

A ``ParsingContext`` is the only way an extraction agent observes already
known state: the subject under analysis, previously extracted entities and
relations, and (in future graph-backed implementations) the already parsed
graph. It is read-only on purpose: agents propose entities and relations
through their returned proposals, never by mutating shared state.

Implementations must already enforce the decision horizon: only entities
and relations with ``info_horizon <=`` the decision horizon may be
visible. All accessors are bounded so prompts stay within budget.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from ...core.models import FrozenModel, ensure_utc

__all__ = [
    "EntityView",
    "InMemoryParsingContext",
    "ParsingContext",
    "RelationView",
]


class EntityView(FrozenModel):
    entity_id: str
    kind: str
    name: str
    description: str = ""


class RelationView(FrozenModel):
    source_id: str
    target_id: str
    relation: str
    confidence: float = 1.0
    rationale: str = ""


@runtime_checkable
class ParsingContext(Protocol):
    """Bounded, horizon-filtered, read-only view over known state."""

    @property
    def subject_id(self) -> str: ...

    @property
    def subject_text(self) -> str: ...

    @property
    def info_horizon(self) -> datetime: ...

    def list_entities(self, *, limit: int = 50) -> tuple[EntityView, ...]: ...

    def search_entities(self, query: str, *, limit: int = 20) -> tuple[EntityView, ...]: ...

    def get_entity(self, entity_id: str) -> EntityView | None: ...

    def list_relations(
        self, entity_id: str | None = None, *, limit: int = 50
    ) -> tuple[RelationView, ...]: ...

    def neighbors(self, entity_id: str, relation: str | None = None) -> tuple[str, ...]: ...

    def snapshot_digest(self) -> str:
        """Hash the visible entity/relation identity set for cache keys."""
        ...


class InMemoryParsingContext:
    """Offline handle over fixed entity/relation tuples.

    The caller is responsible for horizon filtering: only pass entities
    and relations the decision at ``info_horizon`` is allowed to see.
    """

    def __init__(
        self,
        *,
        subject_id: str,
        subject_text: str = "",
        info_horizon: datetime,
        entities: Sequence[EntityView] = (),
        relations: Sequence[RelationView] = (),
    ) -> None:
        self._subject_id = subject_id
        self._subject_text = subject_text
        self._horizon = ensure_utc(info_horizon)
        self._entities = tuple(entities)
        self._relations = tuple(relations)
        self._by_id = {entity.entity_id: entity for entity in self._entities}

    @property
    def subject_id(self) -> str:
        return self._subject_id

    @property
    def subject_text(self) -> str:
        return self._subject_text

    @property
    def info_horizon(self) -> datetime:
        return self._horizon

    def list_entities(self, *, limit: int = 50) -> tuple[EntityView, ...]:
        return self._entities[: max(0, limit)]

    def search_entities(self, query: str, *, limit: int = 20) -> tuple[EntityView, ...]:
        needle = query.strip().lower()
        if not needle:
            return ()
        matched = [
            entity
            for entity in self._entities
            if needle in entity.name.lower()
            or needle in entity.description.lower()
            or needle in entity.entity_id.lower()
        ]
        return tuple(matched[: max(0, limit)])

    def get_entity(self, entity_id: str) -> EntityView | None:
        return self._by_id.get(entity_id)

    def list_relations(
        self, entity_id: str | None = None, *, limit: int = 50
    ) -> tuple[RelationView, ...]:
        if entity_id is None:
            return self._relations[: max(0, limit)]
        matched = [
            relation
            for relation in self._relations
            if relation.source_id == entity_id or relation.target_id == entity_id
        ]
        return tuple(matched[: max(0, limit)])

    def neighbors(self, entity_id: str, relation: str | None = None) -> tuple[str, ...]:
        found: list[str] = []
        for item in self._relations:
            if relation is not None and item.relation != relation:
                continue
            if item.source_id == entity_id and item.target_id not in found:
                found.append(item.target_id)
            elif item.target_id == entity_id and item.source_id not in found:
                found.append(item.source_id)
        return tuple(sorted(found)[:50])

    def snapshot_digest(self) -> str:
        material = "|".join(
            [
                self._subject_id,
                *[entity.entity_id for entity in sorted(self._entities, key=lambda e: e.entity_id)],
                *sorted(
                    f"{item.source_id}>{item.target_id}:{item.relation}" for item in self._relations
                ),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
