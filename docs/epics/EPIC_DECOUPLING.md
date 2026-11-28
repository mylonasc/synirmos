# EPIC: Decouple sources, graph storage, and context for document-first ONTO-KG

Status: target architecture and phased implementation plan, not implemented behavior.
Audit date: 2026-11-28. Implementation branch: `onto-kg-feature` for shared
ONTO-KG foundations; JERE-agent changes remain on `jere-feature` under #9.
Backend baseline: released GestaltDB **0.17.0**. See the
[capability/scale review](../GESTALTDB_SCALE_REVIEW.md) for tagged evidence,
reproducible probes, and the distinction between native features and planned
synirmos integration. Performance recommendations below are not measured SLOs.

## Execution status — update during delivery

Last updated: 2026-11-28. This section is the live progress record; historical
audit tables below retain their original date and are not current issue status.
Follow `AGENTS.md` for checkpoint, push and technical-debt tracking rules.

- **Merged baseline:** PR #18 merged to `main` as `830b7c4`: ontology scaffold,
  document-first architecture, GestaltDB 0.17 dependency/API migration, capability
  and scale review, and characterization script. No D-slice implementation is
  complete. Last implementation gates: 359 tests, 92.03% coverage, example/build/
  wheel checks; six ontology notebook cells executed in order.
- **Current stage:** D0/#11 implementation continues on `onto-kg-feature`.
  PR #21 is still open and will include the implementation checkpoints as well
  as its execution instructions; no PR is merged automatically. First increment:
  document/revision/content identities, byte spans, explicit time semantics and
  narrow document-source/content-reader ports are implemented, along with the
  first increment's executable notebook. D0 is not complete.
- **Second increment implemented/verified:** neutral graph values/profiles/write intents,
  deeply immutable JSON properties, finite trusted grants intersected with
  requests, explicit snapshot pins and separate logical/physical read budgets.
  Empty selection means no access, never an implicit wildcard. Native adapters,
  real authorization and durable publication remain D1/D3 responsibilities.
  Context/exposure/read-session contracts are now in progress, not yet verified.
- **Implemented/verified first increment:** `core/{contracts,documents,temporal}.py`
  and `core/ports/documents.py`: immutable versioned values, framed qualified
  identity, conservative byte-count limits, original-byte span integrity, and
  independent source-valid/capture/justified-knowledge times. Existing repository
  APIs/IDs are unchanged. See [the contract specification](../DOCUMENT_CONTRACTS.md).
  Core boundary checks now recurse into ports and test fresh-process imports.
- **Checkpoint delivery:** contract implementation/test commit `6350c5b` is pushed.
  `examples/onto_kg/notebooks/D0_contracts.ipynb` now demonstrates source-qualified
  identity, collection independence, capture retries, time eligibility, byte spans,
  chunk occurrences and page limits with assertions. The full gate executes it
  and notebook 00 in fresh processes (six code cells each) without Jupyter;
  installed-wheel smoke exercises new core values and nested ports as well.
- **Checkpoint verification (graph/scope increment):** `uv run python scripts/check.py`
  passes: Ruff lint/format, 427 tests, 92.64% coverage, example regression, metrics, build and
  installed-wheel smoke, plus three ONTO-KG notebook checks. New contract modules
  have complete test coverage. `git diff --check` passes.
- **Next implementation:** context/exposure/extraction contracts and read-session
  lifetimes, with corresponding notebook coverage. Finish
  D0's executable examples, JSON round-trips and recursive import-boundary tests
  before moving to D1/D2. Existing repository contracts/IDs remain unchanged.
- **Remaining:** D0 → D1/D2 → D3; complete #2 before dependent feature sign-off;
  #3/#4 → D4/#5 → #6; D5 and #7 → D6 → final #8, honoring the exact prerequisites
  in section 9 rather than adding a whole-epic dependency.
- **Tracking mismatch:** merge auto-closed #2, but artifact I/O, merge/supersession
  and comprehensive release consistency acceptance remain unfinished. Reopen or
  link an explicitly reviewed completion issue before treating #2 as complete.
- **Decisions still to measure:** deployment workload/SLO targets and eventual
  ANN/backend selection. These do not block D0; no scale certification is claimed.
- **Parsing/chunking direction:** evaluate reusable deterministic LangChain
  parser/splitter adapters in D2, preserving neutral contracts, byte-span/source
  maps, explicit capture and bounded dependencies; no new dependency is added by
  these D0 value/protocol checkpoints. Actual source/parsing adapters remain D2.
