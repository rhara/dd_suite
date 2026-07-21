"""Two console commands:
  dd_suite <command> [args...]                 -- Layer 1: run any dd_*
      project's own console-script (e.g. `dd_docking-dock`) in its own
      dedicated env, from any shell, no `conda activate` needed.
  dd_suite-pipeline <pipeline> [args...]        -- Layer 2: run a composed
      multi-stage workflow (see `pipelines.py`).
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import dispatch, pipelines
from .envs import EnvNotFoundError, ExecutableNotFoundError


def main(argv: Optional[Sequence[str]] = None) -> None:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("usage: dd_suite <command> [args...]  (e.g. dd_suite dd_docking-dock --help)", file=sys.stderr)
        sys.exit(2)
    command, rest = argv[0], argv[1:]
    try:
        sys.exit(dispatch.run(command, rest))
    except (EnvNotFoundError, ExecutableNotFoundError) as e:
        print(f"dd_suite: {e}", file=sys.stderr)
        sys.exit(1)


def main_pipeline(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="dd_suite-pipeline")
    sub = parser.add_subparsers(dest="pipeline", required=True)

    p = sub.add_parser("dock_and_validate", help="ensemble dock -> MD stability validation on the top hit")
    p.add_argument("raw_pdb", help="Raw co-crystal PDB (receptor + a bound reference ligand)")
    p.add_argument("ligand_resname", help="3-letter residue name of the bound reference ligand in raw_pdb")
    p.add_argument("ligands_smi", help=".smi file to screen: 'SMILES  ID' per line")
    p.add_argument("-o", "--out-dir", required=True)
    p.add_argument("--member-id", default=None)
    p.add_argument("--chain", default="A")
    p.add_argument("--top-n", type=int, default=None)
    p.add_argument("--platform", default="CUDA", choices=["CUDA", "CPU", "Reference", "OpenCL"])
    p.add_argument("--screen-ns", type=float, default=None)
    p.add_argument("--prod-ns", type=float, default=None)

    args = parser.parse_args(argv)
    if args.pipeline == "dock_and_validate":
        result = pipelines.dock_and_validate(
            args.raw_pdb, args.ligand_resname, args.ligands_smi, args.out_dir,
            member_id=args.member_id, chain=args.chain, top_n=args.top_n,
            platform=args.platform, screen_ns=args.screen_ns, prod_ns=args.prod_ns,
        )
        print(f"\n[done] dock_and_validate -> {result.report_json}", flush=True)
