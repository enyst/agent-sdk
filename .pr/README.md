# Architecture gate repair evidence

Base: `9f47d471ee6f91ba1d140d10d34f3b26d5ac2427` (latest upstream `main` at clone and recheck). Branch: `fix/architecture-gate-enforcement`.

This change repairs existing CI gates. It does not change SDK/server product behavior or activate an independently governed conformance bundle.

## Import contract

All four distributions are checked. SDK cannot import tools/workspace/server; tools cannot import workspace/server; workspace cannot import server; server cannot import workspace. Ordinary `import`, `from` imports, aliases, wildcard imports from prohibited modules, and relative imports are resolved. Unparseable/unreadable source fails instead of becoming an empty import set. Filename selection checks package containment using paths, retaining the existing whole-selected-package scan.

The workspace restriction has one explicit established exception: `openhands-workspace/openhands/workspace/docker/dev_workspace.py` may import `openhands.agent_server.docker.build`. The supported `DockerDevWorkspace` delegates development image building to this canonical helper; the workspace manifest already declares the server dependency. This is a file-and-module exception, not permission for general workspace/server coupling. Regression controls accept this import in that file, reject the same import elsewhere, and reject other server imports in the exception file. Product files are unchanged.

This is a static import gate; runtime-computed imports, plugin loading, transitive dependency analysis, and classification of new distributions are outside this fix.

## Before/after controls

Run `uv run python .pr/gate-controls.py base` and `uv run python .pr/gate-controls.py repaired`. The base run loads exact source using `git show` at the base SHA, without switching the checkout. Import controls execute copied scripts in isolated temporary package trees. REST controls call the actual script entry function; controlled metadata/schema substitutions are explicit. Missing-tag extraction and missing executable checks use real subprocess operations.

| Control | Base | Repaired |
| --- | --- | --- |
| SDK `import openhands.tools` | Reject (1) | Reject (1) |
| SDK `from openhands import tools as tools_alias` | Incorrect pass (0) | Reject (1) |
| SDK `from .. import workspace` | Incorrect pass (0) | Reject (1) |
| Workspace server import | Incorrect pass (0) | Reject (1) |
| SDK relative import of its own `workspace` | Pass (0) | Pass (0) |
| Workspace import of SDK/tools | Pass (0) | Pass (0) |
| Each actual distribution source-only path | Not selected | Selected |
| Future `openhands-*` distribution source | Not selected | Selected |
| README-only change | Not selected | Not selected |
| Missing baseline / PyPI outage | Incorrect pass (0) | Unavailable (2) |
| Missing historical git tag | Incorrect pass (0) | Unavailable (2) |
| Compatible comparison | Pass (0) | Pass (0) |
| Failed comparator with no report | Incorrect pass (0) | Unavailable (2) |
| Missing `oasdiff` | Incorrect pass (0) | Unavailable (2) |

`base-controls.txt` and `repaired-controls.txt` contain the observations. The workflow controls parse the actual YAML patterns with `fnmatchcase` for these simple positive globs; they do not claim to execute the hosted `changed-files` action.

## Actual schemas and comparator

`oasdiff version 1.19.1` matches CI. Run `PATH="$PWD/.agent_tmp/bin:$PATH" uv run python .pr/real-rest-controls.py` after installing that version locally. Current source and archived `v1.53.0` source both generate real OpenAPI schemas under the locked workspace dependencies. The script's baseline selector is explicitly pinned for these controls because the normal PyPI metadata request timed out in this environment.

Observed: actual current versus actual `v1.53.0` passes (0); adding a REST endpoint passes (0); deleting nondeprecated `GET /api/agent-profiles` from the actual generated schema fails (1) with `api removed without deprecation`; generating the actual candidate while extracting a nonexistent historical tag blocks (2). See `real-rest-controls.txt`.

The ordinary command `PATH="$PWD/.agent_tmp/bin:$PATH" uv run python .github/scripts/check_agent_server_rest_api_breakage.py` encountered a real PyPI metadata timeout and exited 2, correctly reporting compatibility was not verified. See `live-rest-baseline.txt`. No bootstrap bypass was added: an absent first-release baseline is also unavailable. Existing union expansion, response widening, accepted historical removals, and schema-repair policies are unchanged. Exit 0 requires a completed compatible comparison, exit 1 indicates a policy violation, and exit 2 indicates unavailable verification. Invalid comparator JSON and unexpected comparator statuses also block.

## Validation and limits

- `make build`: completed, installing the locked workspace development dependencies.
- `uv run pre-commit run --files scripts/check_import_rules.py .github/scripts/check_agent_server_rest_api_breakage.py .github/workflows/tests.yml tests/cross/conftest.py tests/cross/test_check_import_rules.py tests/cross/test_check_agent_server_rest_api_breakage.py tests/cross/test_cross_test_selection.py`: all hooks pass. See `pre-commit.txt`.
- `CI=true uv run pytest tests/cross/test_check_import_rules.py tests/cross/test_cross_test_selection.py tests/cross/test_check_agent_server_rest_api_breakage.py tests/cross/test_agent_server_rest_api_contract_summary.py`: 100 focused regressions and existing semantic-policy tests pass. See `focused-tests.txt`.
- `uv run python scripts/check_import_rules.py`: full actual repository scan passes. See `import-scan.txt`.
- `git diff --check`: passes.

The attempted full `CI=true uv run pytest tests/cross` run is incomplete. Automatic approval review rejected it when `test_conversation_restore_lifecycle_happy_path` attempted HTTPS to an LLM proxy; it identified possible disclosure of repository/test inputs to an unverified destination without specific live-provider authorization. It was not retried or bypassed. No full-suite pass or provider compatibility is claimed. Validation completed here uses structural gates, controlled fixtures, real local schema generation and comparator execution.

The cross-selector change partially addresses issue #4912; contributor PR #4915 contains a broader downstream-job proposal. This PR does not close #4912 or take over #4915.

Repository PR-description validation requires a linked issue (new issues must be `ready-for-dev`) and a human-written note of at least 20 visible characters. The draft preserves the HUMAN template placeholder as instructed; the AI has not supplied a human attestation.
