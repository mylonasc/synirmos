# Extensible repository analysis: refactoring plan

Status: proposed architecture and staged migration, with initial platform-port
scaffolding implemented. This is not a claim that the pipeline is already
provider-neutral, remote-authoritative, or multi-language.

The [document/graph/context decoupling epic](epics/EPIC_DECOUPLING.md) adds a
document-first implementation track for ONTO-KG and JERE. It delivers selected
neutral-contract, storage-mapping, and pure-parser seams from P1/P4/P5 without
claiming completion of those phases or requiring all Git/provider migrations
first. Remote-authoritative Git and the other provider/language phases below
remain separately scoped; standalone local-text capture is not a fallback
authority for repository history.

For the released GestaltDB 0.17 baseline, follow the
[capability/scale review](GESTALTDB_SCALE_REVIEW.md): reuse native scoped readers,
transactions, history and selected ontology/reasoning capabilities; benchmark
batching, commit growth, snapshot costs, candidate work and ANN requirements.
Those are delivery acceptance criteria, not already integrated optimizations.

## 1. Decisions and scope

1. **GitHub is the first concrete adapter.** Preserve its existing behavior and
   evidence replay during migration. GitLab follows, using merge requests and
   its native issues/work items. Jira is a future issue-tracker integration.
2. **A platform is not a repository.** A platform instance identifies a service
   deployment or tenant. It can expose multiple projects and repositories. A
   repository can be associated with a code host and independent issue trackers.
3. **Git is not a hosting platform.** Git commits, trees, blobs, refs, and diffs
   belong to `repository_history/`. GitHub/GitLab API payloads belong to
   `platform_integrations/`. A GitLab adapter must not reimplement Git traversal.
4. **Remote state is authoritative.** The initial supported mode has no local
   development history or dirty worktree content as an analysis source. Local
   storage is a cache of captured remote objects, not an alternative truth.
5. **A worktree is local execution state, not a GitHub/GitLab API entity.** PRs
   and MRs are hosted review objects. Uniformity means shared ingestion contracts
   for remote resources, not pretending that worktrees are hosted work items.
6. **Language support is a separate extension axis.** Adding a platform must not
   require changing a code parser; adding a language must not require changing a
   Git adapter, graph sink, or hosting-platform implementation.
7. Preserve evidence, temporal semantics, budgets, replay, and explicit coverage
   gaps. Extensibility must not weaken the current safety guarantees.

Non-goals for this refactor: implementing all languages, implementing Jira,
reconstructing every historical branch movement, bidirectional synchronization,
mutating upstream work items, or creating a distributed plugin marketplace.

## 2. Current coupling to remove

| Current location | Problem | Destination/resolution |
| --- | --- | --- |
| `sources/github.py` | HTTP, retries, caches, provider DTOs, discovery, and event conversion share one large module | Split under `platform_integrations/github/`; normalize through shared contracts |
| `sources/git.py` | Clone/fetch, traversal, tree parsing, local branches, worktrees, and identity/presentation are combined | Split under `repository_history/`; capture remote refs explicitly |
| `core/models.py:RepositorySpec` | Repository identity, provider selection, time window, and integer issue allowlists are bundled | Separate repository identity, capture selection, and platform bindings |
| `core/models.py:RuntimeConfig` | One built-in `github` section assumes a single platform | Named integration instances and explicit repository/tracker associations |
| `core/ids.py:IdFactory` | Work items are repository-scoped integers; repository identity is URL-derived | Versioned external identities and explicit association/migration rules |
| `processing/content.py` | Fetching snapshots, language detection, Markdown parsing, Python AST traversal, and assembly are combined | Pure parser plugins plus a snapshot/content coordinator |
| `processing/labeling.py` | Accepts `GitHubWorkItem` and embeds `github` in provider-label results | Consume normalized work items and provider-qualified labels |
| `processing/linking.py` | GitHub URLs, PR fields, numeric references, and graph-write types leak into inference | Integration-specific reference codecs; neutral inference; storage-owned mapping |
| `storage/graph.py` | `GitHubDiscovery`, GitHub IDs, and PR semantics are hardcoded | Map neutral records, retaining native provider provenance |
| `reporting/inspection.py` | Public queries expose `GitHubDiscovery` and GitHub-only lookup forms | Provider-neutral projections and explicit external references |
| `runtime/worker.py` | Replayable jobs must survive any new result/schema shapes | Versioned job inputs, parser/config fingerprints, and migration tests |

