"""D0 document/time/identity primitives need no source, database or framework."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from synirmos.core.contracts import ArtifactSpec, SourceKey, contract_id, json_fingerprint
from synirmos.core.documents import (
    ChunkContent,
    ChunkOccurrence,
    ContentMismatchError,
    ContentReference,
    DocumentBatch,
    DocumentCollection,
    DocumentLimits,
    DocumentRevision,
    OriginReference,
    SourceSpan,
    TextDocument,
)
from synirmos.core.models import CoverageGap, CoverageStatus
from synirmos.core.ports.documents import ContentReader, DocumentSource
from synirmos.core.temporal import ReadPoint, RevisionTiming, ValidInterval

NOW = datetime(2026, 11, 28, 12, tzinfo=UTC)
EARLIER = NOW - timedelta(days=1)
LATER = NOW + timedelta(days=1)
BODY = "# Héllo\r\n\nHéllo\r\n".encode()


def revision(*, body=BODY, source="source:a", key="notes", observed_at=NOW, **kwargs):
    return DocumentRevision(
        document=TextDocument(key=SourceKey(source_instance=source, native_key=key)),
        content=ContentReference.from_bytes(body),
        timing=RevisionTiming(
            valid=ValidInterval(start=EARLIER),
            observed_at=observed_at,
            info_horizon=observed_at,
        ),
        **kwargs,
    )


def chunker(**kwargs):
    return ArtifactSpec(
        implementation="test:splitter",
        implementation_version="1",
        config_fingerprint=json_fingerprint(kwargs),
    )


def test_qualified_identity_is_framed_case_sensitive_and_not_name_based():
    left = SourceKey(source_instance="source:a", native_key="b:c")
    right = SourceKey(source_instance="source:a:b", native_key="c")
    assert left.identifier("document") != right.identifier("document")
    assert left.identifier("document") != left.identifier("collection")
    assert left.identifier("document") != SourceKey(
        source_instance="source:a", native_key="B:C"
    ).identifier("document")
    doc = TextDocument(key=left, title="first")
    renamed = TextDocument(key=left, title="renamed")
    assert doc.document_id == renamed.document_id
    assert doc.document_id.startswith("document:")


@pytest.mark.parametrize("parts", [(), ("",), ("  ",), (1,), ("ok", None)])
def test_identity_requires_nonblank_string_components(parts):
    with pytest.raises(ValueError, match="nonblank"):
        contract_id("document", *parts)


@pytest.mark.parametrize(
    "kwargs",
    [{"source_instance": " "}, {"native_key": ""}, {"native_key": "\n"}],
)
def test_source_key_rejects_blank_components(kwargs):
    with pytest.raises(ValidationError):
        SourceKey(**({"source_instance": "a", "native_key": "b"} | kwargs))


def test_json_fingerprints_are_order_independent_without_key_coercion():
    assert json_fingerprint({"b": [1, True], "a": "é"}) == json_fingerprint(
        {"a": "é", "b": [1, True]}
    )
    assert json_fingerprint({"a": 1}) != json_fingerprint({"a": "1"})
    with pytest.raises(ValidationError):
        json_fingerprint({1: "a"})
    with pytest.raises(ValueError):
        json_fingerprint({"a": float("nan")})
    with pytest.raises(ValidationError):
        json_fingerprint({"a": object()})


def test_content_sharing_never_collapses_source_document_or_revision_identity():
    a = revision()
    b = revision(source="source:b")
    c = revision(key="other")
    assert a.content == b.content == c.content
    assert len({r.document.document_id for r in (a, b, c)}) == 3
    assert len({r.revision_id for r in (a, b, c)}) == 3
    assert a.revision_id == revision().revision_id  # exact captured retry
    assert a.revision_id != revision(observed_at=LATER).revision_id
    assert a.revision_id != revision(body=b"new").revision_id


def test_metadata_native_revision_and_evidence_participate_in_revision_identity():
    a = revision(native_revision="v1", evidence_ids=("e:2", "e:1", "e:1"))
    b = revision(native_revision="v1", evidence_ids=("e:1", "e:2"))
    assert a.revision_id == b.revision_id
    assert a.evidence_ids == ("e:1", "e:2")
    assert a.revision_id != revision(native_revision="v2", evidence_ids=b.evidence_ids).revision_id
    renamed = DocumentRevision(
        **(a.model_dump() | {"document": TextDocument(key=a.document.key, title="new")})
    )
    assert renamed.document.document_id == a.document.document_id
    assert renamed.revision_id != a.revision_id
    assert revision(supersedes_revision_id=a.revision_id).revision_id != revision().revision_id


def test_collection_membership_has_no_identity_ownership():
    doc = revision().document
    a = DocumentCollection(
        key=SourceKey(source_instance="collection:local", native_key="a"),
        document_ids=(doc.document_id, "other", doc.document_id),
    )
    b = DocumentCollection(
        key=SourceKey(source_instance="collection:local", native_key="b"),
        document_ids=(doc.document_id,),
    )
    assert a.collection_id != b.collection_id
    assert doc.document_id in a.document_ids and doc.document_id in b.document_ids
    assert a.document_ids == tuple(sorted({doc.document_id, "other"}))
    changed = DocumentCollection(key=a.key, document_ids=())
    assert changed.collection_id == a.collection_id
    assert doc.document_id == revision().document.document_id


def test_half_open_valid_interval_and_unbounded_end():
    interval = ValidInterval(start=EARLIER, end=NOW)
    assert interval.contains(EARLIER)
    assert not interval.contains(NOW)
    assert not interval.contains(EARLIER - timedelta(microseconds=1))
    assert ValidInterval(start=EARLIER).contains(LATER)
    with pytest.raises(ValueError, match="UTC offset"):
        interval.contains(datetime(2026, 11, 28))


@pytest.mark.parametrize("end", [EARLIER, EARLIER - timedelta(microseconds=1)])
def test_reversed_and_empty_valid_intervals_reject(end):
    with pytest.raises(ValidationError, match="end must follow"):
        ValidInterval(start=EARLIER, end=end)


def test_all_temporal_fields_normalize_utc_and_reject_naive_values():
    shifted = NOW.astimezone(timezone(timedelta(hours=2)))
    point = ReadPoint(valid_time=shifted, info_horizon=shifted)
    assert point.valid_time == point.info_horizon == NOW
    assert point.valid_time.tzinfo is UTC
    timing = RevisionTiming(
        valid=ValidInterval(start=EARLIER, end=shifted), observed_at=shifted, info_horizon=shifted
    )
    assert timing.valid.end.tzinfo is UTC
    assert timing.observed_at.tzinfo is timing.info_horizon.tzinfo is UTC
    naive = datetime(2026, 11, 28)
    for values in ({"valid_time": naive}, {"info_horizon": naive}):
        with pytest.raises(ValidationError, match="UTC offset"):
            ReadPoint(**({"valid_time": NOW, "info_horizon": NOW} | values))
    for values in ({"start": naive}, {"end": naive}):
        with pytest.raises(ValidationError, match="UTC offset"):
            ValidInterval(**({"start": EARLIER, "end": NOW} | values))
    for values in ({"observed_at": naive}, {"info_horizon": naive}):
        with pytest.raises(ValidationError, match="UTC offset"):
            RevisionTiming(
                **({"valid": timing.valid, "observed_at": NOW, "info_horizon": NOW} | values)
            )


def test_validity_does_not_establish_earlier_knowledge():
    timing = revision().timing
    assert not ReadPoint(valid_time=EARLIER, info_horizon=EARLIER).includes(timing)
    assert ReadPoint(valid_time=EARLIER, info_horizon=NOW).includes(timing)
    assert ReadPoint(valid_time=LATER, info_horizon=NOW).includes(timing)
    assert not ReadPoint(valid_time=EARLIER - timedelta(microseconds=1), info_horizon=NOW).includes(
        timing
    )


def test_historical_availability_requires_evidence_not_just_old_validity():
    values = {"valid": ValidInterval(start=EARLIER), "observed_at": NOW}
    with pytest.raises(ValidationError, match="explicit evidence"):
        RevisionTiming(**values, info_horizon=EARLIER)
    with pytest.raises(ValidationError, match="cannot follow"):
        RevisionTiming(**values, info_horizon=LATER)
    justified = RevisionTiming(
        **values, info_horizon=EARLIER, availability_evidence_ids=("e:2", "e:1", "e:2")
    )
    assert justified.availability_evidence_ids == ("e:1", "e:2")
    assert ReadPoint(valid_time=EARLIER, info_horizon=EARLIER).includes(justified)


def test_source_validity_can_be_in_the_future_of_observation():
    timing = RevisionTiming(valid=ValidInterval(start=LATER), observed_at=NOW, info_horizon=NOW)
    assert ReadPoint(valid_time=LATER, info_horizon=NOW).includes(timing)
    assert not ReadPoint(valid_time=NOW, info_horizon=NOW).includes(timing)


def test_verified_original_byte_spans_handle_unicode_crlf_and_repeated_text():
    rev = revision()
    needle = "Héllo".encode()
    start = BODY.rindex(needle)
    span = SourceSpan(
        revision_id=rev.revision_id, content=rev.content, start=start, end=start + len(needle)
    )
    assert span.extract(BODY) == needle
    assert len(needle) != len(needle.decode())
    assert (
        SourceSpan(
            revision_id=rev.revision_id, content=rev.content, start=len(BODY), end=len(BODY)
        ).extract(BODY)
        == b""
    )
    with pytest.raises(ContentMismatchError):
        span.extract(BODY.replace(b"H", b"h"))  # same length, different digest
    with pytest.raises(ContentMismatchError):
        span.extract(BODY[:-1])


@pytest.mark.parametrize("start,end", [(-1, 1), (0, -1), (2, 1), (0, len(BODY) + 1), (True, 2)])
def test_invalid_spans_reject(start, end):
    with pytest.raises(ValidationError):
        SourceSpan(
            revision_id="revision:1",
            content=ContentReference.from_bytes(BODY),
            start=start,
            end=end,
        )


def test_empty_content_and_malformed_reference_validation():
    empty = ContentReference.from_bytes(b"")
    assert empty.byte_length == 0
    empty.verify(b"")
    for changes in ({"byte_length": -1}, {"byte_length": True}, {"digest": "not-a-hash"}):
        with pytest.raises(ValidationError):
            ContentReference(**(empty.model_dump() | changes))


def test_chunk_content_and_occurrence_separate_reuse_from_source_placement():
    a, b = revision(), revision(source="source:b")
    chunk = ChunkContent(content=ContentReference.from_bytes(BODY), chunker=chunker(size=100))
    occurrences = [
        ChunkOccurrence(
            chunk=chunk,
            span=SourceSpan(revision_id=r.revision_id, content=r.content, start=0, end=len(BODY)),
        )
        for r in (a, b)
    ]
    assert occurrences[0].chunk.chunk_id == occurrences[1].chunk.chunk_id
    assert occurrences[0].occurrence_id != occurrences[1].occurrence_id
    changed = ChunkContent(content=chunk.content, chunker=chunker(size=50))
    assert changed.chunk_id != chunk.chunk_id
    newer = ArtifactSpec(
        implementation=chunk.chunker.implementation,
        implementation_version="2",
        config_fingerprint=chunk.chunker.config_fingerprint,
    )
    assert ChunkContent(content=chunk.content, chunker=newer).chunk_id != chunk.chunk_id


def test_batches_are_bounded_unique_and_report_incomplete_empty_results():
    a, b = revision(), revision(key="b")
    limits = DocumentLimits(max_revisions=1, max_content_bytes=len(BODY))
    assert DocumentBatch(revisions=(a,), limits=limits).revisions == (a,)
    for values, message in (
        ({"revisions": (a, b), "limits": limits}, "max_revisions"),
        ({"revisions": (a,), "limits": DocumentLimits(max_content_bytes=1)}, "max_content_bytes"),
        ({"revisions": (a, a)}, "duplicate revision"),
    ):
        with pytest.raises(ValidationError, match=message):
            DocumentBatch(**values)
    gap = CoverageGap(
        code="capture-incomplete", status=CoverageStatus.PARTIAL, message="budget", source="test"
    )
    page = DocumentBatch(continuation="opaque:next", gaps=(gap,))
    assert not page.revisions and page.continuation and page.gaps
    assert not DocumentBatch().gaps
    for values in ({"max_revisions": 0}, {"max_content_bytes": 0}, {"max_revisions": True}):
        with pytest.raises(ValidationError):
            DocumentLimits(**values)


def test_contracts_are_frozen_and_json_roundtrip_rejects_unknown_versions():
    rev = revision(
        native_revision="v1",
        evidence_ids=("e:1",),
        media_type="text/markdown",
    )
    origin = OriginReference(
        source_entity_id="commit:old-id", field="message", source_version="sha"
    )
    doc = TextDocument(key=rev.document.key, kind="commit-message", origin=origin)
    collection = DocumentCollection(
        key=SourceKey(source_instance="local", native_key="a"), document_ids=(doc.document_id,)
    )
    span = SourceSpan(revision_id=rev.revision_id, content=rev.content, start=0, end=len(BODY))
    occurrence = ChunkOccurrence(
        chunk=ChunkContent(content=rev.content, chunker=chunker()), span=span
    )
    values = [
        rev,
        doc,
        origin,
        collection,
        span,
        occurrence,
        DocumentBatch(revisions=(rev,)),
        ReadPoint(valid_time=EARLIER, info_horizon=NOW),
    ]
    for value in values:
        restored = type(value).model_validate_json(value.model_dump_json())
        assert restored == value
        with pytest.raises(ValidationError, match="frozen"):
            value.schema_version = 2
        for invalid_version in (2, True, 1.0, "1"):
            with pytest.raises(ValidationError):
                type(value).model_validate(value.model_dump() | {"schema_version": invalid_version})
        with pytest.raises(ValidationError, match="Extra inputs"):
            type(value).model_validate(value.model_dump() | {"unknown": True})
    assert (
        DocumentRevision.model_validate_json(rev.model_dump_json()).revision_id == rev.revision_id
    )
    assert isinstance(rev.evidence_ids, tuple)
    assert isinstance(collection.document_ids, tuple)


def test_source_and_reader_ports_do_not_require_repository_or_framework_types():
    class Source:
        source_instance = "memory:example"

        def capture(self, *, native_keys, limits, continuation=None):
            assert native_keys == () and continuation is None
            return DocumentBatch(limits=limits)

    class Reader:
        def read(self, reference, *, max_bytes):
            reference.verify(b"")
            assert max_bytes == 0
            return b""

    source, reader = Source(), Reader()
    assert isinstance(source, DocumentSource)
    assert isinstance(reader, ContentReader)
    assert source.capture(native_keys=(), limits=DocumentLimits()).revisions == ()
    assert reader.read(ContentReference.from_bytes(b""), max_bytes=0) == b""
