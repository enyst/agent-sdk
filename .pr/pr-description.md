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

Implementation-controlled tests can be weakened in one PR before a violating
implementation lands in another. A green test name also cannot establish that
required scenarios ran or that the accepted result came from an independent
verifier. This adds a bounded, executable starting point for separately activated
launch-construction conformance, without claiming that merging source activates
protected admission.

## Summary

- Add a stdlib-only launch policy snapshot and fixed scenario manifest. The runner
  reads an inert, bounded Git source archive and binds pass/fail/blocked evidence
  to the exact revision, archive digest, and independently approved bundle digest.
- Qualify the bundle with valid candidates and deliberate violations, missing and
  tampered evidence, hostile candidate runner/plugin files, activation mismatch,
  source limits, and Git export-attribute bypass controls.
- Add advisory proposal CI, an inactive independent-controller workflow example,
  and concrete owner activation instructions for a dedicated publisher and
  expected-App/ruleset admission. No credentials or GitHub settings are changed.

## Issue Number
No linked issue. Implements the bounded protected-bundle groundwork from the
approved architecture enforcement strategy's second slice.

## How to Test

```sh
make build
python -I -S tests/agent_server/test_conformance_bundle.py
uv run pytest tests/agent_server/test_conformance_bundle.py -q
uv run pre-commit run --files conformance/verify.py conformance/manifest.json \
  conformance/README.md conformance/independent-workflow.yml.example \
  .github/workflows/conformance-proposal.yml \
  tests/agent_server/test_conformance_bundle.py
```

The isolated stdlib entrypoint passes 13 qualification control groups; pytest
passes the same 13 tests. Per-file pre-commit checks pass, including pyright.
The actual source archive of fresh main
`9f47d471ee6f91ba1d140d10d34f3b26d5ac2427` passes the required launch scenario
with 96 parsed Agent Server Python files. Its evidence is attached at
`.pr/main-conformance-evidence.json`. Negative controls detect every existing
construction pattern, including a real Git commit trying to hide a violating
module with `export-ignore`. A second real Git archive redirects a nested package
directory to unscanned source through a symlink: the original verifier passes it,
and the corrected verifier blocks the same commit/archive. Before/after identities
and verdicts are recorded in `.pr/symlink-directory-control.json`. All links and
special members within the scanned package are rejected before `.py` selection;
ordinary directories remain supported and links are never followed.

No live server behavior is claimed: this initial contract checks the existing
launch predicate's static syntax patterns. External App publication, GitHub
expected-source protection, two-PR deployment controls, and merge freshness need
owner deployment; they are deliberately not represented as passing local tests.

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

- [ ] Bug fix
- [x] Feature
- [ ] Refactor
- [ ] Breaking change
- [ ] Docs / chore

## Notes

Merging does not activate protected admission. The proposal CI result must remain
advisory. The owner must select a qualified immutable bundle commit and digest in
a separately governed controller, authenticate its output, and require the
dedicated publisher App identity. The inactive workflow example collects
evidence but does not publish a required check, schedule every PR/merge revision,
pin a bit-for-bit hosted runtime, or enforce repository rules.

The active snapshot intentionally does not track future implementation-test
edits until independently activated. Its archive digest identifies source, not a
built server image. Self-verification and JSON consistency do not authenticate
candidate-produced reports: the controller must fetch the exact source commit
and execute the approved verifier itself.

The HUMAN section remains the repository's unchanged human-only placeholder.
Keep this PR draft until a human supplies that note before requesting review.
