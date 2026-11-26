"""Executable checks of the initial platform seam, without live provider APIs."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from synirmos.core.budgets import BudgetLedger
from synirmos.core.models import Budgets
from synirmos.platform_integrations.gitlab import GitLabIntegration
from synirmos.platform_integrations.interfaces import (
    EvidenceFetcher,
    GitHostingPlatform,
    PayloadNormalizer,
    PlatformIntegration,
)
from synirmos.platform_integrations.jira import JiraIntegration
from synirmos.platform_integrations.models import (
    CollectionRequest,
    EvidencePage,
    ExternalRef,
    PlatformBatch,
    PlatformCapabilities,
    PlatformInstance,
    RepositoryBinding,
    ResourceKind,
)


def reference(provider="github", base_url="https://github.com", scope="acme/project", **kwargs):
    return ExternalRef(
        platform=PlatformInstance(provider=provider, base_url=base_url),
        scope=scope,
        kind=kwargs.get("kind", ResourceKind.WORK_ITEM),
        native_id=kwargs.get("native_id", "42"),
    )


def test_native_identity_is_independent_of_repository_or_branch():
    github = reference()
    assert github != reference("gitlab", "https://gitlab.example")
    assert github != reference(base_url="https://github.internal")
    assert github != reference(scope="other/project")
    assert github != reference(kind=ResourceKind.CHANGE_REQUEST)
    jira = reference("jira", "https://issues.example", "ENG", native_id="ENG-42")
    assert jira.native_id == "ENG-42"
    assert "repository_id" not in type(jira).model_fields


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@github.com",
        "https://github.com?token=secret",
        "https://github.com#token",
        "file:///somewhere",
    ],
)
def test_platform_identity_cannot_embed_credentials_or_non_http_urls(url):
    with pytest.raises(ValidationError):
        reference(base_url=url)


def test_self_hosted_instances_can_have_a_deployment_prefix():
    ref = reference("gitlab", "https://git.example/deploy/gitlab")
    assert str(ref.platform.base_url) == "https://git.example/deploy/gitlab"


def test_repository_binding_is_an_explicit_project_association():
    project = reference(kind=ResourceKind.PROJECT, native_id="project-17")
    binding = RepositoryBinding(project=project, repository_id="repo:logical-id")
    assert binding.project == project
    with pytest.raises(ValidationError, match="project reference"):
        RepositoryBinding(project=reference(), repository_id="repo:logical-id")


@pytest.mark.parametrize("size", [0, 101])
def test_page_requests_are_bounded(size):
    with pytest.raises(ValidationError):
        CollectionRequest(subject=reference(), collection=ResourceKind.COMMENT, page_size=size)


def test_fetching_and_normalization_are_separate_structural_ports():
    request = CollectionRequest(subject=reference(), collection=ResourceKind.COMMENT)
    page = EvidencePage(
        evidence_id="evidence:one",
        request=request,
        source_url="https://github.com/acme/project",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))),
        status_code=200,
        content_type="application/json",
        payload=b"[]",
        next_cursor="opaque",
    )
    assert page.observed_at.utcoffset() == timedelta(0)
    with pytest.raises(ValidationError):
        page.model_copy().observed_at = datetime.now(UTC)

    class FakeFetcher:
        def fetch_page(self, request, *, ledger):
            return page

    class FakeNormalizer:
        def normalize(self, page):
            assert json.loads(page.payload) == []
            return PlatformBatch(evidence_ids=(page.evidence_id,))

    class FakeGitHost:
        instance = request.subject.platform
        capabilities = PlatformCapabilities(collections=frozenset({ResourceKind.COMMENT}))
        fetcher = FakeFetcher()
        normalizer = FakeNormalizer()

        def resolve_repository(self, project, *, ledger):
            return RepositoryBinding(project=project, repository_id="repo:logical-id")

    host = FakeGitHost()
    assert isinstance(host, PlatformIntegration)
    assert isinstance(host, GitHostingPlatform)
    assert isinstance(host.fetcher, EvidenceFetcher)
    assert isinstance(host.normalizer, PayloadNormalizer)
    ledger = BudgetLedger(Budgets())
    fetched = host.fetcher.fetch_page(request, ledger=ledger)
    normalized = host.normalizer.normalize(fetched)
    assert normalized.evidence_ids == (page.evidence_id,)
    project = reference(kind=ResourceKind.PROJECT)
    assert host.resolve_repository(project, ledger=ledger).project == project
    assert ledger.api_requests == 0


@pytest.mark.parametrize("placeholder", [GitLabIntegration, JiraIntegration])
def test_future_adapters_fail_explicitly_instead_of_appearing_to_succeed(placeholder):
    with pytest.raises(NotImplementedError):
        placeholder()