- **Deferred technical debt (not new whole-epic blockers):**
  - [#19](https://github.com/mylonasc/synirmos/issues/19): separate remote-authoritative
    Git capture/owned cache policy from local immutable-object reading; the full
    transport/authority migration remains outside document projection delivery.
  - [#20](https://github.com/mylonasc/synirmos/issues/20): migrate remaining legacy
    repository consumers to provider-neutral identities/records, with explicit
    persisted-ID/event/job compatibility. D0–D6's required neutral seams and
    compatibility remain in those slices, not deferred here.

## 1. Purpose and relationship to existing plans

Make synirmos usable for standalone text documents and document collections,
while retaining repository analysis as a specialization. Both workflows must
share evidence, parsing, extraction, resolution, storage, and retrieval contracts.
Context providers must be usable and testable without an agent or repository.

This is [architectural prerequisite sub-epic #10](https://github.com/mylonasc/synirmos/issues/10)
of [ONTO-KG #1](https://github.com/mylonasc/synirmos/issues/1),
not a replacement for its feature slices #2–#8. It coordinates with
[JERE #9](https://github.com/mylonasc/synirmos/issues/9). The GitHub tracking
section below records the new parent, indexed slices, and dependency edges.

Read alongside:

- [EPIC_ONTO_KG.md](EPIC_ONTO_KG.md): ontology-guided construction/retrieval,
  with the explicit refinements in this plan taking precedence for affected designs.
- `EPIC_JERE.md` on `jere-feature`: existing agent prototype and staged work;
  its absence on this branch does not mean that code has merged or disappeared.
- [../REFACTORING_PLAN.md](../REFACTORING_PLAN.md): provider-neutral domain
  contracts, independent parsing, storage-owned mappings, remote-authoritative
  Git plans, and compatibility requirements remain applicable.
- [../../PROJECT_SPEC.md](../../PROJECT_SPEC.md): current guarantees, safety,
  packaging, provenance, temporal semantics, and quality gates remain in force.
- `ref_ontokg_files/`: user-supplied inspiration, currently untracked. Do not
  silently add it to distributions or make library behavior depend on its presence.

Only documents and Git/GitHub composition are delivery requirements here.
MR text is a supported future normalized input shape, not a claim that GitLab
ingestion exists. This epic does not implement GitLab/Jira, replace the graph
backend, import all of OWL, or complete the entire older refactoring roadmap.

## 2. Audited baseline: implemented versus intended

Branches were inspected separately without treating their contents as one release:

| Location | Verified implementation | Not yet established |
| --- | --- | --- |
| `main` at `844e0ab` | Repository pipeline, content parser, temporal GestaltDB sink, journals/workers, provider scaffolds | Generic document pipeline, generic scoped graph reads, ontology/JERE additions |
| `onto-kg-feature`, `58e39ff` plus `b2ecbc1` | `processing/ontology/{models,registry,seed}.py`, 10 unit tests, notebook 00; class/property registration, aliases, deprecation, subclass-aware triple checks, working-registry schema compilation, fingerprinted releases | Merge/unmerge, TOML/JSON artifact APIs, comprehensive release consistency validation, ontology graph persistence, embeddings, guided extraction, staging, retrieval |
| `jere-feature` at `6b34635` | `processing/agentic/` prototype, `ParsingContext`, shared helpers, `enrichment.py` delegation, 8 JERE tests and epic | Source-neutral identity, dynamic ontology vocabulary, enforced scoped context, canonical resolution, complete framework wiring |
| GitHub #1–#9 | All issues open at audit; no PRs found | A pushed branch commit is not a merged release or a reason to close its whole tracker |

At that audit, #2 remained open legitimately: the implemented scaffold is useful,
but its original acceptance text includes work absent from the branch. Do not
mark merge semantics or artifact round-trips complete based on the prior summary.

### Concrete coupling and correctness gaps

1. `storage/graph.py` combines generic records, persistence, repository/GitHub
   mappings, domain-specific indexes, and label/relation counting defaults.
   `GraphSink` mechanics are mostly reusable; extract specialization, not a
   second near-identical sink.
2. `processing/content.py` combines byte acquisition, Markdown/Python parsing,
   Git snapshot assembly, and coverage reporting. `ParsedContent`,
   `SnapshotContent`, and `SectionRecord` embed Git identifiers. Reuse parser
   behavior behind neutral contracts rather than inventing commits for documents.
3. `IdFactory`, `RepositorySpec`, `RuntimeConfig`, journal manifests,
   `TemporalCoordinator`, and `WorkJob` assume a repository/work-item run.
   Standalone documents need a separate entry point, not optional fields throughout
   those existing contracts or a fabricated repository URL.
4. Current `GraphSink.neighbors()`/`find_nodes()` use current projections.
   Individual `node_as_of()`/`edge_as_of()` reads select valid time; that alone
   does not establish what was known at an earlier information horizon.
5. JERE context records have no temporal fields, in-memory filtering is delegated
   to the caller, and the digest omits descriptions/other values. Grounding checks
   a separate entity listing, not the exact records exposed to the model.
6. JERE enums exclude general classes such as Person/Organization. The provider
   currently derives new entity IDs via `IdFactory.evidence()` from names;
   structural predicates can be folded into `RELATED_TO`. Neither behavior is
   an acceptable canonical identity/semantics policy for general ONTO-KG.
7. Core import-boundary tests only recurse in some cases; new nested contracts
   need recursive checks. Agentic package imports are eager; neutral imports
   must not accidentally load LangChain or storage/Git implementations.

## 3. Target architecture and ownership

```text
explicit source selection                  captured Git/platform evidence
          |                                            |
TextDocumentSource                       pure document projections
          +-------------------+------------------------+
                              v
              document identities + immutable revisions
                              v
               pure parsing -> sections/spans -> chunking
                              v
                    ExtractionSubject
                              |
ontology release -> compiler -> ExtractionProfile
                              |
scoped KnowledgeReader -> ContextProvider -> ParsingContext facade
                              |
                      LangChain JERE agent
                              v
             typed candidates + verified evidence spans
                              v
                validation -> resolution -> approval/staging
                              v
                domain mappers -> GraphWriteBatch
                              v
             generic temporal writer / GestaltDB adapter
                              |
                 scoped graph/evidence reader
                              v
             GraphRAG retrieval policy -> cited context
```

Boundaries:

- **Sources acquire/capture evidence.** No ontology decisions, extraction,
  hidden parsing, or graph writes.
- **Parsers/chunkers describe content.** No Git traversal, fetching, model calls,
  or database dependencies.
- **Context providers select knowledge.** Read-only, bounded, independently
  testable; no persistence ownership or LangChain types.
- **Agents propose.** Model/tool implementations stay in `processing/agentic`.
  No direct canonical graph mutation or unattended ontology publication.
- **Validation/resolution/approval decide admissibility.** Schema conformity is
  necessary, not proof that an assertion is true.
- **Storage maps and persists.** Domain mappings are specializations; the backend
  does not import Git/GitHub or decide entity equivalence.
- **Runtime composes.** It injects clocks, readers, budgets, profiles, and models;
  application assets are never discovered relative to the installed package.

### Proposed module homes (create only when responsibility moves)

```text
core/
  documents.py                 # document/revision/collection/origin/span values
  graph.py                     # neutral write/read records and graph scope/profile
  context.py                   # knowledge views, requests, bounded results
  extraction.py                # subject, candidate/assertion/evidence contracts
  ports/
    documents.py               # source + immutable content-reader contracts
    graph.py                   # read/write capabilities
    knowledge.py               # knowledge lookup contract
sources/
  text_document.py             # caller text/bytes and explicit local-file capture
  projections/                 # pure captured Git/platform -> document projection
parsing/
  interfaces.py
  documents/{markdown,plain_text}.py
processing/
  documents/                   # chunking, lexical assembly
  context/                     # empty, in-memory, graph-backed, composition
  extraction/                  # profiles, validation, resolution orchestration
  ontology/                    # registry, release loading, native compiler adapter
  agentic/                     # JERE, model adapters, tool formatting/dispatch
storage/
  graph.py                     # compatibility facade, not repository implementation
  backends/gestaltdb.py         # generic temporal persistence
  profiles/                    # evidence, lexical, repository specifications
  mappings/                    # Git, GitHub, documents, ontology, assertions
  readers/                     # scope-enforcing storage adapters
runtime/
  document_pipeline.py         # standalone document composition
```

Pure profile/contract descriptors belong in core; concrete storage profiles and
mappings can live in storage. `processing/context` consumes a read port rather
than importing `storage/graph.py`. Keep the existing ontology module where it is
until a concrete dependency requires promoting a pure contract: no speculative
package-wide move or monolithic universal provider interface.

## 4. Source, content, and identity contracts

### 4.1 Document source and revisions

`TextDocumentSource` is a peer to `sources/git.py` and `sources/github.py`, not
an implementation of the repository-only `RepositorySource` protocol.

- `TextDocument`: stable logical identity, source instance/native key, title,
  extensible document kind, optional origin binding.
- `DocumentRevision`: immutable content reference/digest, native revision when
  available, encoding/media type, source time, observation time, information
  horizon, evidence and supersession information.
- `DocumentCollection`: explicit selection and membership. Membership is not
  identity ownership; the same document can occur in several collections.
- `DocumentBatch`: bounded captured revisions/events, continuation and gaps.
- Content reader: bounded reads of captured bytes, independent of transport.

Start with caller-provided text/bytes and explicitly selected files/manifests.
Capture bytes once, digest those captured bytes, then process the captured
revision: avoid a stat/read race. File roots, symlink policy, byte limits,
encodings, and errors are explicit. No implicit directory crawl or URL fetch.
Local mtime is not evidence of historical content availability; default to
capture-time knowledge unless a trustworthy historical revision is supplied.

Standalone local documents do not weaken the planned remote-authoritative Git
policy: local text capture is a separate source with its own provenance, never
a fallback for repository history.

### 4.2 Identity separation

Keep separate identities for logical document, captured revision, content blob,
parse artifact, chunk content, chunk occurrence, mention, candidate, canonical
entity, assertion, and extraction run. Define versioned derivation rules in D0.

- Same bytes may reuse parse/embedding artifacts, not source identity or access.
- Chunk content identity includes chunker/config/version; a chunk occurrence
  references its document revision and span. Ordinal alone is not stable across
  changed chunkers.
- A document moving between collections must not change its canonical ID.
- Candidate local keys are not canonical entity IDs; exact identity keys are
  source-/domain-qualified. Normalized names and embeddings are match signals,
  not sufficient merge authority.
- Retry operation keys exclude incidental run IDs. Keep run lineage separately
  so replay/re-delivery does not duplicate assertions; distinguish a deliberate
  new analysis version from a retry.
- Existing repository IDs remain readable and unchanged during extraction of
  generic storage. Do not silently reinterpret persisted hashes.

### 4.3 Parsing, spans, and projections

Use neutral byte inputs with media/path hints. Extract Markdown behavior first,
add plain-text fallback, and retain a Git adapter for `ContentIndex` consumers.
Use half-open byte spans into immutable original content with explicit decoded
text/source maps. Test Unicode, CRLF, BOM, empty content, and normalized text.

Reuse suitable non-LLM LangChain parser/splitter capabilities behind concrete
adapters rather than rewriting standard chunking algorithms; evaluate the
separate `langchain-text-splitters` package when implementing D2. Core records and
ports remain framework-neutral. Framework document metadata/character offsets
are not authoritative byte spans or identities: preserve whitespace/heading/
overlap mappings, handle repeated text, and fingerprint adapter/library/config
versions. Keep source acquisition separate from loaders with hidden I/O. Existing
parser compatibility and evidence accuracy take precedence over forced reuse.

PR descriptions, commit messages, repository documentation, and docstrings are
document views with an `OriginReference` to their source entity/field/version.
Projection performs no fetching. Mutable PR text retains observation horizons;
commit messages use captured immutable commit semantics. Decoded docstrings need
source maps (escapes/dedenting), not guessed source offsets. Ordinary Markdown
links establish textual references, not automatic `CITES_CLAUSE` or
`REFERS_TO_DEFINITION` semantics without supporting evidence.

## 5. Generic graph storage, parameterized without a god context

Use composition, not `RepositoryGraphSink` subclasses that duplicate persistence.
Repository/document facades combine a profile, mapper, queries, and one store.

### 5.1 GraphProfile: structural specification

Immutable descriptor: profile ID/version/fingerprint, labels/predicate identities,
required properties, reserved provenance keys, identity/mapping versions, index
requirements, and backend capability requirements. Compose evidence, lexical,
repository, and ontology-derived profiles deterministically; reject conflicting
definitions instead of last-writer-wins overrides. Never use an arbitrary
callable/config service container as the profile.

An ontology is not a database schema. Compile approved domain vocabulary into
validation/profile artifacts; do not force infrastructure concepts into every
domain ontology or require full OWL reasoning in the backend. Translate the
supported logical subset to GestaltDB's native ontology compiler instead of
building a parallel reasoner. Closed-vocabulary extraction checks, release
governance and retrieval annotations remain application responsibilities.
Multiple allowed registry domains/ranges are alternatives, unlike conjunctive
native domain/range entailments: test that mapping rather than blindly emitting
one axiom per allowed class. Retrieval annotations are separately versioned policy
inputs. Preserve full predicate IDs through storage;
backend label mappings must be reversible and collision-tested.

Profile updates produce a reviewed capability/index/migration plan. They must
not automatically drop indexes, relabel history, or rewrite identities. The
first backend remains GestaltDB; unsupported vector/temporal operations fail
explicitly. Co-location is an implementation preference, not a source contract.

### 5.2 GraphScope: visibility specification

Scope includes selected collections/sources, valid-time selection, information
horizon, pinned graph snapshot/release identity, approval visibility, and bounded
query limits. Trusted application authorization intersects with requested scope;
agents cannot broaden it. Scope membership is enforced, not just ID prefixes.

Readers must select a version visible at the knowledge horizon, then apply
valid-time constraints; filtering the latest value alone can incorrectly hide
an older visible value. Filter entities, edges, their endpoints, evidence, and
indexes consistently **before** ranking/top-k. Current-neighbor traversal plus
historical node lookup is not an adequate temporal implementation.

Use native `graph.temporal`/`TemporalHistory` and authenticated read views for
supported historical scopes, rather than implement a second bitemporal engine.
Pair the temporal view with a backend-verifiable snapshot for coherent reads and
authenticated decode reuse. These capabilities do not enforce collection/access
policy or translate application observation horizons automatically. If a requested
scope cannot be represented, report unsupported scope; an explicit bounded
projection is a separately tested fallback, never a silent current-state read.
Pinned views isolate a run from concurrent writes and make retries reproducible.

### 5.3 WriteContext: execution/provenance specification

Run/operation identity, mapping/profile versions, origin, evidence, and applicable
ontology release accompany batches. Per-assertion time/evidence override rules
must be explicit; conflicting batch/record provenance is rejected. Read scope is
not write authority. A trusted write policy validates destinations and approval.

Retain generic `EntityWrite`/`RelationshipWrite` semantics, temporal append and
corrections, idempotence, single-writer ownership, and closed-handle behavior.
Document the transaction boundary between durable journal/outbox and graph
application; recover interrupted batches by idempotent replay, not an assumed
cross-file/database atomic transaction.

Use bounded native `commit_versions` batches and, on LMDB, a native transaction
for temporal history plus mutable projection. Batch limits include bytes as well
as record count; preserve source horizons and retry/version identities. Current
per-record writes remain compatibility behavior until D1 implements the batch
boundary. Native history never updates current projections automatically.

### 5.4 Knowledge versus assertions

Even if accepted facts are initially stored as attributed typed edges, the neutral
assertion contract includes evidence, status, validity/knowledge metadata, model/
prompt/schema versions, and supersession. Distinct supports and contradictory
claims remain distinct records; a current canonical edge is a projection, not
the entire evidentiary history. Evaluate native `graph.epistemic` claims and
authenticated claim readers before inventing another generic assertion store;
map evidence/status/approval semantics explicitly. Assertion nodes versus edges
remain a storage choice, not a requirement to bypass native support. Deletion
of one source does not delete a shared entity or establish a
historical retraction without policy/evidence.

## 6. Reusable context providers and extraction profiles

Separate these contracts:

| Contract | Responsibility |
| --- | --- |
| `ExtractionSubject` | Immutable text, revision/chunk occurrence, span/evidence, origin |
| `KnowledgeReader` | Read-only entity/relation/evidence queries through enforced scope |
| `ContextProvider` | Select/retrieve relevant knowledge within scope and shared budgets |
| `ContextResult` | Structured items, evidence, snapshot ID, truncation/continuation, gaps |
| `ExtractionProfile` | Ontology/schema, prompt/task version, tools, evidence requirements, limits |
| `ParsingContext` facade | Compatibility composition consumed by the existing JERE interface |

Start with empty, in-memory, and graph-backed providers. All run the same
conformance suite without an LLM; graph-backed providers use a storage read port.
Add composite providers only after individual contracts stabilize. Composition
intersects scopes, shares budgets, deduplicates qualified identities deterministically,
and reports conflicts rather than expanding permissions or picking arbitrary versions.

Return complete structured records within limits; never cut an ID mid-record.
Record the exact entity IDs/evidence actually delivered to the model and validate
reuse against that exposure set. A successful direct lookup can expose an entity
outside an initial listing; a hidden/unretrieved entity is not grounded merely
because it exists in the database. Relation claims need evidence too.

Cache identity binds full visible subject/context values, scope/snapshot,
provider/config versions, ontology/schema/profile fingerprints, model/prompt,
tool behavior and limits. Revalidate cached proposals under the current pinned
contract. Temporal/access metadata and changed descriptions must invalidate reuse.
Cache corruption and missing capability are explicit outcomes, not fabricated data.

Add budgets for source documents/bytes, context queries/results/traversal, embedding
requests/tokens, and model calls. Aggregate across composed providers and attempts;
persist usage on failure/resume. A tokenizer estimate is not a hard token limit:
provider output caps and conservative accounting must enforce actual bounds.

Extraction returns candidates/mentions/assertions. Schema/grounding checks,
identity resolution, and approval/staging happen outside agent tool dispatch.
Keep arbitrary ontology IDs in neutral models while retaining a legacy profile
for JERE v0 behavior. No lossy `DEFINES`/`PART_OF` -> `RELATED_TO` mapping in the
new canonical path. Extraction context and answer-retrieval policies share readers,
not necessarily ranking/traversal policy. Neither agents nor retrieved text can
publish an ontology or grant access.

### 6.1 Read-session and physical-work policy

Runtime owns a bounded read session: approved scope, MVCC snapshot, temporal
horizon, ontology release and profile/policy identity. Providers borrow narrow
read capabilities and reuse the same view across tool calls; they do not open
handles, hash the full graph, rebuild indexes or reauthenticate the whole commit
prefix for every lookup. Close sessions promptly and measure long-snapshot
retention under writes; do not hold one indefinitely for an entire service.

Separate returned-result/token caps from physical candidate/byte/work budgets.
Historical traversal can materialize candidate sets before yielding, and live
reservoir sampling scans degree: `limit`/fanout alone is not a work bound.
Use supported indexed predicates/cohorts before hydration, iterator APIs, explicit
hub policies and honest unsupported-bound outcomes. Worker isolation is needed
for hard time/RSS limits. No integrity/durability bypass is a scale optimization.

Register and verify required indexes before reads: unindexed native exact/range
lookups may return empty rather than raise. Rebuild deferred indexes at an
explicit writer-owned readiness barrier, never from the new scoped read path.
The legacy `GraphSink._ensure_ready()` behavior is not the target reader design.

## 7. Existing design refinements and scope ownership

Only the specified assumptions below are superseded; the existing issues and
their remaining goals stay open. GitHub amendments link here and preserve the
original issue bodies for auditability.

| Issue/plan | Preserve | Refine / no longer implement literally |
| --- | --- | --- |
| #1 ONTO-KG umbrella | Document-first ontology-guided construction/retrieval; final demonstration | Add this prerequisite track without replacing #2–#8 |
| #2 ontology scaffold | Registry, fingerprinted releases, aliases, seed, notebook | Finish missing artifact/consistency work; merges remain unimplemented. Seed is an example profile, not mandatory lexical/domain coupling. Map logical axioms to native compiler; no lossy JERE/LinkRelation folding |
| #3 ontology persistence | Queryable releases, compiler, notebook | Use generic mapper/profile; immutable release manifest with exact membership, native compilation and linked application/native revisions. Pin release+knowledge scope; valid-time alone is insufficient |
| #4 chunks/embeddings | Lexical graph, model/index ports, bounded search, notebook | Neutral documents first, Git adapter second; separate content/occurrence identity. Extraction owns ontology-use metadata. Exact search is a small-corpus oracle with byte/corpus ceilings and an ANN transition criterion, not a scale architecture; hash embeddings prove no semantic quality |
| #5 guided extraction/staging | Closed vocabulary, validation, explicit gaps and staging, notebook | Dynamic ontology IDs and verified evidence; reuse native structural validation only under matching completeness assumptions. Mapper owns writes. Gaps are not persistent candidate/review state |
| #6 resolution/writer | Conservative identity matching, reversible merges, replay, notebook | Names/embeddings and scoped native equality are signals, not physical merge authority; retry keys exclude incidental runs. Bounded transactional batches retain assertion/support lineage |
| #7 retrieval | Ontology-governed bounded expansion and citations, notebook | Scoped indexed readers enforce horizon/access before ranking; reuse pinned sessions, measure work behind limits. Approved release/policy changes only; explicitly admit native inferred queries/sampling if needed, never assume automatic integration |
| #8 final demo | Public corpus selection, licensing, full run and polished notebooks | Remains the only final demo issue; compare standalone and composed contexts and refine this plan with measured results |
| #9 JERE | LangChain agent implementation, prompt/tools/consolidation/evaluation stages | Shared context contract replaces ad hoc context implementations; no repository identity fabrication or automatic name-based canonicalization. Agent stages remain owned by #9, not duplicated here |
| Older refactoring P1/P4/P5 | Neutral domain values, storage mappings, pure parsers, compatibility | Deliver the document-relevant subset without waiting for full GitHub/Git transport refactoring. Do not declare P1–P8 complete or widen to more providers |
| ONTO-KG epic Phase 6 | Useful future evolution/governance direction | Not the same as GitHub Slice 6 (#8), which is the final demo. A production reviewer UI, calibrated auto-publication, and broad migration engine remain separately scoped follow-ups |

The registry's application-level closed-vocabulary checks are not equivalent to
OWL or SHACL. RDF/OWL domain/range semantics must not be advertised as ordinary
closed-world validation. Preserve stable semantic IDs and document the supported
subset if import/export is added; no requirement to adopt a full reasoner here.

### 7.1 Native reuse and scale acceptance

GestaltDB 0.17 already supplies bounded ontology compilation/reasoning, structural
validation, snapshot-local equality, temporal closure, claim extraction and
explicit inference query/sampler adapters. Their presence is not evidence that
synirmos has integrated them. Reuse selected capabilities behind adapter ports;
do not expand feature scope to activate every optional subsystem. Preserve the
distinction between domain/range inference, closed-world validation, logical
equality, physical identity, and approval.

The [scale review](../GESTALTDB_SCALE_REVIEW.md) is the implementation checklist:
benchmark commit growth and degree skew, not only graph size; batch temporal
publication; amortize authenticated snapshots; use indexed candidate selection;
materialize reusable sparse traversal artifacts only when justified. Native
logical-history batching remains opt-in, not a universal fast path. LMDB results
do not establish PyRex/LevelDB performance or snapshot support.

The embedding port must support a measured ANN strategy at larger corpus sizes,
including a derived sidecar when appropriate. Bind indexes to model/metric,
snapshot, access/approval partition and deletion state. Scope candidates before
top-k or use an explicitly supported bounded filtered-ANN policy; global top-k
then filtering is not equivalent. Define target workloads/SLOs before declaring
scale readiness; small probes are characterization, not a deployment capacity.

## 8. Phased implementation slices

Each D-slice is a separately reviewable delivery, with tests, migration notes,
and a notebook or executable example explaining the seam. Names below are
design targets, not imports guaranteed to exist. No simultaneous rewrite of all
sources, storage, and runtime is required.

### D0 — Neutral contracts and identity/temporal specifications (P0)

Depends on: nothing beyond audited baseline. Deliver core document, graph,
context, extraction records/ports and documented identity/time rules. Establish
scope/result/approval semantics and serialization versions; retain legacy APIs.

Acceptance: qualified identity collision tests; same bytes/different origins and
same document/multiple collections; UTC/horizon validation; immutable snapshot
contracts; JSON round-trips; recursive import-boundary tests. Plain core/context
imports do not load LangChain, pygit2, or GestaltDB. Notebook `D0_contracts.ipynb`.
Specify read-session lifetime, unsupported-capability outcomes, and separate
logical output caps from physical work/byte/deadline budgets.

### D1 — Generic graph store and composable profiles (P0)

Depends on: D0. Extract backend, neutral writes, repository/GitHub mappings and
counts/defaults from `storage/graph.py`; retain re-exports and existing IDs.
Add deterministic profile composition, capability checks, explicit migration
plans, reserved-property validation, and write context. Do not alter existing
index/version ID behavior without a versioned compatibility decision.

Acceptance: repository goldens and temporal/idempotence/correction tests unchanged;
arbitrary document/entity profile works without repository configuration; profile
conflicts rejected; no source imports in generic backend; interrupted-batch replay
and conflicting-provenance tests. Notebook `D1_graph_profiles.ipynb`.
Additionally: bounded native batch sizes/bytes; history+current transaction
rollback on LMDB; explicit index-readiness barrier; measured commit-count growth
and replay behavior without changing existing source knowledge semantics.

### D2 — Text document source and pure parsing/chunking (P0)

Depends on: D0. Add `sources/text_document.py`, manifest/memory/file capture,
neutral parser contracts, Markdown extraction, plain text and deterministic
chunking. Preserve original content and source maps. Existing Git processing
uses an adapter; no duplicated parser. Source/parse/chunk flow works without DB,
ontology, repository configuration, or LLM.
Evaluate existing parser reuse and deterministic LangChain splitting behind
neutral adapters; add only required compatible dependencies and lock updates.

Acceptance: explicit file boundary/symlink/byte-limit/decoding cases; revision
identity, Unicode/CRLF/BOM spans; existing Markdown parsing goldens; deterministic
chunking and cache invalidation on configuration changes; no code execution or
hidden I/O. Notebook `D2_text_sources.ipynb`.
Exercise bounded streaming batches and report text/embedding/evidence byte growth.

### D3 — Scoped readers and independently testable context providers (P0)

Depends on: D0 and D1. Empty/in-memory providers, scope-enforcing GestaltDB
reader, graph-backed provider, bounded structured results and exposure/digest
contracts. Implement historical projection or fail explicitly for unsupported
scopes. Context selection remains outside storage and outside agents.

Acceptance: shared conformance suite without an LLM; in-memory/backend parity;
future observations invisible even with old valid_from; older visible version
selected correctly; endpoint/evidence/collection filtering; staged excluded by
default; truncation distinct from empty; descriptions/scope changes alter cache
identity; concurrent writes cannot mutate a pinned view. Notebook
`D3_context_providers.ipynb`.
Use native temporal/history readers and a reusable pinned read session; no hidden
index repair or handle creation. Add high-degree candidate-work instrumentation,
index-presence checks, repeated-tool-call reuse tests and snapshot-lifetime tests.

### D4 — JERE boundary adaptation and configurable extraction (P0)

Depends on: D0, D2, D3; consumes the existing #9 prototype, not #9 closure.
Implement subject/profile/context composition and the `ParsingContext`
compatibility facade. Neutral candidate/mention/assertion outputs, dynamic schema
interface, exposure-based grounding, complete cache identity, budget/error
accounting, and no automatic canonical-name IDs. Coordinate the agent-side
changes in `jere-feature`; #9 retains prompt/tool factory and evaluator ownership.
ONTO-KG-specific compiler/staging integration remains #5.

Acceptance: identical extraction API for standalone text and repository-origin
text; empty/in-memory/graph contexts interchangeable; Person/Organization and a
custom predicate accepted under a supplied schema; fake-model tests for invented
IDs/unsupported claims/cache invalidation; rejected candidates never written;
legacy profile migration tests. Notebook `D4_extraction_profiles.ipynb`.

### D5 — Standalone runtime and repository composition (P1)

Depends on: D1, D2, D3, D4. Separate `DocumentRunConfig` and document pipeline;
source-neutral journal/run envelopes and replay adapter without requiring a repo.
Pure projections for captured commit messages, GitHub descriptions, repository
documents and docstrings. Inject shared budgets/content readers/approved context.
Do not implement GitLab transport just to demonstrate normalized MR text.

Acceptance: in-memory extraction without DB; standalone indexed run with DB;
combined document/repository run preserves original PR/commit identities and
horizons; source mapping for docstrings; no hidden fetch; process restart and
duplicate delivery preserve budgets/results. Existing repository config/jobs
remain supported; new envelope versions do not silently reinterpret old jobs.
Notebook `D5_standalone_and_composed.ipynb`.
Replace full-journal rereads on every `EventJournal.append()` with validated
single-writer append state/checkpoint recovery; test prefix integrity after
interruption and characterize append growth rather than inherit quadratic work.

### D6 — Cross-feature integration and release-readiness gate (P1)

Depends on: D5 and ONTO-KG #7 (which includes #2–#6 through its dependencies).
Integrate the branches/contracts in an agreed order, run compatibility/security/
packaging/quality gates, and document actual supported backend capabilities and
remaining gaps. This is a synthetic integration gate, **not** a duplicate final
public-corpus demonstration. It unlocks #8.

Acceptance: one synthetic corpus passes ontology-guided indexing, resolution,
replay and scoped retrieval; repository example regressions unchanged; no staged
or future knowledge leakage; installed-wheel imports; notebook execution tests
are in CI; APIs and migration notes match behavior. Notebook `D6_integration.ipynb`.
Include reproducible cold/warm workload benchmarks with commit/version growth,
degree skew, selectivity, batch/payload size and concurrent writes: p50/p95/p99,
throughput, candidates/KV work, RSS, disk/index size, rebuild/recovery cost and
retrieval quality against declared SLOs. Report unmet targets and backend scope.

### Existing final slice — #8, public document demonstration (P1)

After D6, #8 selects a small public corpus with clear redistribution terms,
stable revisions, rich cross-document relationships and competency questions.
Record selection alternatives, license/attribution, content hashes, collection
manifest and capture dates. Do not pick a corpus requiring new PDF/HTTP support
just to reach the demo. A short public Markdown/plain-text technical standard or
specification set is a candidate, not a preselected or downloaded dependency.

Demonstrate ontology approval/compilation, document revisions/chunks, JERE
candidates with spans, resolution/staging, generic graph writes, ontology-policy
retrieval and cited answers. Compare empty, collection-backed and graph-backed
contexts, plus a repository-text projection. Show a constraint rejection and an
approved policy-version change. Measure extraction/resolution/retrieval separately.

Provide an offline reproducible path with transparently labeled recordings/fakes;
a real-model rerun is opt-in with consent/cost limits. Scripted replies or hash
embeddings do not establish real extraction/semantic retrieval quality. Record
real-run results when approved, and report unavailable live validation honestly.
Publish findings and refine the plans; do not mark earlier scopes complete from
a polished notebook alone. Original ONTO-KG notebook names remain valid; D-series
notebooks complement rather than renumber them.

## 9. Implementation order and GitHub tracking

Architectural parent: [#10](https://github.com/mylonasc/synirmos/issues/10), a
sub-issue of #1. D0–D6 were created through the GitHub API. Native sub-issue
hierarchy distinguishes ownership from dependency; native blocked-by edges
encode the DAG below.

| Slice | GitHub issue | Priority | Completion prerequisites |
| --- | --- | --- | --- |
| D0 — Neutral contracts | [#11](https://github.com/mylonasc/synirmos/issues/11) | P0 | Audited baseline |
| D1 — Generic graph/profile | [#12](https://github.com/mylonasc/synirmos/issues/12) | P0 | #11 |
| D2 — Text source/parser | [#13](https://github.com/mylonasc/synirmos/issues/13) | P0 | #11 |
| D3 — Scoped readers/context | [#14](https://github.com/mylonasc/synirmos/issues/14) | P0 | #11, #12 |
| D4 — JERE boundary | [#15](https://github.com/mylonasc/synirmos/issues/15) | P0 | #11, #13, #14; existing #9 prototype, not tracker closure |
| D5 — Runtime/composition | [#16](https://github.com/mylonasc/synirmos/issues/16) | P1 | #12, #13, #14, #15 |
| D6 — Integration gate | [#17](https://github.com/mylonasc/synirmos/issues/17) | P1 | #16, #7 |
| Existing final demo | [#8](https://github.com/mylonasc/synirmos/issues/8) | P1 | Existing #2–#7 plus #17 |

Existing feature issues retain their original prerequisite edges and add:

| Existing issue | Additional prerequisites | Scope amendment |
| --- | --- | --- |
| #3 ontology persistence | #12, #14 | Generic storage and horizon-safe release reads |
| #4 lexical/embedding layer | #12, #13 | Neutral document inputs and chunk occurrences |
| #5 guided extraction/staging | #15 | Configurable neutral candidate boundary |
| #7 retrieval | #14 | Scoped context/read enforcement |
| #8 final demonstration | #17 | Integrated standalone/composed architecture |

#2 and #6 receive acceptance/scope corrections without additional blockers.
#9 receives coordination links, not a whole-tracker blocker. See section 7 for
the precise replacements. No existing issue was closed or renamed by this plan.

API verification on 2026-11-28 confirmed #1 has eight native sub-issues
(#2–#8 and #10), #10 has seven (#11–#17), the blocked-by graph is acyclic,
and #1/#9/#10 have no whole-tracker blockers. Original issue-body prefixes and
labels were preserved; amendments are explicitly marked. New labels are `epic`,
`area:architecture`, `priority:p0`, `priority:p1`, and `design:scope-refined`.
At that pre-merge verification, all #1–#17 were open. PR #18 subsequently merged
the baseline/plan and auto-closed incomplete #2; consult the execution-status
section for current progress and reconciliation, not these historical snapshots.

```text
D0 -> D1 -> D3 ----+
 |                 v
 +--> D2 --------> D4 -> D5 -----------+
                                      v
#2 + D1 + D3 -> #3                #7 -> D6 -> #8
D1 + D2     -> #4                 ^
D4 + #3 + #4 -> #5 -> #6 ---------+
                    #3 + #4 ------+
```

Edges are prerequisites for completion, not a ban on independent preparation.
Do not add whole-tracker blocking edges to #9: only its context/framework work
must align with D3/D4; prompt hardening and fake-model evaluation can proceed.
Likewise the ONTO-KG parent must not be blocked by its own child epic.

Existing ownership: #1 retains #2–#8; #9 remains a separate related tracker.
The architectural epic is a child of #1 and owns D0–D6. Use `priority:p0` for
prerequisites and `priority:p1` for composition/integration/demo, not urgency
claims about completed scaffolding. `design:scope-refined` marks affected issue
text, **not** an abandoned feature or an implemented correction. Slice indices
and dependency edges, rather than many order labels, define execution order.

## 10. Migration, tests, and completion criteria

- Work on `onto-kg-feature` for shared ONTO-KG foundations and `jere-feature` for
  agent-specific changes. Integrate reviewed shared contracts before consumers;
  explicitly reconcile branch-specific AGENTS notes when branches meet. No force
  checkout/reset or unrelated work removal. This planning change does not merge,
  commit, or push implementation branches by implication.
- Maintain focused compatibility imports for `storage.graph` and old context
  entry points, with deprecation/removal criteria. No indefinite divergent paths.
- Version source envelopes, parse/chunk artifacts, extraction schemas, identities,
  graph profiles, ontology releases and policies separately. Inventory persisted
  fixtures before changing keys, event kinds or version-selection rules.
- Add document event kinds/payloads with typed replay support rather than encoding
  documents as work-item events. Preserve journal prefix/checkpoint validation.
- `AnalysisResult.create()` currently keys decisions without profile/model/context
  fingerprints; design versioned analysis-operation identity to distinguish
  deliberate new analyses while keeping retries idempotent. Do not globally change
  legacy result IDs without migration tests.
- Opaque handles, scopes, providers and model clients are runtime resources, not
  worker-job payloads. Jobs carry versioned subject/scope/snapshot references or
  embedded immutable inputs, never live database/agent objects.
- Library tests use synthetic inputs; examples remain separate consumers excluded
  from distributions. Add notebook execution/example tests to the existing quality
  command instead of relying only on manually executed cells. Keep Ruff notebook
  lint/format checks, 90% combined coverage, complexity gates, wheel smoke tests.
- Explicit tests: identity collisions; parse span correctness; scope isolation;
  historical graph visibility; profile conflicts; shared budget exhaustion/resume;
  prompt-injection-as-data handling; cache corruption/invalidation; exposure-based
  grounding; distinct contradictory assertions; merge reversibility; replay;
  missing extras/backend capabilities; recursive import boundaries.

Completion means a document collection is independently capturable, parsable,
extractable, indexable and queryable, with interchangeable scoped contexts; the
same components compose with repository evidence; and #8 demonstrates the system
with traceable evidence. It does not mean every historical roadmap item, ontology
reasoner, provider integration, governance UI, or autonomous evolution feature exists.
