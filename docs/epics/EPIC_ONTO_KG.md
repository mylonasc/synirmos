# EPIC: Ontology-Driven Knowledge-Graph Construction (ONTO-KG), Documents First

> **Architecture refinement (2026-11-28):** Read
> [EPIC_DECOUPLING.md](EPIC_DECOUPLING.md) before implementing the remaining
> slices. It preserves #1–#8 and their feature ownership, adds source-neutral
> documents, generic graph profiles/scopes, reusable context providers, and
> explicit dependency gates. Its section 7 supersedes only the identified
> design assumptions below (Git-only inputs, ontology version on one mutable
> chunk, run-dependent retry keys, and valid-time-only context reads among them).
> The original proposal is retained for traceability, not asserted as current
> implementation. Slice 0 has scaffolding on `onto-kg-feature`; #2 remains open
> with missing acceptance items. **GitHub Slice 6 (#8) is the final demonstration;
> this document's Phase 6 governance work is a separate future scope.**
>
> Architectural prerequisite tracker: [#10](https://github.com/mylonasc/synirmos/issues/10),
> indexed implementation slices D0–D6: #11–#17. They complement rather than
> renumber the original ONTO-KG slices #2–#8; see the decoupling epic's section 9.
>
> **GestaltDB 0.17 refinement:** The [released capability/scale review](../GESTALTDB_SCALE_REVIEW.md)
> supersedes the bespoke-compiler and blanket "no reasoner" assumptions below:
> reuse native compilation, scoped history/claims, and selected validation or
> inference adapters behind neutral ports. Domain/range inference is not
> extraction validation; native equality is not physical merge approval. Exact
> vector scanning is a bounded reference, not the large-corpus design. Native
> views, batching and indexes have measured costs; no historical scope is free.

## 1. Source analysis

Two reference files in `ref_ontokg_files/` (both inspired by Jesús Barrasa's
ontology-driven GraphRAG talk) were analyzed. They agree on the core pattern
but differ in scope:

| | Playbook (`…_playbook_vgmn.md`) | System spec (`…_system_v_cgpt.md`) |
| --- | --- | --- |
| Scope | Static indexing pipeline: documents → graph → verified retrieval | Full lifecycle platform: bootstrap, ingest, evolve, govern, retrieve |
| Ontology | Reuse a standard (FIBO, SNOMED, Schema.org); formalize classes, `subClassOf`, domain/range; single `.ttl`/`.jsonld` artifact | Versioned canonical ontology + metamodel (IRIs, aliases, constraints, SHACL), retrieval-policy metadata kept separate from domain semantics |
| Architecture | **Dual-layer** (lexical vs domain) + **co-located** storage (text, vectors, entities, ontology in one store) | Same dual-layer, plus staging workspace, audit/version store, vector indexes |
| Retrieval | Operational semantics **in** the ontology (`rag:contextualizingRelationship` via `subPropertyOf`) so traversal is data-driven | Retrieval **policy** as separate versioned config (intent, direction, hops, fan-out, budgets, security) resolved per query |
| Evolution | Day-2: monitor rejections, `ontologyVersion` on chunks, selective re-index | First-class: gap detection → staged candidates → autonomy policy (Observe/Suggest/Guarded/Policy) → human review → versioned publish → impact analysis → incremental migration |

**Ideas worth adopting** (the viable core): one versioned ontology as the
shared contract for extraction *and* retrieval; dual-layer lexical/domain
graphs linked by `MENTIONS`; validation-before-write with rejection routed
to staging, not silently dropped; retrieval behavior as data, not code;
immutable ontology releases with selective re-extraction; evidence-first,
abstain-never-invent, full provenance.

**Ideas to defer or reshape**: a full OWL/SHACL reasoning engine (too heavy
for v1 — an internal metamodel with JSON-schema-equivalent validation
suffices); fully autonomous publication (violates house rules — default to
Observe/Suggest); a second database for vectors or staging.

## 2. Fit assessment: what synirmos already has

| Reference concept | synirmos equivalent (existing) | Gap |
| --- | --- | --- |
| Lexical graph (Document→Section→Chunk) | `SnapshotContent`/`SectionRecord`/`ParsedContent` in `processing/content.py`; Snapshot/File nodes in `storage/graph.py` | No `Chunk` nodes in the graph; sections are records, not nodes |
| Domain graph (typed entities/relations) | WorkItem/ProviderLabel nodes; `DeterministicLabeler` + versioned `TopicRegistry` | No generic `Entity` node, no ontology-defined relation types beyond the 4 link relations |
| Versioned ontology registry | `TopicRegistry` (versioned, aliases, merges, supersession) | No ontology artifact: no classes, properties, domain/range, retrieval tags |
| Ontology-guided extraction | `BasicJereProvider` (EPIC_JERE) + `ParsingContext` | Extraction schema is hardcoded, not compiled from an ontology |
| Validation before write | Grounding checks, domain/range-free; `CoverageGap` taxonomy | No schema-conformance validation against an ontology |
| Staging / autonomy | `DecisionStatus.PROPOSED`/`ABSTAINED`, gaps, journal replay | No staging workspace, no candidate lifecycle, no approval flow |
| Provenance / horizons / budgets | `EvidenceRef`, `AnalysisResult`, `info_horizon`, `BudgetLedger` | Directly reusable — the epic builds on these, not around them |
| Co-located vectors | Nothing (no embeddings anywhere) | Verified: GestaltDB round-trips float-array properties but has **no native vector index** |

The plan below therefore **adapts** the reference pattern to these facts
rather than copying the Neo4j-centric playbook verbatim.

## 3. Target architecture (adapted)

```text
+------------------------------------------------------------------+
|  GestaltDB (single store; temporal versions + current projection) |
|                                                                  |
|  [ ONTOLOGY SUBGRAPH ]  versioned, immutable releases            |
|   OntologyClass / OntologyProperty nodes                        |
|   SUBCLASS_OF / SUBPROPERTY_OF edges; retrieval tags as         |
|   properties (e.g. contextualizing=true) on OntologyProperty    |
|        | guides extraction            | drives retrieval           |
|        v                                  v                      |
|  [ DOMAIN SUBGRAPH ] <--- MENTIONS --- [ LEXICAL SUBGRAPH ]      |
|   Entity nodes + ontology-typed    Document -> Section -> Chunk  |
|   edges (provenance properties)     nodes; text + embedding      |
|                                     properties co-located        |
+------------------------------------------------------------------+
   Staging (PROPOSED results + candidate ontology changes, file-backed
   JSONL like the journal) sits *outside* the authoritative graph.
   Vector search is an EmbeddingIndex port over co-located embeddings
   (brute-force scan v1; no new mandatory dependency).
```

Key adaptations vs the references:

1. **Internal metamodel first, W3C serialization second.** Ontology =
   `FrozenModel`s (`OntologyClass`, `OntologyProperty` with domain/range,
   `OntologyRelease` with version + fingerprint), stored as a versioned
   TOML/JSON artifact. Turtle/JSON-LD export is a formatter, not the
   source of truth. No OWL reasoner, no SHACL engine; conformance =
   domain/range + closed-vocabulary checks (same fail-closed style as
   `JereProposal` grounding).
2. **Ontology lives in GestaltDB as data.** `OntologyClass` /
   `OntologyProperty` nodes + hierarchy edges, `valid_from` = release
   time, so `*_as_of` gives the ontology at any horizon for free and
   retrieval policies resolve against the release active at the query's
   horizon. Retrieval tags are properties on `OntologyProperty` nodes
   (playbook-style, simple); richer per-intent policies (spec-style) come
   later as versioned config, not graph schema.
3. **No native vector index — port + brute force.** Embeddings are
   co-located as `Chunk.embedding` properties (verified to round-trip).
   Search goes through an `EmbeddingIndex` port; v1 is an in-memory
   brute-force scan over bounded corpora behind the same budget ledger.
   The embedding *model* is also a port: deterministic hash-embedding fake
   for tests, real model as an opt-in extra (mirrors the `openai` extra).
4. **Facts start as edges.** Qualified `FactAssertion` nodes (spec §8)
   are deferred; v1 uses typed edges carrying the standard provenance
   properties (`prov_run_id`, `prov_info_horizon`, evidence IDs) — the
   existing `RelationshipWrite` path already supports this.
5. **Staging = persisted `PROPOSED` results.** The `DecisionStatus`
   enum already has `PROPOSED`; the staging workspace is a file-backed
   store of proposed entity/relation/ontology-change candidates with
   evidence, plus an autonomy policy that defaults to Observe/Suggest.
   Nothing reaches the single writer without explicit approval.
6. **Reuse, don't rebuild.** Chunking consumes `ContentIndex`
   (sections/markdown/AST spans); schema compilation feeds
   `BasicJereProvider`; entity resolution extends `_Resolver`-style
   known-set logic; evaluation extends `score_links`/`evaluate.py`.

## 4. Phased plan (documents first)

### Phase 0 — Ontology metamodel + registry

- `processing/ontology/` (new): `OntologyClass`, `OntologyProperty`
  (domain/range, aliases, `contextualizing` flag), `OntologyRelease`
  (immutable, versioned, fingerprinted), `OntologyRegistry` (register /
  alias / merge / deprecate, mirroring `TopicRegistry` semantics).
- Artifact I/O: canonical TOML/JSON; `ontologyVersion` fingerprint.
- Seed with a minimal document-domain ontology (Document, Section,
  Chunk, Person, Organization, Concept, Topic + MENTIONS, PART_OF,
  RELATED_TO) so later phases have something to compile.
- Acceptance: registry unit tests (collisions fail, merges supersede,
  versions immutable); TOML round-trip; architecture test keeps
  `core` dependency-free.

### Phase 1 — Persist the ontology in GestaltDB

- `storage` mappings: ontology release → `OntologyClass` /
  `OntologyProperty` nodes, `SUBCLASS_OF` / `SUBPROPERTY_OF` edges,
  `valid_from` = release time; retrieval tags as edge/node properties.
- Reader: load active release at horizon H via `*_as_of(H)`;
  `compile_schema(release)` emits the closed extraction vocabulary
  (allowed classes, properties, domain/range triples).
- Acceptance: write release v1 + v2, read v1 `as_of` an old horizon;
  compiled schema goldens.

### Phase 2 — Lexical chunk layer + co-located embeddings

- Chunker over `ContentIndex`: Document → Section → Chunk nodes
  (stable IDs from `(content_id, ordinal)`), `NEXT_CHUNK` sequencing,
  structural refs where the parser already yields them
  (`REFERS_TO_DEFINITION`/`CITES_CLAUSE` from Markdown links).
- `Chunk` nodes carry `text` + `embedding` properties;
  `EmbeddingPort` (fake hash-embedding for tests) + `EmbeddingIndex`
  port (brute-force v1, budget-bounded fan-out).
- Stamp `ontologyVersion` on every chunk at extraction time (enables
  selective re-extraction on ontology change).
- Acceptance: chunk goldens from existing `test_content` fixtures;
  property round-trip; index recall@k = 1.0 on fixture corpus vs
  brute-force oracle (itself, trivially — plus a small hand-labeled set).

### Phase 3 — Ontology-guided JERE extraction

- Schema compiler output becomes the provider's closed vocabulary:
  `BasicJereProvider` (or a thin `OntoJereProvider` wrapper) validates
  entity kinds and relation domain/range against the active release
  **before** proposing; violations become `CoverageGap`s
  (`onto-unknown-class`, `onto-domain-range-violation`) routed to staging
  with evidence — never invented into the graph.
- Cross-layer `MENTIONS` edges chunk → entity, emitted as
  `RelationshipWrite`s through the existing single-writer path.
- Acceptance: fake-model tests — conforming proposal accepted;
  out-of-ontology class/relation rejected + staged; domain/range
  violation rejected; `ontologyVersion` recorded on every write.

### Phase 4 — Entity resolution + idempotent domain writer

- Resolution order: exact canonical key → normalized name + class
  match → embedding similarity as a *candidate signal only* (never
  sole proof, per spec §9.1); ambiguous merges → staged, reversible,
  alias-preserving.
- Idempotency keys on (`chunk_id`, `ontology_version`, `run`) so
  retries and replays never duplicate facts; corrections append new
  versions (existing `correct_entity`/`correct_relationship` path).
- Acceptance: dedup tests (same entity twice → one node, two
  `MENTIONS`); merge/unmerge round-trip; replay idempotence test.

### Phase 5 — Dynamic ontology-driven retrieval (verify the loop)

- Retriever: embed query → `EmbeddingIndex` top-k chunks →
  `MENTIONS` hop to entities → read allowed relations from the
  ontology subgraph **in the same horizon** (`contextualizing=true`
  tags) → bounded traversal (hops, fan-out, token budget) →
  assemble chunk text + subgraph + citations.
- Toggling a tag in a new ontology release changes retrieval with no
  code change — the playbook's verification test, adapted to
  GestaltDB + horizon reads.
- Acceptance: end-to-end test on a fixture corpus (answer cites
  chunk evidence; tag-toggle flips the retrieved context);
  retrieval metrics logged (recall@k, context precision, cost).

### Phase 6 — Evolution loop with human-in-the-loop (Observe/Suggest only)

- Gap mining: aggregate staged rejections (repeated unknown
  predicates/classes) into candidate ontology changes with evidence,
  impact estimates, and alternatives (spec §9.1 classification).
- Autonomy policy config (default-deny): Observe logs, Suggest stages;
  Guarded/Policy modes are parsed but *refuse to auto-publish* until
  a later epic explicitly enables them with calibration data.
- Approval flow: approve/reject/revise/alias/merge decisions are
  timestamped, attributed `AnalysisResult`s; publication creates a new
  immutable release; migration = selective re-extraction of chunks
  whose `ontologyVersion` predates the release (impact analysis first,
  dry-run support).
- Acceptance: candidate lifecycle state-machine tests; publish →
  migrate → re-query test; rollback to prior release test.

## 5. Risks and explicit non-goals

- No OWL/SHACL engine and no `neosemantics`-style importer in v1; if
  interop with a real FIBO/SNOMED subset is needed, it arrives as a
  Turtle *importer into* the internal metamodel, not as a reasoner.
- Brute-force vector search bounds corpus size; corpora beyond that
  need an ANN backend behind the same port (explicit future stage,
  not silent scope creep).
- Autonomy stays human-gated: any "auto-publish" path is a separate
  epic requiring calibration data, two-person rules for high-impact
  changes, and rollback drills.
- Structured sources (CRM/ERP/CSV) reuse the same ontology later;
  documents come first per the request.

## 6. Implementation slices

Tracked under parent issue #1 (index #2–#8), one notebook per slice in
`examples/onto_kg/notebooks/`:

| Slice | Issue | Content |
| --- | --- | --- |
| 0 | #2 | Ontology metamodel + registry + seed document ontology |
| 1 | #3 | Persist ontology in GestaltDB + schema compiler |
| 2 | #4 | Lexical chunk layer + co-located embeddings + EmbeddingIndex port |
| 3 | #5 | Ontology-guided JERE extraction + validation + staging |
| 4 | #6 | Entity resolution + idempotent domain writer |
| 5 | #7 | Dynamic ontology-driven retrieval |
| 6 (final) | #8 | Real-document demonstration with notebooks |

## 7. Open questions (for iteration)

1. Internal metamodel vs RDF/OWL canonical form: is TOML/JSON +
   optional Turtle export sufficient, or is triplestore interop a
   release criterion?
2. `FactAssertion` nodes: at what point do edge-properties stop being
   enough (contradictions, validity intervals, per-fact review state)?
3. Chunking authority: derive chunk boundaries purely from existing
   `SectionRecord`s, or introduce an overlapping-window chunker for
   long sections?
4. Embedding model choice for the opt-in extra (and its privacy/budget
   story, mirroring `LLMSettings` consent gates)?
5. Reviewer UX for Phase 6: CLI-first approvals vs a minimal web UI?
