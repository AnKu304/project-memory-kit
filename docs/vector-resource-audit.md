# PMEM vector resource audit — 2026-09-05

Repository: `AnKu304/project-memory-kit` 0.22.2. Baseline:
`ecaade31f03077a09d6afd30e429f4b498cd1271`; implementation: `d278cbf` plus required recovery fix `dfecddc`.
Worktree: `/tmp/pmem-vector-work.Jrnf2v`, branch `codex/pmem-vector-resources`.
Measurements from the other `codex-project-memory` repository do not apply here.

## Confirmed causes

- Each fallback upsert read and parsed the entire existing JSONL, materialized a
  list of vectors/payloads, then serialized and rewrote every row. For 500 new
  chunks this parsed 124,750 rows (175,708,897 bytes) and serialized 125,250 rows
  (176,413,398 bytes), although the resulting file was only 704,501 bytes.
- If FastEmbed construction failed after QdrantClient was created, `auto`
  released the resource lock and discarded the client without closing it.
  Strict mode also released the lock before eventual destructor cleanup.
  A fake-client regression reproduced both lifecycle outcomes without importing
  models, downloading anything or starting a Qdrant service.

## Changes and contracts

`QdrantLocalStore.batch_fallback` explicitly batches fallback writes within each
indexed file in `services/index_project.py`. It flushes at 128
pending unique IDs or 1 MiB of serialized pending text, and on context exit.
An oversized single record remains supported and flushes immediately. Duplicate
IDs are last-write-wins, including across batches; order matches sequential
upserts. Payloads are serialized on acceptance, so later caller mutation does
not change pending records.

`_flush_fallback` streams existing rows and atomically replaces the JSONL from a
temporary file in the same directory. Existing malformed JSON or write/replace
failures leave the prior file intact and remove the owned temporary file. No
resident cache of the whole existing JSONL is kept. Ordinary upserts outside a
batch remain immediately written. Existing rows retain their JSON formatting;
the id/vector/payload data format is unchanged.

Completed chunks flush when the batch body raises. This is not a transaction
rollback: earlier accepted chunks can persist if later work fails. `_index_file`
first clears the old file state, then parses/writes chunks and flushes the file's
fallback batch, and only then publishes the new hash with the original parser
name and raw warnings. Thus failed/interrupted flushes leave the file eligible
for `index changed`; a failure between successful flush and hash publication
also safely retries. The initial whole-index batch implementation was rejected
because it published hashes too early: do not integrate `d278cbf` without
`dfecddc`. Tests verify hash absence at replace time and actual retry after a
replace failure. No SIGKILL/power-loss experiment was run; ordering is the basis
for the process-interruption reasoning, not a new fsync/power-loss guarantee.
SQLite and vectors are still not a coordinated transaction. Runtime write
commands retain their existing outer project lock; batching adds no lock bypass
or automatic retry. Direct concurrent unguarded class callers are not made safe
by atomic replacement alone. Streaming peak memory still includes one existing
JSONL line, the pending data and the incoming row; the 1 MiB limit is not a hard
whole-process RAM cap.

Initialization failures now call `close()` before releasing the resource lock,
covering both auto and strict modes. The existing idempotent close implementation
handles client close errors and then releases the lock.

Qdrant embedding, upsert and semantic query logic is unchanged. Fallback search
already returned `[]` before this patch; hybrid retrieval then uses SQLite/BM25.
This patch preserves that behavior and all stored fallback vectors; it does not
claim to add semantic ranking to deterministic fallback. Knowledge/rationale
single-record callers remain immediate and were not edited.

## Comparable fixture results

macOS, Python 3.14.3; three sequential repetitions per size/revision, medians,
no cold-cache control. Each fixture is a fresh TemporaryDirectory, fallback
backend, 64-dimensional deterministic vectors, unique chunk IDs and small
synthetic symbol payloads sharing `file_path=fixture.py`, in one file-sized
batch. Timed region includes embedding and persistence,
not fixture setup. This is a vector-store helper microbenchmark, not a timing
of actual indexing of 250/500 files. Actual index integration was separately
verified on one Python file with 130 symbols. No user project or database was scanned.

| Chunks | Wall before | Wall after | CPU before | CPU after | Final JSONL, both |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 250 | 1.0689 s | 0.00967 s | 1.0678 s | 0.00966 s | 351,902 B |
| 500 | 4.1960 s | 0.02478 s | 4.1898 s | 0.02478 s | 704,111 B |

