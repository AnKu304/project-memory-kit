"""Isolated stdlib resource probe; never opens an installed project or model."""
from __future__ import annotations

import json
import gc
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from unittest import mock

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_text
from tools.project_memory.ignore import is_binary
from tools.project_memory.services.auto_index import index_freshness


def main():
    with tempfile.TemporaryDirectory(prefix="pmem-freshness-probe-") as temporary:
        root = Path(temporary)
        large = root / "large.dat"
        with large.open("wb") as handle:
            for _ in range(512):
                handle.write(b"x" * 65536)
        durations = []
        tracemalloc.start()
        for _ in range(3):
            started = time.perf_counter()
            assert not is_binary(large)
            durations.append((time.perf_counter() - started) * 1000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        large.unlink()
        store = SQLiteGraphStore(root, root / ".project-memory/graph.sqlite")
        store.initialize()
        count = 1000
        content = "value = 1\n"
        for i in range(count):
            (root / f"fixture_{i:04}.py").write_text(content, encoding="utf-8")
        connection = store.connect()
        try:
            with connection:
                connection.executemany(
                    "INSERT INTO file_index_state(path,hash,indexed_at,parser,warnings_json) VALUES(?,?,?,?,?)",
                    [(f"fixture_{i:04}.py", sha256_text(content), "fixture", "fixture", "[]") for i in range(count)],
                )
        finally:
            connection.close()
        original = SQLiteGraphStore.connect
        connection_count = 0

        def connect(instance):
            nonlocal connection_count
            connection_count += 1
            return original(instance)

        timings = []
        try:
            with mock.patch.object(SQLiteGraphStore, "connect", connect):
                for _ in range(3):
                    started = time.perf_counter()
                    assert index_freshness(root).fresh
                    timings.append((time.perf_counter() - started) * 1000)
        finally:
            gc.collect()
        print(json.dumps({
            "binary_probe_bytes": 33554432, "binary_probe_repeats": 3,
            "binary_probe_median_ms": round(statistics.median(durations), 3),
            "binary_probe_tracemalloc_peak_bytes": peak,
            "freshness_files": count, "freshness_repeats": 3,
            "freshness_median_ms": round(statistics.median(timings), 3),
            "freshness_connections_per_call": connection_count // 3,
            "note": "Temporary fixtures only; tracemalloc is Python allocation peak, not RSS. No vector backend or index build.",
        }, indent=2))


if __name__ == "__main__":
    main()
