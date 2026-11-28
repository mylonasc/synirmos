# Agent notes

## Master plan and target state

- Read `docs/epics/EPIC_DECOUPLING.md` before ONTO-KG work. Its execution-status
  section is the current progress record; sections 7–9 define scope, acceptance,
  ownership, and dependencies. Also read `docs/GESTALTDB_SCALE_REVIEW.md`,
  `docs/epics/EPIC_ONTO_KG.md`, and relevant parts of `docs/REFACTORING_PLAN.md`.
- Target: standalone documents and captured repository text share capture,
  parsing/chunking, scoped context, extraction, validation, resolution,
  staging/approval, temporal persistence, and cited retrieval. Documents must not
  require fabricated repository identities. Context providers must be usable and
  testable without an agent, Git, a database, or a real model as appropriate.
- Keep responsibilities separate: sources capture; parsers describe; context
  providers read/select; agents propose; validation/resolution/approval decide;
  storage persists; runtime composes. No monolithic universal context object.

### Implementation order

| Order | Delivery | Required outcome |
| --- | --- | --- |
| 1 | D0 / #11 | Neutral document/graph/context/extraction contracts, identity/time rules, resource lifetimes, budgets, serialization and import-boundary tests |
| 2 | D1 / #12 | Generic storage with repository mappings separated, composable profiles, bounded native batches, history/current transactions, explicit index readiness, legacy compatibility |
| 3 | D2 / #13 | Explicit text/bytes/file capture, pure Markdown/plain-text parsing, source spans, deterministic reusable chunking without Git/DB/LLM |
| 4 | D3 / #14 | Scope-enforcing pinned readers; interchangeable empty, in-memory and graph-backed contexts; independent conformance tests |
| 5 | Complete #2; #3 and #4 | Finish ontology artifact/consistency/merge acceptance; persist exact release membership and native compilation; lexical graph and embedding/search ports |
| 6 | D4 / #15, then #5 | Adapt JERE to neutral subjects/profiles/context; add ontology-guided validation, actual exposure/evidence checks, and persistent staging |
| 7 | #6 | Conservative canonical resolution, distinct supports, reviewed reversible merges, idempotent publication |
| 8 | D5 / #16 and #7 | Standalone/repository runtime composition, replay/budget recovery, scoped policy-driven retrieval and citations |
| 9 | D6 / #17 | Synthetic end-to-end, isolation, migration, packaging and workload-performance gates |
| 10 | #8 | Sole final public-document demonstration, executed explanatory notebooks, reproducible offline path and measured findings |

- The table is a recommended traversal, not extra blocking edges: D1 and D2 are
  independent after D0; D3 follows D1; #3 and #4 can proceed when their own
  prerequisites pass. D4 needs D0/D2/D3 and the #9 prototype, not completion of
  the whole JERE tracker. D5 and #7 can proceed independently once ready.
- Settle D0's precise identity, source-validity/observation/DB-time mapping,
  collection/access/approval visibility, and read-session ownership in executable
  examples before dependent implementations. A DB commit clock is not a source
  information horizon; names are not canonical entity identity.
- Separate extraction constraints from native entailment. Multiple allowed
  registry domain/range classes are alternatives, not multiple conjunctive native
  domain/range axioms. Native scoped equality never approves physical merges.
- Reuse GestaltDB 0.17 transactions, temporal/history readers, indexes and selected
  ontology/reasoning capabilities behind neutral ports. Do not build a parallel
  generic engine. Preserve source horizons, existing IDs and repository behavior.
- Scope before ranking/traversal; reuse bounded pinned sessions; never silently
  fall back to current data or repair indexes from a scoped reader. Output caps
  are not physical-work/RSS/time guarantees. Define workload/SLO targets before
  claiming scale readiness; exact vector search is only a bounded reference.
- Do not start another broad rewrite or activate every optional backend feature.
  Full OWL/SHACL, new hosting providers and autonomous publication are not goals.

## Branches