A separate earlier JSON parse/serialize counter probe used distinct synthetic
file_path labels inside a single batch, with 500 chunks. It observed 500 new
serialized rows (704,501 bytes) and 768 parsed old rows (1,082,376 bytes) after
batching. Total file output is new serialized bytes plus retained copied lines:
1,786,877 bytes on this all-unique fixture, versus 176,413,398 before. These are
logical UTF-8 bytes, not measured physical filesystem/device writes.

Separate counter-probe process peak RSS was 58,146,816 B before and 29,818,880 B
after. This includes interpreter/imports/instrumentation and both fixture sizes;
it is not production MCP/Qdrant RSS. The wall/CPU table above was collected
without counter instrumentation after the recovery fix. The earlier counter
probe preceded the reuse of the computed incoming UTF-8 row length.

Fixed-size batching reduces amplification but **does not eliminate quadratic
cost**: growing files are still scanned/copied once per batch, O(N² / 128) for
similar-size unique inserts within a large file. Many one-chunk files do not
receive the 128-row batching benefit: only streaming and avoiding serialization
of unchanged rows help that workload. Large pre-existing files and single-record updates
still require a scan. An incremental persistence format would require a separate
migration/compatibility design, not a hidden format change in this patch.

## Verification and reproduction

New `tests/test_vector_resources.py` covers initialization cleanup order,
last-write-wins byte equivalence, bounded pending rows, payload snapshotting,
oversized rows, exception-body flush, malformed JSON, failed atomic replace,
temporary cleanup, actual index integration (130 symbols → two flushes), no-op
index preserving JSONL bytes, and a fake Qdrant semantic-query contract.

Failing-first: baseline failed the lifecycle assertions and lacked the requested
batch API/atomic-replace contract. The initial whole-index batch also failed two new recovery/publication-order
regressions. Final affected suite: 10 tests PASS, 0.275 s.
`git diff --check` passed. Coordinator owns the full baseline/final suite; this
component result is not an end-to-end retrieval-quality certification.

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests -p test_vector_resources.py -q
```

Run the following Python with the same PYTHONPATH from this repository to
reproduce the clean timing comparison. It loads baseline source only into a
local temporary module and creates only disposable fallback fixtures:

```python
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import statistics, subprocess, tempfile, time
from tools.project_memory.vector.qdrant_store import QdrantLocalStore

with tempfile.TemporaryDirectory() as source_dir:
    source = Path(source_dir) / 'baseline.py'
    source.write_bytes(subprocess.check_output([
        'git', 'show', 'ecaade3:src/project_memory_kit/installer/runtime/tools/'
        'project_memory/vector/qdrant_store.py']))
    spec = importlib.util.spec_from_file_location('baseline', source)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    for label, cls in [('before', baseline.QdrantLocalStore), ('after', QdrantLocalStore)]:
        for count in (250, 500):
            wall, cpu = [], []
            for _ in range(3):
                with tempfile.TemporaryDirectory() as fixture:
                    store = cls(Path(fixture), backend='fallback')
                    batch = store.batch_fallback() if hasattr(store, 'batch_fallback') else nullcontext()
                    start, start_cpu = time.perf_counter(), time.process_time()
                    with batch:
                        for i in range(count):
                            store.upsert_chunk(f'chunk-{i}', f'function example_{i}(): return {i}',
                                               {'file_path': 'fixture.py', 'kind': 'symbol'})
                    wall.append(time.perf_counter() - start)
                    cpu.append(time.process_time() - start_cpu)
                    size = store.fallback_file.stat().st_size
                    store.close()
            print(label, count, statistics.median(wall), statistics.median(cpu), size)
```

Self-hosted `./pmem` pre/postflight, knowledge/rationale and failure-memory
updates were unavailable: the saved checkout and new worktree contain no
installed `pmem`, `tools`, `.project-memory` or `.agents` runtime. No root
installation or new semantic memory was created to work around that absence.
Source inspection and isolated tests supplied impact verification. No models,
dependencies, services, existing installations, user history or databases were
changed. Historical heavy-use RAM/CPU and real FastEmbed/Qdrant quality remain
unmeasured by this component audit.
