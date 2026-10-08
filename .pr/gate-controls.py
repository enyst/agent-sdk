"""Reproduce gate gaps on the recorded base and qualify repaired entry points."""
import importlib.util
import json
import subprocess
import sys
import tempfile
from fnmatch import fnmatchcase
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
STAGE = sys.argv[1]
IS_BASE = STAGE == 'base'
BASE_REF = "9f47d471ee6f91ba1d140d10d34f3b26d5ac2427"
SNAPSHOTS = tempfile.TemporaryDirectory()


def source(relative_path):
    if IS_BASE:
        return subprocess.run(['git', '-C', str(ROOT), 'show', f'{BASE_REF}:{relative_path}'], check=True, capture_output=True, text=True).stdout
    return (ROOT / relative_path).read_text()


IMPORT_SOURCE = source('scripts/check_import_rules.py')
REST_SCRIPT = Path(SNAPSHOTS.name) / 'check_agent_server_rest_api_breakage.py'
REST_SCRIPT.write_text(source('.github/scripts/check_agent_server_rest_api_breakage.py'))
WORKFLOW_SOURCE = source('.github/workflows/tests.yml')


def record(name, actual, expected):
    print(json.dumps({'control': name, 'observed': actual, 'expected': expected}), flush=True)
    assert actual == expected, name


with tempfile.TemporaryDirectory() as tmp:
    repo = Path(tmp)
    target_script = repo / 'scripts' / 'check_import_rules.py'
    target_script.parent.mkdir()
    target_script.write_text(IMPORT_SOURCE)
    cases = [
        ('sdk', 'import openhands.tools', 1, 1),
        ('sdk', 'from openhands import tools as tools_alias', 0, 1),
        ('sdk', 'from .. import workspace', 0, 1),
        ('workspace', 'import openhands.agent_server', 0, 1),
        ('workspace', 'from openhands import agent_server', 0, 1),
        ('sdk', 'from . import workspace', 0, 0),
        ('workspace', 'from openhands import sdk, tools', 0, 0),
    ]
    for package, source, base_exit, repaired_exit in cases:
        directory = repo / ('openhands-' + ('agent-server' if package == 'agent_server' else package)) / 'openhands' / package
        directory.mkdir(parents=True, exist_ok=True)
        fixture = directory / 'probe.py'
        fixture.write_text(source + '\n')
        result = subprocess.run([sys.executable, str(target_script), str(fixture)], capture_output=True, text=True)
        record(f'import/{package}/{source}', result.returncode, base_exit if IS_BASE else repaired_exit)
        fixture.unlink()

workflow = yaml.safe_load(WORKFLOW_SOURCE)
step = next(step for step in workflow['jobs']['cross-tests']['steps'] if step.get('id') == 'changed')
patterns = step['with']['files'].splitlines()
for changed_path in ['openhands-sdk/openhands/sdk/agent/base.py', 'openhands-tools/openhands/tools/terminal/definition.py', 'openhands-workspace/openhands/workspace/docker/workspace.py', 'openhands-agent-server/openhands/agent_server/api.py', 'openhands-future/openhands/future/module.py']:
    record(f'select/{changed_path}', any(fnmatchcase(changed_path, p) for p in patterns), not IS_BASE)
record('select/tests/cross/test_remote_conversation_live_server.py', any(fnmatchcase('tests/cross/test_remote_conversation_live_server.py', p) for p in patterns), True)
record('select/README.md', any(fnmatchcase('README.md', p) for p in patterns), False)

spec = importlib.util.spec_from_file_location('gate_rest_control', REST_SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.REPO_ROOT = ROOT
module.AGENT_SERVER_PYPROJECT = ROOT / 'openhands-agent-server/pyproject.toml'
schema = {'openapi': '3.0.0', 'paths': {}}
with patch.object(module, '_fetch_pypi_metadata', return_value={'releases': {}}):
    record('REST/no-published-baseline', module.main(), 0 if IS_BASE else 2)
with patch.object(module, '_fetch_pypi_metadata', side_effect=OSError('controlled metadata outage')):
    record('REST/PyPI-unavailable', module.main(), 0 if IS_BASE else 2)
with patch.object(module, '_get_baseline_version', return_value='0.0.0-controlled-missing'), patch.object(module, '_generate_current_openapi', return_value=schema):
    record('REST/nonexistent-git-tag', module.main(), 0 if IS_BASE else 2)
with patch.object(module, '_get_baseline_version', return_value='1.53.0'), patch.object(module, '_generate_current_openapi', return_value=schema), patch.object(module, '_generate_openapi_for_git_ref', return_value=schema), patch.object(module, '_run_oasdiff_breakage_check', return_value=([], 0)):
    record('REST/compatible-comparison', module.main(), 0)
with patch.object(module, '_get_baseline_version', return_value='1.53.0'), patch.object(module, '_generate_current_openapi', return_value=schema), patch.object(module, '_generate_openapi_for_git_ref', return_value=schema), patch.object(module, '_run_oasdiff_breakage_check', return_value=([], 7)):
    record('REST/comparison-failed', module.main(), 0 if IS_BASE else 2)
with tempfile.TemporaryDirectory() as empty_path, patch.dict('os.environ', {'PATH': empty_path}), patch.object(module, '_get_baseline_version', return_value='1.53.0'), patch.object(module, '_generate_current_openapi', return_value=schema), patch.object(module, '_generate_openapi_for_git_ref', return_value=schema):
    record('REST/oasdiff-absent', module.main(), 0 if IS_BASE else 2)

SNAPSHOTS.cleanup()
