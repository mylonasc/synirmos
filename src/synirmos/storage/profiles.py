"""Deterministic profile composition, validation, and migration planning (D1).

Pure functions over :mod:`synirmos.core.graph` descriptors. No storage handles,
no source adapters, no network. Composition rejects conflicting definitions
instead of last-writer-wins overrides; validation is fail-closed against the
declared vocabulary; migration plans never authorize silent drops.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from ..core.contracts import ArtifactSpec, ContractModel, NonBlank
from ..core.graph import EntityRecord, GraphProfile, IndexRequirement, RelationshipRecord


class ProfileConflictError(ValueError):
    """Two profiles cannot be composed without an explicit reviewed decision."""


class ProfileViolationError(ValueError):
    """A record or capability set does not satisfy the composed profile."""


class MigrationError(ValueError):
    """A profile change needs explicit approval; it is not applied silently."""


#: Provenance and driver-managed keys that domain payloads must never set.
RESERVED_PROVENANCE_KEYS: tuple[str, ...] = (
    "prov_run_id",
    "prov_origin",
    "prov_origin_id",
    "prov_event_id",
    "prov_info_horizon",
    "prov_evidence_ids",
    "type",
)


def _check_composable(profiles: Sequence[GraphProfile], identity_version: NonBlank) -> None:
    """Reject duplicate, divergent, or scheme-mismatched profile identities."""
    seen: dict[str, GraphProfile] = {}
    for profile in profiles:
        known = seen.get(profile.profile_id)
        if known is None:
            seen[profile.profile_id] = profile
        elif known.version != profile.version:
            raise ProfileConflictError(
                f"profile {profile.profile_id!r} declares versions "
                f"{known.version!r} and {profile.version!r}"
            )
        elif known.fingerprint != profile.fingerprint:
            raise ProfileConflictError(
                f"profile {profile.profile_id!r} version {profile.version!r} "
                "has conflicting definitions"
            )
    schemes = {profile.identity_version for profile in profiles}
    if len(schemes) != 1 or identity_version not in schemes:
        raise ProfileConflictError(
            f"composition identity {identity_version!r} does not match inputs {sorted(schemes)}"
        )


def compose_profiles(
    profiles: Sequence[GraphProfile],
    *,
    profile_id: NonBlank,
    version: NonBlank,
    mapping: ArtifactSpec,
    identity_version: NonBlank,
) -> GraphProfile:
    """Merge descriptors deterministically; reject conflicting definitions.

    Union semantics apply to labels, predicates, properties, indexes, and
    capabilities. The same ``profile_id`` must always carry identical content;
    identity schemes cannot be mixed within one composition.
    """
    if not profiles:
        raise ProfileConflictError("composition requires at least one profile")
    _check_composable(profiles, identity_version)
    return GraphProfile(
        profile_id=profile_id,
        version=version,
        mapping=mapping,
        identity_version=identity_version,
        labels=tuple(label for profile in profiles for label in profile.labels),
        predicates=tuple(edge for profile in profiles for edge in profile.predicates),
        required_properties=tuple(
            name for profile in profiles for name in profile.required_properties
        ),
        reserved_properties=tuple(
            name for profile in profiles for name in profile.reserved_properties
        ),
        indexes=tuple(index for profile in profiles for index in profile.indexes),
        required_capabilities=tuple(
            name for profile in profiles for name in profile.required_capabilities
        ),
    )


def missing_capabilities(profile: GraphProfile, available: Collection[str]) -> tuple[str, ...]:
    """Capabilities the profile requires but the backend does not supply."""
    provided = set(available)
    return tuple(name for name in profile.required_capabilities if name not in provided)


def require_capabilities(profile: GraphProfile, available: Collection[str]) -> None:
    """Fail closed when the backend cannot satisfy the composed profile."""
    missing = missing_capabilities(profile, available)
    if missing:
        raise ProfileViolationError(
            f"profile {profile.profile_id!r} requires unavailable capabilities: "
            + ", ".join(missing)
        )


def validate_record(record: EntityRecord | RelationshipRecord, profile: GraphProfile) -> None:
    """Check vocabulary, required/reserved keys, and index-relevant properties.

    Empty declared vocabulary rejects every record: a profile that declares
    nothing authorizes nothing. Reserved keys include the profile's own list
    plus the driver-managed provenance keys.
    """
    payload = record.properties.to_dict()
    if isinstance(record, EntityRecord):
        unknown = [label for label in record.labels if label not in profile.labels]
        if unknown:
            raise ProfileViolationError(
                f"entity {record.entity_id!r} uses undeclared labels: " + ", ".join(unknown)
            )
    elif record.predicate_id not in profile.predicates:
        raise ProfileViolationError(
            f"relationship {record.relationship_id!r} uses undeclared predicate "
            f"{record.predicate_id!r}"
        )
    missing = [name for name in profile.required_properties if name not in payload]
    if missing:
        raise ProfileViolationError("record missing required properties: " + ", ".join(missing))
    reserved = set(profile.reserved_properties) | set(RESERVED_PROVENANCE_KEYS)
    collisions = sorted(key for key in payload if key in reserved)
    if collisions:
        raise ProfileViolationError("record sets reserved properties: " + ", ".join(collisions))


class MigrationPlan(ContractModel):
    """Reviewed diff between two profile fingerprints; descriptive, not applied."""

    from_fingerprint: NonBlank
    to_fingerprint: NonBlank
    added_labels: tuple[str, ...] = ()
    removed_labels: tuple[str, ...] = ()
    added_predicates: tuple[str, ...] = ()
    removed_predicates: tuple[str, ...] = ()
    added_indexes: tuple[IndexRequirement, ...] = ()
    removed_indexes: tuple[IndexRequirement, ...] = ()
    identity_version_changed: bool = False
    requires_approval: bool = True


def plan_migration(
    old: GraphProfile, new: GraphProfile, *, allow_drops: bool = False
) -> MigrationPlan:
    """Describe a profile change; refuse silent drops, relabels, or rewrites.

    Removed labels, predicates, or indexes, and any identity-scheme change,
    require ``allow_drops=True`` plus a separately recorded approval. This
    function never mutates history, drops indexes, or rewrites identities.
    """
    removed_labels = tuple(sorted(set(old.labels) - set(new.labels)))
    removed_predicates = tuple(sorted(set(old.predicates) - set(new.predicates)))
    removed_indexes = tuple(
        sorted(
            set(old.indexes) - set(new.indexes),
            key=lambda item: (item.entity_kind, item.property_name),
        )
    )
    identity_changed = old.identity_version != new.identity_version
    if (
        removed_labels or removed_predicates or removed_indexes or identity_changed
    ) and not allow_drops:
        raise MigrationError(
            "profile change drops labels/predicates/indexes or rewrites identity; "
            "record an explicit approved migration with allow_drops=True"
        )
    return MigrationPlan(
        from_fingerprint=old.fingerprint,
        to_fingerprint=new.fingerprint,
        added_labels=tuple(sorted(set(new.labels) - set(old.labels))),
        removed_labels=removed_labels,
        added_predicates=tuple(sorted(set(new.predicates) - set(old.predicates))),
        removed_predicates=removed_predicates,
        added_indexes=tuple(
            sorted(
                set(new.indexes) - set(old.indexes),
                key=lambda item: (item.entity_kind, item.property_name),
            )
        ),
        removed_indexes=removed_indexes,
        identity_version_changed=identity_changed,
    )
