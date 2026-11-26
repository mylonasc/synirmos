"""Provider-neutral envelopes shared by hosted-platform adapters.

Native payloads remain evidence. Normalizers emit the existing event envelope;
typed work-item/change-request records are a subsequent migration milestone.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, Field, field_validator

from ..core.events import IngestEvent
from ..core.models import CoverageGap, FrozenModel, ensure_utc


class ResourceKind(StrEnum):
    PROJECT = "project"
    WORK_ITEM = "work-item"
    CHANGE_REQUEST = "change-request"
    COMMENT = "comment"
    ACTIVITY = "activity"
    LABEL = "label"
    RELATION = "relation"


class PlatformInstance(FrozenModel):
    """One deployment/tenant, not a repository or a branch."""

    provider: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    base_url: AnyHttpUrl

    @field_validator("base_url")
    @classmethod
    def credential_free_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("platform base URL must not contain credentials, query, or fragment")
        return value


class ExternalRef(FrozenModel):
    """A provider-qualified native identity; IDs need not be numeric or Git-related."""

    platform: PlatformInstance
    scope: str = Field(min_length=1)
    kind: ResourceKind
    native_id: str = Field(min_length=1)


class RepositoryBinding(FrozenModel):
    """Association to a Git repository; neither identity owns the other."""

    project: ExternalRef
    repository_id: str = Field(min_length=1)

    @field_validator("project")
    @classmethod
    def project_reference(cls, value: ExternalRef) -> ExternalRef:
        if value.kind != ResourceKind.PROJECT:
            raise ValueError("repository binding requires a project reference")
        return value


class PlatformCapabilities(FrozenModel):
    """Support declarations, not guarantees about permission or current coverage."""

    collections: frozenset[ResourceKind] = frozenset()
    historical_body_revisions: bool = False
    historical_label_revisions: bool = False


class CollectionRequest(FrozenModel):
    """One bounded page request for a subject's collection.

    A project subject lists explicitly scoped resources; work-item or
    change-request subjects select their comments, activities, or relations.
    Cursor contents are opaque and owned by the adapter. The orchestrator owns
    allowlists and total page/item budgets; a page size is not a total budget.
    """

    subject: ExternalRef
    collection: ResourceKind
    cursor: str | None = None
    page_size: int = Field(default=50, ge=1, le=100)


class EvidencePage(FrozenModel):
    """A captured response; pure normalization must not fetch subsequent pages."""

    evidence_id: str = Field(min_length=1)
    request: CollectionRequest
    source_url: str
    observed_at: datetime
    status_code: int = Field(ge=100, le=599)
    content_type: str
    payload: bytes
    next_cursor: str | None = None

    @field_validator("observed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class PlatformBatch(FrozenModel):
    """Normalized events and explicit coverage, with the evidence used retained."""

    events: tuple[IngestEvent, ...] = ()
    gaps: tuple[CoverageGap, ...] = ()
    evidence_ids: tuple[str, ...] = ()
