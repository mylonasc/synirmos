# Synirmos

**Evidence-backed repository-history analysis.**

Synirmos is a standalone Python framework for indexing Git history, source code,
documentation, and GitHub work items, then tracing how they connect over time.
It keeps source evidence, normalized events, and derived analysis distinct so
you can inspect not just what changed, but why a label or relationship was
assigned and what information was available at the time.

- Select bounded history by commit anchor and time window, with historical
  baseline snapshots and explicit coverage gaps.
- Extract Markdown structure and Python symbols without executing repository code.
- Capture and replay GitHub evidence for issues, pull requests, labels, and hierarchy.
- Assign topics and resolve cross-entity links deterministically, with optional
  LangChain-based LLM enrichment.
- Inspect changes, work-item traces, branch containment, and topic timelines;
  persist temporal graphs and render evidence-linked visualizations.

[GestaltDB](https://github.com/mylonasc/gestaltdb) is the current temporal graph
storage backend, not the scope of the project. Git indexing, content extraction,
labeling, linking, and in-memory inspection can be used without opening a graph
database. GitHub is the currently implemented work-item provider.

See the [project specification](PROJECT_SPEC.md) for architecture, temporal
semantics, safety, and scope. Both the uv/Python distribution and import package
are named `synirmos`.

## Development

```bash
git clone git@github.com:mylonasc/synirmos.git
cd synirmos
uv sync --locked --dev
uv run pytest
```

Synirmos is a packaged uv project with a committed `uv.lock` and a Python 3.11
development default in `.python-version`. Python 3.11–3.13 are supported.
To use it from another uv project:

```bash
uv add "synirmos @ git+https://github.com/mylonasc/synirmos.git"
```

Importing the package does not require provider credentials. Live GitHub and LLM
runs are opt-in. The default test suite needs no secrets or network access.

Build the wheel and source distribution using uv's native backend and standard
`src/synirmos/` layout:

```bash
uv build
```

Artifacts are written to `dist/`. No package-name overrides or extra build
scripts are needed. See [CHANGELOG.md](CHANGELOG.md) for changes and import
migration notes.

## Local quality checks and CI

```bash
uv run python scripts/check.py          # all checks used by CI and pre-push
uv run ruff check .                    # lint, imports, Python modernization, complexity
uv run ruff format --check .           # formatting (omit --check to format)
uv run pytest --cov=synirmos --cov-report=html
uv run python scripts/metrics.py       # complexity, maintainability, source size
uv run pre-commit install              # install pre-commit and pre-push hooks
```

Every push and pull request runs the full checks on Python 3.11, 3.12, and 3.13
via [GitHub Actions](.github/workflows/quality.yml). Lint and formatting must
pass, combined statement/branch coverage must remain at least **90%**, and
function cyclomatic complexity is capped at **30** (the initial ceiling for
existing code, not a target for new functions). CI also builds the distribution,
smoke-tests an installed wheel outside the source tree, and runs the example's
separate offline regression test. Live GitHub/LLM runs are never part of CI.

Reports are generated under `reports/`: coverage XML/HTML, per-module
maintainability and complexity JSON, and a Markdown summary. CI uploads these
as artifacts and publishes the metrics summary. Hooks run lint/format checks
before commits and the full quality suite before pushes; install them once per
clone. All checks are also available manually without hooks.

## PyPI releases

Increasing `project.version` on `main` triggers
[`publish-pypi.yml`](.github/workflows/publish-pypi.yml). It reruns the Python
quality matrix, builds and validates the distributions, then publishes using
PyPI trusted publishing (OIDC, no API-token secret). Unchanged versions are not
published. See [publishing instructions](docs/PUBLISHING.md) for version bumps,
lockfile updates, retries, and trusted-publisher configuration.

## Package structure

The [detailed refactoring plan](docs/REFACTORING_PLAN.md) describes the next
steps toward remote-authoritative Git captures, interchangeable GitHub/GitLab
integrations, future Jira issues, and independent language-parser plugins.
Initial platform contracts live in `platform_integrations/`; the existing
GitHub pipeline has not yet been migrated to them.

```text
src/synirmos/
  core/        # domain contracts, configuration, IDs, events, budgets, protocols
  sources/     # Git and GitHub evidence adapters
  processing/  # content parsing, topics, LLM enrichment, linking
  storage/     # GestaltDB persistence and backend capability checks
  runtime/     # journal/replay orchestration and worker processes
  reporting/   # inspection queries, SVG rendering, evaluation metrics
```

Implementations and imports use these domain packages directly, such as
`synirmos.sources.git` and `synirmos.processing.content`. There is no separate
legacy namespace or flat compatibility layer to package. Boundary tests prevent
example dependencies or provider imports from entering `core`.

## Analyze your own repository

The library accepts a repository URL, a full commit SHA, a UTC time window, and
an explicit work-item allowlist. Start with the generic
[`configs/repository.toml`](configs/repository.toml) template; the library has
no built-in repository selection or implicit configuration path.

Copy that configuration to your own TOML file and set:

- `repository.owner`, `name`, and `url` to your target repository.
- `repository.anchor` to a full 40-character commit SHA.
- `repository.window.start` and `end` to your UTC interval (start inclusive,
  end exclusive).
- `repository.allowed_work_items` to the issue/PR numbers to fetch, or `[]`
  for no GitHub work-item discovery.
- Budgets, cache paths, and graph settings for your workload.

For local Git and content analysis, use an existing checkout containing the
anchor and required ancestry:

```python
from synirmos import load_config
from synirmos.processing.content import ContentExtractor
from synirmos.sources.git import GitHistory

config = load_config("my-repository.toml")
history = GitHistory.open("/path/to/checkout", repository_url=config.repository.url)
try:
    selection = history.select(
        config.repository.anchor,
        config.repository.window,
        max_depth=config.git.max_depth,
    )
    if len(selection.selected_commits) > config.budgets.max_commits:
        raise ValueError("selected history exceeds the configured commit budget")
    index = history.index(selection)
    content = ContentExtractor.from_history(history).extract(index)
    print(f"{len(index.selection.selected_commits)} commits, {len(content.snapshots)} snapshots")
finally:
    history.close()
```

This path makes no GitHub or LLM calls and opens no graph database. Missing
ancestry and unsupported content are reported as coverage gaps. Always pass
your configuration explicitly to `load_config(path)`; calling it without a
path is an error. Paths in the configuration are relative to the working
directory of the calling application.

## Reproducible sample

The self-contained [`examples/tf_gnns/`](examples/tf_gnns/README.md) workflow
owns its configuration, scripts, recorded evidence, tests, and historical
artifacts. It consumes the installed library without changing `sys.path`.
Neither the library, its generic tests, nor its wheel/source distributions
depend on that example. See the example README for setup and run commands.

## Setup and privacy

Setup is local-first: the default test suite and the recorded-evidence
fixtures need no secrets and no network. Remote access is explicit:

- Git clone/fetch operations access the configured remote when explicitly called;
  opening and analyzing an existing local checkout does not fetch history.
- GitHub access reads the configured repository and allowlisted work items through `httpx`
  (`GITHUB_TOKEN` from the configured `token_env`; unauthenticated runs also
  work within rate limits).  Raw responses are cached under `data/cache`
  without credentials; the token is used only for authentication and is not
  persisted in evidence files.
- LLM enrichment requires `llm.enabled = true` **and**
  `llm.privacy_consent = true`, plus the `openai` extra
  (`uv run --with langchain-openai ...`) and `OPENAI_API_KEY`.  Prompts carry
  only repository evidence already selected for indexing, and every call is
  budgeted, cached, and recorded with model/prompt/schema provenance.

The analysis does not execute target-repository code or mutate remote work
items. Git clone/fetch writes to the local checkout or object cache; unavailable
source history is reported as explicit coverage gaps, never invented.
`examples/tf_gnns/evaluate.py` reproduces the bounded live evaluation; pass `--llm` only
with consent and a key.

## Content extraction

`ContentExtractor` reads blobs through the Git index instead of the working
tree, so baseline snapshots describe the historical commit rather than `HEAD`:

```python
from synirmos.processing.content import ContentExtractor

index = history.index(selection)
extractor = ContentExtractor.from_history(history)
content_index = extractor.extract(index)
```

Parsing is keyed by `(blob oid, media type)`, so identical bytes are parsed once
while every snapshot keeps its own `snapshot_id`, commit, path, and source URL.
Markdown headings, links, fenced code blocks, and sections carry character
offsets and line ranges into the original blob; Python files are inspected with
`ast` only and are never imported or executed.

Statuses are explicit: `parsed`, `empty`, `unsupported` (binary or Git LFS
pointer), `oversized`, `undecodable`, `gitlink`, and `unavailable`. Each
non-parsed status emits a `CoverageGap`, as do truncated section, symbol, and
import lists, so configured limits stay observable in the output.

## GitHub work items and evidence

`GitHubDiscoverer` reads only the work items named by
`repository.allowed_work_items` and keeps every raw response it used:

```python
from synirmos.sources.github import (
    EvidenceCache,
    GitHubCredentials,
    GitHubDiscoverer,
)

discovery = GitHubDiscoverer(
    config.repository,
    config.github,
    cache=EvidenceCache(config.cache_dir),
    credentials=GitHubCredentials.from_env(config.github),
).run()
```

Responses are stored with fetch metadata (URL, status, hashes, ETag,
Last-Modified, rate-limit headers, and the next pagination link), keyed by a hash
of the canonical request URL. Re-runs send conditional requests, and an offline
run replays saved evidence without opening a socket. Missing evidence, denied
optional endpoints, exhausted budgets, and pagination truncation become explicit
`CoverageGap`s or `AbsenceRecord`s instead of silently empty results.

A parent lookup that was a 404 online leaves no cache entry, so offline replay
treats the missing entry the same way: no parent edge, no gap. Online and
offline runs therefore agree on events and coverage.

Current issue bodies, labels, and comments are observations stamped at fetch
time; they are never backdated to the item's creation. Creation, comments, and
timeline events keep their source timestamps, while `RevisionAvailability`
records that GitHub REST does not expose earlier body/label revisions. Labels,
native parent/sub-issue edges, PR heads, bases, merge commits, and PR commit
lists are captured when present, and out-of-scope hierarchy edges are flagged
without fetching the external item. Credentials are read from the configured
environment variable and are never written to the cache.

## Temporal replay and resumable orchestration

`TemporalCoordinator` merges Git and GitHub event streams into one
deterministic history: stable ordering by `(event_time, source, source_id,
sequence)`, causal conflict resolution (later observations correct earlier
ones; exact ties break deterministically), and deferral of events whose
dependencies have not arrived yet. `git_selection_events` turns a bounded
`GitSelection` into `BASELINE` events for boundary commits and `COMMIT` events
for selected commits; immutable commits carry `info_horizon == event_time`,
while mutable remote observations carry `info_horizon == observed_at`.

```python
from synirmos.runtime.orchestration import (
    EventJournal,
    StageRunner,
    TemporalCoordinator,
    git_selection_events,
)

runner = StageRunner.resume_or_create(
    config.orchestration.journal_file,
    config.orchestration.checkpoint_file,
    manifest,
    config.budgets,
)
snapshot = runner.run_stage("git", lambda: (git_events, git_gaps))
result = TemporalCoordinator(config.repository).collect(snapshot.events)
usable = TemporalCoordinator.visible_at(result.effective, horizon)
```

`EventJournal` persists events and gaps as an append-only JSONL log with a
manifest header (run, repository, config fingerprint); byte-identical
duplicates are skipped and corrections are kept. `CheckpointStore` records
completed stages with the budget ledger counters and a digest binding the
checkpoint to the journal prefix, so retries and resumes continue spending the
same budgets and a diverged journal fails closed. `bootstrap` splits
per-boundary bootstrap state from in-window replay, and `visible_at` gates
enrichment by information horizon so future labels, docs, or async results
cannot seed past decisions. Unavailable history stays a retryable gap; nothing
is invented for it.

## GestaltDB temporal graph persistence

`GraphSink` is the single writer: it owns the database handle, stamps every
version with provenance (`prov_run_id`, origin event, information horizon,
evidence IDs), and records the run in each temporal commit's metadata:

```python
from synirmos.storage.graph import GraphSink, map_discovery, map_git_index

mapped = map_git_index(index, ids, run_id=run_id)
sink = GraphSink.create(config.graph, run_id=run_id, overwrite=True)
sink.write_entities(mapped.entities, analysis_run_id=run_id, defer_indexes=True)
sink.write_relationships(mapped.relationships, analysis_run_id=run_id)
sink.close()
```

`map_git_index` emits `Commit`, `Snapshot`, `File`, and `Branch` entities with
`PARENT_COMMIT`, `MEMBER_OF`, `OF_FILE`, and `TIP_OF` relationships;
`map_discovery` emits `WorkItem` and `ProviderLabel` entities with `HAS_LABEL`,
`CHILD_OF`, and `MERGED_AS` relationships. Out-of-scope parents and hierarchy
edges are skipped, never invented.

Version IDs are deterministic UUIDs, so ingesting the same batch twice is
idempotent: the driver rejects the duplicate ID and the sink skips it after
verifying the stored payload. Corrections (`correct_entity`,
`correct_relationship`) append superseding versions; old evidence is retained
and readable via `node_history` and `node_as_of`. The mutable current
projection (`current_node`, `find_nodes`, `neighbors`) is rebuildable by
replaying the journal into a fresh database. Bulk loads use `defer_indexes`;
every read path rebuilds stale indexes first, since the driver refuses
temporal and indexed queries while they are stale. `GraphSettings` (`[graph]`
section) sets the path, backend, overwrite flag, and LMDB map size.

## Topic registry and deterministic labeling

`DeterministicLabeler` assigns topics without a model: deterministic
path/language/heading/reference features describe each subject, a classical
TF-IDF baseline retrieves candidate topics by cosine similarity, and the
outcome is reuse, a genuinely new proposal, an alias suggestion, or an
explicit abstention — each with matched terms as the rationale:

```python
from synirmos.processing.labeling import (
    DeterministicLabeler,
    extract_snapshot_features,
    seed_registry,
)

labeler = DeterministicLabeler(config.labeling)
registry = seed_registry(at=now)
assignment = labeler.assign(
    features, registry, subject_id=subject_id,
    run_id=run_id, info_horizon=horizon,
)
```

Provider labels are preserved verbatim by `preserve_provider_labels` in a
separate assignment namespace; derived topics never absorb them silently.
Assignments are `AnalysisResult` envelopes, so each decision key already binds
subject, method, horizon, and evidence. Growing the registry (registrations,
aliases, merges) never rewrites old assignments: they reference the registry
version they were decided against, merges mark old topics as superseded
instead of deleting them, and re-running against a kept registry snapshot
reproduces the original decisions exactly. `LabelingSettings` (`[labeling]`
section) sets the reuse/alias thresholds, minimum score, and retrieval limit.

## LangChain structured LLM enrichment

`Enricher` wraps an injected LangChain chat model (`BaseChatModel`) with
opt-in consent, budgets, caching, validation, and full provenance. Proposals
are typed (`LLMTopicProposal`, `LLMSummaryProposal`, `LLMLinkProposal`) and
grounded: reused topics and link targets must come from the supplied
candidates, and invalid output is retried, then abstained — never invented:

```python
from synirmos.processing.enrichment import Enricher, EnrichmentCache, build_chat_model

settings.llm.enabled = True  # plus privacy_consent=True, or it refuses
model = build_chat_model(settings.llm)  # documented OpenAI configuration
enricher = Enricher(
    model, settings.llm, ledger=ledger,
    cache=EnrichmentCache(settings.llm.cache_file), run_id=run_id,
)
result = enricher.enrich_topic(
    subject_id=..., subject_text=..., candidates=[...],
    registry_version=..., info_horizon=...,
)
```

Every call reserves LLM requests/tokens from the shared `BudgetLedger`
before invoking (retries spend too), records estimated and actual usage in
`Provenance`, and caches the validated proposal under a key of model, prompt
version, schema version, method, and context hash — changing any of them
invalidates the entry. Tests use `GenericFakeChatModel` from
`langchain-core`; the real smoke runs `ChatOpenAI` (`gpt-4.1-mini`) via the
`openai` extra with explicit consent. Unavailable history becomes a
`llm-history-unavailable` gap instead of a prompt. `[llm]` settings cover
provider, model, temperature, privacy consent, retry attempts, prompt version,
and cache file.

## Separate worker processes

`WorkerPool` runs work-item analysis in spawned OS processes. Jobs are
durable, versioned envelopes with fully embedded inputs (feature snapshot,
candidates, registry snapshot, horizon), so any worker — now or after a
restart — replays the same job:

```python
from synirmos.runtime.worker import JobQueue, WorkerPool, collect_results, make_job_id

queue = JobQueue("data/work")
queue.submit(WorkJob(job_id=make_job_id(...), ...))  # resubmits dedupe
pool = WorkerPool(queue, max_workers=2, task_timeout_seconds=120.0)
pool.run_pending()  # crashed/timed-out jobs stay resumable
results = collect_results(queue)  # merged in (horizon, job_id) order
```

Required enrichment (deterministic labeling) must succeed for a job to
complete; optional enrichment (LLM proposals, rebuilt from embedded settings
and scripted replies) may abstain or fail while the job still completes, and
the two outcomes stay distinguishable in `WorkResult`. Results echo the job's
horizon and record the worker PID; merging sorts by horizon so out-of-order
completion cannot publish future context into an earlier event. Repeats are
byte-identical by `job_id`, and the coordinator charges the shared ledger only
for accepted optional usage.

## Evidence-backed cross-entity linking

`linking.py` resolves textual references (`#123`, `owner/repo#123`, issue/PR
URLs, commit SHAs, known file paths) and provider relationships (merged PRs,
head/base branches) against known entities only. Unresolved numbers, foreign
repositories, unknown or ambiguous SHAs, and deleted branches are reported as
references, never invented into links:

```python
from synirmos.processing.linking import (
    infer_topical_links,
    resolve_provider_links,
    resolve_textual_links,
)

text_report = resolve_textual_links(texts, ids=ids, ...)
provider_report = resolve_provider_links(discovery, index, ids=ids, ...)
topic_report = infer_topical_links(item_topics, file_topics, ids=ids, ...)
```

Relations stay distinct: `MENTIONS` (textual reference), `INTENDS_TO_RESOLVE`
(fix/close/resolve intent, never inferred from `Merge pull request` lines),
`CLOSED_BY` (provider closure: merged PR to merge commit, with squash
evidence as `merge_style: non-head` and no invented ancestry), and
`RELATED_TO` (scored inference: shared derived topics, branch association).
Weak topical overlap abstains with its score instead of linking.
`LinkRecord.to_result()` wraps each link as an analysis envelope, and
`link_edge_writes()` maps accepted links to single-writer relationship
writes. `score_links()` measures precision/recall over annotated fixtures.
`LinkingSettings` (`[linking]` section) sets the inference score floor.

## Inspection queries and visualization

`Inspector` answers the six user-visible questions from adapter outputs —
no database, no network — with horizon and coverage attached to every
answer: commit-range changes, work-item traces with evidence, branch
containment, topic timelines (emergence then recurrence), files and sections
for a work item at a chosen time, and attribution for labels and links:

```python
from synirmos.reporting.inspection import Inspector

inspector = Inspector(
    index=index, discovery=discovery, content=content, links=links,
    assignments=assignments, info_horizon=horizon, run_id=run_id,
    repository_url=repo_url,
)
changes = inspector.changes_in_range(from_sha, to_sha)
traces = inspector.work_items_for_commits([sha, ...])
timeline = inspector.topic_timeline(topic_id)
```

The [reference runbook](examples/tf_gnns/runbook.py) executes the analysis on
its recorded slice and saves `report.md` plus `slice.svg` in its output directory. The figure
is deterministic SVG (stdlib only): factual links are solid blue, inferred
topical links are dashed amber, nodes are capped at a fixed budget with
omissions reported, and the footer records run, horizon, counts, and gaps.
`viz.render_slice_svg()` renders any bounded slice the same way.
