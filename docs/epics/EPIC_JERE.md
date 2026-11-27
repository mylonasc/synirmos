# EPIC: Agentic Joint Entity-and-Relation Extraction (JERE)

## 1. Goal

Add a LangChain-based **joint entity-and-relation extraction** (JERE) module
under `synirmos.processing.agentic`, starting with a basic provider at
`processing/agentic/basic_jere_provider.py`.

- The extractor is a **LangChain agent** (`BaseChatModel`, `langchain-core`
  only, no new dependencies) that proposes **entities and relations jointly**
  in a single proposal.
- The agent's only view of known state is a **`ParsingContext` handle**:
  a read-only, horizon-filtered, bounded accessor over other entities,
  relations, and — in a later stage — the already parsed graph.
- House rules carry over from `processing/enrichment.py`: explicit consent,
  bounded budgets, file-backed caching, complete provenance, structural
  grounding, and **abstain-never-invent** on failure.

Non-goals for this epic: changing the active pipeline/orchestration wiring,
multi-language parsing, graph-write mapping, and a second provider. Those
are staged explicitly below.

## 2. What shipped in this iteration (design v0)

New package `src/synirmos/processing/agentic/`:

| File | Responsibility |
| --- | --- |
| `agentic/__init__.py` | Re-exports; declares agentic as owner of agent plumbing |
| `agentic/common.py` | **Single owner** of consent gates, model checks, token estimates, JSON parsing, cache keys, file-backed `AgentCache` |
| `agentic/parsing_context.py` | `ParsingContext` protocol (read-only, bounded, horizon-filtered) + `InMemoryParsingContext` for tests/offline |
| `agentic/jere_models.py` | `JereProposal` / entity / relation schemas, `JereEntityKind`, `JereRelationKind`, `link_relation_for` mapping onto the shared link vocabulary |
| `agentic/basic_jere_provider.py` | `BasicJereProvider`: bounded tool loop over a `ParsingContext`, grounding, cache, budgets, `AnalysisResult(kind="jere")` envelopes, `Labeler`/`RelationshipResolver` adapters |

Consolidation (no behavior change, full suite green):

- `processing/enrichment.py` now **imports from `agentic.common`** and keeps
  backward-compatible aliases (`EnrichmentError`, `EnrichmentCache`, …).
  Cache-key bytes and error messages are unchanged, so existing caches and
  all 352 tests keep passing. README/example/worker imports are untouched.

Tests: `tests/test_jere_basic.py` (acceptance, cache, tool round-trip,
empty-subject fast path, grounding rejection, budget exhaustion, adapters,
context accessors).

## 3. Core design

### 3.1 ParsingContext (the handle)

```python
class ParsingContext(Protocol):
    subject_id / subject_text / info_horizon  # decision under analysis
    list_entities(limit) / search_entities(query, limit) / get_entity(id)
    list_relations(entity_id?, limit) / neighbors(entity_id, relation?)
    snapshot_digest()  # identity set hash for cache keys
```

- **Read-only by construction**: agents propose; they never mutate state.
- **Horizon-filtered by the implementation**: only `info_horizon <=`
  decision-horizon state is visible (enforced in constructors, e.g. the
  future graph-backed context filters `GraphSink` reads via `*_as_of`).
- **Bounded everywhere**: every accessor takes a `limit`; prompts and
  observations are truncated (`JERE_MAX_CONTEXT_CHARS`,
  `JERE_MAX_OBSERVATION_CHARS`).

### 3.2 Agent loop (`BasicJereProvider.extract`)

```text
subject + context digest → cache lookup (hit: return, no budget spent)
  → empty subject? abstain deterministically (no LLM call)
  → per attempt (settings.max_attempts):
       build history [system, subject + entity/relation snapshot + schema]
       loop (max_tool_steps + 1 model calls):
         reserve_llm → invoke → parse JSON
           tool_call? → dispatch against context (bounded, errors become
                        observations, malformed calls are retried) → continue
           final JSON? → validate JereProposal + grounding → accept/abstain
           invalid? → feedback message → retry
  → exhausted? abstain with reason (never cached)
```

- **Tools** (prompt-described, provider-dispatched, no framework needed):
  `search_entities`, `get_entity`, `list_relations`, `neighbors`.
