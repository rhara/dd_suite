"""Run a dd_* project's own console-script in its own dedicated env, from
any shell/env, without `conda activate` -- see `envs.py`'s docstring for
why activation is avoided. Streams stdout/stderr live so each project's
existing `print(..., flush=True)` progress conventions (StepProgress,
MDProgress, DockProgress, ...) still show up in real time.
"""
from __future__ import annotations

import subprocess
from typing import List, Sequence

from .envs import find_executable, project_for_command, resolve_env_prefix, subprocess_env


def run(command: str, args: Sequence[str] = ()) -> int:
    """Resolve `command` to its owning env's executable and run it with
    `args`, inheriting this process's stdout/stderr (so output streams
    live) and returning the real exit code. The subprocess's `PATH` is
    adjusted (see `envs.subprocess_env`) so nested shell-outs inside the
    target CLI (e.g. `dd_docking-prep` calling meeko's own
    `mk_prepare_receptor.py`) resolve correctly too, not just the one
    binary we invoke directly."""
    prefix = resolve_env_prefix(project_for_command(command))
    exe = find_executable(prefix, command)
    argv: List[str] = [str(exe), *args]
    return subprocess.run(argv, env=subprocess_env(prefix)).returncode
