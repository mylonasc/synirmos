# D0: extraction, evidence and assertion contracts

These additive `synirmos.core.extraction` values complete the neutral extraction
boundary of #11; they do not implement JERE, ontology compilation, a resolver,
reviewer workflow, or canonical graph publication. Those remain D4/#15 and
#3/#5/#6/#9. Existing analysis/result IDs and repository APIs are not changed.

## Inputs and trust

`ExtractionSubject` binds an immutable revision, original-content span, exact
decoded text, optional chunk occurrence, and matching source/time visibility.
The span must refer to that revision/content, and the subject must pass its
operation's effective scope. `verify(original_bytes)` checks content integrity
and exact decoding. A syntactically valid subject is not a proof that the host
verified bytes/access: runtime must do so before model dispatch and revalidate
cached proposals at publication boundaries.

The v1 subject is contiguous original text. D2's adapters/source maps must handle
normalized/transformed input explicitly rather than assign guessed original
offsets. `EvidenceSpan` represents a **claimed** nonempty exact original quote;
its verification checks the full content digest/length, source bytes and declared
encoding. Merely constructing/deserializing the value is not verification.

`ExtractionProfile` pins schema fingerprint/optional ontology release plus exact
task, model, prompt, tools and limit configurations. It contains no callable,
model handle, credentials or implicit provider discovery. The application loads
the approved schema and verifies its fingerprint separately. Logical candidate/
evidence caps are checked by proposal values; actual token/call spending,
consent, model output limits and runtime cancellation belong to the dispatcher.

## Retry-safe operation identity

An `ExtractionOperation` requires a scope-visible subject and a profile whose
ontology release matches the selected pin (including the no-ontology case).
Its identity includes:

- Full immutable subject values and identity.
- Full extraction profile/configuration fingerprint.
- Exact ordered host-recorded context/exposure fingerprint, including visible
  values, source/access/time/pin/policy identity and query/tool behavior.
- An explicit `analysis_version` for a deliberate new analysis.

Incidental `run_id` and physical read counters do not define that identity.
Warm/cold cache differences cannot manufacture another operation; changed
descriptions, permissions, schema/model/prompt/tools, visible context or declared
analysis version do. Preserve captured inputs, original grants/receipts and
operation keys on replay. Store run lineage separately. Same operation/local
key with a changed proposal payload is a conflict to retain/review or reject,
not an idempotence success or automatic new canonical fact.

## Candidates, mentions and grounding

`EntityCandidate` has an operation-local key, name, arbitrary full class ID and
nonempty original evidence. Optional canonical reuse must occur in the host's
actual `ExposureSet`; a hidden/unretrieved entity is not grounded just because
it exists in the database. A later successful direct lookup may extend that set.
Names and embeddings alone never assign canonical identities.

`RelationCandidate` preserves the full predicate ID and polarity, references
declared entity-candidate local keys, and has its own nonempty relation evidence.
No predicate is folded into `RELATED_TO`. Candidate and mention IDs are derived
from operation/local-key/exact-span identity, not incidental runs. Structural
checks reject duplicate local keys, operation mismatches, undeclared endpoints,
evidence outside the input subject and candidate/evidence-count overruns.

In this proposal path, new candidate evidence must lie within the contiguous
subject and use its exact encoding. Multi-source publication supports are
separate assertion records, not permission for a model to cite unexposed text.
`ExtractionCandidates.status` can only be `proposed`; a model reply cannot approve
it. Empty legitimate results are allowed; dispatcher failures must be explicit
errors/gaps rather than fabricated successful empty extraction. Raw failed
attempts need durable audit capture before validation, as part of D4/D5.

These checks establish structural consistency, not factual truth, quote
authentication, closed-vocabulary admissibility or canonical resolution. #5
validates approved schema/grounding/evidence and persists staging; #6 controls
resolution/publication. Native domain/range **entailment** is not closed-world
validation, and native scoped equality is not physical merge approval.

## Assertions and review

`AssertionSupport` distinguishes a canonical statement (subject/predicate/object/
polarity) from individual supports. The statement ID excludes source support;
the assertion ID binds operation/profile, canonicalized evidence, source-valid
interval and explicit supersession. Different independent supports remain
distinct; positive and negative statements do not overwrite one another.

Run lineage, observed/knowledge metadata and review transitions do not change
that support's logical ID. Record those changes as new immutable versions; never
mutate history. Review-free supports are proposed. A trusted `ReviewDecision`
records actor, decision, time and rationale, and cannot be known before its
decision time. Deserialization of an actor/decision ID is not review authority;
the trusted application still authenticates the actor, validates destinations
and enforces write/approval policy. No automatic canonical writer is supplied to
the `Extractor` port, whose only output is unapproved candidates.

## Verification and migration

`test_knowledge_contracts.py` covers exact exposures, changed-value cache
invalidation, direct lookups, hidden reuse, cumulative budgets, lifetime cleanup,
subject/quote integrity, retry/run/telemetry separation, full ontology IDs,
candidate structure, contradictory supports, review timing and JSON round-trips.
Core import tripwires include all new modules/ports in a fresh process.

No persisted legacy envelope/hash is reinterpreted and no new runtime dependency
is added. The JSON-property adapter also passes imports, schema and round-trip
checks with Pydantic 2.8.2, the declared minimum series. D1–D5 must adopt these
contracts incrementally with compatibility adapters; their conformance and real
backend/model behavior are not implied by pure value tests.
