"""Candidate-producing extraction capability, with no canonical graph writer."""

from typing import Protocol, runtime_checkable

from ..extraction import ExtractionCandidates, ExtractionOperation


@runtime_checkable
class Extractor(Protocol):
    """Host verifies source bytes/access/schema fingerprints before model dispatch.

    Runtime owns actual token/call budgets, consent, exposure receipts and retry
    cache. A successful retry reuses captured inputs/operation identity, retaining
    run lineage separately. Same operation/key with changed payload is a conflict
    to stage or reject, not permission to publish another canonical fact. Results
    are structurally grounded proposals; validation, resolution and approval are
    separate application policies. No direct graph write authority is supplied.
    """

    def propose(self, operation: ExtractionOperation, *, run_id: str) -> ExtractionCandidates: ...
