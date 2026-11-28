"""Real GestaltDB capability smoke test against the pinned backend.

This exercises the temporal APIs RH-06 depends on, using a temporary LMDB graph.
It requires no network access or model credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("gestaltdb")

from gestaltdb.graphdb import Edge, GraphDB, Node  # noqa: E402
from gestaltdb.versioning import EdgeVersionWrite, NodeVersionWrite  # noqa: E402

from synirmos.storage.capabilities import require_capabilities  # noqa: E402

UTC = UTC
VALID_FROM = datetime(2026, 9, 14, 20, 15, 31, tzinfo=UTC)


def test_required_capabilities_include_gestaltdb_temporal_api():
    checks = {item.name: item for item in require_capabilities(backend="lmdb")}
    assert checks["gestaltdb"].available
    assert checks["gestaltdb-temporal-api"].available


def test_temporal_write_read_reopen_and_index(tmp_path):
    path = tmp_path / "graph"
    database = GraphDB.create(str(path), backend="lmdb", overwrite=True)
    try:
        node = Node(
            node_id="commit:9bfe6c1",
            labels=("Commit",),
            properties={"sha": "9bfe6c1", "message": "trust fetched contracts"},
        )
        version = database.temporal.put_node_version(node, valid=(VALID_FROM, None))
        assert version.logical_id == "commit:9bfe6c1"

        before = database.temporal.get_node_as_of(
            "commit:9bfe6c1", valid_time=VALID_FROM - timedelta(seconds=1)
        )
        assert before is None

        observed = database.temporal.get_node_as_of(
            "commit:9bfe6c1", valid_time=VALID_FROM + timedelta(hours=1)
        )
        assert observed is not None
        assert observed.node.properties["sha"] == "9bfe6c1"
        assert observed.node.labels == ("Commit",)

        database.create_node_property_index("sha")
        assert "sha" in database.index_statistics()["indexed_node_properties"]
        assert len(list(database.temporal.iter_node_versions("commit:9bfe6c1"))) == 1
    finally:
        database.close()

    reopened = GraphDB.open(str(path))
    try:
        observed = reopened.temporal.get_node_as_of(
            "commit:9bfe6c1", valid_time=VALID_FROM + timedelta(hours=1)
        )
        assert observed is not None
        assert observed.node.properties["message"] == "trust fetched contracts"
    finally:
        reopened.close()


def test_native_temporal_batch_and_pinned_commit_view(tmp_path):
    """0.17 can publish a batch and read old edges after later correction."""

    database = GraphDB.create(tmp_path / "graph", backend="lmdb")
    try:
        edge = Edge("edge:1", "person:1", "org:1", {"type": "MEMBER_OF"})
        first = database.temporal.commit_versions(
            [
                NodeVersionWrite.assertion(Node("person:1"), (VALID_FROM, None)),
                NodeVersionWrite.assertion(Node("org:1"), (VALID_FROM, None)),
                EdgeVersionWrite.assertion(edge, (VALID_FROM, None)),
            ]
        )
        original = first.versions[-1]
        database.temporal.correct_edge_version(
            Edge("edge:1", "person:1", "org:2", {"type": "MEMBER_OF"}),
            supersedes_version_id=original.version_id,
        )
        with database.temporal.open_read_view(
            database,
            manifest=database.manifest,
            database_id=database.database_id,
            valid_time=VALID_FROM,
            through_commit=first.commit_id,
        ) as view:
            (old,) = view.iter_edges_as_of(source="person:1", edge_type="MEMBER_OF")
            assert old.edge.target == "org:1"
            assert view.commit_horizon == first.commit_id
        latest = database.temporal.get_edge_as_of("edge:1", valid_time=VALID_FROM)
        assert latest.edge.target == "org:2"
        assert database.get_edge("edge:1") is None  # history does not project itself
    finally:
        database.close()


def test_native_transaction_rolls_back_history_and_current_records(tmp_path):
    database = GraphDB.create(tmp_path / "graph", backend="lmdb")
    try:
        with pytest.raises(RuntimeError, match="abort"):
            with database.transaction() as transaction:
                transaction.temporal.put_node_version(Node("doc:1"), valid=(VALID_FROM, None))
                transaction.put_node(Node("doc:1"))
                raise RuntimeError("abort")
        assert database.get_node("doc:1") is None
        assert database.temporal.get_node_as_of("doc:1", valid_time=VALID_FROM) is None
    finally:
        database.close()