- **Grounding**: relation endpoints must be declared entity keys, observed
  entity IDs, or the subject itself; entity/relation counts are capped
  (32/64). Failures are retried, then abstained.
- **Identity**: new entities get deterministic `stable_id("jere-entity", …)`
  IDs via the injected `IdFactory`; repository scoping stays identical to
  every other adapter.
- **Envelope**: `AnalysisResult(kind="jere", method="jere-basic")` with full
  `Provenance` (model, prompt/schema versions, estimated/actual tokens),
  `tool_steps`, `context_hash`, cached flag, and reason strings.
- **Protocols**: `label()` / `resolve()` adapt `extract()` to the existing
  `Labeler` / `RelationshipResolver` protocols (context dict carries
  `parsing_context` + `evidence`), so future orchestration wiring needs no
  provider changes.

### 3.3 Why `langchain-core` only

The loop is a small explicit ReAct over `BaseChatModel.invoke`, testable
with `GenericFakeChatModel`. No `langchain`/`langgraph` dependency is
added; if we later adopt `create_agent`, only `_run_agent` changes — the
schemas, context, grounding, cache, and envelope stay.

## 4. Staged implementation plan

### Stage 1 — Prompt/version hardening (next)

- Extract prompt builders into `agentic/prompts.py` (pure functions,
  `prompt_version`-parameterized, golden-tested).
- Add `JereSettings` (max entities/relations, observation chars, tool
  steps) to `core/models.py` + config plumbing; keep provider defaults
  identical.
- Acceptance: prompt goldens for v1; settings round-trip via TOML.

### Stage 2 — Richer context tools

- Add tools: `get_entity_details` (spans/sections/symbols),
  `text_search` over subject-adjacent content, `candidate_relations`.
- Tool specs as data (`TOOL_SPECS` with JSON schemas) shared by prompt
  rendering and dispatch validation.
- Acceptance: fake-model tests per tool; unknown/malformed-arg cases.

### Stage 3 — Finish the consolidation (agentic owns all agent code)

- Move `build_chat_model` provider logic behind an `agentic/models.py`
  factory; `enrichment.build_chat_model` becomes a thin wrapper.
- Unify `Enricher._envelope` / `BasicJereProvider._envelope` via a common
  envelope helper in `agentic/common.py`.
- Acceptance: zero duplicated cache/envelope/parse logic (`grep`);
  architecture test extended to assert `enrichment` imports agent
  plumbing only from `processing.agentic`.

### Stage 4 — Graph-backed ParsingContext

- `GraphParsingContext`: read-only adapter over `GraphSink` current +
  `*_as_of(horizon)` projections (entities, relations, neighbors).
- Horizon enforcement moves into the implementation (filter by
  `valid_from`/`info_horizon`); `InMemoryParsingContext` stays for tests.
- Acceptance: horizon tests (future state invisible), parity test
  in-memory vs graph-backed on a fixture graph.

### Stage 5 — Evaluation harness

- `score_jere` (entity/relation precision/recall/F1, mirroring
  `linking.score_links`) + golden extraction fixtures.
- Acceptance: deterministic scores; regression goldens in CI.

### Stage 6 — Framework wiring (needs wider refactoring — deferred)

- Orchestration stage calling the provider with a graph-backed context;
  journal/replay of `kind="jere"` results; worker job support.
- Map resolved JERE entities/relations to `EntityWrite` /
  `RelationshipWrite` via `storage` mappings (not from processing).
- Acceptance: end-to-end replay test; budget/resume behavior preserved.

## 5. Open questions (for iteration)

1. Relation vocabulary: keep folding `DEFINES`/`PART_OF` into
   `RELATED_TO`, or extend the neutral link vocabulary?
2. Entity identity for `FILE`/`SYMBOL` kinds: reuse canonical
   `IdFactory.file`/symbol IDs instead of `jere-entity` IDs?
3. Tool-calling models: rely on JSON-in-text (current, fake-testable) or
   adopt `bind_tools` when available, with JSON fallback?
4. Second provider: a stricter/cheaper variant, or a reviewer-critic over
   the basic provider's proposals?

## 6. Iteration hooks

- The seams to iterate on are `ParsingContext` implementations, prompt
  versions, tool sets, and the relation vocabulary — all additive.
- `extract()`'s signature is stable; framework wiring (Stage 6) can land
  without touching the provider core.
