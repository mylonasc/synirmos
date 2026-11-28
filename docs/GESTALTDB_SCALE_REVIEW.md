# GestaltDB 0.17: reuse and scale review

Reviewed 2026-11-28 against released **0.17.0**, tag commit
`8199b1d1025ae64967f8fa300f9542a324a15bd3`, not upstream `main`.
This is a capability audit and small local characterization, **not** a
production-capacity certification. The design changes below are targets for
[D0–D6](epics/EPIC_DECOUPLING.md), not features implemented by the upgrade.

## Decision

Depend on `gestaltdb[lmdb,arrow]>=0.17,<0.18` (lock: 0.17.0). Reuse its scoped
services, transactions, history, indexes, ontology compiler, and explicitly
selected reasoning/claim adapters. Keep synirmos responsible for document
identity, authorization, extraction admissibility, approval, provenance policy,
and retrieval policy. Do not build a second generic graph or reasoning engine.

## Native capabilities and ownership

| Released capability | Reuse in synirmos | Important boundary |
| --- | --- | --- |
| `graph.nodes/edges`, narrow readers, `indexes`, `lookup`, `traversal` | Backend adapters behind small neutral ports; indexed ID selection before hydration | These are store-scope capabilities, not collection/tenant authorization |
| `graph.temporal`, `TemporalHistory`, indexed bitemporal selection, corrections/retractions | Scoped historical readers and immutable provenance | Temporal versions do not automatically update mutable current records |
| `graph.transaction()`, LMDB MVCC, `current_read_view()` | Atomic graph/history projection batches; read-session snapshot lifetime | No atomic transaction with an external JSONL journal; backend capabilities differ |
| `commit_versions`, current bulk writes, Arrow ingestion, deferred-index lifecycle | Bounded ingestion batches and explicit index-readiness barrier | Batching changes commit/knowledge granularity; native ingest does not map application evidence for us |
| `ontology.compile_ontology`, `CompiledSchemaCache`, named `gestalt-core-v1` axioms | Compile an approved release's logical subset once; cache by exact revision | Domain/range **infer types**, not closed-world proposal validation; no full OWL/SHACL |
| `reasoning.structural` / `validation` | Evaluate reuse for required fields, cardinality bounds, datatypes, exclusivity, disjointness/conflicts | Structural checks require explicit closed-class completeness; they are not full SHACL or extraction-grounding policy |
| Typed rules, scoped stratified negation/aggregates, equality, temporal closure | Opt-in capabilities only if a concrete feature needs them | Snapshot-local equality never authorizes physical canonical-entity merges; bounded fragment and combination admission rules apply |
| Pinned graph/claim extraction, batched claims, generations/sessions, explicit inferred query/sampler adapters | Preserve exact evidence IDs, source authentication and scope when enabling inference | Not transparent query rewriting, automatic ordinary-sampler integration, or free incremental maintenance |
| Sparse CSR/memmap sampler snapshots and typed adjacency | Reuse materializations for repeated eligible traversal workloads | Build/hash/filter costs, candidate buffers and long-lived snapshot storage still count |
| Optional RDF and NetworkX interchange, offline visualization | Optional application/notebook adapters as needed | No implicit remote import resolution; import support is not universal ontology semantics |

The named ontology compiler supports subclass/subproperty, named equivalence,
domain/range, inverse/symmetric/transitive properties, binary property chains,
left-side conjunction/disjunction, and scoped reflexivity. Broader reasoning
modules also exist: **do not confuse the small compiler/default Datalog fragment
with the entire release**. In particular, equality and structural cardinality
validation are present even though they are outside that compiler fragment.
The packaged short ontology guide and older testing guide underdescribe some
later additions; use the tagged implementation and construct matrix for exact
admission. Unsupported constructs must fail explicitly, not silently disappear.

No native ANN/vector-index or full-text search API was found in the released
Python surface. Float-array property round-trips are storage, not search.
Keep an `EmbeddingIndex` port: exact search is a bounded small-corpus oracle;
larger deployments need a measured ANN adapter, potentially a derived sidecar.
Co-location is a preference, not a reason to force whole-graph vector scans.

## Observed costs

`scripts/characterize_gestaltdb.py` reproduces the probe shapes:

```bash
TMPDIR=/tmp/opencode uv run python scripts/characterize_gestaltdb.py > /tmp/opencode/gestaltdb-probes.json
```

