from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

from project_memory_kit.installer.manifest import InstallReport, write_text_file
from project_memory_kit.installer.templates import runtime_root
from project_memory_kit.version import __version__


def _json(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"Managed metadata must not be a symlink: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Managed metadata must be an object: {path}")
    return data


def _atomic_json(path: Path, data: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".pmem-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise ValueError("Managed metadata must not be a symlink")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _registry_lock(shared: Path):
    # Serializes installer operations, independently of project DB write locks.
    import fcntl
    with (shared / ".install.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def install_shared_runtime(target: Path, with_vector: bool = False, *, install_dependencies: bool = True) -> InstallReport:
    if target.is_symlink():
        raise ValueError("Shared runtime root must not be a symlink")
    shared = target.resolve()
    if shared == Path.home() or shared == Path(shared.anchor):
        raise ValueError("Select a dedicated shared runtime directory")
    if shared.exists() and any(shared.iterdir()) and not (shared / "runtime.json").is_file() and not (shared / "install-pending.json").is_file():
        raise ValueError("Shared runtime directory is nonempty and is not managed by PMEM")
    shared.mkdir(parents=True, exist_ok=True)
    report = InstallReport(shared)
    with _registry_lock(shared):
        previous_path = shared / "runtime.json" if (shared / "runtime.json").exists() else shared / "install-pending.json"
        previous = _json(previous_path) if previous_path.exists() else {}
        if previous and previous.get("package") != "project-memory-kit":
            raise ValueError("Existing shared runtime belongs to another package")
        _atomic_json(shared / "install-pending.json", {"schema_version": 1, "package": "project-memory-kit", "with_vector": bool(with_vector or previous.get("with_vector"))})
        source = runtime_root()
        digest = hashlib.sha256()
        source_files = sorted(p for p in source.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"})
        for path in source_files:
            digest.update(str(path.relative_to(source)).encode())
            digest.update(path.read_bytes())
        release = shared / "releases" / f"{__version__}-{digest.hexdigest()[:16]}"
        if not release.exists():
            staging = Path(tempfile.mkdtemp(prefix=".runtime-", dir=shared))
            try:
                for path in source_files:
                    destination = staging / path.relative_to(source)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
                release.parent.mkdir(exist_ok=True)
                staging.rename(release)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            report.add_path("created", release)
        python = shared / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.exists():
            venv_command = [sys.executable, "-m", "venv", str(shared / ".venv")]
            if not install_dependencies:  # Offline source-tree tests reuse the test environment.
                venv_command.append("--system-site-packages")
            subprocess.run(venv_command, check=True)
            report.add_path("created", python.parent.parent)
        if install_dependencies:
            dependencies = ["pathspec>=0.12", "PyYAML>=6", "typer>=0.12", "rich>=13"]
            if with_vector or previous.get("with_vector"):
                dependencies.extend(["qdrant-client>=1.9", "fastembed>=0.3"])
            subprocess.run([str(python), "-m", "pip", "install", *dependencies], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            report.commands.append("shared managed dependencies installed")
        write_text_file(shared / "launch.py", Path(__file__).with_name("shared_launcher.py").read_text(encoding="utf-8"), report)
        manifest = {"schema_version": 1, "package": "project-memory-kit", "version": __version__, "runtime_path": str(release.relative_to(shared)), "with_vector": bool(with_vector or previous.get("with_vector"))}
        _atomic_json(shared / "runtime.json", manifest)
        current = shared / "current"
        if current.exists() and not current.is_symlink():
            raise ValueError("Managed current runtime pointer is not a symlink")
        pointer = shared / f".current-{uuid.uuid4()}"
        pointer.symlink_to(release, target_is_directory=True)
        os.replace(pointer, current)
        if not (shared / "projects.json").exists():
            _atomic_json(shared / "projects.json", {"schema_version": 1, "projects": {}})
        (shared / "install-pending.json").unlink()
        report.commands.append(f"shared runtime ready: {release}")
    return report


def shared_binding(root: Path) -> dict | None:
    path = root / ".project-memory/runtime-binding.json"
    return _json(path) if path.exists() else None


def _assert_quiescent(root: Path) -> None:
    if os.name == "nt":
        return  # Windows clients must be stopped by their deployment owner.
    listing = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=True)
    for line in listing.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or "tools.project_memory.cli" not in parts[1]:
            continue
        pid, command = parts
        if not any(word in command.split() for word in ("mcp", "watch")):
            continue
        selected = str(root) in command
        if not selected and shutil.which("lsof"):
            cwd = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True)
            selected = f"n{root}" in cwd.stdout.splitlines()
        if selected:
            raise ValueError(f"Legacy PMEM consumer PID {pid} still uses this root; stop that project consumer before binding")


def _backup_local_runtime(root, shared, manifest, python, binding_id, previous, report):
    state = root / ".project-memory"
    metadata_path = state / "install.json"
    local_runtime = root / "tools/project_memory"
    local_venv = state / "runtime/.venv"
    if local_venv.parent.is_symlink():
        raise ValueError("Project runtime directory must not be a symlink")
    if local_venv.is_symlink() and local_venv.resolve() != (shared / ".venv").resolve():
        raise ValueError("Existing environment link points to a different runtime")
    environment_inventory = None
    if local_venv.is_dir() and not local_venv.is_symlink():
        allowed = {"bin", "include", "lib", "lib64", "share", "pyvenv.cfg", ".gitignore", "CACHEDIR.TAG", "Scripts", "Lib", "Include"}
        if any(path.name not in allowed for path in local_venv.iterdir()):
            raise ValueError("Local venv contains unexpected user files; preserve and reconcile explicitly")
        local_python = local_venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        inventory = subprocess.run([str(local_python), "-m", "pip", "list", "--format=json"], capture_output=True, text=True, check=True)
        environment_inventory = json.loads(inventory.stdout)
        names = {package["name"].lower().replace("_", "-") for package in environment_inventory}
        if names & {"qdrant-client", "fastembed"} and not manifest.get("with_vector"):
            raise ValueError("Preserve optional ML dependencies: install shared runtime with --with-vector before binding")
        shared_inventory = subprocess.run([str(python), "-m", "pip", "list", "--format=json"], capture_output=True, text=True, check=True)
        shared_names = {package["name"].lower().replace("_", "-") for package in json.loads(shared_inventory.stdout)}
        missing = names - shared_names - {"pip", "setuptools", "wheel", "project-memory-kit"}
        if missing:
            raise ValueError(f"Shared environment lacks existing local packages; preserve them before binding: {', '.join(sorted(missing))}")
    candidates = [p for p in [local_runtime, root / "pmem", root / "pmem.ps1"] if p.exists() and not p.is_symlink()]
    if candidates and not previous:
        backup = state / "runtime-backups" / f"{binding_id}.tar.gz"
        backup.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(backup, "w:gz") as archive:
            for path in candidates:
                archive.add(path, arcname=str(path.relative_to(root)), recursive=True)
            archive.add(metadata_path, arcname=".project-memory/install.json")
        report.add_path("backed_up", backup)
        if environment_inventory is not None:
            _atomic_json(backup.with_suffix(".environment.json"), {"packages": environment_inventory, "python_version": sys.version, "recreate": "python -m venv .project-memory/runtime/.venv; install the listed package versions"})


def _activate_binding(root, shared, manifest, python, binding_id, registry, report):
    state = root / ".project-memory"
    original_registry = json.loads(json.dumps(registry))
    original_files = {path: path.read_bytes() if path.exists() else None for path in [state / "runtime-binding.json", root / "pmem", root / "pmem.ps1"]}
    try:
        preflight = subprocess.run([str(python), "-I", "-c", "import yaml, sqlite3"], capture_output=True, text=True)
        if preflight.returncode:
            raise ValueError(f"Shared runtime dependencies unavailable: {preflight.stderr}")
        registry["projects"][binding_id] = {"project_root": str(root)}
        _atomic_json(shared / "projects.json", registry)
        _atomic_json(state / "runtime-binding.json", {"schema_version": 1, "project_root": str(root), "runtime_root": str(shared), "binding_id": binding_id})
        q = shlex.quote
        bash = f'#!/usr/bin/env bash\nset -euo pipefail\nexec {q(str(python))} -I {q(str(shared / "launch.py"))} --project-root {q(str(root))} --binding {q(binding_id)} -- "$@"\n'
        write_text_file(root / "pmem", bash, report, executable=True)
        psquote = lambda value: "'" + str(value).replace("'", "''") + "'"
        ps1 = f"$ErrorActionPreference = 'Stop'\n& {psquote(python)} -I {psquote(shared / 'launch.py')} --project-root {psquote(root)} --binding {psquote(binding_id)} -- @args\nexit $LASTEXITCODE\n"
        write_text_file(root / "pmem.ps1", ps1, report)
        check = subprocess.run([str(root / "pmem"), "version"], capture_output=True, text=True)
        if check.returncode or check.stdout.strip() != manifest["version"]:
            raise ValueError(f"Shared runtime launch failed: {check.stderr or check.stdout}")
        if (state / "graph.sqlite").exists():
            check = subprocess.run([str(root / "pmem"), "doctor"], capture_output=True, text=True)
            if check.returncode:
                raise ValueError(f"Shared runtime doctor failed: {check.stderr or check.stdout}")
    except Exception:
        _atomic_json(shared / "projects.json", original_registry)
        for path, content in original_files.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise


def _retire_local_runtime(root, shared, manifest, binding_id):
    local_runtime = root / "tools/project_memory"
    local_venv = root / ".project-memory/runtime/.venv"
    if local_runtime.exists() and not local_runtime.is_symlink():
        shutil.rmtree(local_runtime)
    local_runtime.parent.mkdir(exist_ok=True)
    current = shared / "current"
    release = shared / manifest["runtime_path"]
    if not current.exists():
        current.symlink_to(release, target_is_directory=True)
    if not local_runtime.exists():
        local_runtime.symlink_to(current / "tools/project_memory", target_is_directory=True)
    if local_venv.is_dir() and not local_venv.is_symlink():
        retired = local_venv.with_name(f".retired-{binding_id}")
        if retired.exists():
            raise ValueError("Previous environment retirement is pending; preserve it for recovery")
        local_venv.rename(retired)
        try:
            local_venv.symlink_to(shared / ".venv", target_is_directory=True)
        except Exception:
            retired.rename(local_venv)
            raise
        shutil.rmtree(retired)
    elif not local_venv.exists():
        local_venv.parent.mkdir(exist_ok=True)
        local_venv.symlink_to(shared / ".venv", target_is_directory=True)


def bind_shared_runtime(target: Path, runtime: Path) -> InstallReport:
    root = target.resolve(strict=True)
    shared = runtime.resolve(strict=True)
    if root == shared or root.is_relative_to(shared) or shared.is_relative_to(root):
        raise ValueError("Shared runtime and project memory root must be separate directories")
    state = root / ".project-memory"
    metadata_path = state / "install.json"
    if state.is_symlink() or metadata_path.is_symlink():
        raise ValueError("Project memory directory and install metadata must not be symlinks")
    metadata = _json(metadata_path)
    if metadata.get("package") != "project-memory-kit" or not (state / "config.yaml").is_file():
        raise ValueError("Bind requires an existing installed PMEM project")
    manifest = _json(shared / "runtime.json")
    if manifest.get("package") != "project-memory-kit" or manifest.get("schema_version") != 1:
        raise ValueError("Invalid shared runtime installation")
    python = shared / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists() or not (shared / "launch.py").is_file():
        raise ValueError("Shared runtime environment is incomplete")
    report = InstallReport(root)
    local_runtime = root / "tools/project_memory"
    if local_runtime.parent.is_symlink():
        raise ValueError("Project tools directory must not be a symlink")
    if any((root / name).is_symlink() for name in ("pmem", "pmem.ps1")):
        raise ValueError("Project launchers must not be symlinks")
    if local_runtime.is_symlink() and local_runtime.resolve() != (shared / manifest["runtime_path"] / "tools/project_memory").resolve():
        raise ValueError("Existing compatibility link points to a different runtime")
    previous = shared_binding(root)
    if not previous:
        _assert_quiescent(root)
    if previous and (previous.get("project_root") != str(root) or previous.get("runtime_root") != str(shared)):
        raise ValueError("Project already has a different binding; reconcile explicitly")
    binding_id = str(previous.get("binding_id")) if previous else str(uuid.uuid4())
    _backup_local_runtime(root, shared, manifest, python, binding_id, previous, report)
    with _registry_lock(shared):
        registry = _json(shared / "projects.json")
        if registry.get("schema_version") != 1 or not isinstance(registry.get("projects"), dict):
            raise ValueError("Invalid shared project registry")
        if any(key != binding_id and entry.get("project_root") == str(root) for key, entry in registry["projects"].items()):
            raise ValueError("Project already registered under another binding")
        _activate_binding(root, shared, manifest, python, binding_id, registry, report)
        _retire_local_runtime(root, shared, manifest, binding_id)
        metadata.update(runtime_layout="shared", shared_runtime=str(shared), binding_id=binding_id, runtime_version=manifest["version"])
        _atomic_json(metadata_path, metadata)
    report.commands.append(f"verified exact-root shared binding: {binding_id}")
    return report


def runtime_command(argv: list[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="pmem runtime")
    commands = parser.add_subparsers(dest="action", required=True)
    install = commands.add_parser("install")
    install.add_argument("--target", required=True)
    install.add_argument("--with-vector", action="store_true")
    bind = commands.add_parser("bind")
    bind.add_argument("--target", required=True)
    bind.add_argument("--runtime", required=True)
    options = parser.parse_args(argv)
    try:
        report = install_shared_runtime(Path(options.target), options.with_vector) if options.action == "install" else bind_shared_runtime(Path(options.target), Path(options.runtime))
        print(report.summary())
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"PMEM shared runtime error: {error}", file=sys.stderr)
        return 2
