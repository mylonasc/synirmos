"""Agentic processing: LangChain-backed analyzers and their shared plumbing.

Concrete agent implementations live here (for example the basic JERE
provider). Scattered LangChain helpers now delegate to
:mod:`synirmos.processing.agentic.common` so caching, consent gates, model
checks, and token estimates have a single owner.
"""

from .basic_jere_provider import BasicJereProvider
from .common import (
    AgentCache,
    AgentConsentError,
    AgentError,
    AgentModelError,
    cache_key,
    check_model,
    estimate_tokens,
    parse_json_object,
    require_consent,
    strip_fences,
)
from .jere_models import (
    JERE_METHOD,
    JERE_METHOD_VERSION,
    JERE_SCHEMA_VERSION,
    JereEntityKind,
    JereEntityProposal,
    JereProposal,
    JereRelationKind,
    JereRelationProposal,
    link_relation_for,
)
from .parsing_context import EntityView, InMemoryParsingContext, ParsingContext, RelationView

__all__ = [
    "AgentCache",
    "AgentConsentError",
    "AgentError",
    "AgentModelError",
    "BasicJereProvider",
    "EntityView",
    "InMemoryParsingContext",
    "JERE_METHOD",
    "JERE_METHOD_VERSION",
    "JERE_SCHEMA_VERSION",
    "JereEntityKind",
    "JereEntityProposal",
    "JereProposal",
    "JereRelationKind",
    "JereRelationProposal",
    "ParsingContext",
    "RelationView",
    "cache_key",
    "check_model",
    "estimate_tokens",
    "link_relation_for",
    "parse_json_object",
    "require_consent",
    "strip_fences",
]
