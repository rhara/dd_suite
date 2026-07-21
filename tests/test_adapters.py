import csv
from unittest.mock import patch

import pytest

from dd_suite import adapters


def _mock_run(returncode=0):
    return patch("dd_suite.adapters.dispatch.run", return_value=returncode)


def test_dd_mdstability_prep_builds_args_and_paths(tmp_path):
    with _mock_run() as run_mock:
        result = adapters.dd_mdstability_prep(
            "raw.pdb", str(tmp_path), name="4eqc", ligand="XR1",
        )
    run_mock.assert_called_once_with(
        "dd_mdstability-prep", ["raw.pdb", "-o", str(tmp_path), "--name", "4eqc", "--ligand", "XR1"],
    )
    assert result.receptor_pdb == tmp_path / "4eqc_md.pdb"
    assert result.ligand_sdf == tmp_path / "4eqc_ligand.sdf"
    assert result.report_json == tmp_path / "4eqc_prep_report.json"


def test_dd_mdstability_prep_without_ligand_has_no_sdf(tmp_path):
    with _mock_run():
        result = adapters.dd_mdstability_prep("raw.pdb", str(tmp_path), name="4eqc")
    assert result.ligand_sdf is None


def test_dd_docking_prep_builds_repeated_member_flags(tmp_path):
    with _mock_run() as run_mock:
        result = adapters.dd_docking_prep(
            [("4eqc", "raw.pdb", "XR1")], str(tmp_path), chain="A",
        )
    run_mock.assert_called_once_with(
        "dd_docking-prep", ["-o", str(tmp_path), "--chain", "A", "--member", "4eqc", "raw.pdb", "XR1"],
    )
    assert result.manifest_json == tmp_path / "manifest.json"


def test_dd_docking_dock_paths(tmp_path):
    with _mock_run():
        result = adapters.dd_docking_dock(str(tmp_path / "ensemble"), "ligands.smi", str(tmp_path / "screen"))
    assert result.ranked_csv == tmp_path / "screen" / "ranked_results.csv"
    assert result.top_hits_sdf == tmp_path / "screen" / "top_hits.sdf"


def test_dd_mdstability_run_paths(tmp_path):
    with _mock_run() as run_mock:
        result = adapters.dd_mdstability_run(
            "raw.pdb", "top_hits.sdf", str(tmp_path), name="nu6102", flex_pdbqt="pose.pdbqt", platform="CPU",
        )
    run_mock.assert_called_once_with(
        "dd_mdstability-run",
        ["raw.pdb", "top_hits.sdf", "-o", str(tmp_path), "--name", "nu6102", "--platform", "CPU", "--flex-pdbqt", "pose.pdbqt"],
    )
    assert result.workdir == tmp_path / "nu6102"
    assert result.report_json == tmp_path / "nu6102" / "report.json"


def test_stage_error_on_nonzero_exit(tmp_path):
    with _mock_run(returncode=1):
        with pytest.raises(adapters.StageError):
            adapters.dd_mdstability_prep("raw.pdb", str(tmp_path))


def test_top_ranked_pose_reads_first_row(tmp_path):
    csv_path = tmp_path / "ranked_results.csv"
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["rank", "ligand_id", "pose_pdbqt"])
        writer.writeheader()
        writer.writerow({"rank": "1", "ligand_id": "nu6102", "pose_pdbqt": "screen/001_nu6102.pdbqt"})
        writer.writerow({"rank": "2", "ligand_id": "other", "pose_pdbqt": "screen/002_other.pdbqt"})
    top = adapters.top_ranked_pose(csv_path)
    assert top["ligand_id"] == "nu6102"


def test_top_ranked_pose_empty_raises(tmp_path):
    csv_path = tmp_path / "ranked_results.csv"
    with open(csv_path, "w", newline="") as fh:
        csv.DictWriter(fh, fieldnames=["rank", "ligand_id"]).writeheader()
    with pytest.raises(adapters.StageError):
        adapters.top_ranked_pose(csv_path)
