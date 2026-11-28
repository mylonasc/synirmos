"""Immutable budget negotiation and explicit physical-work capability boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, StrictInt, field_validator

from .contracts import ContractModel
from .models import ensure_utc


class UnsupportedReadError(RuntimeError):
    """A requested guarantee cannot be enforced; never silently weaken it."""


class ReadLimitError(ValueError):
    """Measured work or returned payload exceeds the negotiated budget."""

    def __init__(self, message: str, *, usage: ReadUsage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


class ReadLimits(ContractModel):
    """Per-session ceilings, shared across tools/providers by the runtime ledger.

    Zero permits no work/output. None on physical limits means no requested bound,
    not a claim that work is free. Deadlines are absolute UTC; their enforcement
    requires an advertised capability, possibly backed by process isolation.
    """

    max_results: StrictInt = Field(default=100, ge=0)
    max_output_bytes: StrictInt = Field(default=64 * 1024, ge=0)
    max_candidates: StrictInt | None = Field(default=None, ge=0)
    max_read_bytes: StrictInt | None = Field(default=None, ge=0)
    max_memory_bytes: StrictInt | None = Field(default=None, ge=0)
    deadline: datetime | None = None

    @field_validator("deadline")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    def intersect(self, other: ReadLimits) -> Self:
        values = {}
        for name in type(self).model_fields:
            if name == "schema_version":
                continue
            a, b = getattr(self, name), getattr(other, name)
            values[name] = b if a is None else a if b is None else min(a, b)
        return type(self)(**values)


class ReadCapabilities(ContractModel):
    """Truthful guarantees for this exact reader/worker, not backend aspirations."""

    candidate_limit: bool = False
    read_byte_limit: bool = False
    memory_limit: bool = False
    deadline: bool = False

    def require(self, limits: ReadLimits) -> None:
        for limit, capability in (
            ("max_candidates", "candidate_limit"),
            ("max_read_bytes", "read_byte_limit"),
            ("max_memory_bytes", "memory_limit"),
            ("deadline", "deadline"),
        ):
            if getattr(limits, limit) is not None and not getattr(self, capability):
                raise UnsupportedReadError(f"reader cannot enforce {limit}")


class ReadUsage(ContractModel):
    """Cumulative measured usage; unknown physical work is never reported as zero."""

    results: StrictInt = Field(default=0, ge=0)
    output_bytes: StrictInt = Field(default=0, ge=0)
    candidates: StrictInt | None = Field(default=None, ge=0)
    read_bytes: StrictInt | None = Field(default=None, ge=0)

    def add(self, other: ReadUsage) -> Self:
        return type(self)(
            results=self.results + other.results,
            output_bytes=self.output_bytes + other.output_bytes,
            candidates=(
                None
                if self.candidates is None or other.candidates is None
                else self.candidates + other.candidates
            ),
            read_bytes=(
                None
                if self.read_bytes is None or other.read_bytes is None
                else self.read_bytes + other.read_bytes
            ),
        )

    def check(self, limits: ReadLimits) -> None:
        for usage, limit in (
            ("results", "max_results"),
            ("output_bytes", "max_output_bytes"),
            ("candidates", "max_candidates"),
            ("read_bytes", "max_read_bytes"),
        ):
            measured, ceiling = getattr(self, usage), getattr(limits, limit)
            if ceiling is not None:
                if measured is None:
                    raise UnsupportedReadError(f"cannot verify unknown {usage} usage")
                if measured > ceiling:
                    raise ReadLimitError(f"{usage} exceeds {limit}", usage=self)
