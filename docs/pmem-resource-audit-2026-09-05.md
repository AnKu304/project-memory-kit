# PMEM resource audit — 2026-09-05

Target: AnKu304/project-memory-kit, source baseline
`ecaade31f03077a09d6afd30e429f4b498cd1271` (0.22.2).
This is the heavier PMEM implementation, not codex-project-memory and not Tencent.
The user's priority is preserving useful retrieval and dependency context while
reducing avoidable resource consumption, not replacing it with fewer capabilities.

## Confirmed: whole-file read for a prefix check

`tools/project_memory/ignore.py:is_binary` used `path.read_bytes()[:2048]`.
Python first allocated/read the entire file and only then selected the prefix.
The implementation now opens the file and reads at most 2048 bytes. Null detection,
empty files, unreadable files, and the existing prefix-sampling semantics remain
unchanged. This does not claim that binary data beyond the prefix is detected.

## Confirmed: SQLite connection amplification in freshness checks

`services/auto_index.py:index_freshness` called `store.file_hash` for every file.
Each lookup opened/configured SQLite and read configuration again. The new
`SQLiteGraphStore.indexed_file_hashes` reads one path/hash snapshot and closes its
connection; additions, same-size content changes and removals are still checked.
No resident cache, timer, skipped source hashing, or schema migration was added.
The in-memory manifest is proportional to indexed paths; this is not constant-memory
indexing or elimination of the full freshness scan.

## Comparable root-agent probe

Python 3.11, same machine, temporary fixtures only, median of three sequential
calls, no cold-cache control. Binary fixture: 32 MiB. Freshness fixture: 1000 small
Python files with a pre-populated SQLite manifest. No installed project, vector
model, Qdrant process, or user archive is opened. Fixture construction is outside
the timed region. Connection instrumentation counts calls without retaining them.

| Operation | Before | After |
| --- | ---: | ---: |
| Binary probe Python allocation peak (`tracemalloc`) | 33,559,138 B | 7,021 B |
| Binary probe median | 4.863 ms | 0.035 ms |
| Freshness connections per call | 1002 | 2 |
| Freshness median | 288.753 ms | 74.310 ms |

Allocation peak is not process RSS. These measurements do not establish the cause
of the user's historical 50 GB directory or all machine-wide RAM/CPU usage.
Source revision was baseline with this working-tree patch; exact patch is retained
in Git. Reproduction script: `scripts/measure-freshness-resources.py`.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 scripts/measure-freshness-resources.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests -p test_freshness_resources.py -q
```

Baseline full suite: 54 passed (38.904 s). New regressions failed before changes
for unbounded reads and 22 connections for 20 files; all three targeted tests then
passed. Combined acceptance after integrating the vector work is recorded below,
not implied by these component results.

Combined source acceptance: **67 tests passed in 38.712 s**, including the three
freshness regressions and ten vector/resource/recovery tests. The first combined
run's terminal completion was not retained; the suite was repeated once to
capture this verifiable result. No performance conclusion is based on that lost
output. The vector component is described in `vector-resource-audit.md`.
An existing installation was subsequently inspected read-only. Its detailed
project-specific audit is retained privately outside the source repository;
only reusable implementation changes and synthetic measurements belong here.

The checkout has no installed `./pmem`, `tools/project_memory`, or `.project-memory`
runtime. Self-hosted doctor/context/index lifecycle is unavailable here; the root
was not initialized as a smoke test. Runtime/installer tests use disposable fixtures.
Existing projects have copied runtime files: updating this source checkout alone
does not update those installations. No user database or existing configuration
was modified, and no memory/history cleanup or backend migration was performed.

## Request and changed-index follow-up

Context now shares one freshness/impact result per request, and reuses its
embedding model and query vector across layer searches. The cache is capped at
eight resources, keyed by project root/model/backend/vector size as appropriate,
and discarded after the request. It never retains a Qdrant client or database
lock. Typed vector-busy diagnostics reach ordinary and compiled context even
with zero hits; a busy backend is not retried for each layer. The next request
can try again. This is not a persistent daemon or a guarantee of semantic recall.

Changed indexing compares all allowed source hashes with one SQLite manifest.
Git's working diff previously hid a committed/pulled changed file whenever an
unrelated dirty file existed. A two-file regression reproduced `indexed=1`
instead of `indexed=2`; the manifest-based implementation indexes both. A
no-change indexing pass no longer initializes vectors or an embedding model.
Only changed files are parsed/embedded; hashing is still project-wide. Removed
SQLite sources are cleaned from the same inventory; this does not yet compact
or prune old vector storage.

Focused verification: two new index regressions, eight scope checks, ten vector
resource checks, ten busy-search checks, ten request checks and twelve filter
checks passed. One busy test's embedding mock had to return an actual vector
instead of an unconfigured Mock after query vectors became immutable cached
tuples. These results are not the later integrated release acceptance.

SQLite operation contexts now close their connection after commit/rollback.
Previously `with sqlite3.Connection` only ended a transaction and left handle
lifetime to garbage collection. Two failing-first checks cover successful
commit/close and exception rollback/close. The relation/overview checks also pass
with the new lifecycle, without the previously observed unclosed-connection
warnings. Explicitly opened connections still require caller-owned `close`.
