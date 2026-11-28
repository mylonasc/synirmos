"""Document-source and captured-content read ports, not repository specializations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..documents import ContentReference, DocumentBatch, DocumentLimits


@runtime_checkable
class DocumentSource(Protocol):
    """Capture an explicit selection; empty keys mean none, never an implicit crawl.

    Adapters bind continuation to the same source/selection/limits and reject
    changed or invalid cursors. The source captures bytes once, preserves capture
    timestamps on retry, and returns a page within the caller's limits. This port
    grants no parsing, ontology or graph-write authority.
    """

    @property
    def source_instance(self) -> str: ...

    def capture(
        self,
        *,
        native_keys: tuple[str, ...],
        limits: DocumentLimits,
        continuation: str | None = None,
    ) -> DocumentBatch: ...


@runtime_checkable
class ContentReader(Protocol):
    """Read already captured bytes, never re-fetch the original source.

    Implementations enforce access independently of the content digest, reject a
    negative byte limit, raise DocumentLimitError before returning oversized
    content, and verify the reference. Missing/denied content raises explicitly;
    neither is represented by empty bytes. The caller owns the reader lifetime.
    """

    def read(self, reference: ContentReference, *, max_bytes: int) -> bytes: ...
