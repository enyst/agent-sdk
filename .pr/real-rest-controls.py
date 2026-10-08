"""Exercise actual schema generation and pinned oasdiff with controlled deltas."""
import copy
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('real_rest_controls', ROOT / '.github/scripts/check_agent_server_rest_api_breakage.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

current = module._generate_current_openapi()
assert current is not None, 'actual current schema must generate'
historical = module._generate_openapi_for_git_ref('v1.53.0')
assert historical is not None, 'actual archived tag schema must generate'

with patch.object(module, '_get_baseline_version', return_value='1.53.0'):
    result = module.main()
    print(json.dumps({'control': 'actual schemas/current-vs-v1.53.0', 'exit': result}), flush=True)
    assert result == 0

operation_path = next(path for path in sorted(current['paths']) if path.startswith('/api/') and 'get' in current['paths'][path] and not current['paths'][path]['get'].get('deprecated'))
removed = copy.deepcopy(current)
del removed['paths'][operation_path]['get']
with patch.object(module, '_get_baseline_version', return_value='1.53.0'), patch.object(module, '_generate_current_openapi', return_value=removed), patch.object(module, '_generate_openapi_for_git_ref', return_value=current):
    result = module.main()
    print(json.dumps({'control': 'actual schema/remove nondeprecated GET', 'path': operation_path, 'exit': result}), flush=True)
    assert result == 1

added = copy.deepcopy(current)
added['paths']['/api/control-addition'] = {'get': {'responses': {'200': {'description': 'Control addition'}}}}
with patch.object(module, '_get_baseline_version', return_value='1.53.0'), patch.object(module, '_generate_current_openapi', return_value=added), patch.object(module, '_generate_openapi_for_git_ref', return_value=current):
    result = module.main()
    print(json.dumps({'control': 'actual schema/add endpoint', 'exit': result}), flush=True)
    assert result == 0

with patch.object(module, '_get_baseline_version', return_value='0.0.0-no-baseline'):
    result = module.main()
    print(json.dumps({'control': 'actual current schema/missing archived baseline', 'exit': result}), flush=True)
    assert result == 2
