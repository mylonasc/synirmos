"""Small 0.17/LMDB characterization probes, not a capacity benchmark.

Run with ``uv run python scripts/characterize_gestaltdb.py > results.json``.
All stores are disposable; no network, models, or application data are used.
"""

from __future__ import annotations

import json
import platform
import statistics
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from itertools import islice
from pathlib import Path

from gestaltdb.graphdb import Edge, GraphDB, Node
from gestaltdb.versioning import EdgeVersionWrite, NodeVersionWrite

VALID = datetime(2026, 1, 1, tzinfo=UTC)
OPTIONS = {"map_size": 128 * 1024**2}


@contextmanager
def counted_metadata(graph):
    """Count calls/returned bytes, not disk I/O, allocations, or all KV reads."""
    original = graph.store.get_metadata
    counts = {"metadata_gets": 0, "metadata_bytes": 0}

    def counted(key):
        value = original(key)
        counts["metadata_gets"] += 1
        counts["metadata_bytes"] += len(value) if value is not None else 0
        return value

    graph.store.get_metadata = counted
    try:
        yield counts
    finally:
        graph.store.get_metadata = original


def timed(operation):
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(samples), 3)


def measured(graph, probe, operation, **dimensions):
    median = timed(operation)
    with counted_metadata(graph) as counts:
        operation()
    return {"probe": probe, **dimensions, "median_ms": median, **counts}


def history_probes(root):
    for size in (16, 64, 256):
        path = root / f"history-{size}"
        with GraphDB.create(path, backend="lmdb", backend_options=OPTIONS) as graph:
            for i in range(size):
                graph.temporal.put_node_version(Node(f"n:{i}"), valid=(VALID, None))
        with GraphDB.open(path) as graph:

            def point():
                assert graph.temporal.get_node_as_of("n:0", valid_time=VALID) is not None

            yield measured(graph, "one_version_point_read", point, commits=size)

            def open_view(expected_horizon=size):
                with graph.temporal.open_read_view(
                    graph,
                    manifest=graph.manifest,
                    database_id=graph.database_id,
                    valid_time=VALID,
                ) as view:
                    assert view.commit_horizon == expected_horizon

            yield measured(graph, "open_temporal_view", open_view, commits=size)


def write_probes(root):
    for batch_size in (1, 32, 128):
        with GraphDB.create(
            root / f"batch-{batch_size}", backend="lmdb", backend_options=OPTIONS
        ) as graph:
            start = time.perf_counter()
            for offset in range(0, 256, batch_size):
                graph.temporal.commit_versions(
                    [
                        NodeVersionWrite.assertion(Node(f"n:{i}"), (VALID, None))
                        for i in range(offset, offset + batch_size)
                    ]
                )
            yield {
                "probe": "maintained_temporal_write",
                "versions": 256,
                "batch_size": batch_size,
                "commits": 256 // batch_size,
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
            }


def current_probes(root):
    with GraphDB.create(root / "mutable", backend="lmdb", backend_options=OPTIONS) as graph:
        graph.put_nodes(
            [
                Node(f"n:{i}", labels=["Entity"], properties={"cohort": "all", "text": "x" * 256})
                for i in range(2001)
            ]
        )
        graph.put_edges_bulk(
            [Edge(f"e:{i}", "n:0", f"n:{i}", {"type": "LINKS"}) for i in range(1, 2001)]
        )
        graph.create_node_property_index("cohort")
        for capture in (False, True):

            def open_current(capture_provenance=capture):
                with graph.current_read_view(capture_provenance=capture_provenance) as view:
                    assert view.get_node("n:0") is not None

            yield {
                "probe": "open_current_view",
                "nodes": 2001,
                "edges": 2000,
                "capture_provenance": capture,
                "median_ms": timed(open_current),
            }
        yield {
            "probe": "neighbors_current",
            "degree": 2000,
            "eager_median_ms": timed(lambda: graph.neighbors_by_edge_type("n:0", "LINKS")),
            "first_20_iterator_median_ms": timed(
                lambda: list(islice(graph.iter_typed_adjacency("n:0", "LINKS"), 20))
            ),
        }


def historical_hub_probes(root):
    for degree in (32, 128):
        with GraphDB.create(
            root / f"hub-{degree}", backend="lmdb", backend_options=OPTIONS
        ) as graph:
            graph.temporal.commit_versions(
                [
                    EdgeVersionWrite.assertion(
                        Edge(f"e:{i}", "hub", f"n:{i}", {"type": "LINKS"}), (VALID, None)
                    )
                    for i in range(degree)
                ]
            )

            def first_edge():
                return next(
                    graph.temporal.iter_edges_as_of(
                        source="hub", edge_type="LINKS", valid_time=VALID
                    )
                )

            yield measured(
                graph, "first_historical_edge", first_edge, degree=degree, commits=1, returned=1
            )
            # MVCC enables authenticated reuse. Skip only unrelated mutable-state
            # hashing: temporal provenance authentication remains enabled.
            with graph.current_read_view(capture_provenance=False) as pinned:
                with pinned.temporal.open_read_view(
                    pinned,
                    manifest=pinned.manifest,
                    database_id=pinned.database_id,
                    valid_time=VALID,
                ) as view:

                    def first_pinned_edge():
                        return next(view.iter_edges_as_of(source="hub", edge_type="LINKS"))

                    yield measured(
                        pinned,
                        "first_historical_edge_snapshot_pinned",
                        first_pinned_edge,
                        degree=degree,
                        commits=1,
                        returned=1,
                    )


def main():
    with tempfile.TemporaryDirectory(prefix="gestaltdb-characterization-") as temp:
        root = Path(temp)
        probes = [
            result
            for probe in (history_probes, write_probes, current_probes, historical_hub_probes)
            for result in probe(root)
        ]
    print(
        json.dumps(
            {
                "version": version("gestaltdb"),
                "lmdb": version("lmdb"),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "probes": probes,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
