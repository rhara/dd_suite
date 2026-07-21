"""Resolve a dd_* console-script name to the conda/mamba env that owns it,
and locate the real executable inside that env -- without ever running
`conda activate` (see `dispatch.py` for why: activation does not reliably
win the PATH race in a non-interactive shell).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict


class EnvNotFoundError(RuntimeError):
    pass


class ExecutableNotFoundError(RuntimeError):
    pass


def project_for_command(command: str) -> str:
    """Every dd_* console-script is named `<project>-<verb>` or, for a
    project with a single command, just `<project>` (e.g. `dd_confhunt`).
    Project names themselves never contain a hyphen, so splitting on the
    first `-` recovers the owning project/env name in both cases."""
    return command.split("-", 1)[0]


@lru_cache(maxsize=1)
def _conda_envs() -> Dict[str, Path]:
    """`{env_name: prefix}` for every conda/mamba env, via `conda info
    --envs --json` -- portable across machines/OSes, unlike hardcoding
    e.g. `/opt/miniforge3/envs`."""
    conda_exe = os.environ.get("CONDA_EXE") or shutil.which("conda") or shutil.which("mamba")
    if conda_exe is None:
        raise EnvNotFoundError("no conda/mamba executable found on PATH (and $CONDA_EXE is unset)")
    out = subprocess.run([conda_exe, "info", "--envs", "--json"], capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    envs: Dict[str, Path] = {}
    for prefix in info["envs"]:
        p = Path(prefix)
        envs[p.name] = p
    return envs


def resolve_env_prefix(project: str) -> Path:
    envs = _conda_envs()
    if project not in envs:
        raise EnvNotFoundError(
            f"no conda env named {project!r} found (looked for a dd_* project's own dedicated env, "
            f"e.g. `mamba create -n {project} ...`) -- available envs: {sorted(envs)}"
        )
    return envs[project]


def find_executable(prefix: Path, command: str) -> Path:
    """Locate `command` inside env `prefix`, without relying on the
    caller's own PATH -- checks `bin/` (Linux/Mac) and `Scripts/`
    (Windows) explicitly via `shutil.which`."""
    search_path = os.pathsep.join(str(prefix / d) for d in ("bin", "Scripts", "."))
    found = shutil.which(command, path=search_path)
    if found is None:
        raise ExecutableNotFoundError(f"{command!r} not found in env {prefix} (checked bin/, Scripts/)")
    return Path(found)


def resolve_command(command: str) -> Path:
    """`command` (e.g. `dd_docking-dock`) -> the real executable path
    inside its owning project's dedicated env."""
    project = project_for_command(command)
    prefix = resolve_env_prefix(project)
    return find_executable(prefix, command)


def subprocess_env(prefix: Path) -> Dict[str, str]:
    """A copy of this process's environment, adjusted so a subprocess run
    with it behaves as if `prefix` had actually been `conda activate`-d --
    needed because several dd_* CLIs shell out to a *second* console-script
    assumed to be on `PATH` (e.g. `dd_docking-prep` invoking meeko's own
    `mk_prepare_receptor.py`), which only resolves if that env's bin
    directory is actually first on `PATH`, not just the one binary we
    resolved directly. Prepending the bin dir (rather than fully replacing
    `PATH`) is enough for this and avoids fully reimplementing conda's
    activation script."""
    env = os.environ.copy()
    bin_dirs = [str(prefix / "bin"), str(prefix / "Scripts"), str(prefix)]
    env["PATH"] = os.pathsep.join([*bin_dirs, env.get("PATH", "")])
    env["CONDA_PREFIX"] = str(prefix)
    env["CONDA_DEFAULT_ENV"] = prefix.name
    return env
