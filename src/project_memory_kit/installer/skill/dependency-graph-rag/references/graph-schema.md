# Graph Schema

## Node Kinds

Project, Directory, File, Module, Symbol, Chunk, Layer, Test, Command, Error, Failure, Fix, ChangeSet, Decision.

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
```

