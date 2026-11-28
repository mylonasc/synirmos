# D0: graph, scope and budget contracts

Part of #11; additive to the document contracts in `DOCUMENT_CONTRACTS.md`.
These are pure values and structural ports, **not** a storage implementation,
an authentication mechanism, or a replacement for GestaltDB.

## Trusted scope construction

Runtime authenticates a principal, resolves policy and collection/source
membership, chooses a verifiable native snapshot, then creates a `ScopeGrant`.
Never accept that grant or an effective `GraphScope` from an untrusted model.
Constructing/deserializing a value cannot establish its authority or authenticate
a claimed snapshot. No opaque ID is an access token.

`SnapshotPin` binds database/snapshot/provenance identity, independent application
read times, optional native commit horizon and ontology release, and graph-profile
identity. In-memory readers can pin immutable corpus identities without inventing
a repository or a real DB commit. Missing native capability must fail explicitly;
it does not authorize a current-state fallback. Runtime keeps actual handles
outside serializable values and worker-job payloads.

A `ScopeRequest` can only narrow a trusted grant:

- `None` selects all IDs already allowed by that grant. Empty tuples mean none.
- Collection/source/status sets intersect independently; no implicit global
  wildcard exists. The default request exposes approved records only, even if
  the trusted grant permits staged records for a reviewer.
- The request must use the trusted pin's exact application time selection.
  Tools cannot change database, horizon or ontology release. Runtime opens a new
  authorized session for a deliberately changed pin.
- Every limit intersects to the stricter ceiling/earlier deadline. Unknown or
  unrequested physical limits never erase an existing bound.

`Visibility` applies to one version's complete payload and evidence, not a union
of properties from different sources. Time eligibility, selected source,
membership overlap and approval must all pass. D3 must enforce these conditions
on entities, relationships, endpoints, evidence **before** ranking/top-k and must
select the correct historical version. `GraphScope.includes` only tests one
version's metadata; it does not choose a temporal winner or query a database.
Mixed-support entities need an explicitly safe projection, never unfiltered
property aggregation from an unauthorized support.

## Logical output limits versus physical work

`ReadLimits` distinguishes returned-record/output-byte caps from candidate/read-
byte/memory budgets and an absolute UTC deadline. Zero means no permitted work;
`None` on a physical dimension means no requested bound, not zero usage.
`ReadCapabilities.require()` rejects unsupported requested guarantees before
work begins. A reader must advertise only enforcement it actually supplies;
memory/hard-deadline guarantees may need an isolated worker, not an iterator.

`ReadUsage` adds cumulative result/byte counts; unknown physical counters remain
unknown when combined. Checking a bound against unknown usage fails explicitly.
It checks measured counts only, not memory/deadline enforcement. Adapters/workers
must actually enforce their advertised guarantees. Runtime shares the ledger
across tool calls/composed providers/attempts and persists it on failure/resume;
giving every tool another full allowance is not conformance.

The scope fingerprint includes every limit, pin, policy, principal and visible
selection. No token estimate or result fanout implies bounded physical work.

## Neutral records, profiles and writes

`EntityRecord` and `RelationshipRecord` retain exact logical/version IDs, reversible
predicate identities, properties, visibility and evidence references. Neutral
predicate strings accept qualified domain IDs/IRIs, not fixed JERE enums.
`Properties` stores canonical JSON internally and emits fresh JSON objects on
serialization/access. Nested dictionaries/lists cannot mutate validated records
or cached identities. Non-objects, non-string keys and nonfinite values reject.

`GraphProfile` describes vocabulary, identity/mapping versions, required/reserved
properties, indexes and capabilities. Set-valued declarations have deterministic
fingerprints; the descriptor does not compose conflicting profiles or perform
index DDL. D1 owns that validation, explicit migration plans and native reuse.

Neutral write values carry `VersionIntent` with mapper-issued stable version keys.
Corrections require a superseded version; assertions/retractions do not accept a
correction target. Native history still validates existence and publication.
Retractions retain an explicit audit payload; writers must not project them as
current assertions. Per-record source/time/evidence metadata is explicit, rather
than silently overridden by duplicate batch defaults.

