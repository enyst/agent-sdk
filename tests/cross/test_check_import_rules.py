"""Qualify the import gate through its command-line entry point."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def import_gate_repo(tmp_path):
    script = tmp_path / "scripts" / "check_import_rules.py"
    script.parent.mkdir()
    source = Path(__file__).resolve().parents[2] / "scripts" / script.name
    script.write_text(source.read_text())
    return tmp_path, script


@pytest.mark.parametrize(
    "package,relative_path,source,forbidden",
    [
        ("sdk", "probe.py", "import openhands.tools as tools", "openhands.tools"),
        ("sdk", "probe.py", "from openhands import tools as t", "openhands.tools"),
        ("sdk", "probe.py", "from .. import workspace", "openhands.workspace"),
        (
            "sdk",
            "nested/probe.py",
            "from ...agent_server import api",
            "openhands.agent_server",
        ),
        (
            "tools",
            "probe.py",
            "from openhands import workspace",
            "openhands.workspace",
        ),
        (
            "workspace",
            "__init__.py",
            "from .. import agent_server",
            "openhands.agent_server",
        ),
        (
            "agent_server",
            "probe.py",
            "from openhands.workspace import *",
            "openhands.workspace",
        ),
    ],
)
def test_prohibited_import_fails(
    import_gate_repo, package, relative_path, source, forbidden
):
    repo, script = import_gate_repo
    distribution = f"openhands-{package.replace('_', '-')}"
    file = repo / distribution / "openhands" / package / relative_path
    file.parent.mkdir(parents=True)
    file.write_text(source + "\n")

    for filenames in ([], [str(file)]):
        result = subprocess.run(
            [sys.executable, str(script), *filenames], capture_output=True, text=True
        )
        assert result.returncode == 1
        assert forbidden in result.stdout
        assert str(file.relative_to(repo)) in result.stdout


@pytest.mark.parametrize(
    "package,source",
    [
        ("sdk", "from . import workspace\nfrom openhands.sdk import tool"),
        ("tools", "from openhands import sdk\nfrom . import terminal"),
        ("workspace", "from openhands import sdk, tools\nfrom . import docker"),
        ("agent_server", "from openhands import sdk, tools\nfrom . import api"),
    ],
)
def test_allowed_imports_pass(import_gate_repo, package, source):
    repo, script = import_gate_repo
    distribution = f"openhands-{package.replace('_', '-')}"
    file = repo / distribution / "openhands" / package / "__init__.py"
    file.parent.mkdir(parents=True)
    file.write_text(source + "\n")

    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_unparseable_source_cannot_pass(import_gate_repo):
    repo, script = import_gate_repo
    file = repo / "openhands-sdk" / "openhands" / "sdk" / "probe.py"
    file.parent.mkdir(parents=True)
    file.write_text("from openhands import (\n")

    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "Unable to check openhands.sdk" in result.stderr


@pytest.mark.parametrize(
    "relative_path,source,expected",
    [
        (
            "docker/dev_workspace.py",
            "from openhands.agent_server.docker.build import BuildOptions, build",
            0,
        ),
        (
            "docker/workspace.py",
            "from openhands.agent_server.docker.build import BuildOptions, build",
            1,
        ),
        (
            "docker/dev_workspace.py",
            "from openhands.agent_server import api",
            1,
        ),
    ],
)
def test_development_builder_exception_is_scoped(
    import_gate_repo, relative_path, source, expected
):
    repo, script = import_gate_repo
    file = repo / "openhands-workspace" / "openhands" / "workspace" / relative_path
    file.parent.mkdir(parents=True)
    file.write_text(source + "\n")

    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True
    )
    assert result.returncode == expected, result.stdout + result.stderr
