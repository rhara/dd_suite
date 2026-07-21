[Japanese version](README.jp.md)

# dd_suite — Cross-env dispatch meets composed pipelines: any dd_* command in, its own dedicated env running it out

A thin orchestration layer that makes the independent `dd_afpocket` /
`dd_chembl` / `dd_confhunt` / `dd_docking` / `dd_mdstability` / `dd_molview`
/ `dd_overlay` / `dd_prep` / `dd_seqalign` repos feel like **one suite**,
without merging their code or environments. Each `dd_*` project keeps its
own dedicated conda/mamba env on purpose -- they were deliberately split
apart specifically to avoid dependency conflicts (as of this writing,
`rdkit` alone differs across envs: `dd_confhunt`=2025.09.6,
`dd_docking`/`dd_mdstability`=2026.03.1, the other five=2026.03.4), so
`dd_suite` never imports another project's code directly and never shares
an env with any of them. It only shells out to each project's existing
console-script CLI, in that project's own env.

- **Dispatch (`dd_suite`)**: `dd_suite <command> [args...]` runs any dd_*
  project's own console-script (`dd_prep-run`, `dd_docking-dock`,
  `dd_mdstability-run`, ...) in that project's own dedicated env, from
  *any* shell -- no `conda activate` needed, ever. The owning env is
  derived straight from the command's own name (every dd_* console-script
  is named `<project>-<verb>`, or just `<project>` for a single-command
  project like `dd_confhunt`; project names never contain a hyphen, so
  splitting on the first `-` recovers the env name), then resolved to a
  real env prefix via `conda info --envs --json` (portable across
  machines/OSes -- no hardcoded `/opt/miniforge3/...`) and run by
  absolute path. Output streams live, so each project's existing
  `print(..., flush=True)` progress conventions
  (`StepProgress`/`MDProgress`/`DockProgress`/...) still show up in real
  time, and the real exit code is forwarded.
- **Pipelines (`dd_suite-pipeline`)**: composes several dispatched stages
  into a workflow that's already real and manually documented today, e.g.
  `dock_and_validate`: `dd_mdstability-prep` -> `dd_docking-prep` ->
  `dd_docking-dock` -> `dd_mdstability-run` (the exact worked example in
  `dd_mdstability/README.md`, run as one command instead of four manual
  ones). Implemented as plain composed Python functions
  (`dd_suite/pipelines.py`), not a generic pipeline DSL/config format --
  there are only 1-2 real pipelines today, and each project's CLI already
  writes its output to deterministic, documented filenames (`manifest
  .json`, `ranked_results.csv`, `<name>/report.json`, ...), so there is
  nothing to parse or template: `dd_suite` just constructs the same paths
  a user already types by hand.

## Why not one shared env / one monorepo?

Considered and rejected. Every `dd_*` project needs a different pin of at
least one core package (concretely `rdkit`, but also e.g. `openmm`/Qt6
depending on the project) -- forcing one shared env would either break the
project pinned to an older version or require re-validating every other
project against a new one. A `conda activate`-based wrapper was also
considered and rejected: activating an env inside a non-interactive shell
does not reliably win the `PATH` race (a known pitfall already hit
elsewhere in this suite), so every subprocess `dd_suite` launches is
resolved and run by **absolute path** instead, with that env's `bin`/
`Scripts` directory prepended to the subprocess's own `PATH` (needed
because some dd_* CLIs themselves shell out to a second console-script
assumed to be on `PATH`, e.g. `dd_docking-prep` calling meeko's own
`mk_prepare_receptor.py`).

## Installation

`dd_suite` never imports `rdkit`/`openmm`/any heavy scientific package
itself -- it only shells out to other envs' own CLIs -- so its own env is
intentionally minimal:

```bash
mamba create -n dd_suite -c conda-forge python=3.12 pytest
conda activate dd_suite
cd dd_suite
pip install --no-deps -e .
```