The existing six responsibility-based packages are a first step, not the end
of modularization. Merely moving large modules into new folders does not remove
these type, identity, and behavioral dependencies.

## 3. Proposed package layout

Use `synirmos` as the public namespace, matching the distribution and standard
`src/synirmos/` layout. The earlier `repo_history` namespace has been retired;
see the breaking-change notes in `CHANGELOG.md`.

```text
synirmos/
  core/
    domain/
      repositories.py       # logical RepositoryId, CommitId, RefName, SnapshotId
      external.py           # platform instance, ExternalRef, external scope
      work_items.py         # work items, change requests, comments, activities
      content.py            # source spans, symbols, sections, references
      evidence.py           # evidence IDs, observations, coverage
    ports/
      blobs.py              # read-only BlobSource; no pygit2 types
      clocks.py
      evidence.py
      persistence.py
    config.py
    events.py
    ids.py
    budgets.py
  platform_integrations/
    interfaces.py           # PlatformIntegration, GitHostingPlatform, small ports
    models.py               # ingestion envelopes; re-export promoted domain types
    registry.py             # explicit factory/instance registration
    common/
      transport.py          # bounded transport primitives, not endpoint semantics
      evidence.py           # raw response envelopes and replay
      errors.py
    github/
      integration.py
      client.py
      dto.py
      fetcher.py
      normalizer.py
      references.py
    gitlab/
      integration.py        # placeholder now; MR/work-item adapter later
      client.py
      dto.py
      fetcher.py
      normalizer.py
      references.py
    jira/
      integration.py        # explicit placeholder; no Git-hosting inheritance
      references.py         # future Jira keys/URLs, not implemented now
  repository_history/
    interfaces.py           # RemoteRefSource, GitObjectStore, HistoryReader
    models.py               # capture manifests, commits, trees, diffs
    capture.py              # remote snapshot/consistency policy
    selection.py            # pure selection and boundary calculations
    indexing.py             # assemble history from immutable object readers
    git/
      transport.py          # pygit2 fetch/advertise; tool-owned object cache
      objects.py            # read commits/trees/blobs by object ID
      refs.py               # captured remote refs, not local HEAD guesses
      diffs.py
    workspace.py            # optional local-cache verification, not source truth
  parsing/
    interfaces.py           # CodeParser, DocumentParser, detector contracts
    models.py               # parse inputs/results/capabilities
    registry.py             # explicit parser selection
    detection.py
    code/
      python_ast.py
      tree_sitter.py        # optional future backend, not a mandatory dependency
    documents/
      markdown.py
      plain_text.py
  processing/
    content.py              # coordinate BlobSource -> parser -> snapshot assembly
    labeling.py
    linking.py
    enrichment.py
  storage/
    mappings/               # repository, work-item, content, and link mappings
    graph.py
  runtime/
    orchestration.py
    worker.py
  reporting/
    inspection.py
    viz.py
    evaluate.py
```

Create these modules as responsibilities move; do not populate every proposed
file with empty abstractions. Do not reintroduce a separate legacy namespace or
flat compatibility layer. `repository_history` is recommended over `git`
at the package root: it names the domain while `repository_history.git` names
the implementation and avoids confusion with hosting-platform APIs.

### Dependency rules

- Domain values and ports depend only on the standard library and shared
  validation primitives. They import no HTTP, Git, parser backend, or database.
- `platform_integrations` owns external API behavior. Its pure normalizers may
  depend on domain types but not on Git traversal, parsing, or graph storage.
- `repository_history` knows object IDs and remote refs, not PR/MR/Jira DTOs.
- `parsing` consumes bytes and metadata. It imports neither repository-history
  readers, platform clients, orchestration, nor graph storage.
- Processing consumes normalized domain values and read-only ports. Move
  `link_edge_writes` to storage mappings so linking no longer imports graph writes.
- Runtime is the composition root: it selects implementations and connects them.
  Reporting consumes read projections, never transport clients.
- Provider-specific DTOs, pagination shapes, and URL patterns never cross the
  normalizer boundary. Unsupported native fields remain accessible as evidence.

Enforce these rules recursively with import-boundary tests. As the package grows,
consider import-linter rather than growing custom AST rules indefinitely.

## 4. Platform contract

### Identity and associations

Use distinct values for:

- `PlatformInstance(provider, base_url)`: GitHub.com, a GitHub Enterprise instance,
  a GitLab deployment (including a deployment prefix), or a Jira tenant.
- `ExternalRef(platform, scope, kind, native_id)`: globally qualified identity,
  with string native IDs rather than integer-only repository issue numbers.