Recorded initial scratch-script run: Python 3.11.14, GestaltDB 0.17.0,
LMDB 3.0.0, Linux x86-64, Intel i7-13700F; default serializer (JSON),
128 MiB LMDB map, local disposable stores, default durability settings.
Read timings are medians of five calls on the same handle (warm-dominated,
not isolated cold-cache trials); metadata counts are a subsequent warm call.
Writes are **single trials**, include Python record construction and index
maintenance, and exclude store creation/close. The checked-in script preserves
these shapes; timings will vary. Metadata counts count `get_metadata` calls and
returned bytes, not disk I/O or total KV work. RSS, tail latency, contention,
disk growth and semantic recall were not measured.

| Probe | Shape | Recorded result |
| --- | --- | --- |
| One old node lookup with only one version of that node | 16 / 64 / 256 total commits | 27 / 75 / 267 metadata gets; 0.100 / 0.121 / 0.235 ms |
| Open temporal view, no result query | Same commit counts | 69 / 261 / 1,029 gets; 0.545 / 1.157 / 16.580 ms |
| Publish 256 node versions, maintained indexes | 256 × 1 / 8 × 32 / 2 × 128 | 621.945 / 39.871 / 24.788 ms |
| Open mutable snapshot and read one node | 2,001 nodes, 2,000 edges | 12.350 ms with full provenance hash; 0.328 ms without it |
| Current adjacency | 2,000 neighbors | 0.589 ms eager list vs 0.012 ms for first 20 iterator records (different output sizes) |
| First historical edge on live store | One commit, degree 32 / 128 | 1,202 / 17,042 gets; 2.034 / 21.195 ms |
| Same first edge, already-open MVCC + temporal view | Same hubs, warmed reads | 12 / 12 gets; 0.729 / 2.527 ms; excludes opening views |

The snapshot probe disables only unrelated **mutable-state** provenance hashing
via `current_read_view(capture_provenance=False)`, then opens an authenticated
temporal view on that scope. It does not disable temporal integrity checks.
That mode is not a replacement for mutable provenance when mutable records are
also evidence. Opening and retaining a view has costs of its own.

### Why these results matter

1. **Commit count is a scale dimension.** Temporal index freshness checks compute
   a visibility checksum across commit markers; opening a temporal view also
   authenticates a prefix. A selective logical lookup can still depend on unrelated
   history. Many tiny commits make writes and repeated reads more expensive.
2. **Amortize authentication, do not bypass it.** Live-store cached commits still
   revalidate mutable envelopes/records. A verifiable snapshot permits authenticated
   decode reuse. The 0.17 cache is scope/store/decoder-bound and limited to 256
   entries and 64 MiB of serialized-size accounting, **not decoded heap or RSS**.
3. **Result limits are not work limits.** Historical edge selection materializes
   candidates before yielding. The pinned hub cost still grows with degree.
   Live reservoir sampling also scans degree. `limit=1` or fanout alone cannot
   guarantee bounded physical work, latency, or memory.
4. **Native is not automatically faster.** The release explicitly leaves native
   logical-history batching opt-in: selective native latency/RSS missed adoption
   targets. Arrow transport and Polars experiments do not establish zero-copy
   end-to-end performance or justify bypassing ordinary authenticated reads.
5. **Materialize once, reuse when justified.** Sparse sampler directories avoid
   dense node × relation offsets, but cohort selection, snapshot build/hashing,
   temporal candidates, positive membership, and materialized outputs all cost
   memory/work. Measure the complete pipeline, not only the sampling kernel.

## Revised design requirements

- **D0 / #11:** separate output caps from candidate/byte/work/deadline budgets;
  specify read-session lifetime and provenance identity. Unsupported physical
  work bounds are reported as such. Logical limits alone are not hard RSS/time
  limits; isolate expensive operations in cancellable workers when needed.
- **D1 / #12 and #6:** map neutral writes to bounded `commit_versions` batches,
  with explicit record/byte limits, idempotent replay and transaction rollback
  tests. On LMDB, write temporal history and its current projection within one
  native transaction. Keep the journal/outbox recovery boundary explicit. Preserve
  original source observation/horizon semantics when batching; a DB commit clock
  is not a substitute for an application information horizon. No unbounded batch.
- **D1 / #12:** register required property indexes before queries, validate
  `index_statistics()`, and rebuild deferred indexes at a writer-owned readiness
  barrier. Unindexed exact/range lookups can return empty rather than raise.
  A scoped reader must never repair indexes implicitly. The legacy facade's
  rebuild-on-read behavior is compatibility debt, not the new reader design.
