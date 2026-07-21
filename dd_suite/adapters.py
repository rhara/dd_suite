"""One small wrapper function per chainable dd_* CLI stage. Each wrapper
builds the subprocess args for that stage's own console-script (run via
`dispatch.run`, so it always executes inside that project's own dedicated
env) and returns the stage's already-deterministic output path(s) -- no
guessing: every path here matches what that project's own CLI documents
and what the manual worked examples in each README already use.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from . import dispatch


class StageError(RuntimeError):
    """A wrapped dd_* CLI invocation exited non-zero."""


def _run_or_raise(command: str, args: Sequence[str]) -> None:
    rc = dispatch.run(command, args)
    if rc != 0:
        raise StageError(f"{command} {' '.join(args)!r} exited with code {rc}")


@dataclass
class PrepResult:
    receptor_pdb: Path
    ligand_sdf: Optional[Path]
    report_json: Path


@dataclass
class EnsembleResult:
    manifest_json: Path


@dataclass
class DockResult:
    ranked_csv: Path
    top_hits_sdf: Path


@dataclass
class MDResult:
    workdir: Path
    report_json: Path


def dd_mdstability_prep(
    raw_pdb: str, out_dir: str, *, name: Optional[str] = None, ligand: Optional[str] = None,
) -> PrepResult:
    """`dd_mdstability-prep RAW.pdb -o out_dir [--name NAME] [--ligand RESNAME]`
    -> MD-grade receptor + (if `ligand`) a bond-order-corrected co-crystal
    ligand SDF, e.g. for a self-docking positive control."""
    name = name or Path(raw_pdb).stem
    out_dir_p = Path(out_dir)
    args = [str(raw_pdb), "-o", str(out_dir), "--name", name]
    if ligand:
        args += ["--ligand", ligand]
    _run_or_raise("dd_mdstability-prep", args)
    return PrepResult(
        receptor_pdb=out_dir_p / f"{name}_md.pdb",
        ligand_sdf=(out_dir_p / f"{name}_ligand.sdf") if ligand else None,
        report_json=out_dir_p / f"{name}_prep_report.json",
    )


def dd_docking_prep(
    members: Sequence[tuple], out_dir: str, *, chain: str = "A",
) -> EnsembleResult:
    """`dd_docking-prep --member ID PDB LIG_RESNAME [--member ...] -o out_dir`
    -> Vina-ready rigid/flexible-side-chain ensemble (`manifest.json`).
    `members`: sequence of (member_id, raw_pdb, ligand_resname)."""
    args = ["-o", str(out_dir), "--chain", chain]
    for member_id, raw_pdb, ligand_resname in members:
        args += ["--member", member_id, str(raw_pdb), ligand_resname]
    _run_or_raise("dd_docking-prep", args)
    return EnsembleResult(manifest_json=Path(out_dir) / "manifest.json")


def dd_docking_dock(
    ensemble_dir: str, ligands_smi: str, out_dir: str, *, top_n: Optional[int] = None,
) -> DockResult:
    """`dd_docking-dock ensemble_dir ligands.smi -o out_dir [--top-n N]`
    -> `ranked_results.csv` + `top_hits.sdf`."""
    args = [str(ensemble_dir), str(ligands_smi), "-o", str(out_dir)]
    if top_n is not None:
        args += ["--top-n", str(top_n)]
    _run_or_raise("dd_docking-dock", args)
    return DockResult(
        ranked_csv=Path(out_dir) / "ranked_results.csv",
        top_hits_sdf=Path(out_dir) / "top_hits.sdf",
    )


def top_ranked_pose(ranked_csv: Path) -> dict:
    """Row 1 (best rank) of a `dd_docking-dock` `ranked_results.csv` --
    already carries `receptor_pdb`/`pose_pdbqt` as `dd_mdstability.pipeline
    .poses_from_ranked_csv` reads them, so no filename reconstruction is
    needed."""
    with open(ranked_csv, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise StageError(f"{ranked_csv}: no ranked poses")
    return rows[0]


def dd_mdstability_run(
    receptor_pdb: str, ligand_pose: str, out_dir: str, *,
    name: Optional[str] = None, flex_pdbqt: Optional[str] = None, platform: str = "CUDA",
    screen_ns: Optional[float] = None, prod_ns: Optional[float] = None,
) -> MDResult:
    """`dd_mdstability-run RECEPTOR.pdb POSE.sdf -o out_dir [--name NAME]
    [--flex-pdbqt ...] [--platform ...]` -> per-pose `report.json`
    (`stable`, RMSD fields, ...)."""
    name = name or Path(ligand_pose).stem
    args = [str(receptor_pdb), str(ligand_pose), "-o", str(out_dir), "--name", name, "--platform", platform]
    if flex_pdbqt:
        args += ["--flex-pdbqt", str(flex_pdbqt)]
    if screen_ns is not None:
        args += ["--screen-ns", str(screen_ns)]
    if prod_ns is not None:
        args += ["--prod-ns", str(prod_ns)]
    _run_or_raise("dd_mdstability-run", args)
    workdir = Path(out_dir) / name
    return MDResult(workdir=workdir, report_json=workdir / "report.json")
