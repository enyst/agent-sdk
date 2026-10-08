<!-- Keep this PR as draft until it is ready for review. -->

<!-- AI/LLM agents:
Do not edit the HUMAN section.
-->

HUMAN:

<!--
Human author: please replace this comment with a short note (at least 20 visible
characters) before marking ready for review.
AI agents: you must not edit this section.
-->

---

AGENT:
<!-- AI/LLM agents:
Follow the review guide's evidence requirements in the fields below.
For lifecycle/integration fixes, exercise the real workflow, not just constructed
unit-test state. For docs-only changes, state what you validated and its limits.
-->

## Why

Existing architecture and compatibility checks could report success without exercising the promised restriction: the import checker missed parent-namespace imports and the workspace package, cross tests did not select actual distribution source paths, and REST compatibility passed without a baseline or comparator.

## Summary

- Scan all four package boundaries with resolved static import forms, retaining only the documented DockerDevWorkspace-to-canonical-builder exception.
- Select cross scenarios for real `openhands-*` source roots and gate-script edits, including future distribution roots.
- Return a distinct nonzero unavailable verdict for missing baselines, schemas, comparator tooling, or usable comparison results; preserve existing semantic compatibility allowances.

## Issue Number
Refs #4912 for the narrow cross-selector correction. This is a partial implementation and does not close that issue.

## How to Test

```bash
make build
uv run python scripts/check_import_rules.py
CI=true uv run pytest tests/cross/test_check_import_rules.py tests/cross/test_cross_test_selection.py tests/cross/test_check_agent_server_rest_api_breakage.py tests/cross/test_agent_server_rest_api_contract_summary.py
uv run pre-commit run --files scripts/check_import_rules.py .github/scripts/check_agent_server_rest_api_breakage.py .github/workflows/tests.yml tests/cross/conftest.py tests/cross/test_check_import_rules.py tests/cross/test_check_agent_server_rest_api_breakage.py tests/cross/test_cross_test_selection.py
uv run python .pr/gate-controls.py base
uv run python .pr/gate-controls.py repaired
# Install oasdiff 1.19.1, then use its directory in PATH:
PATH="$PWD/.agent_tmp/bin:$PATH" uv run python .pr/real-rest-controls.py
git diff --check
```

Before/after controls demonstrate the base accepted prohibited imports and unavailable REST verification; the repaired scripts reject them and preserve positive controls. Actual current and archived v1.53.0 schemas compare successfully with pinned oasdiff; endpoint addition passes, nondeprecated endpoint removal fails, and a missing historical tag blocks. Details and logs are in `.pr/README.md`.

The normal REST command encountered a PyPI metadata timeout here and returned unavailable (2), as intended. The full `tests/cross` attempt was rejected by automatic approval review when a restore test attempted HTTPS to an LLM proxy, citing possible unauthorized disclosure of repository/test inputs. That run is incomplete and was not retried. The focused safe checks above pass.

## Video/Screenshots

<!--
For visual changes, show video or screenshots. Otherwise, use logs, API responses,
or reproduction notes in How to Test; media is optional.

-->

## Design Doc

<!--
Optional, encouraged for non-trivial PRs. Add a self-contained HTML design doc under the
temporary `.pr/` directory (e.g. `.pr/design.html`) covering the code/API design and a
before/after of your change, then link it here via htmlpreview so reviewers see it at a glance:

  https://htmlpreview.github.io/?https://github.com/<your-fork>/<repo>/blob/<your-branch>/.pr/design.html

The `.pr/` directory is temporary. It is removed on approval for same-repository PRs. If it
reaches `main`, including through a fork PR, the workflow opens or updates a cleanup PR. See
CONTRIBUTING.md ("Design doc for non-trivial PRs") for details.
-->

## Type

- [x] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Breaking change
- [x] Docs / chore

## Notes

No SDK/server product behavior or package versions changed. Verification unavailable now blocks compatibility admission, including first-release/no-baseline and network failures. This PR does not implement independent conformance governance, WebSocket compatibility, runtime-computed import analysis, or every downstream test-job selector.

The broader downstream selector proposal remains in [PR 4915](https://github.com/OpenHands/software-agent-sdk/pull/4915); this PR only corrects the cross-suite pattern and adds the gate-script paths needed by these controls.

The HUMAN template placeholder remains untouched. The repository requires a human note of at least 20 visible characters before its PR-description check can pass.