- **D2 / #13:** stream bounded document/parse/chunk batches and reuse content
  artifacts independently of source occurrence/access identity. Measure text,
  embedding and evidence bytes, not just node counts.
- **D3 / #14 and #7:** open one authorized, pinned session per bounded request/run
  unit and reuse it across tool calls; close promptly. Intersect trusted scope
  before ranking. Push selective predicates/cohorts and IDs into supported indexes,
  hydrate only candidates, prefer iterators to eager lists, and cap hubs/work.
  Native indexes are not an access-control boundary. Measure snapshot retention
  under concurrent writes; do not pin an indefinitely growing LMDB read transaction.
- **#2 / #3 / #5:** retain release registry, aliases, application annotations and
  closed-vocabulary validation; translate supported axioms to the native compiler
  instead of adding another logical reasoner. Keep application and native revision
  fingerprints distinct but linked. Reuse structural checks where completeness
  assumptions match; do not turn inferred domain/range types into acceptance proof.
  The current registry treats multiple allowed domain/range classes as
  alternatives; multiple native RDF-style domain/range axioms infer **all** listed
  types. Do not translate those lists literally without an explicit semantic
  mapping and conformance tests.
- **#6:** reuse scoped equality only as a declared analysis aid. Canonical identity,
  conservative resolution, support lineage, review and reversible physical merges
  remain application policy. No global union from a local inference result.
- **#4 / #7:** define exact-search corpus/byte ceilings and the ANN transition
  criterion. Version derived indexes by model/dimension/metric, source snapshot,
  approval/access partition and deletion state. Use eligible scoped candidates
  before top-k, or an explicitly supported bounded filtered-ANN strategy; a global
  top-k followed by filtering is neither isolation nor recall parity.
- **D5 / #16:** fix the current `EventJournal.append()` full-journal reread in its
  runtime slice, using validated prefix/checkpoint recovery and single-writer
  append state. Avoid quadratic append behavior without weakening integrity.
- **D6 / #17:** benchmark cold/warm reads, commit growth, versions/entity, skewed
  hubs, collection selectivity, approval visibility, batch size, payload bytes,
  reasoning closure/proofs, and long snapshot lifetimes. Report p50/p95/p99,
  throughput, candidates/KV work, RSS, disk/index size, rebuild/recovery cost,
  and retrieval quality against a declared target workload/SLO. No SLO is claimed
  here; choose it before calling the architecture scale-ready.

LMDB is the backend exercised here. Transactional PyRex has different snapshot
and columnar tradeoffs; LevelDB lacks unified mutable snapshots. Re-run backend
conformance and complete workload benchmarks before selecting another backend.
Do not disable durability or authentication to produce a speed claim.

## Upgrade and compatibility scope

The adapter now calls `database.temporal.*`; the removed GraphDB wrappers are
not emulated. Startup capability checks inspect `TemporalEngine`. Regression
tests cover LMDB reopen, batched temporal publication, historical edge correction
at a pinned commit, and native rollback of history plus mutable projection.
Existing sink writes remain per-record in this PR: batching and native ontology
integration are planned deliveries, not hidden behavior changes.

A separate disposable **0.12.1 → 0.17.0 LMDB/JSON** check reopened two current
nodes, an edge, and node/edge temporal assertions with the same database identity.
History and node-as-of worked before rebuilding; both node/edge-as-of passed after
an explicit temporal-index rebuild. This is a small characterization, not a
committed legacy fixture or universal migration guarantee. Back up valuable stores,
test a copy with its actual serializer/history, and do not assume downgrade
compatibility after new writes. Never open one directory concurrently with two
GestaltDB versions.

## Tagged evidence

- [Release/changelog](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/CHANGELOG.md)
  and [performance guide](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/docs/performance.rst).
- [Ontology model/compiler](https://github.com/mylonasc/gestaltdb/tree/v0.17.0/src/gestaltdb/ontology)
  and [reasoning construct matrix](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/reasoning/profiles.py).
- [Scoped services](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/graphdb.py),
  [temporal reads/cache](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/_graph/temporal_reads.py),
  [freshness checksum](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/_graph/temporal_indexes.py),
  [candidate selection](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/_graph/temporal_selection.py).
- [Structural validation](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/reasoning/structural.py),
  [equality](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/reasoning/equality.py),
  [range closure](https://github.com/mylonasc/gestaltdb/blob/v0.17.0/src/gestaltdb/reasoning/temporal_closure.py),
  [explicit reasoning adapters](https://github.com/mylonasc/gestaltdb/tree/v0.17.0/src/gestaltdb/reasoning/adapters).
