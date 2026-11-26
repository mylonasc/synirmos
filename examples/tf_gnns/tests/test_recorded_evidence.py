"""Example-only regression checks against the captured tf_gnns evidence."""

from pathlib import Path

from synirmos.core.budgets import BudgetLedger
from synirmos.core.config import load_config
from synirmos.core.ids import IdFactory
from synirmos.core.models import Budgets
from synirmos.sources.github import EvidenceCache, GitHubDiscoverer


def test_recorded_github_evidence_replays_offline():
    root = Path(__file__).parent
    config = load_config(root.parent / "config.toml")
    discovery = GitHubDiscoverer(
        config.repository,
        config.github,
        cache=EvidenceCache(root / "data", offline=True),
        ledger=BudgetLedger(Budgets()),
    ).run()

    assert [item.number for item in discovery.work_items] == [10, 11, 12]
    assert all(item.kind == "pull_request" for item in discovery.work_items)
    assert {pull.merge_commit_sha for pull in discovery.pull_requests} == {
        "f787d50f5bb8fc27b2ed0a0d3a0aa0a729e91eeb",
        "3f7ea9879666c5b04fb5dfec8bab926a26079e42",
        "6324b89cd52dceb9963e44cb5c3e1716dd5a1698",
    }
    assert [gap.code for gap in discovery.gaps] == ["github-historical-revisions-unavailable"]
    assert discovery.counters["api_requests"] == 0
    assert len(discovery.to_events(IdFactory(config.repository.url))) == 31
