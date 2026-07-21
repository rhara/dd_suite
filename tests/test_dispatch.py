import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dd_suite import dispatch
from dd_suite.envs import (
    EnvNotFoundError,
    ExecutableNotFoundError,
    _conda_envs,
    find_executable,
    project_for_command,
    resolve_command,
    resolve_env_prefix,
)


def test_project_for_command_hyphenated():
    assert project_for_command("dd_docking-dock") == "dd_docking"
    assert project_for_command("dd_mdstability-run") == "dd_mdstability"


def test_project_for_command_bare():
    assert project_for_command("dd_confhunt") == "dd_confhunt"


@pytest.fixture(autouse=True)
def _clear_env_cache():
    _conda_envs.cache_clear()
    yield
    _conda_envs.cache_clear()


def _fake_conda_info(envs):
    payload = json.dumps({"envs": envs}).encode()
    return MagicMock(stdout=payload.decode())


def test_resolve_env_prefix_found(tmp_path):
    fake_prefix = tmp_path / "envs" / "dd_docking"
    with patch("dd_suite.envs.shutil.which", return_value="/usr/bin/conda"), \
         patch("dd_suite.envs.subprocess.run", return_value=_fake_conda_info([str(fake_prefix)])):
        prefix = resolve_env_prefix("dd_docking")
    assert prefix == fake_prefix


def test_resolve_env_prefix_missing(tmp_path):
    with patch("dd_suite.envs.shutil.which", return_value="/usr/bin/conda"), \
         patch("dd_suite.envs.subprocess.run", return_value=_fake_conda_info([str(tmp_path / "envs" / "other")])):
        with pytest.raises(EnvNotFoundError):
            resolve_env_prefix("dd_docking")


def test_find_executable_found(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "dd_docking-dock"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    found = find_executable(tmp_path, "dd_docking-dock")
    assert found == script


def test_find_executable_missing(tmp_path):
    (tmp_path / "bin").mkdir()
    with pytest.raises(ExecutableNotFoundError):
        find_executable(tmp_path, "dd_docking-dock")


def test_resolve_command_end_to_end(tmp_path):
    prefix = tmp_path / "envs" / "dd_docking"
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "dd_docking-dock"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    with patch("dd_suite.envs.resolve_env_prefix", return_value=prefix):
        found = resolve_command("dd_docking-dock")
    assert found == script


def test_dispatch_run_forwards_args_and_returncode(tmp_path):
    prefix = tmp_path / "envs" / "dd_docking"
    fake_exe = prefix / "bin" / "dd_docking-dock"
    fake_env = {"PATH": "/fake"}
    with patch("dd_suite.dispatch.resolve_env_prefix", return_value=prefix), \
         patch("dd_suite.dispatch.find_executable", return_value=fake_exe), \
         patch("dd_suite.dispatch.subprocess_env", return_value=fake_env) as subprocess_env_mock, \
         patch("dd_suite.dispatch.subprocess.run") as run_mock:
        run_mock.return_value = MagicMock(returncode=3)
        rc = dispatch.run("dd_docking-dock", ["a", "b"])
    subprocess_env_mock.assert_called_once_with(prefix)
    run_mock.assert_called_once_with([str(fake_exe), "a", "b"], env=fake_env)
    assert rc == 3
