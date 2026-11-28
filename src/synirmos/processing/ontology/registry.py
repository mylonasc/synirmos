"""Versioned ontology registry: the working set behind immutable releases.

Mirrors ``TopicRegistry`` semantics: collisions fail instead of merging,
aliases attach without rewriting history, deprecation supersedes rather
than deletes, and every mutation bumps the working version. Calling
:meth:`OntologyRegistry.release` freezes the working set into an
immutable, fingerprinted :class:`OntologyRelease`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import datetime

from ...core.models import FrozenModel, ensure_utc
from .models import OntologyClass, OntologyProperty, OntologyRelease, OntologyStatus

__all__ = ["OntologyRegistry"]


class OntologyRegistry(FrozenModel):
    version: int = 0
    classes: tuple[OntologyClass, ...] = ()
    properties: tuple[OntologyProperty, ...] = ()
    updated_at: datetime

    def lookup_class(self, name_or_alias_or_id: str) -> OntologyClass | None:
        wanted = name_or_alias_or_id.strip().lower()
        for item in self.classes:
            known = {item.class_id.lower(), item.name.lower(), *(a.lower() for a in item.aliases)}
            if wanted in known:
                return item
        return None

    def lookup_property(self, name_or_alias_or_id: str) -> OntologyProperty | None:
        wanted = name_or_alias_or_id.strip().lower()
        for item in self.properties:
            known = {
                item.property_id.lower(),
                item.name.lower(),
                *(a.lower() for a in item.aliases),
            }
            if wanted in known:
                return item
        return None

    def active_classes(self) -> tuple[OntologyClass, ...]:
        return tuple(item for item in self.classes if item.status is OntologyStatus.ACTIVE)

    def active_properties(self) -> tuple[OntologyProperty, ...]:
        return tuple(item for item in self.properties if item.status is OntologyStatus.ACTIVE)

    def register_class(
        self,
        item: OntologyClass,
        *,
        at: datetime,
    ) -> tuple[OntologyRegistry, OntologyClass]:
        """Add a genuinely new class; collisions fail instead of merging."""

        if self.lookup_class(item.class_id) is not None or self.lookup_class(item.name) is not None:
            raise ValueError(f"Ontology class {item.name!r} already exists; use an alias")
        for parent_id in item.parent_ids:
            parent = next((c for c in self.classes if c.class_id == parent_id), None)
            if parent is None:
                raise ValueError(f"Unknown parent class {parent_id!r}")
            if parent.status is not OntologyStatus.ACTIVE:
                raise ValueError(f"Parent class {parent_id!r} is not active")
        return (
            self.model_copy(
                update={
                    "version": self.version + 1,
                    "classes": (*self.classes, item),
                    "updated_at": ensure_utc(at),
                }
            ),
            item,
        )

    def register_property(
        self,
        item: OntologyProperty,
        *,
        at: datetime,
    ) -> tuple[OntologyRegistry, OntologyProperty]:
        """Add a genuinely new property; domains/ranges/parents must exist."""

        if (
            self.lookup_property(item.property_id) is not None
            or self.lookup_property(item.name) is not None
        ):
            raise ValueError(f"Ontology property {item.name!r} already exists; use an alias")
        for class_id in (*item.domains, *item.ranges):
            if next((c for c in self.classes if c.class_id == class_id), None) is None:
                raise ValueError(f"Unknown domain/range class {class_id!r}")
        for parent_id in item.parent_ids:
            if next((p for p in self.properties if p.property_id == parent_id), None) is None:
                raise ValueError(f"Unknown parent property {parent_id!r}")
        return (
            self.model_copy(
                update={
                    "version": self.version + 1,
                    "properties": (*self.properties, item),
                    "updated_at": ensure_utc(at),
                }
            ),
            item,
        )

    def add_class_alias(
        self, class_id: str, alias: str, *, at: datetime
    ) -> tuple[OntologyRegistry, OntologyClass]:
        """Attach a name variant; original references keep working."""

        return self._with_updated(
            "classes", class_id, alias, at, self.lookup_class, "class_id", "aliases"
        )

    def add_property_alias(
        self, property_id: str, alias: str, *, at: datetime
    ) -> tuple[OntologyRegistry, OntologyProperty]:
        """Attach a name variant to a property."""

        return self._with_updated(
            "properties", property_id, alias, at, self.lookup_property, "property_id", "aliases"
        )

    def set_contextualizing(
        self, property_id: str, value: bool, *, at: datetime
    ) -> tuple[OntologyRegistry, OntologyProperty]:
        """Tag or untag a retrieval-traversal property without code changes."""

        target = next((p for p in self.properties if p.property_id == property_id), None)
        if target is None:
            raise ValueError(f"Unknown property {property_id!r}")
        if target.contextualizing == value:
            return self, target
        updated = target.model_copy(update={"contextualizing": value})
        items = tuple(updated if p.property_id == property_id else p for p in self.properties)
        return (
            self.model_copy(
                update={
                    "version": self.version + 1,
                    "properties": items,
                    "updated_at": ensure_utc(at),
                }
            ),
            updated,
        )

    def deprecate_class(
        self, class_id: str, *, at: datetime
    ) -> tuple[OntologyRegistry, OntologyClass]:
        """Retire a class from active use; history stays resolvable."""

        return self._with_status("classes", class_id, OntologyStatus.DEPRECATED, at)

    def deprecate_property(
        self, property_id: str, *, at: datetime
    ) -> tuple[OntologyRegistry, OntologyProperty]:
        """Retire a property from active use; history stays resolvable."""

        return self._with_status("properties", property_id, OntologyStatus.DEPRECATED, at)

    def subclasses_of(self, class_id: str) -> tuple[str, ...]:
        """Return ``class_id`` plus all transitive subclasses (active only)."""

        children: dict[str, list[str]] = {}
        for item in self.classes:
            if item.status is not OntologyStatus.ACTIVE:
                continue
            for parent_id in item.parent_ids:
                children.setdefault(parent_id, []).append(item.class_id)
        found = [class_id]
        queue = [class_id]
        while queue:
            current = queue.pop(0)
            for child in children.get(current, []):
                if child not in found:
                    found.append(child)
                    queue.append(child)
        return tuple(found)

    def validate_triple(
        self, subject_class_id: str, property_id: str, object_class_id: str
    ) -> bool:
        """Check a candidate (subject, predicate, object) against the ontology.

        The subject must be the property's domain class or one of its
        subclasses; likewise for the object and the range. An empty domain
        or range list means unconstrained on that side. Inactive or unknown
        elements never validate.
        """

        prop = next((p for p in self.properties if p.property_id == property_id), None)
        if prop is None or prop.status is not OntologyStatus.ACTIVE:
            return False
        subject = next((c for c in self.classes if c.class_id == subject_class_id), None)
        obj = next((c for c in self.classes if c.class_id == object_class_id), None)
        if (
            subject is None
            or obj is None
            or subject.status is not OntologyStatus.ACTIVE
            or obj.status is not OntologyStatus.ACTIVE
        ):
            return False
        return self._side_ok(prop.domains, subject_class_id) and self._side_ok(
            prop.ranges, object_class_id
        )

    def compile_schema(self) -> dict[str, object]:
        """Emit the closed extraction vocabulary for the active release."""

        return {
            "version": self.version,
            "classes": [
                {"class_id": c.class_id, "name": c.name, "definition": c.definition}
                for c in self.active_classes()
            ],
            "properties": [
                {
                    "property_id": p.property_id,
                    "name": p.name,
                    "definition": p.definition,
                    "domains": list(p.domains),
                    "ranges": list(p.ranges),
                    "contextualizing": p.contextualizing,
                }
                for p in self.active_properties()
            ],
        }

    def release(
        self, version: str, *, at: datetime, created_by: str, supersedes: str | None = None
    ) -> OntologyRelease:
        """Freeze the active working set into an immutable release."""

        moment = ensure_utc(at)
        payload = {
            "version": version,
            "classes": sorted(
                json.dumps(c.model_dump(mode="json"), sort_keys=True) for c in self.active_classes()
            ),
            "properties": sorted(
                json.dumps(p.model_dump(mode="json"), sort_keys=True)
                for p in self.active_properties()
            ),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return OntologyRelease(
            version=version,
            fingerprint=hashlib.sha256(canonical.encode()).hexdigest(),
            classes=self.active_classes(),
            properties=self.active_properties(),
            created_at=moment,
            created_by=created_by,
            supersedes=supersedes,
        )

    # -- internals -----------------------------------------------------
    def _side_ok(self, allowed: Sequence[str], actual: str) -> bool:
        if not allowed:
            return True
        for class_id in allowed:
            if actual in self.subclasses_of(class_id):
                return True
        return False

    def _with_status(
        self, field: str, item_id: str, status: OntologyStatus, at: datetime
    ) -> tuple[OntologyRegistry, OntologyClass | OntologyProperty]:
        key = "class_id" if field == "classes" else "property_id"
        items = list(getattr(self, field))
        updated = None
        for index, item in enumerate(items):
            if getattr(item, key) == item_id:
                updated = item.model_copy(update={"status": status})
                items[index] = updated
        if updated is None:
            raise ValueError(f"Unknown ontology element {item_id!r}")
        return (
            self.model_copy(
                update={
                    "version": self.version + 1,
                    field: tuple(items),
                    "updated_at": ensure_utc(at),
                }
            ),
            updated,
        )

    def _with_updated(
        self,
        field: str,
        item_id: str,
        alias: str,
        at: datetime,
        lookup: Callable[[str], OntologyClass | OntologyProperty | None],
        key: str,
        plural: str,
    ) -> tuple[OntologyRegistry, OntologyClass | OntologyProperty]:
        clean = alias.strip()
        if not clean:
            raise ValueError("Aliases cannot be empty")
        existing = lookup(clean)
        items = list(getattr(self, field))
        target = next((i for i in items if getattr(i, key) == item_id), None)
        if target is None:
            raise ValueError(f"Unknown ontology element {item_id!r}")
        if existing is not None and getattr(existing, key) != item_id:
            raise ValueError(f"Alias {clean!r} already belongs to another element")
        known = {
            getattr(target, key).lower(),
            target.name.lower(),
            *(a.lower() for a in getattr(target, plural)),
        }
        if clean.lower() not in known:
            target = target.model_copy(update={plural: (*getattr(target, plural), clean)})
            items = [target if getattr(i, key) == item_id else i for i in items]
        return (
            self.model_copy(
                update={
                    "version": self.version + 1,
                    field: tuple(items),
                    "updated_at": ensure_utc(at),
                }
            ),
            target,
        )
