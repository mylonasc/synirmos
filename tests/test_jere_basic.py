"""Basic JERE provider over an in-memory ParsingContext.

No network and no credentials: every model is an in-process
``GenericFakeChatModel`` with scripted replies, so tool rounds, retries,
budgets, caching, and grounding are fully reproducible.
"""

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from synirmos.core.analysis import DecisionStatus
from synirmos.core.budgets import BudgetLedger
from synirmos.core.ids import IdFactory
from synirmos.core.models import Budgets, LLMSettings
from synirmos.processing.agentic import (
    AgentCache,
    AgentConsentError,
    BasicJereProvider,
    EntityView,
    InMemoryParsingContext,
    RelationView,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
IDS = IdFactory("https://github.com/o/r")


def fake_model(*contents: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=c) for c in contents]))


def cycling_model(*contents: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=itertools.cycle([AIMessage(content=c) for c in contents]))


def provider(
    chat_model, tmp_path, *, budgets: Budgets | None = None, **overrides
) -> tuple[BasicJereProvider, BudgetLedger]:
    settings_data = {"enabled": True, "privacy_consent": True}
    max_tool_steps = overrides.pop("max_tool_steps", 3)
    settings_data.update(overrides)
    settings = LLMSettings(**settings_data)
    ledger = BudgetLedger(budgets or Budgets())
    return (
        BasicJereProvider(
            chat_model,
            settings,
            ledger=ledger,
            cache=AgentCache(tmp_path / "jere-cache.json"),
            run_id="run-1",
            ids=IDS,
            max_tool_steps=max_tool_steps,
        ),
        ledger,
    )


def context(**overrides) -> InMemoryParsingContext:
    data: dict = {
        "subject_id": "snap:1",
        "subject_text": "Training fails on sparse graphs.",
        "info_horizon": NOW,
        "entities": (
            EntityView(
                entity_id="topic:sparse",
                kind="TOPIC",
                name="sparse-training",
                description="sparse graphs",
            ),
        ),
    }
    data.update(overrides)
    return InMemoryParsingContext(**data)


def valid_proposal() -> str:
    return json.dumps(
        {
            "entities": [
                {
                    "key": "e1",
                    "kind": "CONCEPT",
                    "name": "sparse training",
                    "confidence": 0.9,
                    "rationale": "Subject discusses sparse training.",
                    "evidence_quotes": ["sparse graphs"],
                }
            ],
            "relations": [
                {
                    "source": "e1",
                    "target": "topic:sparse",
                    "relation": "RELATED_TO",
                    "confidence": 0.7,
                    "rationale": "New concept refines the known topic.",
                }
            ],
            "abstained": False,
            "rationale": "Grounded in subject and context.",
        }
    )


def test_consent_is_required(tmp_path):
    with pytest.raises(AgentConsentError):
        provider(fake_model(valid_proposal()), tmp_path, enabled=False)


def test_single_shot_acceptance_is_grounded_cached_and_budgeted(tmp_path):
    the_provider, ledger = provider(fake_model(valid_proposal()), tmp_path)

    result = the_provider.extract(context=context())

    assert result.status is DecisionStatus.ACCEPTED
    assert result.kind == "jere"
    assert result.value["cached"] is False
    assert result.value["tool_steps"] == 0
    assert result.value["proposal"]["entities"][0]["entity_id"]
    assert result.value["proposal"]["relations"][0]["target_id"] == "topic:sparse"
    assert result.provenance.method == "jere-basic"
    assert result.provenance.schema_version == "1"
    assert result.provenance.info_horizon == NOW
    assert ledger.llm_requests == 1

    repeat = the_provider.extract(context=context())
    assert repeat.value["cached"] is True
    assert repeat.value["proposal"] == result.value["proposal"]
    assert the_provider.invocations == 1
    assert ledger.llm_requests == 1


def test_tool_round_trip_can_reference_observed_entities(tmp_path):
    tool_call = json.dumps(
        {"tool_call": {"name": "search_entities", "args": {"query": "sparse", "limit": 5}}}
    )
    final = json.dumps(
        {
            "entities": [],
            "relations": [
                {
                    "source": "snap:1",
                    "target": "topic:sparse",
                    "relation": "MENTIONS",
                    "confidence": 0.6,
                    "rationale": "Subject names the known topic.",
                }
            ],
            "abstained": False,
            "rationale": "Linked after a context lookup.",
        }
    )
    the_provider, _ = provider(fake_model(tool_call, final), tmp_path)

    result = the_provider.extract(context=context())

    assert result.status is DecisionStatus.ACCEPTED
    assert result.value["tool_steps"] == 1
    assert the_provider.invocations == 2


def test_empty_subject_abstains_without_spending_budget(tmp_path):
    the_provider, ledger = provider(fake_model(valid_proposal()), tmp_path)

    result = the_provider.extract(context=context(subject_text="   "))

    assert result.status is DecisionStatus.ABSTAINED
    assert the_provider.invocations == 0
    assert ledger.llm_requests == 0


def test_ungrounded_endpoints_abstain_without_caching(tmp_path):
    bad = json.dumps(
        {
            "entities": [],
            "relations": [
                {
                    "source": "snap:1",
                    "target": "topic:invented",
                    "relation": "MENTIONS",
                    "confidence": 0.9,
                    "rationale": "Invented target.",
                }
            ],
            "abstained": False,
            "rationale": "Bad.",
        }
    )
    the_provider, _ = provider(cycling_model(bad), tmp_path, max_attempts=1, max_tool_steps=0)

    first = the_provider.extract(context=context())
    second = the_provider.extract(context=context())

    assert first.status is DecisionStatus.ABSTAINED
    assert first.value["proposal"] is None
    assert "topic:invented" in (first.value.get("reason") or "")
    assert second.value["cached"] is False  # validation failures are not cached
    assert the_provider.invocations == 2


def test_budget_exhaustion_returns_an_explicit_envelope(tmp_path):
    the_provider, ledger = provider(
        cycling_model(valid_proposal()), tmp_path, budgets=Budgets(max_llm_requests=1)
    )
    first = the_provider.extract(context=context())
    second = the_provider.extract(
        context=context(subject_id="snap:2", subject_text="Dense graphs instead.")
    )

    assert first.status is DecisionStatus.ACCEPTED
    assert second.status is DecisionStatus.BUDGET_EXHAUSTED
    assert second.error
    assert ledger.exhausted.get("llm_requests")


def test_label_adapter_delegates_to_extract(tmp_path):
    the_provider, _ = provider(fake_model(valid_proposal()), tmp_path)
    parsing_context = context()

    (result,) = the_provider.label(text="ignored", context={"parsing_context": parsing_context})

    assert result.status is DecisionStatus.ACCEPTED
    assert result.subject_id == "snap:1"


def test_context_accessors_are_bounded_and_digestable():
    parsing_context = InMemoryParsingContext(
        subject_id="s",
        subject_text="t",
        info_horizon=NOW,
        entities=(
            EntityView(entity_id="a", kind="TOPIC", name="alpha"),
            EntityView(entity_id="b", kind="TOPIC", name="beta sparse"),
        ),
        relations=(RelationView(source_id="a", target_id="b", relation="RELATED_TO"),),
    )

    assert [entity.entity_id for entity in parsing_context.search_entities("sparse")] == ["b"]
    assert parsing_context.get_entity("missing") is None
    assert parsing_context.list_entities(limit=1)[0].entity_id == "a"
    assert parsing_context.neighbors("a") == ("b",)
    assert parsing_context.snapshot_digest() == parsing_context.snapshot_digest()
