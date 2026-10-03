"""Standalone, dependency-free entrypoint copied into the shared installation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import sys


def resolve_binding(shared: Path, root: Path, binding_id: str) -> Path:
    shared = shared.resolve(strict=True)
    root = root.resolve(strict=True)
    local = root / ".project-memory" / "runtime-binding.json"
    if local.is_symlink() or local.parent.is_symlink():
        raise ValueError("Project binding and memory directory must not be symlinks")
    binding = json.loads(local.read_text(encoding="utf-8"))
    registry = json.loads((shared / "projects.json").read_text(encoding="utf-8"))
    entry = registry.get("projects", {}).get(binding_id)
    expected = {"project_root": str(root), "runtime_root": str(shared), "binding_id": binding_id}
    if binding.get("schema_version") != 1 or any(binding.get(k) != v for k, v in expected.items()):
        raise ValueError("Project binding does not match the selected root and shared runtime")
    if registry.get("schema_version") != 1 or entry != {"project_root": str(root)}:
        raise ValueError("Project is not registered for this exact memory root")
    manifest = json.loads((shared / "runtime.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("package") != "project-memory-kit":
        raise ValueError("Invalid shared runtime manifest")
    runtime = (shared / manifest["runtime_path"]).resolve(strict=True)
    if not runtime.is_relative_to(shared / "releases") or not (runtime / "tools/project_memory/cli.py").is_file():
        raise ValueError("Shared runtime generation escapes the managed installation")
    return runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PMEM with an exact registered project binding")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--binding", required=True)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    args = options.args[1:] if options.args[:1] == ["--"] else options.args
    try:
        selected = Path(options.project_root).resolve(strict=True)
        runtime = resolve_binding(Path(__file__).parent, selected, options.binding)
        for i, value in enumerate(args):
            if value in {"--r", "--ro", "--roo", "--root"}:
                if i + 1 >= len(args) or Path(args[i + 1]).resolve() != selected:
                    raise ValueError("--root must match this project's registered memory root")
            elif value.partition("=")[0] in {"--r", "--ro", "--roo", "--root"} and Path(value.partition("=")[2]).resolve() != selected:
                raise ValueError("--root must match this project's registered memory root")
        os.chdir(selected)
        os.environ["PMEM_BOUND_ROOT"] = str(selected)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(runtime))
        sys.argv = ["pmem", *args]
        runpy.run_module("tools.project_memory.cli", run_name="__main__")
    except (ValueError, OSError, KeyError) as error:
        print(f"PMEM shared binding error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
