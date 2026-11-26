"""Small read-only ports for transport, normalization, and platform composition.

Constructors inject HTTP, credentials, evidence storage, and clocks. Only the
fetcher and repository lookup may use I/O; normalizers must be pure/offline.
No port owns a checkout, Git branch, worktree, or graph writer.
"""

from typing import Protocol, runtime_checkable

from ..core.budgets import BudgetLedger
from .models import (
    CollectionRequest,
    EvidencePage,
    ExternalRef,
    PlatformBatch,
    PlatformCapabilities,
    PlatformInstance,
    RepositoryBinding,
)


@runtime_checkable
class EvidenceFetcher(Protocol):
    def fetch_page(self, request: CollectionRequest, *, ledger: BudgetLedger) -> EvidencePage:
        """Capture one response, charging every network attempt including retries."""
        ...


@runtime_checkable
class PayloadNormalizer(Protocol):
    def normalize(self, page: EvidencePage) -> PlatformBatch:
        """Normalize only supplied evidence; never use network, clock, or repository I/O."""
        ...


@runtime_checkable
class PlatformIntegration(Protocol):
    @property
    def instance(self) -> PlatformInstance: ...

    @property
    def capabilities(self) -> PlatformCapabilities: ...

    @property
    def fetcher(self) -> EvidenceFetcher: ...

    @property
    def normalizer(self) -> PayloadNormalizer: ...


@runtime_checkable
class GitHostingPlatform(PlatformIntegration, Protocol):
    def resolve_repository(
        self, project: ExternalRef, *, ledger: BudgetLedger
    ) -> RepositoryBinding:
        """Resolve an explicit project association, without opening or mutating Git."""
        ...