- Land all commits related to the ontology-driven KG feature (ONTO-KG,
  parent #1, slices #2–#8 and decoupling #10–#17) on `onto-kg-feature`, not
  `main`. Open PRs against `main` from that branch when a slice is done.
- Agent-specific JERE work remains on `jere-feature` under #9. Integrate agreed
  shared contracts before consumers; do not merge that branch implicitly.
- Synchronize the working branch with merged upstream work before continuing;
  inspect divergence and preserve user changes. Never reset/clean/force-push to
  hide a conflict. Leave untracked `ref_ontokg_files/` untouched and uncommitted.

## Progress, commits and handoffs

- **Update the plan frequently:** after each meaningful completed substep,
  changed assumption, blocker, experiment or scope decision, and before every
  handoff, update the execution-status section in `EPIC_DECOUPLING.md`. Record
  active issue/stage, completed versus remaining acceptance, evidence/checks,
  blockers/debt links, and the next concrete action. Update affected slice text
  and GitHub tracking when the design/dependencies change; keep ownership/DAG
  consistent rather than maintaining contradictory plans.
- Distinguish planned, implemented, verified, pushed and merged work. A notebook,
  closed issue or merged scaffold is not proof that all acceptance passed. If
  automatic closure hides incomplete work (as happened with #2 after PR #18),
  reconcile the tracker by reopening or linking an explicitly reviewed follow-up
  before treating that prerequisite as complete. Do not use closing directives
  in commits/PRs for incomplete issues.
- **Commit and push often:** make small, coherent, validated checkpoints at
  useful implementation/test/documentation milestones, not one giant end-of-epic
  commit. Include relevant progress notes and issue references; push after each
  such checkpoint and before a handoff. Run applicable gates first, report
  failures honestly, and do not bypass hooks or include unrelated user work,
  secrets, generated reports, or reference inputs. No empty churn commits.
- Each slice ships code, focused tests, migration notes and an informative
  notebook or executable example explaining the seam. Reviewable checkpoints
  do not replace full acceptance or a slice PR. Do not merge PRs automatically.

## Parsing and chunking reuse

- Reuse suitable deterministic, non-LLM LangChain parsing/chunking capabilities
  rather than reimplementing standard splitters. Evaluate the narrowly scoped
  `langchain-text-splitters` package (recursive/Markdown-aware splitting, for
  example); it is separate from the existing `langchain-core` dependency. Add a
  compatible bounded dependency and update `uv.lock` only when implementing its
  adapter. Do not assume an API/package is already installed or add the whole
  LangChain/community stack just for splitting.
- Keep framework types/imports inside concrete parser/chunker adapters, outside
  neutral core contracts and provider interfaces. Parsing must remain usable
  without an agent, model credentials, Git or graph storage. Adapt existing parser
  behavior; do not maintain duplicate Git and document parsers.
- Captured immutable bytes, neutral revision IDs and original-source spans are
  authoritative, not LangChain `Document` metadata or loader-generated IDs.
  Verify whether a splitter preserves whitespace/headings/overlap and whether
  offsets are characters or bytes. Maintain explicit source maps; never infer
  reliable spans from an ambiguous substring search in repeated text.
- Fingerprint algorithm/library version, configuration, tokenizer where used,
  and source-map behavior in artifacts/cache keys. Test Unicode, CRLF, BOM,
  repeated text, empty/oversized input, overlap and changed configurations.
  Token estimates are not hard model limits. If a splitter cannot preserve the
  required provenance, adapt it safely or use an existing/purpose-built parser
  with a documented reason; reuse is not permission to weaken correctness.
- No hidden loader crawling, URL fetches, model calls or code execution. Source
  acquisition remains explicit and bounded; parser/chunker reuse is not source
  acquisition policy.

## Technical-debt tracking

- When a concrete improvement needs refactoring beyond the active slice, search
  existing issues first. Create or update a GitHub issue labeled **`techdebt`**,
  using a descriptive `[techdebt]` title, rather than silently expanding scope
  or leaving an untracked TODO. This is an ongoing execution responsibility.
- Include affected files and observed evidence, consequences, why a safe fix is
  too large now, the bounded current mitigation, proposed incremental direction,
  dependencies/related slices, and testable completion criteria. Link the issue
  from the execution plan and relevant PR/code comment where useful. If GitHub
  is unavailable, record a pending issue in the plan and publish it when possible.
- Do not duplicate existing D0–D6/#2–#9 acceptance as "future debt". Security,
  correctness, provenance, isolation, replay and required slice acceptance cannot
  be deferred merely to make tests green: fix them, mark the slice blocked, or
  obtain an explicit scope decision. A debt issue is not approval to implement
  another feature or broaden the current refactor.

## Verification

- Fast gates: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest tests/ -q`.
- Full gates (also CI): `uv run python scripts/check.py` — lint, format,
  tests with a 90% coverage floor, example regressions, metrics, build,
  and installed-wheel smoke test.
- Notebooks under `examples/` are linted by ruff (code cells included);
  keep every imported name used and verify cells execute in order.
