"""Concrete, composed multi-stage workflows -- not a generic pipeline
engine. Each pipeline here is just a Python function chaining `adapters.py`
calls, mirroring a sequence that's already real and manually documented in
an individual project's own README. Add a new pipeline by writing a new
function, not by extending a DSL.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple

from . import adapters


def dock_and_validate(
    raw_pdb: str, ligand_resname: str, ligands_smi: str, out_dir: str, *,
    member_id: Optional[str] = None, chain: str = "A", top_n: Optional[int] = None,
    platform: str = "CUDA", screen_ns: Optional[float] = None, prod_ns: Optional[float] = None,
) -> adapters.MDResult:
    """Ensemble-dock `ligands_smi` against `raw_pdb`'s pocket (defined by
    its co-crystal ligand `ligand_resname`), then run MD stability
    validation on the top-ranked pose -- the exact `dd_mdstability-prep`
    -> `dd_docking-prep` -> `dd_docking-dock` -> `dd_mdstability-run`
    sequence documented as a worked example in `dd_mdstability/README.md`.

    `dd_mdstability-prep` is run first only to produce a bond-order-
    corrected reference ligand SDF for provenance/inspection (matching the
    README's self-docking-benchmark use); the docking ensemble itself is
    built by `dd_docking-prep` directly from `raw_pdb`, and MD-grade
    receptor prep for the final validation run is always redone from
    `raw_pdb` by `dd_mdstability-run` itself regardless of what came
    before it (see `dd_mdstability.pipeline.validate_pose`'s docstring).
    """
    out_dir_p = Path(out_dir)
    member_id = member_id or Path(raw_pdb).stem

    adapters.dd_mdstability_prep(raw_pdb, str(out_dir_p / "prepped"), ligand=ligand_resname)

    adapters.dd_docking_prep(
        [(member_id, raw_pdb, ligand_resname)], str(out_dir_p / "ensemble"), chain=chain,
    )

    dock = adapters.dd_docking_dock(
        str(out_dir_p / "ensemble"), ligands_smi, str(out_dir_p / "screen"), top_n=top_n,
    )

    top = adapters.top_ranked_pose(dock.ranked_csv)

    return adapters.dd_mdstability_run(
        raw_pdb, str(dock.top_hits_sdf), str(out_dir_p / "validate"),
        name=top["ligand_id"], flex_pdbqt=top.get("pose_pdbqt") or None,
        platform=platform, screen_ns=screen_ns, prod_ns=prod_ns,
    )
