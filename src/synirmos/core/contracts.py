"""Small versioned value primitives for the document-first contracts.

No runtime resources or implementation packages belong here. These contracts
are additive: legacy repository IDs and envelopes retain their existing rules.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import ConfigDict, JsonValue, StringConstraints, TypeAdapter, field_validator

from .ids import stable_id
from .models import FrozenModel

NonBlank = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
SHA256 = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
_JSON_VALUE = TypeAdapter(JsonValue)


class ContractModel(FrozenModel):
    """Versioned, extra-forbidding values; containers use immutable tuples."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)
    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer version, not a coerced value")
        return value


def content_digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def json_fingerprint(value: JsonValue) -> str:
    """Canonical JSON identity; NaN/infinity and non-JSON values fail explicitly."""

    validated = _JSON_VALUE.validate_python(value, strict=True)
    encoded = json.dumps(
        validated, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    return content_digest(encoded)


def contract_id(kind: str, *parts: str) -> str:
    """Versioned framed identity, independent of incidental run/collection IDs."""

    if not parts or any(not isinstance(part, str) or not part.strip() for part in parts):
        raise ValueError("identity parts must be nonblank strings")
    return stable_id(kind, "synirmos-contracts-v1", *parts, size=64)


class SourceKey(ContractModel):
    """Caller-qualified source instance plus opaque, case-sensitive native key.

    Instances must be stable, credential-free identities, not display names.
    Key text is preserved exactly; transport-specific normalization is not core
    policy. The same key can qualify documents or collections without aliasing.
    """

    source_instance: NonBlank
    native_key: NonBlank

    def identifier(self, kind: str) -> str:
        return contract_id(kind, self.source_instance, self.native_key)


class ArtifactSpec(ContractModel):
    """Exact implementation/config identity; the caller retains its config manifest."""

    implementation: NonBlank
    implementation_version: NonBlank
    config_fingerprint: SHA256

    @property
    def fingerprint(self) -> str:
        return json_fingerprint(self.model_dump(mode="json"))
