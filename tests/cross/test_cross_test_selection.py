"""Source-only edits must select the cross-package scenarios."""

from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "changed_file,selected",
    [
        ("openhands-sdk/openhands/sdk/agent/base.py", True),
        ("openhands-tools/openhands/tools/terminal/definition.py", True),
        ("openhands-workspace/openhands/workspace/docker/workspace.py", True),
        ("openhands-agent-server/openhands/agent_server/api.py", True),
        ("openhands-future/openhands/future/module.py", True),
        ("scripts/check_import_rules.py", True),
        (".github/scripts/check_agent_server_rest_api_breakage.py", True),
        ("tests/cross/test_remote_conversation_live_server.py", True),
        ("pyproject.toml", True),
        ("uv.lock", True),
        (".github/workflows/tests.yml", True),
        ("README.md", False),
    ],
)
def test_cross_test_source_selection(changed_file, selected):
    repo = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((repo / ".github/workflows/tests.yml").read_text())
    detector = next(
        step
        for step in workflow["jobs"]["cross-tests"]["steps"]
        if step.get("id") == "changed"
    )
    patterns = detector["with"]["files"].splitlines()

    assert any(fnmatchcase(changed_file, pattern) for pattern in patterns) == selected
