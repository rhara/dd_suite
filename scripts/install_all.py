#!/usr/bin/env python3
"""Bulk-installs every dd_* project (the 10 siblings + dd_suite itself),
each into its own dedicated conda/mamba env, by replaying the exact
`mamba create ... ` / `pip install --no-deps -e .` recipe already
documented in that project's own README -- nothing here is invented, this
just automates what a user would otherwise type by hand 11 times.

Idempotent: an env that already exists is left as-is (not recreated) --
only the `pip install --no-deps -e .` step re-runs, which is safe and fast
to repeat. Pass `--force` to actually remove and recreate an existing env
(destructive, off by default).

Pure stdlib (no dependency on dd_suite itself being installed yet), so it
works as the very first step on a fresh checkout, with any Python 3.9+
interpreter: `python3 scripts/install_all.py`.

After every project is processed, writes `install_manifest.json` (next to
this script's repo root) recording each project's installed version (`pip
show`) and git commit -- a simple record of what's actually installed
where, not a lockfile/pin mechanism (each project has no formal release
tagging yet -- see dd_suite's README for the trade-off).
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _current_conda_subdir() -> str:
    """Best-effort conda subdir name (e.g. osx-64, osx-arm64, linux-64, win-64)
    for the machine actually running this script -- used only to decide
    whether to drop platform-specific conda packages this project can't get
    from conda-forge here, not to talk to conda itself."""
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin":
        return "osx-arm64" if machine == "arm64" else "osx-64"
    if system == "Linux":
        return "linux-64"
    if system == "Windows":
        return "win-64"
    return f"{system}-{machine}"


@dataclass
class ProjectSpec:
    name: str
    conda_packages: List[str]
    pip_targets: Optional[List[str]] = None
    pip_extra_args: List[str] = field(default_factory=list)
    build_type: str = "pip"  # "pip" or "cmake"
    note: Optional[str] = None
    platform_package_excludes: dict = field(default_factory=dict)
    platform_notes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.pip_targets is None:
            self.pip_targets = [self.name]


# One entry per project, mirroring that project's own README "Installation"
# section exactly (see dd_suite/README.md's "Installing every dd_* project"
# table for the human-readable version of the same information).
PROJECTS: List[ProjectSpec] = [
    ProjectSpec("dd_prep", ["rdkit", "numpy", "openmm", "pdbfixer"]),
    ProjectSpec(
        "dd_afpocket",
        ["rdkit", "numpy", "pandas", "pdbfixer", "openmm", "mdtraj", "matplotlib",
         "scipy", "scikit-learn", "py3dmol", "pytest", "fpocket"],
    ),
    ProjectSpec("dd_chembl", ["rdkit", "lightgbm", "scikit-learn", "joblib"]),
    ProjectSpec("dd_confhunt", ["rdkit<2026", "dimorphite-dl", "numpy"]),
    ProjectSpec("dd_draw", ["rdkit", "numpy", "jinja2", "reportlab", "svglib", "pytest"]),
    ProjectSpec(
        "dd_docking",
        ["rdkit", "numpy", "pandas", "qvina", "meeko", "pdbfixer", "openmm",
         "openmmforcefields", "openff-toolkit", "mdtraj"],
        note="qvina is an external CLI binary (QuickVina2), not a Python import -- "
             "CPU docking needs it on PATH, which the env provides.",
    ),
    ProjectSpec(
        "dd_mdstability",
        ["rdkit", "numpy", "pandas", "matplotlib", "pdbfixer", "openmm",
         "openmmforcefields", "openff-toolkit", "mdtraj", "pytest"],
    ),
    ProjectSpec(
        "dd_overlay", ["rdkit", "numpy", "scipy", "py3dmol", "pytest", "pybind11"],
        pip_extra_args=["--no-build-isolation"],
        note="pybind11 builds the optional dd_overlay._native accelerator; "
             "falls back to pure Python automatically if no C++ compiler is present.",
    ),
    ProjectSpec(
        "dd_seqalign",
        ["biopython", "pandas", "numpy", "matplotlib", "py3dmol", "streamlit",
         "pymol-open-source", "fpocket", "rdkit"],
        pip_targets=["dd_seqalign[app]"],
        note="fpocket is invoked as a CLI subprocess (no Python bindings) -- "
             "installed via conda-forge, not a pip dependency.",
    ),
    ProjectSpec(
        "dd_molview",
        ["rdkit", "biopython", "pandas", "numpy", "py3dmol", "pybind11", "pytest",
         "qt6-main", "qt6-webengine"],
        pip_targets=[],
        build_type="cmake",
        note="C++/Qt6 build, not automated by this script -- after env creation, "
             "run the `cmake -S . -B build && cmake --build build` steps in "
             "dd_molview/README.md's Installation section by hand.",
        platform_package_excludes={"osx-64": ["qt6-main", "qt6-webengine"]},
        platform_notes={
            "osx-64": "conda-forge does not build qt6-webengine for osx-64 (Intel Mac) "
                      "-- only osx-arm64, linux-64 and win-64 are published, so qt6-main/"
                      "qt6-webengine are dropped from this env here. Install Qt6 yourself "
                      "via Homebrew (`brew install qt`) and follow dd_molview/README.md's "
                      "'macOS (Homebrew Qt6)' section for the cmake build.",
        },
    ),
    ProjectSpec("dd_suite", ["pytest"]),
]


def _conda_exe() -> str:
    exe = shutil.which("mamba") or shutil.which("conda")
    if exe is None:
        sys.exit("install_all.py: no mamba/conda executable found on PATH")
    return exe


def _existing_envs(conda_exe: str) -> dict:
    out = subprocess.run([conda_exe, "info", "--envs", "--json"], capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    return {Path(p).name: Path(p) for p in info["envs"]}


def _env_bin(prefix: Path, name: str) -> Path:
    for d in ("bin", "Scripts"):
        candidate = prefix / d / name
        if candidate.exists() or (prefix / d / f"{name}.exe").exists():
            return prefix / d
    # fall back to bin/ even if not found yet (e.g. right after a fresh install)
    return prefix / "bin"


def install_one(spec: ProjectSpec, work_root: Path, conda_exe: str, *, force: bool, dry_run: bool) -> dict:
    print(f"\n=== {spec.name} ===", flush=True)

    current_subdir = _current_conda_subdir()
    excluded = spec.platform_package_excludes.get(current_subdir, [])
    conda_packages = [p for p in spec.conda_packages if p not in excluded]
    if excluded:
        print(f"[{spec.name}] {current_subdir}: excluding {', '.join(excluded)} -- "
              f"{spec.platform_notes.get(current_subdir, '')}", flush=True)

    envs = _existing_envs(conda_exe)
    exists = spec.name in envs

    if exists and force:
        print(f"[{spec.name}] --force: removing existing env", flush=True)
        if not dry_run:
            subprocess.run([conda_exe, "env", "remove", "-y", "-n", spec.name], check=True)
        exists = False

    if not exists:
        cmd = [conda_exe, "create", "-y", "-n", spec.name, "-c", "conda-forge", "python=3.12", *conda_packages]
        print(f"[{spec.name}] creating env: {' '.join(cmd)}", flush=True)
        if not dry_run:
            subprocess.run(cmd, check=True)
    else:
        print(f"[{spec.name}] env already exists, skipping create", flush=True)

    prefix = _existing_envs(conda_exe).get(spec.name)  # None only possible in --dry-run (env not actually created)
    status = "ok"

    if spec.build_type == "cmake":
        print(f"[{spec.name}] build_type=cmake: not automated -- {spec.note}", flush=True)
        if excluded:
            status = f"env-only, missing {', '.join(excluded)} (manual Qt6 + cmake build required)"
        else:
            status = "env-only (manual cmake build required)"
    else:
        if prefix is not None:
            bin_dir = _env_bin(prefix, "pip")
            pip_exe = shutil.which("pip", path=str(bin_dir)) or str(bin_dir / "pip")
        else:
            pip_exe = f"<{spec.name} env>/bin/pip"  # dry-run only: env doesn't exist yet to resolve a real path
        for target in spec.pip_targets:
            pkg_name = target.split("[")[0]
            target_dir = work_root / pkg_name
            args = [pip_exe, "install", "--no-deps", *spec.pip_extra_args, "-e", f"{target_dir}{target[len(pkg_name):]}"]
            print(f"[{spec.name}] {' '.join(args)}", flush=True)
            if not dry_run:
                subprocess.run(args, check=True, cwd=target_dir)

    if spec.note:
        print(f"[{spec.name}] note: {spec.note}", flush=True)

    return {"name": spec.name, "prefix": str(prefix) if prefix else None, "status": status}


def _installed_version(spec: ProjectSpec, prefix: Optional[Path]) -> Optional[str]:
    if prefix is None or spec.build_type == "cmake":
        return None
    bin_dir = _env_bin(prefix, "pip")
    pip_exe = shutil.which("pip", path=str(bin_dir))
    if pip_exe is None:
        return None
    out = subprocess.run([pip_exe, "show", spec.name], capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None


def _git_commit(repo_dir: Path) -> Optional[str]:
    out = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="PROJECT", help="Install only these project(s) instead of all 10")
    parser.add_argument("--force", action="store_true", help="Remove and recreate an env that already exists (destructive)")
    parser.add_argument("--dry-run", action="store_true", help="Print every command without running it")
    args = parser.parse_args(argv)

    work_root = Path(__file__).resolve().parents[2]
    conda_exe = _conda_exe()
    specs = [p for p in PROJECTS if not args.only or p.name in args.only]
    if args.only:
        missing = set(args.only) - {p.name for p in specs}
        if missing:
            sys.exit(f"install_all.py: unknown project name(s): {sorted(missing)}")

    results = []
    for i, spec in enumerate(specs, 1):
        print(f"\n[{i}/{len(specs)}] {spec.name}", flush=True)
        r = install_one(spec, work_root, conda_exe, force=args.force, dry_run=args.dry_run)
        r["version"] = _installed_version(spec, Path(r["prefix"]) if r["prefix"] else None)
        r["commit"] = _git_commit(work_root / spec.name)
        results.append(r)

    print("\n=== install summary ===")
    header = f"{'project':<16} {'version':<10} {'commit':<9} status"
    print(header)
    for r in results:
        print(f"{r['name']:<16} {(r['version'] or '-'):<10} {(r['commit'] or '-'):<9} {r['status']}")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects": results,
    }
    if not args.dry_run:
        manifest_path = Path(__file__).resolve().parents[1] / "install_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"\n[done] wrote {manifest_path}")


if __name__ == "__main__":
    main()
