# Graph Schema

With `code_provider.backend: gitnexus`, code symbols, imports, calls, inheritance
and executable flows belong to the explicitly selected GitNexus repository.
The local schema below describes PMEM durable/document data plus legacy code
tables retained for migration compatibility. It does not claim that PMEM builds
a second code graph. Code links preserve repository identity and source revision.

## Node Kinds

Project, Directory, File, Module, Symbol, Chunk, Knowledge, KnowledgeChunk, Rationale, RationaleChunk, Layer, Test, Command, Error, Failure, Fix, ChangeSet, Decision.

## Edge Kinds

CONTAINS, DEFINES, IMPORTS, CALLS, INHERITS, REFERENCES, BELONGS_TO_LAYER, TESTS, COVERS_FILE, DESCRIBES, MENTIONS, TOUCHES, OCCURRED_IN, FIXED_BY, CHANGED, CONSTRAINS.

## Core Pattern

```text
File -> DEFINES -> Symbol
Chunk -> DESCRIBES -> Symbol
Chunk -> DESCRIBES -> File
Test -> TESTS -> Symbol
Test -> COVERS_FILE -> File
ChangeSet -> TOUCHES -> File/Symbol
Error -> OCCURRED_IN -> File/Symbol/Test
Error -> FIXED_BY -> ChangeSet/Fix
Knowledge -> CONTAINS -> KnowledgeChunk
Rationale -> CONTAINS -> RationaleChunk
```

## Parser Coverage

Legacy PMEM parser coverage below is not the active GitNexus coverage contract.
Consult the actual selected provider/index diagnostics for code coverage.

- Python: modules, classes, functions, methods, imports, calls, inheritance, docstrings, line ranges.
- JavaScript/TypeScript/JSX/TSX: modules, classes, functions, methods, imports, exports, require calls, dynamic imports, calls, JSX component references, line ranges.
