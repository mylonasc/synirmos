"""Narrow write capability; neither a read scope nor a model tool grants it."""

from typing import Protocol, runtime_checkable

from ..contracts import ContractModel, NonBlank
from ..graph import GraphWriteBatch


class WriteReceipt(ContractModel):
    """Published intent keys include exact duplicates; conflicts must raise."""

    operation_id: NonBlank
    version_keys: tuple[NonBlank, ...]


@runtime_checkable
class GraphWriter(Protocol):
    """Borrowed single-writer capability. No ownership of an external journal.

    The adapter enforces caller batch limits, profile/policy and reserved-key
    checks, preserves per-record source times and returns only after the native
    transaction publishes. Same key/different payload is an error, not a skip.
    A failed batch must not expose a partial history/current projection on a
    backend advertising atomic publication. Unsupported backends fail explicitly.
    """

    def write(self, batch: GraphWriteBatch) -> WriteReceipt: ...
