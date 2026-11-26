"""Synirmos: evidence-backed temporal repository-history analysis.

The package separates source evidence, normalized events, derived analysis, and
GestaltDB persistence. Importing the package does not require model credentials
or an open database.
"""

from .core.config import RuntimeConfig, load_config
from .core.events import EventKind, IngestEvent
from .core.models import (
    Budgets,
    ContentSettings,
    CoverageGap,
    CoverageStatus,
    GitHubSettings,
    GitSettings,
    GraphSettings,
    LabelingSettings,
    LinkingSettings,
    OrchestrationSettings,
    RepositorySpec,
    TimeWindow,
)

__all__ = [
    "Budgets",
    "ContentSettings",
    "CoverageGap",
    "CoverageStatus",
    "EventKind",
    "GitHubSettings",
    "GitSettings",
    "GraphSettings",
    "LabelingSettings",
    "LinkingSettings",
    "IngestEvent",
    "OrchestrationSettings",
    "RepositorySpec",
    "RuntimeConfig",
    "TimeWindow",
    "load_config",
]