- `RepositoryId`: logical Git repository identity, independent of an API client,
  branch, checkout directory, or mutable display URL.
- `RepositoryBinding`: explicit association from a hosted project to a repository.
  Jira uses explicit tracker/project associations, not a fake Git repository.

Do not assume every scope is `owner/name`: GitLab namespaces can be nested and
Jira projects are not repository paths. Prefer persistent native project IDs for
identity and preserve paths/keys as aliases. A rename is not a new entity; a
different deployment with the same project/issue number is not the same entity.

PR and MR normalize to **ChangeRequest**. A change request is a specialized work
item with one canonical external identity, not a duplicated issue plus unrelated
PR entity. GitHub's issue and pull-request endpoints must coalesce accordingly.
GitLab issue IID `12` and MR IID `12` must not collide. Preserve the native kind,
key, state, provider type, and raw evidence rather than flattening them away.

Jira issues can relate to several repositories. Their IDs must not change or be
duplicated when another repository is associated with them. Associations are
explicit configuration/evidence-backed relationships, not ownership assumptions.

### Small interfaces, not a universal client

The initial scaffold in `platform_integrations/interfaces.py` defines:

| Interface | Responsibility |
| --- | --- |
| `EvidenceFetcher.fetch_page(request, ledger=...)` | Retrieve exactly one bounded raw page, recording every attempted request |
| `PayloadNormalizer.normalize(page)` | Pure conversion of captured evidence into normalized events and coverage |
| `PlatformIntegration` | Instance identity, capability declaration, fetcher, and normalizer composition |
| `GitHostingPlatform.resolve_repository(project, ledger=...)` | Resolve an explicit hosted-project association without opening Git |

`CollectionRequest`, `EvidencePage`, and `PlatformBatch` provide one shape for
collection, evidence, and normalized output. Normalization must not follow
pagination links or perform hidden parent/commit lookups: schedule those as
explicit bounded requests in discovery/orchestration.

This first scaffold uses the existing `IngestEvent` envelope. **It does not yet
standardize every event payload or make current downstream consumers portable.**
Before migrating consumers, add typed domain records and a shared event mapper.
Promote stable identity values from the scaffold to `core/domain/external.py`,
retaining re-exports so there is only one definition of each type.

Planned normalized records:

- `WorkItem`: qualified identity, native key/type/state, title/body observations,
  authors, source timestamps, observation time, evidence references.
- `ChangeRequest`: work-item identity, source/target repository IDs, optional
  source/target refs and observed commit IDs, draft/review/merge evidence.
- `Comment`, `Activity`, `LabelObservation`, `HierarchyRelation`: independently
  identified observations/events, not unstructured provider dictionaries.
- `RevisionAvailability`: per-field historical availability, with provider-neutral
  reasons; lack of an edit-history endpoint is not an empty edit history.

Capabilities declare supported collections/history features. A supported feature
can still be denied, unavailable, budget-limited, or partially observed. Preserve
those outcomes separately. Never interpret a placeholder, permission error, empty
cache, or truncated page sequence as a successful empty collection.

### Uniform collection and parsing pipeline

```text
explicit selection/allowlist
  -> adapter-owned request planning
  -> bounded fetcher + credentials + shared budget
  -> immutable raw evidence store
  -> pure provider normalizer
  -> typed domain records
  -> shared event mapping
  -> replay / analysis / persistence
```

The orchestrator owns total requests, items, pages, bytes, retry spending, and
checkpoints. Fetchers expose opaque continuation tokens rather than leaking
GitHub `Link` headers or GitLab pagination headers to downstream code. Store the
request and continuation context so replay does not depend on a live server.

Transport failures use explicit typed errors for authentication, permission,
rate limit, unsupported capability, missing evidence, malformed response, and
scope violations. Reuse transport infrastructure only where behavior is truly
shared; provider rate-limit and endpoint semantics remain adapter-owned.

Separate public identity URLs from request URLs. Never place credentials in IDs,
logs, evidence, or cache keys. Request URL scope validation and redirect handling
must prevent token forwarding to another origin. Credential-free instance URLs
do not by themselves make arbitrary response URLs safe.

### Reference and presentation codecs

Each hosting/tracker integration supplies reference parsing and source-link
formatting, independently of transport:

- GitHub: PR/issue URLs and repository-qualified `#123` references.
- GitLab: MR `!123`, issue/work-item references, nested namespaces, self-hosted URLs.
- Jira: qualified project keys such as `ENG-123` and tenant URLs.

