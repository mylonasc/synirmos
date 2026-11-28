"""Immutable document capture values, with no repository or framework dependency."""

from __future__ import annotations

from typing import Self

from pydantic import Field, StrictInt, field_validator, model_validator

from .contracts import (
    SHA256,
    ArtifactSpec,
    ContractModel,
    NonBlank,
    SourceKey,
    content_digest,
    contract_id,
    json_fingerprint,
)
from .models import CoverageGap
from .temporal import RevisionTiming


class ContentMismatchError(ValueError):
    """Captured bytes differ from their immutable reference."""


class DocumentLimitError(ValueError):
    """A source page or content read exceeds its declared limits."""


class ContentReference(ContractModel):
    """Content address, not a path/URL or access grant."""

    digest: SHA256
    byte_length: StrictInt = Field(ge=0)

    @classmethod
    def from_bytes(cls, content: bytes) -> Self:
        return cls(digest=content_digest(content), byte_length=len(content))

    def verify(self, content: bytes) -> None:
        if len(content) != self.byte_length or content_digest(content) != self.digest:
            raise ContentMismatchError("bytes do not match the captured content reference")


class OriginReference(ContractModel):
    """Pure binding to captured evidence (PR body, commit message, docstring, etc.)."""

    source_entity_id: NonBlank
    field: NonBlank
    source_version: NonBlank


class TextDocument(ContractModel):
    key: SourceKey
    title: str = ""
    kind: NonBlank = "text"
    origin: OriginReference | None = None

    @property
    def document_id(self) -> str:
        return self.key.identifier("document")


class DocumentRevision(ContractModel):
    """One immutable captured observation, including its document metadata.

    The same logical document/content captured later is another observation.
    Re-delivery of the exact observation retains its ID; a source must replay
    captured timestamps instead of assigning a new clock on retries.
    """

    document: TextDocument
    content: ContentReference
    timing: RevisionTiming
    media_type: NonBlank = "text/plain"
    encoding: NonBlank = "utf-8"
    native_revision: NonBlank | None = None
    evidence_ids: tuple[NonBlank, ...] = ()
    supersedes_revision_id: NonBlank | None = None

    @field_validator("evidence_ids")
    @classmethod
    def canonical_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @property
    def revision_id(self) -> str:
        return contract_id("revision", json_fingerprint(self.model_dump(mode="json")))


class DocumentCollection(ContractModel):
    """Explicit membership, never document identity ownership or authorization."""

    key: SourceKey
    document_ids: tuple[NonBlank, ...] = ()

    @field_validator("document_ids")
    @classmethod
    def canonical_membership(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @property
    def collection_id(self) -> str:
        return self.key.identifier("collection")


class SourceSpan(ContractModel):
    """A half-open byte span into one immutable revision's original content.

    Multiple spans/source maps for transformed text are a parser responsibility;
    this primitive never guesses offsets from decoded or normalized text.
    """

    revision_id: NonBlank
    content: ContentReference
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.start > self.end or self.end > self.content.byte_length:
            raise ValueError("span must satisfy 0 <= start <= end <= content byte length")
        return self

    def extract(self, original: bytes) -> bytes:
        self.content.verify(original)
        return original[self.start : self.end]


class ChunkContent(ContractModel):
    """Reusable chunk bytes/config identity; no occurrence or access ownership."""

    content: ContentReference
    chunker: ArtifactSpec

    @property
    def chunk_id(self) -> str:
        return contract_id("chunk", self.content.digest, self.chunker.fingerprint)


class ChunkOccurrence(ContractModel):
    """One revision-specific placement; ordinal alone never defines identity."""

    chunk: ChunkContent
    span: SourceSpan

    @property
    def occurrence_id(self) -> str:
        return contract_id(
            "occurrence",
            self.chunk.chunk_id,
            self.span.revision_id,
            self.span.content.digest,
            str(self.span.start),
            str(self.span.end),
        )


class DocumentLimits(ContractModel):
    max_revisions: StrictInt = Field(default=128, ge=1)
    max_content_bytes: StrictInt = Field(default=2 * 1024 * 1024, ge=1)


class DocumentBatch(ContractModel):
    """Bounded source page. Gaps/continuation distinguish incomplete from empty.

    Byte accounting conservatively sums referenced bytes, including duplicates;
    this bounds page content, not all source I/O or decoded/parse memory.
    """

    revisions: tuple[DocumentRevision, ...] = ()
    limits: DocumentLimits = Field(default_factory=DocumentLimits)
    continuation: NonBlank | None = None
    gaps: tuple[CoverageGap, ...] = ()

    @model_validator(mode="after")
    def bounded_unique_page(self) -> Self:
        if len(self.revisions) > self.limits.max_revisions:
            raise DocumentLimitError("document page exceeds max_revisions")
        if sum(revision.content.byte_length for revision in self.revisions) > (
            self.limits.max_content_bytes
        ):
            raise DocumentLimitError("document page exceeds max_content_bytes")
        identities = [revision.revision_id for revision in self.revisions]
        if len(set(identities)) != len(identities):
            raise ValueError("document page contains duplicate revision identities")
        return self