`WriteContext` separates stable operation identity from incidental run lineage and
pins the mapping/profile/release. `GraphWriteBatch` rejects duplicate version keys
and bounds count and serialized batch bytes (including context/limit metadata).
This is not a hard bound on decoded memory or backend I/O. D1 checks trusted
write policy, reserved keys, profile compatibility and same-key/different-payload
conflicts; a read scope grants no write authority. The borrowed `GraphWriter`
port does not own resource lifetime or an external journal. LMDB adapters use
native transactions for history/current publication; replay bridges the separate
journal/database durability boundary.

## Context, exposure and session contracts

`ContextRequest` binds subject, exact effective scope, query filters and opaque
continuation. None/empty filters retain the same all-granted/none distinction.
Adapters must bind continuation to source/query/subject/scope/provider policy,
not accept it as independent authority. Actual providers/readers remain D3.

`ContextResult` requires whole, visible, unique versioned records. Every returned
relationship has both endpoints in the delivered entities; all referenced
evidence is also delivered and visible. Empty, truncated, denied, unsupported
and failed outcomes are distinct. Truncation requires continuation or a gap;
negative outcomes require explicit gaps and no records/cursor. These structural
checks do not select historical winners, authenticate provenance or sanitize
free-form messages. D3 must scope metadata/gaps/cursors as well as records before
model delivery; do not leak unauthorized IDs or values via diagnostics.

Logical accounting covers all returned entities/relationships/evidence, including
dependency records. Output bytes mean the canonical JSON record payload, zero
when no records exist; envelope/tool formatting and real token output need their
own caps in D4. Counts and payload bytes are calculated and checked, not accepted
as arbitrary provider estimates. `ReadLimitError` retains actual `ReadUsage` for
runtime failure/resume accounting; it is a runtime error so Pydantic validation
does not wrap it and discard those counters. Do not return a fresh allowance
after a failed call.

The trusted host records a `ContextExposure` **only after** delivering those
complete records. If formatting changes/omits values, construct a correspondingly
smaller result and recompute its receipt. Receipt construction/deserialization
does not prove delivery. Receipts bind complete record payload/version identities
and the result fingerprint, including request/policy/pin/provider, descriptions,
approval/time data and outcome. A direct lookup may extend exposure beyond an
initial listing, but existence in storage alone never grounds canonical reuse.

`ExposureSet` combines ordered receipts from the same effective scope and rejects
conflicting versions or same-version/different-payload records. Repeated calls
remain repeated budget charges; total usage is checked against the shared scope
limits. Tool-call order is preserved. Physical counters persist for accounting
but do not participate in context/extraction intent fingerprints: reading the
same pinned values through a warm cache must not create a new logical operation.
Logical limits/configuration remain fingerprinted. Runtime must preserve the
original operation/receipt artifacts on replay, rather than mint another scope
or analysis identity from remaining-budget counters.

`KnowledgeReader` is a borrowed, scope-bound read capability with no writer,
index repair or handle-opening methods. `ReadSessionFactory`/`ReadSession` specify
runtime ownership: enter once, reuse the reader across tools, close promptly on
success and exceptions, and make close idempotent. Reads after close and re-entry
of a closed session raise `ReadSessionClosedError`. Real implementations enforce
that lifecycle in D3; tests use explicit doubles, not a pretend backend. Empty/
in-memory `ContextProvider` implementations need no reader, while graph-backed
providers borrow a matching live reader. None owns authorization or an agent.

## Delivery boundary

Tests in `test_graph_contracts.py` and `test_knowledge_contracts.py` exercise
scope, budget, complete-result/exposure, serialization and session conformance
without storage/LLMs. See `EXTRACTION_CONTRACTS.md` for proposal/assertion values.
Actual providers/readers/writers belong to D1/D3, not this pure model layer.