Resolve only against known, in-scope entities. Bare `#123` needs an explicit
platform/repository context; otherwise abstain. References are not evidence that
an undiscovered remote item exists or that a PR/MR resolved it. Treat a fork's
head repository and a target repository as different identities, even when the
branch names match. Commit/blob links use the selected integration's formatter,
not hardcoded GitHub URL templates in the Git reader.

## 5. Remote-authoritative Git contract

### Authority and local state

Prefer a tool-owned **bare object cache** with an explicit remote snapshot.
Read immutable objects by captured object ID. Do not enumerate arbitrary local
branches, infer authority from `HEAD`, or parse tracked files from a working
directory. A cached object not selected by captured remote evidence does not
become source truth merely because it exists locally.

If an existing checkout is accepted as a cache, validate the selected refs against
the remote snapshot. A developer checkout cannot silently claim a synchronized
state. Ahead/behind/divergent branches, missing mappings, dirty tracked/staged
content, and relevant untracked source files produce a `LocalStateDrift` error
in this initial strict mode. Do not stash, reset, clean, force-checkout, or rewrite
the caller's branches. Supporting local development state is a separate future
mode with distinct provenance, not a fallback.

Detached historical snapshots are allowed only as explicit object-ID reads from
the captured remote ancestry; they are not observations of a current remote
branch checkout. Worktrees, if a future parser needs scratch files, are derived
execution resources pinned to those objects and excluded from repository-domain
truth. The current `GitIndex.worktrees` becomes legacy diagnostic metadata, not
an input to branch containment or remote entity creation.

### Capture algorithm and consistency

1. Resolve configured repository bindings and permitted clone/fetch locations.
   Do not use repository-owned Git config, hooks, filters, or commands as trusted
   executable configuration.
2. Enumerate selected remote refs and resolve the requested anchor to full object
   IDs. Persist a capture ID, repository ID, ref targets, observation time, source,
   scope, and completeness/budget information.
3. Fetch only selected/reachable objects with capped deepening into the owned
   cache. Verify requested objects actually arrived. Do not trust cached local
   branch names or stale remote-tracking refs.
4. Re-observe selected remote refs where needed to detect movement during capture.
   Retry within the same budget, or fail strict capture if a stable selected-ref
   set cannot be established. Pin successful analysis to the resulting IDs.
5. Select commits, boundary trees, blobs, and diffs from that immutable capture.
   Record missing ancestry and limits without silently broadening the selection.
6. Fetch hosted work-item/review evidence separately and stamp its observation
   time. The Git server and hosting APIs do **not** provide a shared atomic
   transaction. Record capture intervals and mismatches instead of claiming one.

Offline replay uses a previously captured manifest and evidence, clearly dated;
it cannot claim to reflect the current remote. Provider PR/MR commit lists are
evidence about the review object, not authority to invent missing Git objects.

A missing ref in an incomplete/denied listing is not proof of branch deletion.
Even a complete current listing establishes an absence at observation time,
not a historical deletion timestamp. Branch containment is reachability from
captured tips, not universal reconstruction of past branch movements.

### Git interfaces and implementation split

Proposed ports in `repository_history/interfaces.py`:

```python
class RemoteRefSource(Protocol):
    def capture(self, selection: CaptureSelection, *, ledger: BudgetLedger) -> RemoteSnapshot: ...

class GitObjectStore(Protocol):
    def commit(self, oid: CommitId) -> CommitRecord: ...
    def tree(self, oid: TreeId) -> TreeRecord: ...
    def blob(self, oid: BlobId) -> bytes: ...

class HistoryReader(Protocol):
    def select(self, snapshot: RemoteSnapshot, selection: HistorySelection) -> HistoryIndex: ...
```

These signatures are design sketches, not implemented imports. Fetching belongs
to capture/transport; selection/indexing must not fetch unexpectedly. Put generic
blob access in a core port so parsing/processing can use an in-memory blob map in
tests without importing `pygit2` or the Git implementation.

Distinguish commit IDs, tree IDs, blob IDs, and ref names. Avoid spreading the
current fixed 40-hex SHA-1 assumption into new contracts; support object-format
metadata and future SHA-256 IDs with explicit algorithm validation. Handle roots,
merges, rename evidence, submodules/gitlinks, binary/LFS pointers, shallow history,
forks, and missing objects through typed results and coverage.

## 6. Multi-language parsing contract

