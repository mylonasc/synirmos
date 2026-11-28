"""Application time values, deliberately separate from database commit clocks."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import field_validator, model_validator

from .contracts import ContractModel, NonBlank
from .models import ensure_utc


class ValidInterval(ContractModel):
    """Half-open source-valid interval; an absent end is unbounded."""

    start: datetime
    end: datetime | None = None

    @field_validator("start", "end")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end is not None and self.end <= self.start:
            raise ValueError("valid interval end must follow start")
        return self

    def contains(self, instant: datetime) -> bool:
        instant = ensure_utc(instant)
        return self.start <= instant and (self.end is None or instant < self.end)


class RevisionTiming(ContractModel):
    """Validity, capture time, and earliest *justified* application knowledge.

    Ordinary capture uses ``info_horizon == observed_at``. Historical availability
    may precede capture only with explicit evidence, verified by the source
    adapter. Merely supplying evidence IDs does not establish their authenticity.
    Source validity is independent of both clocks; none is a DB commit timestamp.
    """

    valid: ValidInterval
    observed_at: datetime
    info_horizon: datetime
    availability_evidence_ids: tuple[NonBlank, ...] = ()

    @field_validator("observed_at", "info_horizon")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("availability_evidence_ids")
    @classmethod
    def canonical_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def justified_horizon(self) -> Self:
        if self.info_horizon > self.observed_at:
            raise ValueError("revision knowledge time cannot follow its observation")
        if self.info_horizon < self.observed_at and not self.availability_evidence_ids:
            raise ValueError("historical availability requires explicit evidence")
        return self


class ReadPoint(ContractModel):
    """Independent source-valid instant and inclusive application knowledge cutoff.

    A storage adapter must enforce both and separately bind a DB snapshot. This
    value is not authorization and does not select a database commit by itself.
    """

    valid_time: datetime
    info_horizon: datetime

    @field_validator("valid_time", "info_horizon")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    def includes(self, timing: RevisionTiming) -> bool:
        return timing.info_horizon <= self.info_horizon and timing.valid.contains(self.valid_time)
