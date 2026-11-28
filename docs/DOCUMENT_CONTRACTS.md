# D0 checkpoint: document identity and time contracts

Part of #11, **not completion of D0**. Imports live in
`synirmos.core.contracts`, `core.documents`, `core.temporal`, and
`core.ports.documents`. These modules use only the standard library, Pydantic,
and existing core values. They do not implement capture, parsing, storage,
authorization, entity resolution, or an agent.

## Identity rules, version 1

New values carry `schema_version=1`, reject extra fields/unknown versions, and
use frozen models and tuple containers. Deserialize with `model_validate` or
`model_validate_json`; Pydantic's unchecked `model_construct`/`model_copy(update=...)`
are not validation APIs and must not be used for untrusted inputs.

`contract_id` uses the existing framed SHA-256 helper with a new explicit
`synirmos-contracts-v1` namespace and a full digest. Existing `IdFactory` outputs
and persisted repository keys are unchanged. Source instance/native keys remain
opaque and case-sensitive; source adapters, not core, own any normalization.
Callers must use stable, credential-free source instances, not display titles.

| Identity | Included | Deliberately excluded |
| --- | --- | --- |
| Logical document | Source instance + native key, with document kind namespace | Display title, collection membership, incidental run ID, content |
| Captured content | SHA-256 of original bytes, with verified byte length | Source/access identity, encoding guesses |
| Revision/observation | Full immutable document metadata, content reference, timing, encoding/media type, native revision, sorted evidence, supersession reference | Incidental processing run, collection membership |
| Collection | Its own source instance + native key, in collection namespace | Current membership; it does not own document identity |
| Artifact specification | Implementation ID/version + configuration fingerprint | Runtime resource handles; retain the actual config manifest separately |
| Reusable chunk content | Chunk-byte digest + chunker specification fingerprint | Source occurrence/access identity |
| Chunk occurrence | Chunk identity + revision ID + original content digest + byte bounds | Ordinal-only identity, incidental run ID |

Canonical JSON fingerprints sort object keys, retain scalar types, reject
non-string object keys/non-JSON values/nonfinite numbers, and never retain the
caller's mutable configuration. Unordered evidence and membership sets are
normalized to sorted tuples; source text is not normalized silently.

Re-delivery of an exact captured observation yields the same revision ID.
Capturing the same bytes later creates another observation/revision, while
retaining the logical document and reusable content identities. Replay must use
the original captured timestamps, not a fresh clock. Native revision IDs do not
override captured content or metadata integrity. No name-based canonical entity
identity or retry-safe assertion identity is introduced by this checkpoint.

## Three clocks, not one

`RevisionTiming` distinguishes:

1. `valid`: a half-open source-valid interval `[start, end)`; no end is unbounded.
2. `observed_at`: when this immutable observation was captured.
3. `info_horizon`: the earliest **justified application knowledge time** for that
   captured revision; this is not a database system timestamp or a processing
   run's latest context cutoff.

All timestamps must have an offset and are normalized to UTC. Ordinary local
capture sets both observation and knowledge time to capture time. File mtime,
an old date in text, or an old validity start does not justify earlier knowledge.
An earlier knowledge time requires explicit `availability_evidence_ids`; adapters
must verify those references and their historical-availability semantics.
Presence of IDs alone proves nothing about their trustworthiness. A revision
cannot first become knowable after the observation that captured it.

Validity is independent of knowledge: a future-effective announcement may be
known today, and an old-valid fact captured today is not automatically known
yesterday. `ReadPoint` specifies independent valid time and an inclusive
application knowledge cutoff. Its `includes()` method tests one revision's time
eligibility only: **it does not select a winner among versions, authorize access,
resolve supersession, or pin a database**. Do not filter only the latest version
and assume an older eligible version cannot exist.

Storage adapters must separately pin a native DB horizon and enforce the
application knowledge cutoff when importing/replaying historical evidence. D0's
remaining scope/session contracts and D3 implement that boundary; these values
do not synthesize database commit times from source timestamps.

## Bytes, occurrences and source maps

`ContentReference.verify()` checks both byte length and digest. `SourceSpan`
uses half-open **byte offsets into original captured bytes**, bound to a revision
ID and content reference. Its `extract()` verifies the complete original before
slicing. Empty spans are valid locations, not nonempty supporting quotes.

A span may refer to a revision ID only when the caller has verified that the
revision actually has that content reference. A chunk occurrence describes a
placement, not verified extraction evidence. These structural values cannot
authenticate evidence or establish access merely from a digest/ID.

Decoded/normalized text, Markdown heading removal, overlap and escaped docstrings
may require multiple source spans/maps. A parser must provide those mappings
explicitly; this checkpoint introduces only the contiguous primitive, not a
source-map implementation. LangChain character offsets/`Document` metadata and
ambiguous substring searches are not original-byte provenance.

## Bounded ports and outcomes

- `DocumentSource.capture()` takes explicit native keys; an empty tuple means
  none, never all files or a crawl. Concrete sources enforce caller limits and
  bind opaque continuation tokens to the same source/selection/limits. A returned
  page's self-declared limits must not be trusted in place of caller policy.
- `DocumentBatch` checks page revision count, conservatively summed referenced
  content bytes (including duplicates), and duplicate revision IDs. It preserves
  continuation and coverage gaps, so an incomplete empty page is not reported as
  a successful complete collection. It does not bound all I/O, decoded heap,
  parsing work or service lifetime.
- `ContentReader.read()` resolves **already captured** bytes within `max_bytes`
  and independently enforces access. Zero is useful for an empty blob; a negative
  limit is invalid. Oversized reads raise `DocumentLimitError`; missing/denied
  content raises explicitly; changed bytes raise `ContentMismatchError`. Never
  fetch a live original or use empty bytes to conceal failure.
- Protocols are structural contracts, not implementations or security wrappers.
  Adapters own enforcement and resource cleanup; D2 will supply actual text/file
  capture and reader conformance. No repository settings are required by these
  ports, and neither grants parsing or graph mutation authority.

## Verification and remaining work

`tests/test_document_contracts.py` covers qualification/collision cases, identical
bytes from distinct sources, multi-collection membership, capture retries,
UTC/horizon rules, content integrity, Unicode/CRLF/repeated-text byte spans,
chunk/occurrence identity, limits, immutability and JSON round-trips.
`tests/test_architecture.py` checks core imports recursively (including nested
ports and relative/absolute imports) and imports the new modules in a fresh
process to detect accidental implementation dependency loading.

`examples/onto_kg/notebooks/D0_contracts.ipynb` demonstrates these distinctions
with assertions. `uv run pytest examples/onto_kg/tests -q` executes it and
notebook 00 in fresh processes, in cell order, without Jupyter or model access;
the full `scripts/check.py` gate includes this regression suite. The installed-
wheel smoke also imports the new nested ports and exercises content/identity
values outside the source checkout.

The subsequent D0 increments define graph/profile/scope/write values, trusted
grant intersection, context/exposure results, read-session lifecycle, extraction
candidate/assertion/retry identity and physical-work capability outcomes in
`GRAPH_CONTEXT_CONTRACTS.md` and `EXTRACTION_CONTRACTS.md`. These document primitives
alone do not implement those boundaries or their concrete adapters. Consult the
epic execution status for verified delivery rather than inferring completion
from this initial checkpoint's presence.