Split `processing/content.py` into byte acquisition, language detection, pure
parsing, and provenance assembly. The coordinator stays in processing; parsers
live in `parsing/` and never traverse Git or fetch a platform resource.

Proposed interfaces in `parsing/interfaces.py`:

```python
class LanguageDetector(Protocol):
    def detect(self, source: ParseInput) -> DetectionResult: ...

class CodeParser(Protocol):
    descriptor: ParserDescriptor
    def parse(self, source: ParseInput, limits: ParseLimits) -> ParseResult: ...

class DocumentParser(Protocol):
    descriptor: ParserDescriptor
    def parse(self, source: ParseInput, limits: ParseLimits) -> ParseResult: ...
```

- `ParseInput`: bytes, path hint, content digest/algorithm, optional encoding,
  language/dialect hint. No live repository, DB, HTTP client, or mutable registry.
- `ParserDescriptor`: stable parser ID/version, supported languages/dialects,
  capabilities (symbols/imports/sections/references), optional backend version.
- `ParseResult`: explicit status, typed symbols/imports/sections/references,
  diagnostics, capability/coverage details, and parser/config provenance.
- `SourceSpan`: canonical half-open byte offsets into original content, with
  documented line/column conventions and source maps when decoding changes
  offsets. Test UTF-8, other supported encodings, CRLF, BOMs, and invalid bytes.

Language identity must be extensible, not a closed `Literal` requiring edits to
the coordinator whenever a language is added. Detection and parsing are distinct:
recognizing `.rs` does not imply implementing Rust symbol analysis. Mixed-language
repositories select parsers per blob/path; Markdown code fences and embedded
languages retain nesting and source mapping where actually supported.

Start by extracting the current Python AST and Markdown parsers unchanged behind
these contracts. Add deterministic plain-text fallback and an explicit parser
registry. Next, prove extensibility with one additional language (recommended:
TypeScript/JavaScript through an optional tree-sitter backend), not many shallow
stubs that pretend to offer semantic understanding.

Cache parsing by content digest, language/dialect, parser ID/version, backend
version, normalized configuration, and resource limits. Cache parsed content
independently of snapshot assembly so identical bytes can be reused without
losing commit/path provenance or reusing an invalid truncated result.

Parser dependencies are optional extras. Registration is explicit and ordered;
ambiguous matches and missing plugins are errors/coverage results, not dependent
on import order. Consider allowlisted entry points only after the in-process
registry is stable. Installing a package must not automatically execute every
third-party parser. No parser imports/executes target code, runs builds, or reads
arbitrary neighboring files. Enforce byte/node/time/memory limits; native parser
crashes need process isolation rather than a Python-only timeout promise.

## 7. Migration sequence and acceptance gates

Use small reviewable changes. Each phase must pass existing replay/evidence tests
before the next removes a legacy path.

| Phase | Work | Depends on | Acceptance gate |
| --- | --- | --- | --- |
| P0 | Publish this plan; initial platform interfaces/envelopes; explicit GitLab/Jira markers | None | Structural fakes, qualified IDs, URL hygiene, bounded requests, and placeholder failures tested; current pipeline unchanged |
| P1 | Neutral domain records, stable IDs, associations, typed selection/config, capability/error contracts | P0 | Host/namespace/kind collisions impossible in fixtures; Jira issue can associate with two repos without duplication; old ID migration documented |
| P2 | Split GitHub transport, DTOs, fetcher, normalizer, and references under `platform_integrations/github` | P1 | Existing recordings replay offline; shared adapter contract suite passes; normalization performs zero I/O; budgets/retries unchanged |
| P3 | Extract `repository_history` and remote capture; retire local refs/worktrees as authority | P1 | Remote movement, stale refs, missing objects, drift rejection, and offline snapshot semantics tested with synthetic remotes |
| P4 | Switch graph mapping, linking, labeling, inspection, and orchestration to neutral projections | P2, P3 | No consumer imports GitHub DTOs or hardcodes `github`; graph/results preserve IDs/provenance or use a tested migration |
| P5 | Extract parser contracts, Python/Markdown implementations, detector, cache, and snapshot assembler | P3 | Existing parsing goldens preserved; pure parser suite needs no Git/HTTP/DB; mixed-language routing and cache invalidation tested |
| P6 | Add one optional second-language parser and packaging tests | P5 | A new parser installs/registers without edits to runtime, Git, provider adapters, storage, or reporting |
| P7 | Implement GitLab MRs/work items and run the same adapter/domain contracts | P4 | Cross-provider fixtures yield equivalent domain semantics without edits to downstream consumers; self-hosted/nested scopes covered |
| P8 | Design Jira association/discovery increment; keep marker until separately scoped | P4 | Requirements and tenant/project identity agreed; no fake success or Git-host assumptions in placeholder |

