# Logical memory layers and explicit relations

PMEM uses one project-local memory store. These logical levels describe how
information is used; they do not create three copies, three databases or three
security boundaries:

| Level | Purpose | Representation |
| --- | --- | --- |
| L1 | Current task, working context, blocker and handoff | Task state and bounded compiled context; temporary research outside Git |
| L2 | Project sources, knowledge, decisions and their rationale | Source files, existing knowledge/rationale Markdown, derived SQLite/search indexes |
| L3 | Explicitly assigned reusable rules and skills | Approved versioned documents/skills, loaded for their intended consumers |

Project scope, memory type, domain and audience are independent axes. The
existing path classifier still rejects `shared`. This change does not implement
shared retrieval, grant access to another project, or automatically promote
project knowledge into general rules. Static dependencies, similarity and prose
containing “because” do not establish causality.

## Service contract and durable representation

The service functions `add_knowledge`/`update_knowledge` and
`add_rationale`/`update_rationale` accept existing string links and explicit
structured dictionaries in `links`. CLI add/update accept `--links-json` alongside
legacy repeated `--link`. MCP exposes `pmem_knowledge_add/update` and
`pmem_rationale_add/update` through the existing project write lock/queue.
MCP file inputs must already exist relative to its fixed root; it accepts no
root override or shell command. A queued result has `completed=false` and no
record: callers must not claim persistence until execution and verification.
Update with omitted links preserves the batch; an explicit empty array clears it.

CLI `overview --limit N` and `relations --kind knowledge|rationale --id ID --limit N`
emit JSON. MCP equivalents are `pmem_overview` and `pmem_relations`. These reads
use an existing in-root database without index/model initialization. There is
still no automatic full-database restore.

Example structured assertion:

```json
{
  "relation": "supports",
  "target": {"kind": "knowledge", "id": "storage-choice"},
  "source": {"path": "docs/storage-experiment.md", "revision": "<64 lowercase SHA-256 hex digits>"},
  "evidence": ["docs/storage-experiment.md#results"],
  "confidence": 0.7,
  "status": "current"
}
```

Allowed relation names: `causes`, `supports`, `contradicts`, `depends_on`,
`derived_from`, `supersedes`, `affects`, `documented_in`. A relation records an
assertion. Source revision records provenance; confidence is the author's
assessment, not a measured probability. Evidence references are preserved,
not fetched or certified. Even a matching source hash and confidence 1.0 do
not mark `causes` or any other assertion verified.

Targets are explicit `knowledge`/`rationale` IDs, `file` paths or `domain`
slugs. Record targets must exist in the same store and their Markdown must
exist inside the project. File targets must exist before writing; paths with
parent traversal, absolute paths and symlinks escaping the project are rejected.
Domain targets must occur in the existing domain allowlist or the actual
`memory.classification.domains` configuration. Unknown fields (including a
foreign project selector), self record links and self file links are rejected.
This is local target resolution, not proof of the historical origin of an
imported document.

Source is a project-relative existing file plus an explicit SHA-256 revision.
A historical revision is allowed: reading details compares it with the current
source and returns `matches`, `stale` or `unavailable`. `matches` describes
bytes, not truth. Relation lifecycle is `current` or `archived`. Target record
lifecycle is reported separately, including missing targets. A `supersedes`
relation does not retire another record; the existing entry lifecycle API
retains its own semantics.

The complete link batch is validated before entry Markdown or entry/link rows
are written. There are at most 100 new links, 20 nonempty evidence references
per structured link, and 2,048 characters per path/reference. This validation
is not a new transaction spanning files, SQLite and vectors: existing failure
and write-lock boundaries still apply.

Generated knowledge/rationale frontmatter includes `pmem_links_kind` and a
single JSON-valued `pmem_links` key (JSON is also valid YAML). The array retains
legacy strings and structured dictionaries. SQLite `knowledge_links` and
`rationale_links` remain derived projections, using their existing
`properties_json`; no schema migration or second database is required.
Existing typed evidence fields and body text keep their previous meaning.
Legacy links are not upgraded to verified structured assertions.

`links=None` on update preserves existing links, including historical source
revisions and archived relation status, and writes them to the new Markdown.
Explicit `links=[]` clears links. An explicit list replaces the batch, as with
the previous API. Add with `links=None` reads `pmem_links` from an imported
Markdown note. Explicit arguments override imported links. Existing untouched
notes are not rewritten or migrated automatically.

## Restore and index limits

`restore_links(store, kind, entry_id, markdown)` explicitly rebuilds link rows
from saved Markdown, **after the owner and all record endpoints have been
restored**. The Markdown must name the matching `pmem_id` and
`pmem_links_kind`, and include `pmem_links`. Validation occurs before replacing
link rows. Missing endpoints/sources fail; the helper does not silently drop
relations or rewrite the supplied Markdown. The caller must restore the saved
Markdown alongside the records, rather than keep an unrelated replacement note.

Ordinary changed indexing leaves existing link tables intact. It does not
rebuild `knowledge_entries`/`rationale_entries` from Markdown. Rebuilding the
whole database therefore still requires a separate coordinated restore flow;
this helper is only the second phase. Cross-record cycles require restoring
all endpoints first. Retaining Markdown makes the assertions recoverable,
without claiming that ordinary reindex already performs that recovery.

General source cleanup owns only File/Module/Symbol/Chunk/Route nodes and their source
FTS rows. It must not remove separately maintained Knowledge/Rationale nodes or
FTS rows at the same path. This matters when upgrading a legacy manifest that
also indexed memory Markdown as ordinary source files. The source walker now
excludes the private `.project-memory` tree; knowledge/rationale are maintained
by their dedicated write paths. Primary notes and link tables are not cleanup
targets.

## Bounded overview

`memory_overview(root, limit=20)` reads the configured in-project SQLite file
through a read-only connection. It returns independent axis counts, entry/link
counts and deterministic file/entry/relation samples. `limit` is 1–100;
`truncated` reports capped groups and samples. Counts aggregate the indexed
rows, so output is bounded but work is not claimed to be constant-time.
Missing tables in a legacy schema are omitted; a missing database is reported
without creating one. Relation samples include legacy assertions, not evidence
validation; use detail retrieval for source revision and lifecycle diagnostics.

The overview always reports `filesystem_checked=false` and
`shared_included=false`. It performs no freshness pass, model initialization,
source traversal or auto-index. Counts describe the index, which may be stale
or incomplete; missing domain metadata is shown as `unclassified`.
