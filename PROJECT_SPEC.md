# Synirmos: project specification

Synirmos is an independent Python library for evidence-backed repository-history
analysis. Applications explicitly select a Git repository, a full commit SHA,
a time window, and an allowlist of work items. No example repository is selected
implicitly, and no example files are needed to import, configure, test, build,
or install the library.

The [extensibility refactoring plan](docs/REFACTORING_PLAN.md) specifies the next
migration: platform integrations independent of repository identity, remote-only
source authority, a dedicated `repository_history` layer, and language-parser
plugins. Its implemented-scaffold/deferred-behavior section distinguishes
current functionality from the target architecture.

## Package boundaries

| Package | Responsibility |
| --- | --- |
| `synirmos.core` | Validated contracts, identity, provenance, configuration, budgets, events, protocols |
| `synirmos.sources` | Git history and bounded GitHub evidence discovery |
| `synirmos.processing` | Content extraction, topic labeling, enrichment, linking |
| `synirmos.storage` | Temporal graph mapping, persistence, backend capabilities |
| `synirmos.runtime` | Durable journals, checkpoints, temporal replay, process workers |
| `synirmos.reporting` | Read-only inspection, SVG visualization, evaluation metrics |

The core depends on neither providers nor outer layers. Implementation modules
use canonical domain-package imports, not aliases at the package root.
Outer layers compose explicit inputs and configuration rather than locating
application assets relative to the library's installation path. The import
package is `synirmos`, matching the distribution and `src/synirmos/` layout;
old `repo_history` imports are intentionally no longer installed.

GestaltDB is the current graph backend and GitHub the current work-item provider.
Provider-independent contracts support future integrations but do not imply
that other providers or storage backends are already implemented.

## Configuration and application ownership

`load_config(path)` requires a caller-supplied TOML file. The generic template
in `configs/repository.toml` is documentation, not an installation-time dependency.
Applications own checkout locations, credentials, caches, output paths, and
network consent. Configuration paths are interpreted relative to the calling
application's working directory.

The `examples/tf_gnns` workflow is a separate consumer of the installed library.
It owns its pinned configuration, scripts, recorded provider evidence, offline
regression tests, historical reports, and original implementation design.
Library tests use independently constructed repositories and synthetic inputs;
they do not read example files. Example tests run as a separate CI step.
Examples are excluded from both wheels and source distributions.

## Evidence and temporal semantics

- Keep source evidence, normalized events, and derived analysis distinct.
- Immutable commits carry their source timestamp as their information horizon;
  mutable provider observations carry their observation time. Never backdate
  current issue text or labels to an item's creation.
- Replay events deterministically and do not use information from the future
  for an earlier analysis decision.
- Preserve provenance and evidence IDs on derived results and graph writes.
  Corrections append versions rather than overwriting historical evidence.
- Missing ancestry, unavailable historical revisions, unsupported content,
  exhausted budgets, and truncated results are explicit coverage gaps.
- Journal/checkpoint resumes retain budget usage and verify the journal prefix.
  Retries and duplicate ingestion must not invent events or duplicate assertions.

## Safety and limits

Repository content is untrusted data. Parse code without importing or executing
it. Do not run indexed hooks, builds, or document commands. Git fetch/clone and
GitHub requests are explicit operations; cached evidence can be replayed offline.
Do not mutate remote work items or persist credentials in evidence files.
Hosted-model enrichment requires explicit enablement and privacy consent, with
bounded retries, request/token budgets, and recorded model/prompt provenance.

Full-history indexing, unrestricted repository agents, universal branch-history
reconstruction, distributed scheduling, and semantic compilation of every
language are not first-release guarantees.

## Development and quality contract

The distribution and import namespace are both `synirmos`. uv manages the
packaged project, native build backend, Python selection, development
dependencies, and committed lockfile. Build with `uv build` without custom
module-name mappings. Python 3.11–3.13 are tested in CI.

`uv run python scripts/check.py` is the shared local/pre-push/CI entry point:
Ruff lint and formatting, synthetic-library tests with a 90% combined
statement/branch coverage floor, separate example regressions, Radon complexity
and maintainability reporting, distribution builds, and an isolated installed
wheel smoke test. Ruff caps function complexity at 30, the initial existing-code
ceiling. Reports are emitted under `reports/` and uploaded by CI on every push
and pull request. Pre-commit hooks provide fast lint/format feedback; pre-push
hooks run the complete suite.