P3 and P2 can be developed independently after shared identity contracts settle.
P5 need not wait for GitLab. Jira implementation is intentionally not part of
the initial migration. Avoid simultaneous rewrites of all adapters and parsers.

### Compatibility and persisted data

- Preserve established public `synirmos` contracts as future modules move, using
  focused re-exports where needed. The initial `repo_history` -> `synirmos`
  namespace change is explicitly breaking, not a second installed package.
  Move each implementation once; do not keep divergent code paths indefinitely.
- Version config, event payloads, graph identity schemas, parser caches, and job
  envelopes separately. Provide readable diagnostics for unsupported versions.
- New qualified IDs must not silently reinterpret old `IdFactory.work_item`
  hashes. Retain a legacy ID reader/alias table or publish an explicit migration
  manifest; test graph links, journal replay, and worker resumption across it.
- Persist immutable raw provider evidence. Re-normalize it into a new, versioned
  event stream/run; do not mutate old journals in place or overwrite provenance.
- Do not rewrite the checked-in reference workload artifacts to conceal drift
  in output. Use old artifacts for compatibility checks and new artifacts for
  explicitly versioned behavior changes.

## 8. Testability and quality strategy

| Test layer | Essential cases |
| --- | --- |
| Domain unit tests | Cross-host/scoped identity, native types/states, relations, observation horizons, no repository ownership for tracker issues |
| Fetcher contracts | Auth/permission/rate-limit errors, pagination, malformed/oversized payloads, cross-origin URLs, retries spending budget, deterministic recorded replay |
| Pure normalizer tests | Same evidence -> same output; no I/O/clock calls; PR/issue endpoint coalescing; MR vs issue IID collisions; unavailable history vs empty history |
| Git contracts | Bare synthetic upstream + separate cache; capture/fetch races; ahead/behind/divergent checkouts; dirty worktrees; force pushes/ref deletion; shallow/fork/merge cases |
| Parser contracts | Python/Markdown goldens, second-language conformance, unsupported dialects, malformed inputs, Unicode spans, limits, cache keys, no target execution |
| Consumer contracts | One neutral fixture per GitHub/GitLab/Jira shape, no provider DTO imports, factual/inferred links and horizons remain distinguishable |
| Integration tests | Real adapters against fake transports and recorded payloads; Git library against temporary local remotes; real remote services remain opt-in |
| Persistence/replay | Duplicate ingestion, corrections, resume budgets, version migrations, cross-repository external items, reproducibility from captured evidence |
| Packaging | Core wheel/source distribution works without examples or optional language plugins; missing extras fail clearly; registry imports are lazy |

Inject transports, clocks, budgets, object stores, parser registries, and evidence
stores. Prefer behavioral fakes and shared contract suites over mocking private
method chains. Use parametrized/property-based tests for identity, pagination,
event ordering, source spans, and idempotence where their value justifies them.

Keep the current 90% combined coverage floor, but require direct behavioral tests
for all new contract guarantees rather than relying on a percentage. Preserve
the existing complexity ceiling of 30 while targeting <=10 for new functions;
decompose high-complexity hot spots instead of increasing the ceiling. Report
recursive per-module complexity/maintainability so nested adapters/parsers do
not disappear from metrics. Track import-boundary violations and replay/schema
compatibility as release gates alongside Ruff, coverage, builds, and wheel tests.

## 9. Implemented now versus deliberately deferred

Implemented with this plan:

- `platform_integrations/models.py` and `interfaces.py`: deployment-qualified
  identities, explicit repository bindings, bounded collection requests, raw
  evidence pages, normalized batch envelopes, and small platform ports.
- `platform_integrations/github/`: reserved migration namespace, not another
  implementation of the current adapter.
- `platform_integrations/gitlab/` and `jira/`: discoverable placeholders that
  fail explicitly on construction and are not registered as supported providers.
- Offline contract tests and recursive quality-metric discovery.

Deferred to the phases above: migrating GitHub behind the new ports, typed
cross-provider work-item payloads, enforcing remote capture/drift rules in the
active pipeline, extracting `repository_history/`, extracting parser plugins,
and implementing GitLab or Jira. The current GitHub path remains operational;
no new configuration should advertise unsupported providers as working today.