This installs two console commands: `dd_suite`, `dd_suite-pipeline`. Every
`dd_*` project it dispatches to must already have its own dedicated env
installed (env name == project name, the established convention across
this suite) -- `dd_suite` does not create or manage those envs itself.

## Usage

### Dispatch: run any dd_* command from any env

```bash
# from the dd_suite env (or any env -- dd_suite itself needs no activation)
dd_suite dd_prep-run --help
dd_suite dd_docking-dock data/ensemble data/ligands.smi -o data/screen
dd_suite dd_mdstability-run data/raw/4EQC_raw.pdb data/screen/top_hits.sdf -o data/validate --platform CPU
```

Each of these runs entirely inside its owning project's own env
(`dd_prep`, `dd_docking`, `dd_mdstability` respectively) -- `dd_suite`
itself never imports their code or touches their dependencies.

### Pipeline: dock_and_validate

Runs the exact worked example from `dd_mdstability/README.md` as one
command: ensemble-dock a `.smi` library against a raw co-crystal PDB's
pocket, then MD-validate the top-ranked hit.

```bash
dd_suite-pipeline dock_and_validate \
  data/raw/4EQC_raw.pdb XR1 data/ligands.smi \
  -o data/out/4eqc --platform CPU --screen-ns 0.25 --prod-ns 2.0
```

Output layout under `<out_dir>/`: `prepped/` (native reference ligand,
via `dd_mdstability-prep`), `ensemble/manifest.json` (via
`dd_docking-prep`), `screen/ranked_results.csv` + `top_hits.sdf` (via
`dd_docking-dock`), `validate/<ligand_id>/report.json` (via
`dd_mdstability-run` on the top-ranked pose -- the final stability
verdict).

### Python API

```python
from dd_suite import dock_and_validate

result = dock_and_validate(
    "data/raw/4EQC_raw.pdb", "XR1", "data/ligands.smi", "data/out/4eqc",
    platform="CPU", screen_ns=0.25, prod_ns=2.0,
)
print(result.report_json)  # -> data/out/4eqc/validate/<ligand_id>/report.json
```

## Adding a new pipeline

1. Add a small adapter function to `dd_suite/adapters.py` for any new
   stage: build its CLI args, call `dispatch.run(command, args)`, return
   its known output path(s) as a small dataclass -- no path-guessing, just
   the filenames that project's own CLI already documents.
2. Compose adapters into a new function in `dd_suite/pipelines.py`.
3. Expose it as a subcommand in `dd_suite/cli.py`'s `main_pipeline`.

No engine/DSL changes needed -- this mirrors how `dd_mdstability.pipeline`
/`dd_docking`'s own CLIs are themselves built from small composed
functions, not a generic framework.

## Module structure (`dd_suite/`)

| File | Purpose |
|---|---|
| `envs.py` | `<command>` -> owning project -> real env prefix (`conda info --envs --json`) -> real executable path (`shutil.which`); `subprocess_env()` builds the `PATH`-adjusted environment a dispatched subprocess runs with |
| `dispatch.py` | `run(command, args)` -- resolve + run by absolute path, streamed stdio, real exit code |
| `adapters.py` | One function + result dataclass per chainable dd_* CLI stage |
| `pipelines.py` | Composed multi-stage workflows (currently: `dock_and_validate`) |
| `cli.py` | `dd_suite` (Layer 1 passthrough) / `dd_suite-pipeline` (Layer 2 subcommands) |

## Limitations

- `dd_suite` assumes every dispatched project's env already exists and is
  named exactly like the project (`mamba create -n <project> ...`) -- it
  does not create, update, or otherwise manage those envs.
- Only one pipeline exists today (`dock_and_validate`). Others (e.g.
  wiring in `dd_afpocket` as an alternative ensemble source, or a
  `dd_chembl` train -> predict -> dock loop) are straightforward to add
  the same way but have not been implemented yet.
