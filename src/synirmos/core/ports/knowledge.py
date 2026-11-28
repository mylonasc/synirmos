"""Borrowed knowledge/context capabilities and caller-owned read-session lifetime."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from ..context import ContextRequest, ContextResult
from ..graph import GraphScope
from ..limits import ReadCapabilities


class ReadSessionClosedError(RuntimeError):
    """A borrowed reader was used after its owning session closed."""


@runtime_checkable
class KnowledgeReader(Protocol):
    """No writer, handle opening, index repair, or lifetime ownership.

    Reject requests whose scope differs from this exact session. Negotiate
    physical guarantees before reading; enforce scope before ranking, select
    historical winners and filter endpoints/evidence consistently. Raise an
    explicit error after close or when a capability is unsupported. Overrun
    errors carry actual usage for runtime persistence, not a fresh allowance.
    """

    @property
    def scope(self) -> GraphScope: ...

    @property
    def capabilities(self) -> ReadCapabilities: ...

    def read(self, request: ContextRequest) -> ContextResult: ...


@runtime_checkable
class ReadSession(Protocol):
    """Runtime-owned bounded context. Enter once, reuse readers, close promptly.

    Close is idempotent and invalidates all borrowed readers on every exit path.
    Reader use after close and re-entering a closed session must raise
    ReadSessionClosedError. No session/reader may be serialized into worker jobs.
    """

    @property
    def scope(self) -> GraphScope: ...

    @property
    def reader(self) -> KnowledgeReader: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class ReadSessionFactory(Protocol):
    def open(self, scope: GraphScope) -> ReadSession: ...


@runtime_checkable
class ContextProvider(Protocol):
    """Selection policy, not a storage owner, agent, or authorization issuer.

    Empty/in-memory providers need no reader. A graph-backed provider borrows a
    live reader with the same effective scope and cannot broaden it. Runtime
    shares the usage ledger across providers/tools; results do not grant a new
    per-call budget. Return complete structured records, never partial IDs.
    """

    def select(
        self,
        request: ContextRequest,
        *,
        reader: KnowledgeReader | None = None,
    ) -> ContextResult: ...
